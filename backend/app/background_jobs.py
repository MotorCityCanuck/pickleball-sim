"""Minimal background job runner for local control-panel workloads."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable


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
            return self._executor.submit(fn, *args, **kwargs)

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


_default_runner: BackgroundJobRunner | None = BackgroundJobRunner()


def get_default_background_job_runner() -> BackgroundJobRunner:
    """Return the process-wide local background runner."""
    global _default_runner
    if _default_runner is None or _default_runner.closed:
        _default_runner = BackgroundJobRunner()
    return _default_runner
