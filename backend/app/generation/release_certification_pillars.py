"""First-class release certification pillar definitions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseCertificationPillar:
    """One certification pillar in the NAPA release certification framework."""

    key: str
    label: str
    description: str
    implementation_status: str


STRUCTURAL_INTEGRITY_PILLAR = ReleaseCertificationPillar(
    key="structural_integrity",
    label="Structural Integrity",
    description="Validate relational correctness, lifecycle consistency, and foundational data integrity.",
    implementation_status="planned",
)

OPERATIONAL_REALISM_PILLAR = ReleaseCertificationPillar(
    key="operational_realism",
    label="Operational Realism",
    description="Validate player, club, team, match, score, and rating realism against configured generation behavior.",
    implementation_status="implemented",
)

SIMULATION_FIDELITY_PILLAR = ReleaseCertificationPillar(
    key="simulation_fidelity",
    label="Simulation Fidelity",
    description="Validate that hidden simulation mechanisms produce measurable downstream effects.",
    implementation_status="implemented",
)

ASSIGNMENT_READINESS_PILLAR = ReleaseCertificationPillar(
    key="assignment_readiness",
    label="Assignment Readiness",
    description="Validate that the generated population supports Olympic candidate and team-selection workflows.",
    implementation_status="implemented",
)

EXPORT_READINESS_PILLAR = ReleaseCertificationPillar(
    key="export_readiness",
    label="Export Readiness",
    description="Validate that release inputs and student-facing export prerequisites are complete.",
    implementation_status="implemented",
)

HISTORICAL_REGRESSION_PILLAR = ReleaseCertificationPillar(
    key="historical_regression",
    label="Historical Regression",
    description="Compare current release behavior against previous approved releases and scale targets.",
    implementation_status="implemented",
)

RELEASE_CERTIFICATION_PILLARS: tuple[ReleaseCertificationPillar, ...] = (
    STRUCTURAL_INTEGRITY_PILLAR,
    OPERATIONAL_REALISM_PILLAR,
    SIMULATION_FIDELITY_PILLAR,
    ASSIGNMENT_READINESS_PILLAR,
    EXPORT_READINESS_PILLAR,
    HISTORICAL_REGRESSION_PILLAR,
)

RELEASE_CERTIFICATION_PILLAR_MAP = {
    pillar.key: pillar for pillar in RELEASE_CERTIFICATION_PILLARS
}


def serialize_release_certification_pillars() -> list[dict[str, str]]:
    """Return JSON-ready pillar metadata."""
    return [
        {
            "key": pillar.key,
            "label": pillar.label,
            "description": pillar.description,
            "implementation_status": pillar.implementation_status,
        }
        for pillar in RELEASE_CERTIFICATION_PILLARS
    ]
