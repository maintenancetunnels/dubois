"""DuBois Result Module

This module defines objects for recording the results of queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QueryStatus(Enum):
    """Status of a query about a given username."""

    CLAIMED = "Claimed"  # Username Detected
    AVAILABLE = "Available"  # Username Not Detected
    UNKNOWN = "Unknown"  # Error Occurred While Trying To Detect Username
    ILLEGAL = "Illegal"  # Username Not Allowable For This Site
    WAF = "WAF"  # Request blocked by WAF (i.e. Cloudflare)

    def __str__(self) -> str:
        return self.value


@dataclass
class QueryResult:
    """Result of a query about a given username."""

    username: str
    site_name: str
    site_url_user: str
    status: QueryStatus
    query_time: float | None = None
    context: str | None = None
    p_profile: float = 0.0
    score_reasons: tuple[str, ...] = ()

    def __str__(self) -> str:
        status = str(self.status)
        if self.status is QueryStatus.CLAIMED:
            status += f" p={self.p_profile:.2f}"
        if self.context is not None:
            status += f" ({self.context})"
        return status
