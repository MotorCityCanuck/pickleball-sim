"""Tests for migrating student dataset release types."""

from pathlib import Path
import sys

from sqlalchemy import create_engine, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.migrate_student_dataset_release_types import _migrate_engine  # noqa: E402


def test_migrate_engine_rewrites_legacy_release_types_for_sqlite():
    engine = create_engine("sqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    """
                    CREATE TABLE generation_runs (
                        id integer primary key
                    )
                    """
                )
            )
            connection.execute(text("INSERT INTO generation_runs (id) VALUES (1)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE student_dataset_releases (
                        id integer primary key,
                        release_name varchar(255) not null,
                        release_type varchar(50) not null,
                        release_month date,
                        generation_run_id bigint not null,
                        data_quality_level varchar(50),
                        output_path text not null,
                        status varchar(30) not null default 'pending',
                        completed_at datetime,
                        error_message text,
                        created_at datetime default current_timestamp not null,
                        updated_at datetime default current_timestamp not null,
                        CONSTRAINT chk_student_release_type
                            CHECK (release_type IN ('historical_baseline', 'monthly_incremental')),
                        CONSTRAINT chk_student_release_status
                            CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
                        FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE student_dataset_release_files (
                        id integer primary key,
                        release_id bigint not null,
                        table_name varchar(255) not null,
                        file_path text not null,
                        created_at datetime default current_timestamp not null,
                        FOREIGN KEY(release_id) REFERENCES student_dataset_releases(id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO student_dataset_releases (
                        id, release_name, release_type, release_month, generation_run_id,
                        data_quality_level, output_path, status
                    ) VALUES
                        (1, 'baseline', 'historical_baseline', NULL, 1, 'none', '/tmp/baseline', 'succeeded'),
                        (2, 'incremental', 'monthly_incremental', '2025-02-01', 1, 'none', '/tmp/incremental', 'succeeded')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO student_dataset_release_files (
                        id, release_id, table_name, file_path
                    ) VALUES
                        (1, 1, 'players', '/tmp/baseline/players.parquet')
                    """
                )
            )

        result = _migrate_engine(engine)

        assert result.dialect == "sqlite"
        assert result.inspected_release_count == 2
        assert result.updated_release_count == 1

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, release_type
                    FROM student_dataset_releases
                    ORDER BY id
                    """
                )
            ).fetchall()
            assert rows == [
                (1, "initial_snapshot"),
                (2, "monthly_incremental"),
            ]
            foreign_key_row = connection.execute(
                text(
                    """
                    SELECT release_id
                    FROM student_dataset_release_files
                    WHERE id = 1
                    """
                )
            ).scalar_one()
            assert foreign_key_row == 1
    finally:
        engine.dispose()
