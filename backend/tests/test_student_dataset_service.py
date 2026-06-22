"""Tests for complete student dataset build orchestration."""

from pathlib import Path
import re
import sys

import pytest
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    PublishedStudentDatasetFamily,
    PublishedStudentDatasetRelease,
    ReleaseWindowValidationError,
    STUDENT_TABLE_ORDER,
    StudentDatasetBuildResult,
    StudentDatasetExportService,
    StudentDatasetExportPreflightError,
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


def test_build_student_dataset_release_fails_when_final_folder_exists_without_delete_confirmation(
    session,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _seed_succeeded_generation_run(session)
    final_root = tmp_path / "napa_student_release"
    final_root.mkdir()
    (final_root / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(
        StudentDatasetExportPreflightError,
        match="Expected release folder already exists",
    ):
        build_student_dataset_release(
            session=session,
            generation_run_id=1,
            initial_history_month_count=2,
            subsequent_month_count=0,
            output_root=tmp_path,
            release_name="napa_student_release",
            overwrite_existing=False,
        )

    assert final_root.exists()
    assert (final_root / "keep.txt").exists()


def test_build_student_dataset_release_deletes_existing_final_folder_when_confirmed(
    session,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _seed_succeeded_generation_run(session)
    final_root = tmp_path / "napa_student_release"
    final_root.mkdir()
    (final_root / "obsolete.txt").write_text("obsolete", encoding="utf-8")

    result = build_student_dataset_release(
        session=session,
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        overwrite_existing=True,
    )

    assert isinstance(result, StudentDatasetBuildResult)
    assert result.published_family.final_root == final_root
    assert result.published_family.final_root.exists()
    assert not (result.published_family.final_root / "obsolete.txt").exists()


def test_registered_export_writes_paired_clean_and_tainted_outputs(session, tmp_path):
    seed_snapshot_query_data(session)
    _seed_succeeded_generation_run(session)
    _create_job_tracking_tables(session)
    service = StudentDatasetExportService()
    registration = service.register_export_job(
        session=session,
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        clean_subfolder="clean",
        tainted_subfolder="tainted",
    )

    result = service.execute_registered_export(
        session=session,
        job_status_id=registration.job_status.id,
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        clean_subfolder="clean",
        tainted_subfolder="tainted",
    )

    assert result is not None
    assert result.clean_published_family is not None
    clean_root = result.clean_published_family.final_root
    tainted_root = result.published_family.final_root
    assert clean_root == tainted_root.parent / "clean"
    assert tainted_root.name == "tainted"
    assert clean_root.parent == tainted_root.parent
    assert clean_root.parent.parent.parent == tmp_path / "napa_student_release"
    assert re.fullmatch(r"\d{8}", clean_root.parent.parent.name)
    assert re.fullmatch(r"\d{6}Z", clean_root.parent.name)
    assert (
        clean_root
        / "napa_student_release_initial_history"
    ).is_dir()
    assert (
        tainted_root
        / "napa_student_release_initial_history"
    ).is_dir()

    release_rows = session.execute(
        text(
            """
            SELECT data_quality_level, output_path
            FROM student_dataset_releases
            ORDER BY data_quality_level
            """
        )
    ).mappings().all()
    assert [row["data_quality_level"] for row in release_rows] == ["medium", "none"]
    assert any("/clean/" in row["output_path"] for row in release_rows)
    assert any("/tainted/" in row["output_path"] for row in release_rows)


def test_published_family_assertion_requires_parquet_files(tmp_path):
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    published = PublishedStudentDatasetFamily(
        release_name="release",
        final_root=tmp_path,
        releases=(
            PublishedStudentDatasetRelease(
                release_id=1,
                release_name="release",
                release_type="initial_snapshot",
                release_dir=release_dir,
                manifest_path=release_dir / "manifest.json",
                file_count=0,
            ),
        ),
    )

    with pytest.raises(StudentDatasetExportPreflightError, match="no Parquet files"):
        StudentDatasetExportService._assert_published_family_has_files(published)

    (release_dir / "players.parquet").write_bytes(b"parquet")

    StudentDatasetExportService._assert_published_family_has_files(published)


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


def _create_job_tracking_tables(session) -> None:
    session.execute(
        text(
            """
            CREATE TABLE job_status (
                id integer primary key autoincrement,
                job_type varchar(50) not null,
                job_id varchar(100) not null unique,
                status varchar(30) not null default 'pending',
                current_phase varchar(100),
                percent_complete numeric(5,2),
                current_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE job_stage_progress (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                stage_sequence integer,
                status varchar(30) not null default 'pending',
                progress_current bigint not null default 0,
                progress_total bigint,
                progress_unit varchar(100),
                progress_percent numeric(5,2),
                last_heartbeat_at datetime,
                progress_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                metadata_json text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique(job_status_id, batch_id, stage_name)
            )
            """
        )
    )
    session.commit()
