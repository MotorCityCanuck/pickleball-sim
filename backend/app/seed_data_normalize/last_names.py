"""Normalize raw last names into production state/province probabilities."""
from __future__ import annotations

from sqlalchemy import Numeric, and_, cast, delete, func, select
from sqlalchemy.orm import Session

from app.models import LastName, RawLastName, RawStateProvBias, Region

from .base import SeedNormalizeResult, run_in_transaction


class LastNameNormalizer:
    """Promote raw country-level surnames into state/province last names."""

    dataset = "last_names"

    def normalize(
        self,
        *,
        replace_production: bool = False,
        session: Session | None = None,
    ) -> SeedNormalizeResult:
        """Replace production last-name rows from raw surnames and bias rules."""
        if not replace_production:
            raise ValueError("Last-name normalization requires --replace-production")

        def _normalize(active_session: Session) -> SeedNormalizeResult:
            rows_read = active_session.scalar(
                select(func.count()).select_from(RawLastName)
            )
            if not rows_read:
                raise ValueError("No raw_last_names rows are available to normalize")

            self._validate_bias_rules(active_session)

            target_states = (
                select(
                    Region.country_code.label("country_code"),
                    Region.state_province_code.label("state_province_code"),
                )
                .where(
                    Region.country_code.in_(("US", "CA")),
                    Region.state_province_code.is_not(None),
                )
                .distinct()
                .subquery()
            )

            target_state_count = active_session.scalar(
                select(func.count()).select_from(target_states)
            )
            if not target_state_count:
                raise ValueError("No production regions are available for last-name scope")

            countries = list(
                active_session.scalars(
                    select(target_states.c.country_code).distinct()
                )
            )
            delete_result = active_session.execute(
                delete(LastName).where(LastName.country_code.in_(countries))
            )

            raw_names = (
                select(
                    RawLastName.country_code.label("country_code"),
                    RawLastName.last_name.label("last_name"),
                    func.sum(RawLastName.frequency_count).label("frequency_count"),
                    func.min(RawLastName.source_dataset).label("source_dataset"),
                )
                .group_by(
                    RawLastName.country_code,
                    RawLastName.last_name,
                )
                .subquery()
            )

            biases = (
                select(
                    RawStateProvBias.country_code.label("country_code"),
                    RawStateProvBias.state_province_code.label("state_province_code"),
                    RawStateProvBias.last_name.label("last_name"),
                    RawStateProvBias.bias_multiplier.label("bias_multiplier"),
                )
                .subquery()
            )

            applied_bias = func.coalesce(
                biases.c.bias_multiplier,
                cast(1, Numeric(10, 4)),
            )
            adjusted_frequency = cast(
                cast(raw_names.c.frequency_count, Numeric(18, 4)) * applied_bias,
                Numeric(18, 4),
            )
            adjusted_total = func.sum(adjusted_frequency).over(
                partition_by=(
                    target_states.c.country_code,
                    target_states.c.state_province_code,
                )
            )
            normalized_probability = cast(
                adjusted_frequency / adjusted_total,
                Numeric(12, 8),
            )

            insert_statement = LastName.__table__.insert().from_select(
                [
                    "country_code",
                    "state_province_code",
                    "last_name",
                    "frequency_count",
                    "bias_multiplier",
                    "adjusted_frequency_count",
                    "normalized_probability",
                    "source_dataset",
                ],
                select(
                    target_states.c.country_code,
                    target_states.c.state_province_code,
                    raw_names.c.last_name,
                    raw_names.c.frequency_count,
                    applied_bias,
                    adjusted_frequency,
                    normalized_probability,
                    raw_names.c.source_dataset,
                )
                .select_from(
                    target_states.join(
                        raw_names,
                        target_states.c.country_code == raw_names.c.country_code,
                    ).outerjoin(
                        biases,
                        and_(
                            biases.c.country_code == target_states.c.country_code,
                            biases.c.state_province_code
                            == target_states.c.state_province_code,
                            biases.c.last_name == raw_names.c.last_name,
                        ),
                    )
                ),
            )
            insert_result = active_session.execute(insert_statement)

            return SeedNormalizeResult(
                dataset=self.dataset,
                status="completed",
                rows_read=rows_read,
                rows_deleted=delete_result.rowcount or 0,
                rows_loaded=insert_result.rowcount or 0,
            )

        return run_in_transaction(_normalize, session=session)

    def _validate_bias_rules(self, session: Session) -> None:
        duplicate_biases = list(
            session.execute(
                select(
                    RawStateProvBias.country_code,
                    RawStateProvBias.state_province_code,
                    RawStateProvBias.last_name,
                    func.count().label("rule_count"),
                )
                .group_by(
                    RawStateProvBias.country_code,
                    RawStateProvBias.state_province_code,
                    RawStateProvBias.last_name,
                )
                .having(func.count() > 1)
                .limit(5)
            )
        )
        if duplicate_biases:
            sample = ", ".join(
                f"{country}/{state}/{last_name}"
                for country, state, last_name, _ in duplicate_biases
            )
            raise ValueError(f"Duplicate state/province last-name bias rules: {sample}")

        missing_surnames = list(
            session.execute(
                select(
                    RawStateProvBias.country_code,
                    RawStateProvBias.state_province_code,
                    RawStateProvBias.last_name,
                )
                .outerjoin(
                    RawLastName,
                    and_(
                        RawLastName.country_code == RawStateProvBias.country_code,
                        RawLastName.last_name == RawStateProvBias.last_name,
                    ),
                )
                .where(RawLastName.id.is_(None))
                .limit(5)
            )
        )
        if missing_surnames:
            sample = ", ".join(
                f"{country}/{state}/{last_name}"
                for country, state, last_name in missing_surnames
            )
            raise ValueError(f"Bias rules reference missing raw last names: {sample}")
