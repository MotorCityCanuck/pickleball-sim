"""Run durable background jobs outside the web server process."""
from __future__ import annotations

import argparse
from contextlib import AbstractContextManager
from dataclasses import dataclass
import logging
from pathlib import Path
import sys
from threading import Event, Thread
import time
from typing import Callable, Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import session_scope  # noqa: E402
from app.generation.durable_worker import (  # noqa: E402
    REALISM_AUDIT_JOB_TYPE,
    WorkerIdentity,
    generate_worker_identity,
    heartbeat_worker,
    register_worker,
    release_job_lease,
    renew_job_lease,
    utc_now,
    write_job_event,
)
from app.generation.realism_audit_job_handler import RealismAuditJobHandler  # noqa: E402
from app.models import BackgroundJobLease  # noqa: E402


logger = logging.getLogger("pickleball.background_worker")
SUPPORTED_QUEUES = frozenset({REALISM_AUDIT_JOB_TYPE})

SessionContextFactory = Callable[[], AbstractContextManager]
JobHandler = Callable[[int], None]


@dataclass(frozen=True)
class WorkerConfig:
    """Runtime settings for the durable worker loop."""

    queues: tuple[str, ...]
    once: bool
    poll_interval_seconds: float
    lease_seconds: float
    heartbeat_seconds: float


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run durable background workers for queued ops jobs."
    )
    parser.add_argument(
        "--queues",
        nargs="+",
        default=[REALISM_AUDIT_JOB_TYPE],
        help="Queue names to poll. Currently supported: realism_audit.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll once and exit, including when no eligible job exists.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="Sleep duration between empty polls.",
    )
    parser.add_argument(
        "--lease-seconds",
        type=float,
        default=900.0,
        help="Lease duration for claimed jobs.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=30.0,
        help="Worker heartbeat and lease-renewal interval during active work.",
    )
    return parser.parse_args(argv)


def config_from_args(args: argparse.Namespace) -> WorkerConfig:
    """Validate parsed arguments and build runtime config."""
    queues = _normalize_queues(args.queues)
    if args.poll_interval_seconds <= 0:
        raise ValueError("--poll-interval-seconds must be greater than zero.")
    if args.lease_seconds <= 0:
        raise ValueError("--lease-seconds must be greater than zero.")
    if args.heartbeat_seconds <= 0:
        raise ValueError("--heartbeat-seconds must be greater than zero.")
    if args.heartbeat_seconds >= args.lease_seconds:
        raise ValueError("--heartbeat-seconds must be less than --lease-seconds.")
    return WorkerConfig(
        queues=queues,
        once=args.once,
        poll_interval_seconds=args.poll_interval_seconds,
        lease_seconds=args.lease_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
    )


def run_worker(
    config: WorkerConfig,
    *,
    session_factory: SessionContextFactory = session_scope,
    identity: WorkerIdentity | None = None,
    realism_audit_handler: JobHandler | None = None,
) -> int:
    """Run the durable worker loop."""
    worker_identity = identity or generate_worker_identity("background_worker")
    handler = realism_audit_handler or _run_realism_audit_handler
    logger.info(
        "Starting background worker worker_id=%s queues=%s once=%s",
        worker_identity.worker_id,
        ",".join(config.queues),
        config.once,
    )
    with session_factory() as session:
        register_worker(
            session,
            worker_identity,
            metadata={
                "queues": list(config.queues),
                "poll_interval_seconds": config.poll_interval_seconds,
                "lease_seconds": config.lease_seconds,
                "heartbeat_seconds": config.heartbeat_seconds,
            },
        )
    logger.info("Registered worker worker_id=%s", worker_identity.worker_id)

    while True:
        lease = _claim_next_job(
            config=config,
            worker_id=worker_identity.worker_id,
            session_factory=session_factory,
        )
        if lease is not None:
            _run_claimed_job(
                lease=lease,
                worker_id=worker_identity.worker_id,
                config=config,
                session_factory=session_factory,
                realism_audit_handler=handler,
            )
            if config.once:
                logger.info("Exiting after one claimed job because --once was set.")
                return 0
            continue

        logger.info("No eligible job found for queues=%s.", ",".join(config.queues))
        if config.once:
            logger.info("Exiting cleanly because --once was set.")
            return 0
        time.sleep(config.poll_interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    _configure_logging()
    try:
        config = config_from_args(parse_args(argv))
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    try:
        return run_worker(config)
    except KeyboardInterrupt:
        logger.info("Worker interrupted; exiting.")
        return 0
    except Exception:
        logger.exception("Worker exited after an unrecoverable error.")
        return 1


class LeaseHeartbeat:
    """Renew worker heartbeat and job lease while a handler is active."""

    def __init__(
        self,
        *,
        session_factory: SessionContextFactory,
        worker_id: str,
        job_status_id: int,
        lease_token: str,
        heartbeat_seconds: float,
        lease_seconds: float,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.job_status_id = job_status_id
        self.lease_token = lease_token
        self.heartbeat_seconds = heartbeat_seconds
        self.lease_seconds = lease_seconds
        self._stop_event = Event()
        self._thread = Thread(
            target=self._run,
            name=f"lease-heartbeat-{job_status_id}",
            daemon=True,
        )

    def __enter__(self) -> "LeaseHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop_event.set()
        self._thread.join(timeout=max(1.0, self.heartbeat_seconds))

    def _run(self) -> None:
        while not self._stop_event.wait(self.heartbeat_seconds):
            try:
                with self.session_factory() as session:
                    heartbeat_worker(session, self.worker_id, now=utc_now())
                    renewed = renew_job_lease(
                        session,
                        job_status_id=self.job_status_id,
                        worker_id=self.worker_id,
                        lease_token=self.lease_token,
                        lease_duration=_seconds_to_timedelta(self.lease_seconds),
                    )
                    if renewed is None:
                        logger.error(
                            "Failed to renew lease job_status_id=%s worker_id=%s",
                            self.job_status_id,
                            self.worker_id,
                        )
                        self._stop_event.set()
                        return
                    logger.debug(
                        "Renewed lease job_status_id=%s worker_id=%s expires_at=%s",
                        self.job_status_id,
                        self.worker_id,
                        renewed.lease_expires_at,
                    )
            except Exception:
                logger.exception(
                    "Heartbeat renewal failed job_status_id=%s worker_id=%s",
                    self.job_status_id,
                    self.worker_id,
                )
                self._stop_event.set()
                return


def _claim_next_job(
    *,
    config: WorkerConfig,
    worker_id: str,
    session_factory: SessionContextFactory,
) -> BackgroundJobLease | None:
    with session_factory() as session:
        heartbeat_worker(session, worker_id)
        for queue in config.queues:
            if queue != REALISM_AUDIT_JOB_TYPE:
                continue
            lease = RealismAuditJobHandler(session).claim_next_job(
                worker_id=worker_id,
                lease_duration=_seconds_to_timedelta(config.lease_seconds),
            )
            if lease is not None:
                job_status_id = lease.job_status_id
                lease_token = lease.lease_token
                attempt_count = lease.attempt_count
                lease_expires_at = lease.lease_expires_at
                logger.info(
                    "Claimed job queue=%s job_status_id=%s attempt=%s expires_at=%s",
                    queue,
                    job_status_id,
                    attempt_count,
                    lease_expires_at,
                )
                return BackgroundJobLease(
                    job_status_id=job_status_id,
                    worker_id=worker_id,
                    lease_token=lease_token,
                    lease_expires_at=lease_expires_at,
                    attempt_count=attempt_count,
                )
    return None


def _run_claimed_job(
    *,
    lease: BackgroundJobLease,
    worker_id: str,
    config: WorkerConfig,
    session_factory: SessionContextFactory,
    realism_audit_handler: JobHandler,
) -> None:
    job_status_id = int(lease.job_status_id)
    lease_token = str(lease.lease_token)
    logger.info("Starting job job_status_id=%s worker_id=%s", job_status_id, worker_id)
    with session_factory() as session:
        write_job_event(
            session,
            job_status_id=job_status_id,
            event_type="job_started",
            worker_id=worker_id,
            message=f"Worker {worker_id} started job {job_status_id}.",
        )

    try:
        with LeaseHeartbeat(
            session_factory=session_factory,
            worker_id=worker_id,
            job_status_id=job_status_id,
            lease_token=lease_token,
            heartbeat_seconds=config.heartbeat_seconds,
            lease_seconds=config.lease_seconds,
        ):
            realism_audit_handler(job_status_id)
    except Exception as exc:
        logger.exception("Job failed job_status_id=%s worker_id=%s", job_status_id, worker_id)
        with session_factory() as session:
            write_job_event(
                session,
                job_status_id=job_status_id,
                event_type="job_failed",
                worker_id=worker_id,
                message=str(exc),
            )
            release_job_lease(
                session,
                job_status_id=job_status_id,
                worker_id=worker_id,
                lease_token=lease_token,
                final_status="failed",
            )
        return

    with session_factory() as session:
        write_job_event(
            session,
            job_status_id=job_status_id,
            event_type="job_succeeded",
            worker_id=worker_id,
            message=f"Worker {worker_id} completed job {job_status_id}.",
        )
        release_job_lease(
            session,
            job_status_id=job_status_id,
            worker_id=worker_id,
            lease_token=lease_token,
            final_status="succeeded",
        )
    logger.info("Completed job job_status_id=%s worker_id=%s", job_status_id, worker_id)


def _run_realism_audit_handler(job_status_id: int) -> None:
    with session_scope() as session:
        RealismAuditJobHandler(session).run_claimed_job(job_status_id=job_status_id)


def _normalize_queues(raw_queues: Sequence[str]) -> tuple[str, ...]:
    queues = tuple(
        queue.strip()
        for raw_queue in raw_queues
        for queue in raw_queue.split(",")
        if queue.strip()
    )
    if not queues:
        raise ValueError("At least one queue must be provided.")
    unsupported = sorted(set(queues) - SUPPORTED_QUEUES)
    if unsupported:
        raise ValueError(
            "Unsupported queue(s): "
            f"{', '.join(unsupported)}. Supported queues: {', '.join(sorted(SUPPORTED_QUEUES))}."
        )
    return queues


def _seconds_to_timedelta(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


if __name__ == "__main__":
    raise SystemExit(main())
