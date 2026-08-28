"""Explicit fixed producer registration and model-artifact verification."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from typing import Protocol

from .errors import VisualProducerRegistrationError
from .models import (
    MAX_DATASET_BYTES,
    MAX_REGISTERED_PRODUCERS,
    VerifiedModelArtifact,
    VisualEvaluationInput,
    VisualProducerManifest,
    VisualProducerResultBatch,
)


class VisualProducerAdapter(Protocol):
    """Fixed code-level adapter; manifests never name or import Python code."""

    def produce(self, evaluation_input: VisualEvaluationInput) -> VisualProducerResultBatch: ...


def verify_model_artifact_bytes(model, content: bytes) -> VerifiedModelArtifact:
    """Verify tiny/in-memory artifact bytes without retaining them in the record."""
    if type(content) is not bytes or not content or len(content) > MAX_DATASET_BYTES:
        raise VisualProducerRegistrationError(
            "model artifact bytes must be nonempty and bounded"
        )
    digest = sha256(content).hexdigest()
    if digest != model.artifact_sha256:
        raise VisualProducerRegistrationError(
            "model artifact content does not match immutable provenance"
        )
    return VerifiedModelArtifact(
        model_provenance_sha256=model.provenance_sha256,
        artifact_sha256=digest,
        size_bytes=len(content),
    )


@dataclass(frozen=True, slots=True)
class RegisteredVisualProducer:
    manifest: VisualProducerManifest
    adapter: VisualProducerAdapter
    verified_artifact: VerifiedModelArtifact

    def __post_init__(self) -> None:
        if type(self.manifest) is not VisualProducerManifest:
            raise VisualProducerRegistrationError("producer manifest must be typed")
        if not callable(getattr(self.adapter, "produce", None)):
            raise VisualProducerRegistrationError(
                "producer adapter must expose one fixed produce method"
            )
        if type(self.verified_artifact) is not VerifiedModelArtifact:
            raise VisualProducerRegistrationError(
                "producer registration requires a verified model artifact"
            )
        if (
            self.verified_artifact.model_provenance_sha256
            != self.manifest.model.provenance_sha256
            or self.verified_artifact.artifact_sha256
            != self.manifest.model.artifact_sha256
        ):
            raise VisualProducerRegistrationError(
                "verified model artifact and producer manifest disagree"
            )


class VisualProducerRegistry:
    """Bounded explicit allowlist; duplicate identity conflicts fail closed."""

    __slots__ = ("_by_id", "_lock")

    def __init__(self) -> None:
        self._by_id: dict[str, RegisteredVisualProducer] = {}
        self._lock = RLock()

    def register(self, registration: RegisteredVisualProducer) -> bool:
        if type(registration) is not RegisteredVisualProducer:
            raise VisualProducerRegistrationError("registration must be typed")
        producer_id = registration.manifest.producer.producer_id
        with self._lock:
            current = self._by_id.get(producer_id)
            if current is not None:
                if current == registration:
                    return False
                raise VisualProducerRegistrationError(
                    "duplicate producer identity carries a conflicting registration"
                )
            if len(self._by_id) >= MAX_REGISTERED_PRODUCERS:
                raise VisualProducerRegistrationError(
                    "producer registry reached its hard capacity"
                )
            self._by_id[producer_id] = registration
            return True

    def require(self, producer_id: str) -> RegisteredVisualProducer:
        if type(producer_id) is not str:
            raise VisualProducerRegistrationError("producer identity must be text")
        with self._lock:
            registration = self._by_id.get(producer_id)
            if registration is None:
                raise VisualProducerRegistrationError("producer identity is not registered")
            return registration

    @property
    def registration_count(self) -> int:
        with self._lock:
            return len(self._by_id)
