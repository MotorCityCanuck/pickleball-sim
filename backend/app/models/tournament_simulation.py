"""Tournament simulation persistence models."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class TournamentEvent(Base, TimestampMixin):
    """Instructor-facing tournament event configured from generated data."""

    __tablename__ = "tournament_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_name = Column(String(255), nullable=False)
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    source_batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        nullable=False,
    )
    tournament_date = Column(Date, nullable=False)
    config_snapshot = Column(JSONB, nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default="draft",
        server_default=text("'draft'"),
    )

    generation_run = relationship("GenerationRun")
    source_batch = relationship("MonthlyBatch")
    student_groups = relationship(
        "TournamentStudentGroup",
        back_populates="event",
    )
    submissions = relationship(
        "TournamentSubmission",
        back_populates="event",
    )
    simulation_runs = relationship(
        "TournamentSimulationRun",
        back_populates="event",
    )

    __table_args__ = (
        Index("idx_tournament_events_generation_run", "generation_run_id"),
        Index("idx_tournament_events_source_batch", "source_batch_id"),
        Index("idx_tournament_events_date", "tournament_date"),
        Index("idx_tournament_events_status", "status"),
        CheckConstraint(
            "status IN ('draft', 'ready', 'running', 'completed', 'cancelled')",
            name="chk_tournament_event_status",
        ),
    )


class TournamentStudentGroup(Base, TimestampMixin):
    """Student group participating in a tournament event."""

    __tablename__ = "tournament_student_groups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        BigInteger,
        ForeignKey("tournament_events.id"),
        nullable=False,
    )
    group_name = Column(String(255), nullable=False)
    external_group_key = Column(String(255))

    event = relationship(
        "TournamentEvent",
        back_populates="student_groups",
    )
    submissions = relationship(
        "TournamentSubmission",
        back_populates="student_group",
    )

    __table_args__ = (
        Index("idx_tournament_student_groups_event", "event_id"),
        UniqueConstraint("event_id", "group_name", name="uq_tournament_group_name"),
        UniqueConstraint(
            "event_id",
            "external_group_key",
            name="uq_tournament_group_external_key",
        ),
    )


class TournamentSubmission(Base, TimestampMixin):
    """Normalized student-group team submission for one portfolio slot."""

    __tablename__ = "tournament_submissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        BigInteger,
        ForeignKey("tournament_events.id"),
        nullable=False,
    )
    student_group_id = Column(
        BigInteger,
        ForeignKey("tournament_student_groups.id"),
        nullable=False,
    )
    slot_country_code = Column(String(2), nullable=False)
    slot_division = Column(String(50), nullable=False)
    team_id = Column(BigInteger, ForeignKey("teams.id"), nullable=False)
    validation_status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    validation_message = Column(Text)

    event = relationship("TournamentEvent", back_populates="submissions")
    student_group = relationship(
        "TournamentStudentGroup",
        back_populates="submissions",
    )
    team = relationship("Team")

    __table_args__ = (
        Index("idx_tournament_submissions_event", "event_id"),
        Index("idx_tournament_submissions_group", "student_group_id"),
        Index("idx_tournament_submissions_team", "team_id"),
        UniqueConstraint(
            "event_id",
            "student_group_id",
            "slot_country_code",
            "slot_division",
            name="uq_tournament_submission_slot",
        ),
        CheckConstraint(
            "slot_country_code IN ('US', 'CA')",
            name="chk_tournament_submission_country",
        ),
        CheckConstraint(
            "slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')",
            name="chk_tournament_submission_division",
        ),
        CheckConstraint(
            "validation_status IN ('pending', 'valid', 'invalid')",
            name="chk_tournament_submission_validation_status",
        ),
    )


class TournamentSimulationRun(Base, TimestampMixin):
    """Execution record for a Monte Carlo or official tournament simulation."""

    __tablename__ = "tournament_simulation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        BigInteger,
        ForeignKey("tournament_events.id"),
        nullable=False,
    )
    run_type = Column(String(30), nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    seed = Column(BigInteger)
    iteration_count = Column(Integer)
    config_snapshot = Column(JSONB, nullable=False)
    job_status_id = Column(BigInteger, ForeignKey("job_status.id"))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    event = relationship("TournamentEvent", back_populates="simulation_runs")
    job_status = relationship("JobStatus")
    team_results = relationship(
        "TournamentTeamResult",
        back_populates="simulation_run",
    )
    group_results = relationship(
        "TournamentGroupResult",
        back_populates="simulation_run",
    )
    division_results = relationship(
        "TournamentDivisionResult",
        back_populates="simulation_run",
    )
    official_matches = relationship(
        "TournamentOfficialMatch",
        back_populates="simulation_run",
    )

    __table_args__ = (
        Index("idx_tournament_simulation_runs_event", "event_id"),
        Index("idx_tournament_simulation_runs_status", "status"),
        Index("idx_tournament_simulation_runs_type", "run_type"),
        Index("idx_tournament_simulation_runs_job", "job_status_id"),
        CheckConstraint(
            "run_type IN ('monte_carlo', 'official')",
            name="chk_tournament_simulation_run_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="chk_tournament_simulation_run_status",
        ),
        CheckConstraint(
            "iteration_count IS NULL OR iteration_count >= 1",
            name="chk_tournament_simulation_iterations",
        ),
    )


class TournamentTeamResult(Base, TimestampMixin):
    """Team-level aggregate or official result for one simulation run."""

    __tablename__ = "tournament_team_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    simulation_run_id = Column(
        BigInteger,
        ForeignKey("tournament_simulation_runs.id"),
        nullable=False,
    )
    slot_country_code = Column(String(2), nullable=False)
    slot_division = Column(String(50), nullable=False)
    team_id = Column(BigInteger, ForeignKey("teams.id"), nullable=False)
    championship_probability = Column(Numeric(8, 5))
    top_three_probability = Column(Numeric(8, 5))
    average_finish = Column(Numeric(8, 3))
    win_percentage = Column(Numeric(8, 5))
    upset_count = Column(Integer)
    final_rank = Column(Integer)
    match_wins = Column(Integer)
    match_losses = Column(Integer)
    games_won = Column(Integer)
    games_lost = Column(Integer)
    point_differential = Column(Integer)

    simulation_run = relationship(
        "TournamentSimulationRun",
        back_populates="team_results",
    )
    team = relationship("Team")

    __table_args__ = (
        Index("idx_tournament_team_results_run", "simulation_run_id"),
        Index("idx_tournament_team_results_team", "team_id"),
        Index(
            "idx_tournament_team_results_division",
            "slot_country_code",
            "slot_division",
        ),
        UniqueConstraint(
            "simulation_run_id",
            "slot_country_code",
            "slot_division",
            "team_id",
            name="uq_tournament_team_result",
        ),
        CheckConstraint(
            "slot_country_code IN ('US', 'CA')",
            name="chk_tournament_team_result_country",
        ),
        CheckConstraint(
            "slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')",
            name="chk_tournament_team_result_division",
        ),
        CheckConstraint(
            "final_rank IS NULL OR final_rank >= 1",
            name="chk_tournament_team_result_rank",
        ),
    )


class TournamentGroupResult(Base, TimestampMixin):
    """Student-group aggregate result for one simulation run."""

    __tablename__ = "tournament_group_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    simulation_run_id = Column(
        BigInteger,
        ForeignKey("tournament_simulation_runs.id"),
        nullable=False,
    )
    student_group_id = Column(
        BigInteger,
        ForeignKey("tournament_student_groups.id"),
        nullable=False,
    )
    expected_score = Column(Numeric(10, 3))
    official_score = Column(Numeric(10, 3))
    average_rank = Column(Numeric(8, 3))
    final_rank = Column(Integer)
    champion_count = Column(Integer)
    runner_up_count = Column(Integer)
    top_four_count = Column(Integer)
    match_wins = Column(Integer)
    rank_distribution = Column(JSONB)

    simulation_run = relationship(
        "TournamentSimulationRun",
        back_populates="group_results",
    )
    student_group = relationship("TournamentStudentGroup")

    __table_args__ = (
        Index("idx_tournament_group_results_run", "simulation_run_id"),
        Index("idx_tournament_group_results_group", "student_group_id"),
        UniqueConstraint(
            "simulation_run_id",
            "student_group_id",
            name="uq_tournament_group_result",
        ),
        CheckConstraint(
            "final_rank IS NULL OR final_rank >= 1",
            name="chk_tournament_group_result_rank",
        ),
    )


class TournamentDivisionResult(Base, TimestampMixin):
    """Division-level summary for one simulation run."""

    __tablename__ = "tournament_division_results"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    simulation_run_id = Column(
        BigInteger,
        ForeignKey("tournament_simulation_runs.id"),
        nullable=False,
    )
    slot_country_code = Column(String(2), nullable=False)
    slot_division = Column(String(50), nullable=False)
    iteration_count = Column(Integer)
    unique_team_count = Column(Integer, nullable=False)
    match_count = Column(Integer, nullable=False)
    champion_team_id = Column(BigInteger, ForeignKey("teams.id"))
    summary_payload = Column(JSONB)

    simulation_run = relationship(
        "TournamentSimulationRun",
        back_populates="division_results",
    )
    champion_team = relationship("Team")

    __table_args__ = (
        Index("idx_tournament_division_results_run", "simulation_run_id"),
        Index(
            "idx_tournament_division_results_division",
            "slot_country_code",
            "slot_division",
        ),
        UniqueConstraint(
            "simulation_run_id",
            "slot_country_code",
            "slot_division",
            name="uq_tournament_division_result",
        ),
        CheckConstraint(
            "slot_country_code IN ('US', 'CA', 'ALL')",
            name="chk_tournament_division_result_country",
        ),
        CheckConstraint(
            "slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')",
            name="chk_tournament_division_result_division",
        ),
        CheckConstraint(
            "unique_team_count >= 0",
            name="chk_tournament_division_team_count",
        ),
        CheckConstraint(
            "match_count >= 0",
            name="chk_tournament_division_match_count",
        ),
    )


class TournamentOfficialMatch(Base, TimestampMixin):
    """Persisted official tournament match result."""

    __tablename__ = "tournament_official_matches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    simulation_run_id = Column(
        BigInteger,
        ForeignKey("tournament_simulation_runs.id"),
        nullable=False,
    )
    slot_country_code = Column(String(2), nullable=False)
    slot_division = Column(String(50), nullable=False)
    match_number = Column(Integer, nullable=False)
    team_one_id = Column(BigInteger, ForeignKey("teams.id"), nullable=False)
    team_two_id = Column(BigInteger, ForeignKey("teams.id"), nullable=False)
    winning_team_id = Column(BigInteger, ForeignKey("teams.id"), nullable=False)
    team_one_games_won = Column(Integer, nullable=False)
    team_two_games_won = Column(Integer, nullable=False)
    team_one_points = Column(Integer, nullable=False)
    team_two_points = Column(Integer, nullable=False)
    visible_team_one_win_probability = Column(Numeric(8, 4))
    final_team_one_win_probability = Column(Numeric(8, 4))

    simulation_run = relationship(
        "TournamentSimulationRun",
        back_populates="official_matches",
    )
    team_one = relationship("Team", foreign_keys=[team_one_id])
    team_two = relationship("Team", foreign_keys=[team_two_id])
    winning_team = relationship("Team", foreign_keys=[winning_team_id])
    games = relationship(
        "TournamentOfficialGame",
        back_populates="official_match",
    )

    __table_args__ = (
        Index("idx_tournament_official_matches_run", "simulation_run_id"),
        Index(
            "idx_tournament_official_matches_division",
            "slot_country_code",
            "slot_division",
        ),
        UniqueConstraint(
            "simulation_run_id",
            "match_number",
            name="uq_tournament_official_match_number",
        ),
        CheckConstraint(
            "slot_country_code IN ('US', 'CA', 'ALL')",
            name="chk_tournament_official_match_country",
        ),
        CheckConstraint(
            "slot_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles')",
            name="chk_tournament_official_match_division",
        ),
        CheckConstraint(
            "match_number >= 1",
            name="chk_tournament_official_match_number",
        ),
        CheckConstraint(
            "team_one_id <> team_two_id",
            name="chk_tournament_official_match_distinct_teams",
        ),
    )


class TournamentOfficialGame(Base, TimestampMixin):
    """Persisted game result for an official tournament match."""

    __tablename__ = "tournament_official_games"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    official_match_id = Column(
        BigInteger,
        ForeignKey("tournament_official_matches.id"),
        nullable=False,
    )
    game_number = Column(Integer, nullable=False)
    team_one_score = Column(Integer, nullable=False)
    team_two_score = Column(Integer, nullable=False)
    winning_team_number = Column(Integer, nullable=False)
    target_score = Column(Integer, nullable=False, default=11, server_default=text("11"))
    win_by = Column(Integer, nullable=False, default=2, server_default=text("2"))
    expected_team_one_score_share = Column(Numeric(8, 4))
    actual_team_one_score_share = Column(Numeric(8, 4))

    official_match = relationship(
        "TournamentOfficialMatch",
        back_populates="games",
    )

    __table_args__ = (
        Index("idx_tournament_official_games_match", "official_match_id"),
        UniqueConstraint(
            "official_match_id",
            "game_number",
            name="uq_tournament_official_game_number",
        ),
        CheckConstraint(
            "game_number >= 1",
            name="chk_tournament_official_game_number",
        ),
        CheckConstraint(
            "winning_team_number IN (1, 2)",
            name="chk_tournament_official_game_winner",
        ),
        CheckConstraint(
            "team_one_score >= 0 AND team_two_score >= 0",
            name="chk_tournament_official_game_scores",
        ),
        CheckConstraint(
            "target_score IN (11, 15, 21)",
            name="chk_tournament_official_game_target",
        ),
        CheckConstraint(
            "win_by >= 1",
            name="chk_tournament_official_game_win_by",
        ),
    )
