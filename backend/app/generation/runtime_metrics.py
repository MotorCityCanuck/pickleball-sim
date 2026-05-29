"""Helpers for recording generation runtime instrumentation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from time import perf_counter
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.models import GenerationRuntimeMetric


logger = logging.getLogger("uvicorn.error")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RuntimeMetricRecorder:
    """Persist low-volume subphase timings for generation diagnostics."""

    def __init__(
        self,
        *,
        session: Session,
        generation_run_id: int,
        batch_id: int | None = None,
        stage_name: str,
    ) -> None:
        self.session = session
        self.generation_run_id = generation_run_id
        self.batch_id = batch_id
        self.stage_name = stage_name
        GenerationRuntimeMetric.__table__.create(
            bind=session.get_bind(),
            checkfirst=True,
        )

    @contextmanager
    def measure(
        self,
        subphase_name: str,
        *,
        input_count: int | None = None,
        output_count: int | None = None,
        attempt_count: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Record one completed or failed subphase after the wrapped block exits."""
        started_at = _utc_now()
        started_perf = perf_counter()
        mutable_metrics: dict[str, Any] = {
            "input_count": input_count,
            "output_count": output_count,
            "attempt_count": attempt_count,
            "metadata": dict(metadata or {}),
        }
        event_type = "completed"
        try:
            yield mutable_metrics
        except Exception as exc:
            event_type = "failed"
            mutable_metrics["metadata"]["error"] = str(exc)
            raise
        finally:
            completed_at = _utc_now()
            elapsed_ms = int((perf_counter() - started_perf) * 1000)
            input_count_value = _optional_int(mutable_metrics.get("input_count"))
            output_count_value = _optional_int(mutable_metrics.get("output_count"))
            attempt_count_value = _optional_int(mutable_metrics.get("attempt_count"))
            elapsed_ms = max(elapsed_ms, 0)
            self.session.add(
                GenerationRuntimeMetric(
                    generation_run_id=self.generation_run_id,
                    batch_id=self.batch_id,
                    stage_name=self.stage_name,
                    subphase_name=subphase_name,
                    event_type=event_type,
                    started_at=started_at,
                    completed_at=completed_at,
                    elapsed_ms=elapsed_ms,
                    input_count=input_count_value,
                    output_count=output_count_value,
                    attempt_count=attempt_count_value,
                    metadata_json=_json_ready(mutable_metrics.get("metadata") or {}),
                )
            )
            _log_runtime_metric(
                event_type=event_type,
                generation_run_id=self.generation_run_id,
                batch_id=self.batch_id,
                stage_name=self.stage_name,
                subphase_name=subphase_name,
                elapsed_ms=elapsed_ms,
                input_count=input_count_value,
                output_count=output_count_value,
                attempt_count=attempt_count_value,
            )

    def flush(self) -> None:
        """Flush pending metric rows after instrumented generated rows are flushed."""
        self.session.flush()


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _log_runtime_metric(
    *,
    event_type: str,
    generation_run_id: int,
    batch_id: int | None,
    stage_name: str,
    subphase_name: str,
    elapsed_ms: int,
    input_count: int | None,
    output_count: int | None,
    attempt_count: int | None,
) -> None:
    log_fn = logger.warning if event_type == "failed" else logger.info
    log_fn(
        "%s Generation runtime phase %s run_id=%s batch_id=%s stage=%s "
        "subphase=%s elapsed_ms=%s input_count=%s output_count=%s attempt_count=%s",
        _timestamp_label(),
        event_type,
        generation_run_id,
        batch_id,
        stage_name,
        subphase_name,
        elapsed_ms,
        input_count,
        output_count,
        attempt_count,
    )


def _timestamp_label() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
