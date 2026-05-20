"""Minimal background job runner for local control-panel workloads."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
from threading import Lock
from typing import Any, Callable


logger = logging.getLogger("uvicorn.error")


class BackgroundJobRunner:
    """Submit local background work on a small thread pool."""

    def __init__(self, *, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pickleball-control",
        )
        self._lock = Lock()
        self._closed = False

    def submit(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        """Submit a unit of background work."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Background job runner is shut down.")
            logger.warning(
                "Submitting background job fn=%s args=%s kwargs=%s",
                getattr(fn, "__qualname__", repr(fn)),
                args,
                kwargs,
            )
            future = self._executor.submit(self._run_job, fn, args, kwargs)
            future.add_done_callback(self._log_background_exception)
            return future

    @property
    def closed(self) -> bool:
        """Return whether the runner has been shut down."""
        with self._lock:
            return self._closed

    def shutdown(self, *, wait: bool = False) -> None:
        """Stop accepting new work and tear down the pool."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._executor.shutdown(wait=wait, cancel_futures=False)

    @staticmethod
    def _log_background_exception(future: Future[Any]) -> None:
        """Log uncaught worker exceptions so they are visible in server logs."""
        exc = future.exception()
        if exc is not None:
            logger.exception("Background job failed.", exc_info=exc)

    @staticmethod
    def _run_job(
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Execute background work with explicit lifecycle logging."""
        logger.warning(
            "Starting background job fn=%s args=%s kwargs=%s",
            getattr(fn, "__qualname__", repr(fn)),
            args,
            kwargs,
        )
        result = fn(*args, **kwargs)
        logger.warning(
            "Completed background job fn=%s",
            getattr(fn, "__qualname__", repr(fn)),
        )
        return result


_default_runner: BackgroundJobRunner | None = None


def get_default_background_job_runner() -> BackgroundJobRunner:
    """Return the process-wide local background runner."""
    global _default_runner
    if _default_runner is None or _default_runner.closed:
        _default_runner = BackgroundJobRunner()
    return _default_runner
