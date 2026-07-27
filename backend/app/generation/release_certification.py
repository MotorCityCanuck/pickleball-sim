"""Phase-1 compatibility layer for the NAPA release certification framework."""
from __future__ import annotations

from .realism_audit import REALISM_AUDIT_QUERIES, RealismAuditQuery, RealismAuditResult
from .realism_audit_history import (
    DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR,
    build_realism_audit_snapshot_filename,
    save_realism_audit_snapshot,
)
from .realism_audit_service import (
    RealismAuditExecution,
    RealismAuditService,
    run_realism_audit,
)

RELEASE_CERTIFICATION_QUERIES = REALISM_AUDIT_QUERIES
DEFAULT_RELEASE_CERTIFICATION_SNAPSHOT_DIR = DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR

ReleaseCertificationQuery = RealismAuditQuery
ReleaseCertificationResult = RealismAuditResult
ReleaseCertificationExecution = RealismAuditExecution


class ReleaseCertificationService(RealismAuditService):
    """Phase-1 release certification uses the existing realism-audit query pack."""


def run_release_certification(*args, **kwargs) -> ReleaseCertificationExecution:
    """Convenience wrapper for the phase-1 release certification execution."""
    return run_realism_audit(*args, **kwargs)


def save_release_certification_snapshot(*args, **kwargs):
    """Persist a release-certification snapshot using the existing JSON format."""
    return save_realism_audit_snapshot(*args, **kwargs)


def build_release_certification_snapshot_filename(*args, **kwargs) -> str:
    """Return the compatibility snapshot filename for release certification."""
    return build_realism_audit_snapshot_filename(*args, **kwargs)
