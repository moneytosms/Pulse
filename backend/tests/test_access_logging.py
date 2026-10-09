"""HTTP operations keep useful route/status logs without private query text."""

import logging

import pytest

from app.core.access_logging import OmitQueryStringFilter


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/patients/synthetic/entries?q=sensitive+clinical+search&limit=20",
        "/api/v1/clinicians/lookup?email=synthetic%40example.com",
        "/api/v1/auth/verify?token=synthetic-secret",
        "/api/v1/ready",
    ],
)
def test_access_log_keeps_route_and_status_without_query_contents(path: str) -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", path, "1.1", 200),
        None,
    )
    assert OmitQueryStringFilter().filter(record)
    assert record.getMessage() == f'127.0.0.1:1234 - "GET {path.partition("?")[0]} HTTP/1.1" 200'
