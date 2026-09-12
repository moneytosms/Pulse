"""Analytics wire contract (P4.2, #53).

No `summary_insight` table (ADR-0009) — these are shapes for values
computed at request time, not persisted rows.
"""

from __future__ import annotations

from enum import StrEnum


class DataQualityFlag(StrEnum):
    """The five flags named in domain-model.md, "Data quality". All
    informational — they never block anything."""

    MISSING_DOB = "MISSING_DOB"
    MISSING_CONTACT = "MISSING_CONTACT"
    FUTURE_DATED_ENTRY = "FUTURE_DATED_ENTRY"
    IMPLAUSIBLE_DOB = "IMPLAUSIBLE_DOB"
    UNCLAIMED_LONG_LIVED = "UNCLAIMED_LONG_LIVED"
