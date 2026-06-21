"""Helpers that materialize compact audit facts during batch execution."""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.generation.runtime_metrics import RuntimeMetricRecorder
from app.models import AuditBatchTeamRoster, Team, TeamMembership


def persist_audit_batch_team_rosters(
    session: Session,
    *,
    generation_run_id: int,
    batch_id: int,
    batch_month: date,
    runtime_recorder: RuntimeMetricRecorder | None = None,
) -> int:
    """Persist one active doubles roster snapshot row per active team for a batch."""
    AuditBatchTeamRoster.__table__.create(
        bind=session.get_bind(),
        checkfirst=True,
    )

    active_rosters = list(
        session.execute(
            select(
                Team.id.label("team_id"),
                func.min(TeamMembership.player_id).label("player_one_id"),
                func.max(TeamMembership.player_id).label("player_two_id"),
            )
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .where(
                Team.generation_run_id == generation_run_id,
                Team.team_status == "active",
                Team.formation_date <= batch_month,
                or_(Team.dissolution_date.is_(None), Team.dissolution_date > batch_month),
                TeamMembership.joined_date <= batch_month,
                or_(
                    TeamMembership.left_date.is_(None),
                    TeamMembership.left_date > batch_month,
                ),
            )
            .group_by(Team.id)
            .having(func.count() == 2)
        ).mappings()
    )

    def _persist() -> int:
        session.execute(
            delete(AuditBatchTeamRoster).where(AuditBatchTeamRoster.batch_id == batch_id)
        )
        rows = [
            {
                "generation_run_id": generation_run_id,
                "batch_id": batch_id,
                "batch_month": batch_month,
                "team_id": int(row["team_id"]),
                "player_one_id": int(row["player_one_id"]),
                "player_two_id": int(row["player_two_id"]),
                "roster_key": f"{int(row['player_one_id'])}:{int(row['player_two_id'])}",
            }
            for row in active_rosters
        ]
        if rows:
            session.execute(insert(AuditBatchTeamRoster), rows)
        session.flush()
        return len(rows)

    if runtime_recorder is None:
        return _persist()

    with runtime_recorder.measure(
        "persist_audit_batch_team_rosters",
        input_count=len(active_rosters),
        metadata={"batch_month": batch_month},
    ) as metric:
        row_count = _persist()
        metric["output_count"] = row_count
        return row_count
