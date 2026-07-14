"""Fake httpx.get() for app/web_search.py tests — no real network calls.

httpx.Request/Response can be constructed standalone (no connection involved),
so a fake response behaves identically to a real one for the code under test
(status codes, .json(), .text, .raise_for_status() all work as documented).
"""

import httpx


def fake_response(url: str, *, status_code: int = 200, json_data=None, text: str | None = None) -> httpx.Response:
    request = httpx.Request("GET", url)
    if json_data is not None:
        return httpx.Response(status_code, request=request, json=json_data)
    return httpx.Response(status_code, request=request, text=text or "")


def make_fake_get(responses_by_url_substring: dict[str, httpx.Response], *, raises: dict[str, Exception] | None = None):
    """Returns a function with httpx.get's signature that looks up a canned
    response by substring-matching the request URL — good enough for these
    tests since each one only ever configures a single base URL at a time.
    `raises` maps a URL substring to an exception to raise instead (e.g. a
    timeout) rather than returning a response."""
    raises = raises or {}

    def _fake_get(url: str, *args, **kwargs):
        for substring, exc in raises.items():
            if substring in url:
                raise exc
        for substring, response in responses_by_url_substring.items():
            if substring in url:
                return response
        raise AssertionError(f"No fake response configured for URL: {url}")

    return _fake_get
