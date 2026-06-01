"""Tests for complete student dataset build orchestration."""

from pathlib import Path
import sys

import pytest
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    ReleaseWindowValidationError,
    STUDENT_TABLE_ORDER,
    StudentDatasetBuildResult,
    build_student_dataset_release,
)
from test_student_dataset_queries import (  # noqa: E402
    seed_snapshot_query_data,
    session,
    session_factory,
)


def test_build_student_dataset_release_runs_complete_workflow(session, tmp_path):
    seed_snapshot_query_data(session)
    _seed_succeeded_generation_run(session)

    result = build_student_dataset_release(
        session=session,
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    assert isinstance(result, StudentDatasetBuildResult)
    assert result.build_parameters.generation_run_id == 1
    assert len(result.release_windows) == 1
    assert not result.staged_family.staging_root.exists()
    assert result.published_family.final_root == tmp_path / "napa_student_release"
    assert result.published_family.final_root.exists()
    assert len(result.published_family.releases) == 1

    release = result.published_family.releases[0]
    assert release.release_name == "napa_student_release_initial_history"
    assert release.release_dir.exists()
    assert release.manifest_path.exists()
    assert release.file_count == len(STUDENT_TABLE_ORDER)

    release_count = session.execute(
        text("SELECT COUNT(*) FROM student_dataset_releases")
    ).scalar_one()
    file_count = session.execute(
        text("SELECT COUNT(*) FROM student_dataset_release_files")
    ).scalar_one()
    assert release_count == 1
    assert file_count == len(STUDENT_TABLE_ORDER)


def test_build_student_dataset_release_rejects_invalid_preflight_before_writing(
    session,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _seed_succeeded_generation_run(session, status="running")

    with pytest.raises(ReleaseWindowValidationError, match="status 'succeeded'"):
        build_student_dataset_release(
            session=session,
            generation_run_id=1,
            initial_history_month_count=2,
            subsequent_month_count=0,
            output_root=tmp_path,
            release_name="napa_student_release",
        )

    assert not list(tmp_path.iterdir())
    release_count = session.execute(
        text("SELECT COUNT(*) FROM student_dataset_releases")
    ).scalar_one()
    assert release_count == 0


def _seed_succeeded_generation_run(session, *, status: str = "succeeded") -> None:
    session.execute(
        text(
            """
            CREATE TABLE generation_runs (
                id integer primary key,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot text,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'not_started',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, status
            )
            VALUES (1, 'student export test', 123, :status)
            """
        ),
        {"status": status},
    )
    session.commit()
