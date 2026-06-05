"""Immutable monthly lifecycle events for teams."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class TeamLifecycleEvent(Base, TimestampMixin):
    """Point-in-time lifecycle transitions for a team."""

    __tablename__ = "team_lifecycle_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        nullable=False,
    )
    team_id = Column(
        BigInteger,
        ForeignKey("teams.id"),
        nullable=False,
    )
    event_date = Column(Date, nullable=False)
    event_type = Column(String(30), nullable=False)

    generation_run = relationship("GenerationRun")
    batch = relationship("MonthlyBatch")
    team = relationship("Team")

    __table_args__ = (
        Index("idx_team_lifecycle_events_run", "generation_run_id"),
        Index("idx_team_lifecycle_events_batch", "batch_id"),
        Index("idx_team_lifecycle_events_team", "team_id"),
        Index("idx_team_lifecycle_events_date", "event_date"),
        CheckConstraint(
            "event_type IN ('formed', 'dormant', 'retired', 'reactivated')",
            name="chk_team_lifecycle_event_type",
        ),
    )
