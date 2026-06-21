"""Persisted batch-local active team rosters for realism audit helpers."""
from sqlalchemy import BigInteger, Column, Date, ForeignKey, Index, String
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class AuditBatchTeamRoster(Base, TimestampMixin):
    """One active doubles roster snapshot per team for a monthly batch."""

    __tablename__ = "audit_batch_team_rosters"

    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        primary_key=True,
        nullable=False,
    )
    batch_month = Column(Date, nullable=False)
    team_id = Column(
        BigInteger,
        ForeignKey("teams.id"),
        primary_key=True,
        nullable=False,
    )
    player_one_id = Column(BigInteger, ForeignKey("players.id"), nullable=False)
    player_two_id = Column(BigInteger, ForeignKey("players.id"), nullable=False)
    roster_key = Column(String(64), nullable=False)

    generation_run = relationship("GenerationRun")
    batch = relationship("MonthlyBatch")
    team = relationship("Team")

    __table_args__ = (
        Index("idx_audit_batch_team_rosters_run_batch", "generation_run_id", "batch_id"),
        Index(
            "idx_audit_batch_team_rosters_run_roster_batch",
            "generation_run_id",
            "roster_key",
            "batch_id",
        ),
        Index(
            "idx_audit_batch_team_rosters_run_batch_month",
            "generation_run_id",
            "batch_month",
        ),
    )
