"""Keep clinical search text and identity queries out of HTTP access logs."""

import logging


class OmitQueryStringFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access record is (client, method, path, version, status).
        # Preserve the route and status for operations without copying the
        # user's search terms, lookup identifiers or verification tokens.
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].partition("?")[0], *args[3:])
        return True


_query_filter = OmitQueryStringFilter()


def configure_access_logging() -> None:
    logging.getLogger("uvicorn.access").addFilter(_query_filter)
