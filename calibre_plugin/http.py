from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

from calibre import as_unicode


class ApiOperation(Protocol):
    """
    Protocol defining a retryable API operation.

    Implementations of this protocol must provide a ``run`` method that
    performs a single API request attempt and returns the result along with
    retry control information.

    Methods:
        run(attempt: int, log: Any) -> tuple[dict[str, Any] | None, str | None, bool, int | None]:
            Execute one attempt of the API operation.
    """

    def run(self, attempt: int, log: Any) -> tuple[dict[str, Any] | None, str | None, bool, int | None]:
        """
        Execute a single API operation attempt.

        Args:
            attempt (int): Zero-based retry attempt number.
            log (Any): Logger-like object or callable used for diagnostic output.

        Returns:
            tuple[dict[str, Any] | None, str | None, bool, int | None]:
                A 4-item tuple containing:
                - dict[str, Any] | None: Parsed response payload if successful, otherwise None.
                - str | None: Error message if the request failed, otherwise None.
                - bool: True if the caller should retry the operation, otherwise False.
                - int | None: Retry delay in seconds if explicitly provided, otherwise None.
        """
        ...


class RetryPolicy(Protocol):
    """
    Protocol defining retry policy behavior for API operations.

    Implementations of this protocol must provide an ``execute`` method
    that applies retry logic to an ``ApiOperation``.

    Methods:
        execute(operation: ApiOperation, log: Any, abort: Any = None) -> tuple[dict[str, Any] | None, str | None]:
            Execute an API operation using a retry strategy.
    """

    def execute(self, operation: ApiOperation, log: Any, abort: Any = None) -> tuple[dict[str, Any] | None, str | None]:
        """
        Execute an API operation according to the retry policy.

        Args:
            operation (ApiOperation): The API operation to execute.
            log (Any): Logger-like object or callable used for diagnostic output.
            abort (Any, optional): Abort controller or event-like object with an
                ``is_set()`` method. If set, execution is cancelled. Defaults to None.

        Returns:
            tuple[dict[str, Any] | None, str | None]:
                A 2-item tuple containing:
                - dict[str, Any] | None: Parsed response payload if successful, otherwise None.
                - str | None: Error message if the operation failed, otherwise None.
        """
        ...


@dataclass(frozen=True)
class ApiConfig:
    """
    Immutable configuration values for API access and retry behavior.

    Attributes:
        meta_endpoint (str): Metadata API endpoint URL.
        max_retries (int): Maximum number of request attempts.
        initial_backoff (int): Initial exponential backoff delay in seconds.
        max_retry_after (int): Maximum allowed server-provided retry delay in seconds.
    """

    meta_endpoint: str
    max_retries: int
    initial_backoff: int
    max_retry_after: int


class ExponentialBackoffRetryPolicy:
    """
    Retry policy that uses exponential backoff between attempts.

    This policy retries failed operations up to a configured limit. When the
    operation does not provide an explicit retry delay, the policy uses an
    exponentially increasing backoff value. It also supports optional abortion
    through an event-like object.

    Attributes:
        max_retries (int): Maximum number of request attempts.
        initial_backoff (int): Initial retry delay in seconds.
        max_retry_after (int): Maximum accepted explicit retry delay in seconds.
    """

    def __init__(self, max_retries: int, initial_backoff: int, max_retry_after: int) -> None:
        """
        Initialize the retry policy.

        Args:
            max_retries (int): Maximum number of request attempts.
            initial_backoff (int): Initial retry delay in seconds.
            max_retry_after (int): Maximum accepted server-specified retry delay in seconds.

        Returns:
            None: This constructor does not return a value.
        """
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_retry_after = max_retry_after

    def execute(self, operation: ApiOperation, log: Any, abort: Any = None) -> tuple[dict[str, Any] | None, str | None]:
        """
        Execute an API operation with retry logic.

        The method repeatedly invokes the supplied operation until one of the
        following occurs:
        - the operation succeeds,
        - the operation reports that it should not be retried,
        - the maximum retry count is reached,
        - the request is aborted.

        Args:
            operation (ApiOperation): Retryable API operation to run.
            log (Any): Logger-like object or callable used for status reporting.
            abort (Any, optional): Abort controller or event-like object with an
                ``is_set()`` method. If set, execution stops early. Defaults to None.

        Returns:
            tuple[dict[str, Any] | None, str | None]:
                A 2-item tuple containing:
                - dict[str, Any] | None: Response payload if the request succeeds, otherwise None.
                - str | None: Error message if the request fails or is aborted, otherwise None.
        """
        backoff = self.initial_backoff
        last_payload: dict[str, Any] | None = None
        last_error: str | None = None

        for attempt in range(self.max_retries):
            if abort is not None and abort.is_set():
                return None, 'Request aborted'

            payload, error, should_retry, retry_after = operation.run(attempt, log)
            last_payload, last_error = payload, error

            if not should_retry or attempt >= self.max_retries - 1:
                return payload, error

            delay = retry_after if retry_after is not None else backoff
            if log:
                log('FicHub: retrying after %ss', delay)

            if not self._sleep_with_abort(delay, abort):
                return None, 'Request aborted'

            if retry_after is None:
                backoff *= 2

        return last_payload, last_error

    def _sleep_with_abort(self, delay: int | float, abort: Any) -> bool:
        """
        Sleep for a delay interval while allowing abortion checks.

        If no abort object is provided, the method sleeps for the full delay.
        Otherwise, it sleeps in short chunks and checks whether abortion has
        been requested between chunks.

        Args:
            delay (int | float): Delay duration in seconds.
            abort (Any): Abort controller or event-like object with an
                ``is_set()`` method, or None.

        Returns:
            bool:
                - True if the sleep completed normally.
                - False if sleep was interrupted due to abortion.
        """
        if abort is None:
            time.sleep(delay)
            return True

        remaining = max(float(delay), 0.0)
        while remaining > 0:
            if abort.is_set():
                return False
            chunk = min(remaining, 0.25)
            time.sleep(chunk)
            remaining -= chunk
        return not abort.is_set()


class FicHubApiOperation:
    """
    API operation for requesting metadata from the FicHub service.

    This class encapsulates the logic for making a single metadata request,
    interpreting HTTP and API-level errors, parsing JSON responses, and
    determining whether a failed request should be retried.

    Attributes:
        browser (Any): Browser-like client used to perform HTTP requests.
        endpoint (str): Metadata API endpoint URL.
        timeout (int | float): Request timeout in seconds.
        max_retry_after (int): Maximum allowed retry delay in seconds.
    """

    def __init__(self, browser: Any, endpoint: str, timeout: int | float, max_retry_after: int) -> None:
        """
        Initialize the API operation.

        Args:
            browser (Any): Browser-like client exposing ``open_novisit(...)``.
            endpoint (str): Metadata API endpoint URL.
            timeout (int | float): Request timeout in seconds.
            max_retry_after (int): Maximum allowed retry delay in seconds.

        Returns:
            None: This constructor does not return a value.
        """
        self.browser = browser
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retry_after = max_retry_after

    def run(self, attempt: int, log: Any) -> tuple[dict[str, Any] | None, str | None, bool, int | None]:
        """
        Execute one metadata request attempt.

        The method performs the HTTP request, handles transport and HTTP errors,
        parses the JSON response body, and interprets application-level response
        codes returned by the FicHub API.

        Args:
            attempt (int): Zero-based retry attempt number.
            log (Any): Logger-like object or callable used for status and error reporting.

        Returns:
            tuple[dict[str, Any] | None, str | None, bool, int | None]:
                A 4-item tuple containing:
                - dict[str, Any] | None: Parsed JSON response payload if successful, otherwise None.
                - str | None: Error message if the request failed, otherwise None.
                - bool: True if the operation should be retried, otherwise False.
                - int | None: Explicit retry delay in seconds if available, otherwise None.
        """
        if log:
            log('FicHub: requesting metadata (attempt %d)', attempt + 1)

        try:
            response = self.browser.open_novisit(self.endpoint, timeout=self.timeout)
        except Exception as e:
            response = getattr(e, 'response', None) or getattr(e, 'fp', None)
            code = getattr(e, 'code', None) or getattr(response, 'code', None)
            if code == 429:
                retry_after = self._retry_delay(response if response is not None else e)
                if log and hasattr(log, 'exception'):
                    log.exception('FicHub: metadata request rate limited')
                return None, 'FicHub API rate limited; please try again later', True, retry_after

            if code is not None and int(code) >= 500:
                if log and hasattr(log, 'exception'):
                    log.exception('FicHub: upstream server error')
                return None, f'FicHub server error: HTTP {code}', True, None

            if log and hasattr(log, 'exception'):
                log.exception('FicHub: metadata request failed')
            return None, as_unicode(e), True, None

        status = getattr(response, 'code', None)
        if status == 429:
            return None, 'FicHub API rate limited; please try again later', True, self._retry_delay(response)

        if status is not None and int(status) >= 500:
            return None, f'FicHub server error: HTTP {status}', True, None

        if status is not None and int(status) >= 400:
            return None, f'FicHub request failed: HTTP {status}', False, None

        try:
            raw = response.read()
            data = json.loads(raw.decode('utf-8'))
        except Exception as e:
            if log and hasattr(log, 'error'):
                log.error('FicHub: failed to parse JSON response')
            if log and hasattr(log, 'exception'):
                log.exception(e)
            return None, 'Failed to parse FicHub response as JSON', False, None

        if isinstance(data, dict):
            data = cast(dict[str, Any], data)
            ret_raw = data.get('ret', 0) or 0
            try:
                ret_code = int(ret_raw)
            except Exception:
                ret_code = 0

            if ret_code == 2:
                msg = data.get('msg') or 'Fic not found'
                if log and hasattr(log, 'error'):
                    log.error('FicHub: Fic not found: %s', self.endpoint)
                return None, f'FicHub: {as_unicode(msg)}', False, None

            if ret_code == 1:
                msg = data.get('msg') or 'upstream error'
                return None, f'FicHub API error: {as_unicode(msg)}', True, None

            if ret_code != 0:
                msg = data.get('msg') or data.get('res') or 'unknown API error'
                return None, f'FicHub API error: {as_unicode(msg)}', False, None

        return cast(dict[str, Any] | None, data if isinstance(data, dict) else None), None, False, None

    def _retry_delay(self, response: Any) -> int:
        """
        Compute a bounded retry delay from a response-like object.

        The method attempts to extract a retry delay value, clamps it to the
        configured maximum, and adds a small buffer before returning it.

        Args:
            response (Any): Response-like object or exception containing retry metadata.

        Returns:
            int: Retry delay in seconds, capped by configuration and adjusted with a buffer.
        """
        retry_after = self._extract_retry_after(response)
        if retry_after is None:
            retry_after = 0
        return min(retry_after, self.max_retry_after) + 2

    def _extract_retry_after(self, response: Any) -> int | None:
        """
        Extract a retry delay from a response-like object.

        The method checks common header locations for a ``Retry-After`` value.
        If no header is found, it attempts to parse the response body as JSON
        and read a ``retry_after`` field.

        Args:
            response (Any): Response-like object that may expose headers and body data.

        Returns:
            int | None:
                - int: Retry delay in seconds if successfully extracted.
                - None: If no valid retry delay value is available.
        """
        if response is None:
            return None

        headers = getattr(response, 'headers', None)
        if headers is not None:
            retry_after = headers.get('Retry-After')
            if retry_after:
                try:
                    return int(retry_after)
                except (ValueError, TypeError):
                    return None

        hdrs = getattr(response, 'hdrs', None) or getattr(response, 'info', lambda: None)()
        if hdrs is not None and hasattr(hdrs, 'get'):
            retry_after = hdrs.get('Retry-After')
            if retry_after:
                try:
                    return int(retry_after)
                except (ValueError, TypeError):
                    return None

        try:
            raw = response.read()
            body = json.loads(raw.decode('utf-8'))
            if isinstance(body, dict):
                body = cast(dict[str, Any], body)
                retry_after = body.get('retry_after')
                if retry_after is not None:
                    return int(retry_after)
        except Exception:
            return None

        return None
