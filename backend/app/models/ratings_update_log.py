"""Rating update audit log model."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class RatingsUpdateLog(Base, TimestampMixin):
    """Per-player, per-match rating update audit row."""

    __tablename__ = "ratings_update_log"

    id = Column(BigInteger, primary_key=True)
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    batch_id = Column(BigInteger, ForeignKey("monthly_batches.id"), nullable=False)
    match_id = Column(BigInteger, ForeignKey("matches.id"), nullable=False)
    match_number = Column(Integer, nullable=False)
    match_date = Column(Date, nullable=False)
    player_id = Column(BigInteger, ForeignKey("players.id"), nullable=False)
    match_team_id = Column(BigInteger, ForeignKey("match_teams.id"), nullable=False)
    team_number = Column(Integer, nullable=False)
    rating_type = Column(String(50), nullable=False)
    rating_before = Column(Numeric(8, 3), nullable=False)
    rating_after = Column(Numeric(8, 3), nullable=False)
    rating_delta = Column(Numeric(8, 3), nullable=False)
    expected_score_share = Column(Numeric(8, 4), nullable=False)
    actual_score_share = Column(Numeric(8, 4), nullable=False)
    expected_raw_points = Column(Numeric(8, 3), nullable=False)
    actual_raw_points = Column(Numeric(8, 3), nullable=False)
    games_played = Column(Integer, nullable=False)
    games_won = Column(Integer, nullable=False)
    match_won = Column(Integer, nullable=False)
    k_factor = Column(Numeric(8, 3), nullable=False)
    confidence_before = Column(Numeric(8, 3))
    confidence_after = Column(Numeric(8, 3))
    calculation_version = Column(String(50))

    generation_run = relationship("GenerationRun")
    batch = relationship("MonthlyBatch")
    match = relationship("Match")
    player = relationship("Player")
    match_team = relationship("MatchTeam")

    __table_args__ = (
        Index("idx_ratings_update_log_batch", "batch_id"),
        Index(
            "idx_ratings_update_log_run_player_day",
            "generation_run_id",
            "player_id",
            "match_date",
        ),
        Index(
            "idx_ratings_update_log_run_player_date",
            "generation_run_id",
            "player_id",
            "match_date",
            "match_id",
        ),
        CheckConstraint("match_number >= 1", name="chk_rating_log_match_number"),
        CheckConstraint("team_number IN (1, 2)", name="chk_rating_log_team_number"),
        CheckConstraint("games_played >= 1", name="chk_rating_log_games_played"),
        CheckConstraint("games_won >= 0", name="chk_rating_log_games_won"),
        CheckConstraint("match_won IN (0, 1)", name="chk_rating_log_match_won"),
        CheckConstraint(
            "rating_before >= 0 AND rating_before <= 5000",
            name="chk_rating_log_before",
        ),
        CheckConstraint(
            "rating_after >= 0 AND rating_after <= 5000",
            name="chk_rating_log_after",
        ),
        CheckConstraint(
            "expected_score_share >= 0 AND expected_score_share <= 1",
            name="chk_rating_log_expected_share",
        ),
        CheckConstraint(
            "actual_score_share >= 0 AND actual_score_share <= 1",
            name="chk_rating_log_actual_share",
        ),
    )
