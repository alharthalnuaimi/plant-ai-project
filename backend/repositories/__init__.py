"""
Repository layer — the ONLY place that talks to the database directly.

Services import these functions; routes never import from here.

Every repository is async and gracefully no-ops when persistence is
disabled (returns `[]` or `None`), so the rest of the app keeps working
even when Postgres is offline.
"""

from . import (
    analytics_events_repo,
    assistant_repo,
    audit_repo,
    devices_repo,
    scans_repo,
    sensor_repo,
    zones_repo,
)

__all__ = [
    "analytics_events_repo",
    "assistant_repo",
    "audit_repo",
    "devices_repo",
    "scans_repo",
    "sensor_repo",
    "zones_repo",
]
