"""Bounded fixed producer invocation with exact owned-process cleanup."""

from __future__ import annotations

from itertools import count
import multiprocessing
from multiprocessing.connection import Connection
import os
from pathlib import Path
import secrets
import signal
from threading import Lock
import time
from typing import Protocol

from .models import (
    VisualEvaluationInput,
    VisualInvocationResult,
    VisualInvocationStatus,
    VisualProducerResultBatch,
)
from .registry import RegisteredVisualProducer


_RUN_ENVIRONMENT_KEY = "AYYO_VISUAL_EVALUATION_RUN_ID"
_RUN_COUNTER = count(1)
_RUN_LOCK = Lock()
_SETUP_TIMEOUT_SECONDS = 2.0
_CLEANUP_GRACE_SECONDS = 0.2


class VisualProducerInvoker(Protocol):
    def invoke(
        self,
        registration: RegisteredVisualProducer,
        evaluation_input: VisualEvaluationInput,
    ) -> VisualInvocationResult: ...


def _child_main(
    connection: Connection,
    registration: RegisteredVisualProducer,
    evaluation_input: VisualEvaluationInput,
    run_id: str,
) -> None:
    try:
        os.setsid()
        os.environ[_RUN_ENVIRONMENT_KEY] = run_id
        connection.send(("ready", os.getpid()))
        command = connection.recv()
        if command != "invoke":
            connection.send(("failed", None))
            return
        try:
            batch = registration.adapter.produce(evaluation_input)
            if type(batch) is not VisualProducerResultBatch:
                connection.send(("failed", None))
                return
            connection.send(("completed", batch))
        except BaseException:
            # Exception text is intentionally not serialized into reports/logs.
            connection.send(("failed", None))
    except BaseException:
        try:
            connection.send(("failed", None))
        except BaseException:
            pass
    finally:
        connection.close()


def _owned_pids(run_id: str) -> tuple[int, ...]:
    expected = f"{_RUN_ENVIRONMENT_KEY}={run_id}".encode("ascii")
    owned: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return ()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            environment = (entry / "environ").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if expected in environment:
            owned.append(int(entry.name))
    return tuple(sorted(set(owned)))


def _signal_exact(pids: tuple[int, ...], signal_number: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal_number)
        except (ProcessLookupError, PermissionError):
            continue


def _cleanup_owned(
    process: multiprocessing.Process,
    run_id: str,
) -> tuple[int, ...]:
    # The direct child is always exact ownership even if setup failed before it
    # installed the inherited marker. Descendants are selected only by marker.
    if process.is_alive():
        process.terminate()
    _signal_exact(_owned_pids(run_id), signal.SIGTERM)
    process.join(_CLEANUP_GRACE_SECONDS)
    deadline = time.monotonic() + _CLEANUP_GRACE_SECONDS
    survivors = _owned_pids(run_id)
    while survivors and time.monotonic() < deadline:
        _signal_exact(survivors, signal.SIGTERM)
        time.sleep(0.005)
        survivors = _owned_pids(run_id)
    if process.is_alive():
        process.kill()
    if survivors:
        _signal_exact(survivors, signal.SIGKILL)
    process.join(_CLEANUP_GRACE_SECONDS)
    deadline = time.monotonic() + _CLEANUP_GRACE_SECONDS
    survivors = _owned_pids(run_id)
    while survivors and time.monotonic() < deadline:
        _signal_exact(survivors, signal.SIGKILL)
        time.sleep(0.005)
        survivors = _owned_pids(run_id)
    return tuple(sorted(set(survivors)))


class OwnedProcessVisualProducerInvoker:
    """Invoke one fixed registration in an owned Linux process session.

    The child receives a unique environment marker after entering a new
    session. Timeout cleanup targets only the direct child and marker-bearing
    descendants; unrelated processes are never selected by name.
    """

    __slots__ = ()

    def invoke(
        self,
        registration: RegisteredVisualProducer,
        evaluation_input: VisualEvaluationInput,
    ) -> VisualInvocationResult:
        if type(registration) is not RegisteredVisualProducer:
            raise TypeError("invocation registration must be typed")
        if type(evaluation_input) is not VisualEvaluationInput:
            raise TypeError("invocation input must be typed")
        with _RUN_LOCK:
            sequence = next(_RUN_COUNTER)
        run_id = (
            f"visual-evaluation-{os.getpid()}-{sequence}-"
            f"{secrets.token_hex(16)}"
        )
        context = multiprocessing.get_context("fork")
        parent_connection, child_connection = context.Pipe(duplex=True)
        process = context.Process(
            target=_child_main,
            args=(child_connection, registration, evaluation_input, run_id),
            name=f"ayyo-visual-evaluation-{sequence}",
        )
        process.daemon = False
        started = time.monotonic_ns()
        process.start()
        child_connection.close()
        try:
            if not parent_connection.poll(_SETUP_TIMEOUT_SECONDS):
                elapsed = time.monotonic_ns() - started
                survivors = _cleanup_owned(process, run_id)
                return VisualInvocationResult(
                    status=(
                        VisualInvocationStatus.CLEANUP_FAILED
                        if survivors
                        else VisualInvocationStatus.PRODUCER_FAILED
                    ),
                    latency_ns=elapsed,
                    batch=None,
                    owned_survivor_pids=survivors,
                )
            ready = parent_connection.recv()
            if (
                type(ready) is not tuple
                or len(ready) != 2
                or ready[0] != "ready"
                or ready[1] != process.pid
            ):
                elapsed = time.monotonic_ns() - started
                survivors = _cleanup_owned(process, run_id)
                return VisualInvocationResult(
                    status=(
                        VisualInvocationStatus.CLEANUP_FAILED
                        if survivors
                        else VisualInvocationStatus.PRODUCER_FAILED
                    ),
                    latency_ns=elapsed,
                    batch=None,
                    owned_survivor_pids=survivors,
                )
            invocation_started = time.monotonic_ns()
            parent_connection.send("invoke")
            timeout_seconds = registration.manifest.resources.timeout_ns / 1_000_000_000
            if not parent_connection.poll(timeout_seconds):
                elapsed = time.monotonic_ns() - invocation_started
                survivors = _cleanup_owned(process, run_id)
                return VisualInvocationResult(
                    status=(
                        VisualInvocationStatus.CLEANUP_FAILED
                        if survivors
                        else VisualInvocationStatus.TIMED_OUT
                    ),
                    latency_ns=elapsed,
                    batch=None,
                    owned_survivor_pids=survivors,
                )
            message = parent_connection.recv()
            elapsed = time.monotonic_ns() - invocation_started
            process.join(_CLEANUP_GRACE_SECONDS)
            survivors = (
                _cleanup_owned(process, run_id)
                if process.is_alive() or _owned_pids(run_id)
                else ()
            )
            if survivors:
                return VisualInvocationResult(
                    status=VisualInvocationStatus.CLEANUP_FAILED,
                    latency_ns=elapsed,
                    batch=None,
                    owned_survivor_pids=survivors,
                )
            if (
                type(message) is tuple
                and len(message) == 2
                and message[0] == "completed"
                and type(message[1]) is VisualProducerResultBatch
            ):
                return VisualInvocationResult(
                    status=VisualInvocationStatus.COMPLETED,
                    latency_ns=elapsed,
                    batch=message[1],
                )
            return VisualInvocationResult(
                status=VisualInvocationStatus.PRODUCER_FAILED,
                latency_ns=elapsed,
                batch=None,
            )
        except (EOFError, BrokenPipeError, OSError):
            elapsed = time.monotonic_ns() - started
            survivors = _cleanup_owned(process, run_id)
            return VisualInvocationResult(
                status=(
                    VisualInvocationStatus.CLEANUP_FAILED
                    if survivors
                    else VisualInvocationStatus.PRODUCER_FAILED
                ),
                latency_ns=elapsed,
                batch=None,
                owned_survivor_pids=survivors,
            )
        finally:
            parent_connection.close()
            if process.is_alive():
                _cleanup_owned(process, run_id)
            if not process.is_alive():
                process.close()


class DeterministicFixtureInvoker:
    """Synchronous test-only invoker with an explicit deterministic latency."""

    __slots__ = ("_latency_ns",)

    def __init__(self, latency_ns: int = 1_000_000) -> None:
        if type(latency_ns) is not int or latency_ns < 0:
            raise ValueError("fixture latency must be nonnegative integer nanoseconds")
        self._latency_ns = latency_ns

    def invoke(
        self,
        registration: RegisteredVisualProducer,
        evaluation_input: VisualEvaluationInput,
    ) -> VisualInvocationResult:
        if self._latency_ns > registration.manifest.resources.timeout_ns:
            return VisualInvocationResult(
                status=VisualInvocationStatus.TIMED_OUT,
                latency_ns=self._latency_ns,
                batch=None,
            )
        try:
            batch = registration.adapter.produce(evaluation_input)
        except BaseException:
            return VisualInvocationResult(
                status=VisualInvocationStatus.PRODUCER_FAILED,
                latency_ns=self._latency_ns,
                batch=None,
            )
        if type(batch) is not VisualProducerResultBatch:
            return VisualInvocationResult(
                status=VisualInvocationStatus.PRODUCER_FAILED,
                latency_ns=self._latency_ns,
                batch=None,
            )
        return VisualInvocationResult(
            status=VisualInvocationStatus.COMPLETED,
            latency_ns=self._latency_ns,
            batch=batch,
        )
