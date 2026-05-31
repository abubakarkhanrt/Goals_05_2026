"""Application metrics exported for Prometheus / Grafana."""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

logger = logging.getLogger(__name__)

_metrics_started = False
_cpu_sampler_started = False

TASK_DURATION = None
TASK_TOTAL = None
TASK_ERRORS = None
ROUTE_TOTAL = None
LLM_FALLBACK_TOTAL = None
CACHE_IO_DURATION = None
DB_DURATION = None
PROCESS_MEMORY = None
PROCESS_CPU = None
HOST_CPU = None
HOST_MEMORY_USED = None
HOST_MEMORY_TOTAL = None


def metrics_enabled() -> bool:
    return os.environ.get("AGENT_METRICS_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def metrics_port() -> int:
    try:
        return max(1024, int(os.environ.get("AGENT_METRICS_PORT", "9464")))
    except ValueError:
        return 9464


def _ensure_metrics() -> None:
    global TASK_DURATION, TASK_TOTAL, TASK_ERRORS, ROUTE_TOTAL, LLM_FALLBACK_TOTAL, CACHE_IO_DURATION
    global DB_DURATION, PROCESS_MEMORY, PROCESS_CPU, HOST_CPU, HOST_MEMORY_USED, HOST_MEMORY_TOTAL
    if TASK_DURATION is not None:
        return

    from prometheus_client import Counter, Gauge, Histogram

    TASK_DURATION = Histogram(
        "agent_task_duration_seconds",
        "Wall time for a workflow task or tool call",
        labelnames=("task", "status"),
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
    )
    TASK_TOTAL = Counter(
        "agent_task_total",
        "Workflow task invocations",
        labelnames=("task", "status"),
    )
    TASK_ERRORS = Counter(
        "agent_task_errors_total",
        "Workflow task failures",
        labelnames=("task", "error_type"),
    )
    ROUTE_TOTAL = Counter(
        "agent_route_total",
        "Input gate routing decisions",
        labelnames=("route",),
    )
    LLM_FALLBACK_TOTAL = Counter(
        "agent_llm_fallback_total",
        "Times the agent fell back to rule-based scoring or Q&A",
        labelnames=("operation", "reason"),
    )
    CACHE_IO_DURATION = Histogram(
        "agent_cache_io_seconds",
        "PDF render and session PNG cache file I/O",
        labelnames=("operation", "status"),
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )
    DB_DURATION = Histogram(
        "agent_db_seconds",
        "SQLite operation latency",
        labelnames=("operation", "status"),
        buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
    )
    PROCESS_MEMORY = Gauge(
        "agent_process_memory_bytes",
        "Resident memory (RSS) of the agent Python process",
    )
    PROCESS_CPU = Gauge(
        "agent_process_cpu_percent",
        "CPU usage percent of the agent Python process (0-100), sampled every 5s",
    )
    HOST_CPU = Gauge(
        "agent_host_cpu_percent",
        "CPU usage percent for the whole machine (0-100), sampled every 5s",
    )
    HOST_MEMORY_USED = Gauge(
        "agent_host_memory_used_bytes",
        "Used physical memory on the host",
    )
    HOST_MEMORY_TOTAL = Gauge(
        "agent_host_memory_total_bytes",
        "Total physical memory on the host",
    )


def _start_cpu_sampler() -> None:
    """Background sampler — psutil cpu_percent(0) is always 0 on isolated scrapes."""
    global _cpu_sampler_started
    if _cpu_sampler_started:
        return
    _cpu_sampler_started = True

    import threading

    def _loop() -> None:
        import psutil

        proc = psutil.Process(os.getpid())
        proc.cpu_percent(interval=None)  # prime process CPU
        psutil.cpu_percent(interval=None)  # prime host CPU
        while True:
            time.sleep(5)
            if not metrics_enabled() or PROCESS_CPU is None or PROCESS_MEMORY is None:
                continue
            try:
                PROCESS_CPU.set(proc.cpu_percent(interval=None))
                PROCESS_MEMORY.set(proc.memory_info().rss)
                if HOST_CPU is not None:
                    HOST_CPU.set(psutil.cpu_percent(interval=None))
                vm = psutil.virtual_memory()
                if HOST_MEMORY_USED is not None:
                    HOST_MEMORY_USED.set(vm.used)
                if HOST_MEMORY_TOTAL is not None:
                    HOST_MEMORY_TOTAL.set(vm.total)
            except Exception:
                pass

    threading.Thread(target=_loop, name="agent-cpu-sampler", daemon=True).start()


def start_metrics_server() -> None:
    """Start Prometheus /metrics HTTP server once per process."""
    global _metrics_started
    if _metrics_started or not metrics_enabled():
        return
    _ensure_metrics()
    _start_cpu_sampler()
    from prometheus_client import start_http_server

    port = metrics_port()
    start_http_server(port)
    _metrics_started = True
    logger.info("Prometheus metrics listening on http://127.0.0.1:%s/metrics", port)


def record_route(route: str) -> None:
    if not metrics_enabled():
        return
    _ensure_metrics()
    ROUTE_TOTAL.labels(route=route or "unknown").inc()


def record_llm_fallback(operation: str, reason: str) -> None:
    if not metrics_enabled():
        return
    _ensure_metrics()
    LLM_FALLBACK_TOTAL.labels(operation=operation, reason=reason).inc()


@contextmanager
def track_task(task: str) -> Iterator[None]:
    """Time a synchronous workflow task and record success/error counters."""
    if not metrics_enabled():
        yield
        return

    _ensure_metrics()
    status = "success"
    started = time.perf_counter()
    try:
        yield
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:
        status = "error"
        TASK_ERRORS.labels(task=task, error_type=type(exc).__name__).inc()
        raise
    finally:
        elapsed = time.perf_counter() - started
        TASK_DURATION.labels(task=task, status=status).observe(elapsed)
        TASK_TOTAL.labels(task=task, status=status).inc()


@asynccontextmanager
async def track_task_async(task: str) -> AsyncIterator[None]:
    """Time an async workflow task and record success/error counters."""
    if not metrics_enabled():
        yield
        return

    _ensure_metrics()
    status = "success"
    started = time.perf_counter()
    try:
        yield
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as exc:
        status = "error"
        TASK_ERRORS.labels(task=task, error_type=type(exc).__name__).inc()
        raise
    finally:
        elapsed = time.perf_counter() - started
        TASK_DURATION.labels(task=task, status=status).observe(elapsed)
        TASK_TOTAL.labels(task=task, status=status).inc()


@contextmanager
def track_cache_io(operation: str) -> Iterator[None]:
    """Time file/cache operations (PDF render, PNG write)."""
    if not metrics_enabled():
        yield
        return

    _ensure_metrics()
    status = "success"
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        status = "error"
        TASK_ERRORS.labels(task=f"cache_{operation}", error_type=type(exc).__name__).inc()
        raise
    finally:
        elapsed = time.perf_counter() - started
        CACHE_IO_DURATION.labels(operation=operation, status=status).observe(elapsed)


@contextmanager
def track_db(operation: str) -> Iterator[None]:
    """Time SQLite operations for DB latency metrics."""
    if not metrics_enabled():
        yield
        return

    _ensure_metrics()
    status = "success"
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        status = "error"
        TASK_ERRORS.labels(task=f"db_{operation}", error_type=type(exc).__name__).inc()
        raise
    finally:
        elapsed = time.perf_counter() - started
        DB_DURATION.labels(operation=operation, status=status).observe(elapsed)
