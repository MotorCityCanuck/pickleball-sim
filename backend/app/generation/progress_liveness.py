"""Shared stage heartbeat and liveness policy helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping


DEFAULT_STAGE_QUIET_AFTER = timedelta(minutes=15)
DEFAULT_STAGE_LIKELY_STALLED_AFTER = timedelta(minutes=30)
STAGE_LIVENESS_OVERRIDES = {
    "matches": (
        timedelta(minutes=20),
        timedelta(minutes=60),
    ),
}


@dataclass(frozen=True)
class StageLivenessPolicy:
    """Heartbeat policy for a running stage."""

    quiet_after: timedelta
    likely_stalled_after: timedelta


def policy_for_stage(
    *,
    stage_name: str | None,
    metadata: Mapping[str, object] | None = None,
    default_quiet_after: timedelta = DEFAULT_STAGE_QUIET_AFTER,
    default_likely_stalled_after: timedelta = DEFAULT_STAGE_LIKELY_STALLED_AFTER,
) -> StageLivenessPolicy:
    """Resolve the liveness policy for a stage from metadata and defaults."""
    quiet_after = default_quiet_after
    likely_stalled_after = default_likely_stalled_after

    if stage_name in STAGE_LIVENESS_OVERRIDES:
        quiet_after, likely_stalled_after = STAGE_LIVENESS_OVERRIDES[stage_name]

    if metadata:
        quiet_override = _seconds_to_timedelta(metadata.get("heartbeat_quiet_after_seconds"))
        if quiet_override is not None:
            quiet_after = quiet_override
        likely_override = _seconds_to_timedelta(
            metadata.get("heartbeat_likely_stalled_after_seconds")
        )
        if likely_override is not None:
            likely_stalled_after = likely_override

    if likely_stalled_after < quiet_after:
        likely_stalled_after = quiet_after

    return StageLivenessPolicy(
        quiet_after=quiet_after,
        likely_stalled_after=likely_stalled_after,
    )


def liveness_state_for_stage(
    *,
    stage_name: str | None,
    status: str,
    last_heartbeat_at: datetime | None,
    now: datetime,
    metadata: Mapping[str, object] | None = None,
    default_quiet_after: timedelta = DEFAULT_STAGE_QUIET_AFTER,
    default_likely_stalled_after: timedelta = DEFAULT_STAGE_LIKELY_STALLED_AFTER,
) -> str:
    """Return `active`, `quiet`, `likely_stalled`, or `inactive`."""
    if status != "running" or last_heartbeat_at is None:
        return "inactive"

    policy = policy_for_stage(
        stage_name=stage_name,
        metadata=metadata,
        default_quiet_after=default_quiet_after,
        default_likely_stalled_after=default_likely_stalled_after,
    )
    age = now - last_heartbeat_at
    if age <= policy.quiet_after:
        return "active"
    if age <= policy.likely_stalled_after:
        return "quiet"
    return "likely_stalled"


def _seconds_to_timedelta(value: object) -> timedelta | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = int(value)
        if seconds <= 0:
            return None
        return timedelta(seconds=seconds)
    return None
