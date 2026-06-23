"""Promotion and metadata persistence for validated student dataset releases."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import StudentDatasetRelease, StudentDatasetReleaseFile

from .writer import (
    MANIFEST_FILE_NAME,
    ReleaseProgressCallback,
    StagedStudentDatasetFamily,
    StagedStudentDatasetRelease,
    StudentDatasetBuildParameters,
)


class StudentDatasetPublishError(RuntimeError):
    """Raised when a validated staged release cannot be promoted."""


@dataclass(frozen=True)
class PublishedStudentDatasetRelease:
    """One promoted release folder and its database record."""

    release_id: int
    release_name: str
    release_type: str
    release_dir: Path
    manifest_path: Path
    file_count: int


@dataclass(frozen=True)
class PublishedStudentDatasetFamily:
    """A promoted release family and its database records."""

    release_name: str
    final_root: Path
    releases: tuple[PublishedStudentDatasetRelease, ...]


def promote_staged_release_family(
    *,
    session: Session,
    staged_family: StagedStudentDatasetFamily,
    build_parameters: StudentDatasetBuildParameters,
    progress_callback: ReleaseProgressCallback | None = None,
) -> PublishedStudentDatasetFamily:
    """Promote a validated staging folder and persist release/file metadata."""

    _validate_staged_family_for_promotion(staged_family)
    final_root = build_parameters.final_root or (
        build_parameters.output_root / staged_family.release_name
    )

    if final_root.exists():
        if not build_parameters.overwrite_existing:
            raise StudentDatasetPublishError(
                f"Final release folder already exists: {final_root}"
            )
        if not final_root.is_dir():
            raise StudentDatasetPublishError(
                f"Final release path exists but is not a directory: {final_root}"
            )
        shutil.rmtree(final_root)

    final_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged_family.staging_root), str(final_root))

    try:
        total_releases = len(staged_family.releases)
        published_releases_list: list[PublishedStudentDatasetRelease] = []
        for index, staged_release in enumerate(staged_family.releases, start=1):
            published_release = _persist_release_metadata(
                session=session,
                staged_release=staged_release,
                final_root=final_root,
                staging_root=staged_family.staging_root,
                build_parameters=build_parameters,
            )
            published_releases_list.append(published_release)
            if progress_callback is not None:
                progress_callback(
                    published_release.release_name,
                    index,
                    total_releases,
                )
        published_releases = tuple(published_releases_list)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return PublishedStudentDatasetFamily(
        release_name=staged_family.release_name,
        final_root=final_root,
        releases=published_releases,
    )


def _validate_staged_family_for_promotion(
    staged_family: StagedStudentDatasetFamily,
) -> None:
    if not staged_family.staging_root.is_dir():
        raise StudentDatasetPublishError(
            f"Staging folder does not exist: {staged_family.staging_root}"
        )
    for release in staged_family.releases:
        manifest_path = release.manifest_path
        if not manifest_path.is_file():
            raise StudentDatasetPublishError(
                f"Release manifest is missing: {manifest_path}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("validation_status") != "passed":
            raise StudentDatasetPublishError(
                f"Release is not validated for promotion: {manifest_path}"
            )


def _persist_release_metadata(
    *,
    session: Session,
    staged_release: StagedStudentDatasetRelease,
    final_root: Path,
    staging_root: Path,
    build_parameters: StudentDatasetBuildParameters,
) -> PublishedStudentDatasetRelease:
    final_release_dir = final_root / staged_release.release_dir.relative_to(staging_root)
    final_manifest_path = final_release_dir / MANIFEST_FILE_NAME
    manifest = json.loads(final_manifest_path.read_text(encoding="utf-8"))

    release = StudentDatasetRelease(
        release_name=staged_release.release_name,
        release_type=staged_release.release_type,
        release_month=_parse_optional_iso_date(
            manifest["release_month"]
            if "release_month" in manifest
            else manifest.get("snapshot_month")
        ),
        generation_run_id=build_parameters.generation_run_id,
        data_quality_level=build_parameters.data_quality_level,
        output_path=str(final_release_dir),
        status="succeeded",
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0),
        error_message=None,
    )
    session.add(release)
    session.flush()

    for file_manifest in staged_release.files:
        final_file_path = final_release_dir / file_manifest.file_name
        session.add(
            StudentDatasetReleaseFile(
                release_id=release.id,
                table_name=file_manifest.table_name,
                file_path=str(final_file_path),
                row_count=file_manifest.row_count,
                schema_hash=file_manifest.schema_hash,
                checksum=file_manifest.checksum,
            )
        )
    session.flush()

    return PublishedStudentDatasetRelease(
        release_id=int(release.id),
        release_name=staged_release.release_name,
        release_type=staged_release.release_type,
        release_dir=final_release_dir,
        manifest_path=final_manifest_path,
        file_count=len(staged_release.files),
    )


def _parse_optional_iso_date(value: str | None):
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()
