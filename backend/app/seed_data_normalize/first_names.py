"""Normalize raw first names into production first-name probabilities."""
from __future__ import annotations

from sqlalchemy import Numeric, and_, cast, delete, func, select
from sqlalchemy.orm import Session

from app.models import FirstName, RawFirstName

from .base import SeedNormalizeResult, run_in_transaction


class FirstNameNormalizer:
    """Promote raw first-name frequency rows into production first names."""

    dataset = "first_names"

    def normalize(
        self,
        *,
        replace_production: bool = False,
        session: Session | None = None,
    ) -> SeedNormalizeResult:
        """Replace production first-name rows from raw first-name staging rows."""
        if not replace_production:
            raise ValueError("First-name normalization requires --replace-production")

        def _normalize(active_session: Session) -> SeedNormalizeResult:
            rows_read = active_session.scalar(
                select(func.count()).select_from(RawFirstName)
            )
            if not rows_read:
                raise ValueError("No raw_first_names rows are available to normalize")

            countries = list(
                active_session.scalars(
                    select(RawFirstName.country_code).distinct()
                )
            )
            delete_result = active_session.execute(
                delete(FirstName).where(FirstName.country_code.in_(countries))
            )

            state_chunks = list(
                active_session.execute(
                    select(
                        RawFirstName.country_code,
                        RawFirstName.state_province_code,
                    )
                    .distinct()
                    .order_by(
                        RawFirstName.country_code.asc(),
                        RawFirstName.state_province_code.asc(),
                    )
                )
            )
            rows_loaded = 0
            for country_code, state_province_code in state_chunks:
                rows_loaded += self._normalize_state_chunk(
                    active_session,
                    country_code=country_code,
                    state_province_code=state_province_code,
                )

            return SeedNormalizeResult(
                dataset=self.dataset,
                status="completed",
                rows_read=rows_read,
                rows_deleted=delete_result.rowcount or 0,
                rows_loaded=rows_loaded,
            )

        return run_in_transaction(_normalize, session=session)

    def _normalize_state_chunk(
        self,
        session: Session,
        *,
        country_code: str,
        state_province_code: str,
    ) -> int:
        grouped = (
            select(
                RawFirstName.country_code.label("country_code"),
                RawFirstName.state_province_code.label("state_province_code"),
                RawFirstName.birth_year.label("birth_year"),
                RawFirstName.gender.label("gender"),
                RawFirstName.first_name.label("first_name"),
                func.sum(RawFirstName.frequency_count).label("frequency_count"),
                func.min(RawFirstName.source_dataset).label("source_dataset"),
            )
            .where(
                and_(
                    RawFirstName.country_code == country_code,
                    RawFirstName.state_province_code == state_province_code,
                )
            )
            .group_by(
                RawFirstName.country_code,
                RawFirstName.state_province_code,
                RawFirstName.birth_year,
                RawFirstName.gender,
                RawFirstName.first_name,
            )
            .subquery()
        )

        cohort_total = func.sum(grouped.c.frequency_count).over(
            partition_by=(
                grouped.c.country_code,
                grouped.c.state_province_code,
                grouped.c.birth_year,
                grouped.c.gender,
            )
        )
        normalized_probability = cast(
            cast(grouped.c.frequency_count, Numeric(20, 8))
            / cast(cohort_total, Numeric(20, 8)),
            Numeric(12, 8),
        )

        insert_statement = FirstName.__table__.insert().from_select(
            [
                "country_code",
                "state_province_code",
                "birth_year",
                "gender",
                "first_name",
                "frequency_count",
                "normalized_probability",
                "source_dataset",
            ],
            select(
                grouped.c.country_code,
                grouped.c.state_province_code,
                grouped.c.birth_year,
                grouped.c.gender,
                grouped.c.first_name,
                grouped.c.frequency_count,
                normalized_probability,
                grouped.c.source_dataset,
            ),
        )
        insert_result = session.execute(insert_statement)
        session.flush()
        return insert_result.rowcount or 0
