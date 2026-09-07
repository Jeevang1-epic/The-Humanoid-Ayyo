"""Immutable, non-executable candidate-policy identity and lineage contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .canonical import canonical_json, semantic_sha256
from .corpus import (
    MAX_IDENTIFIER_LENGTH,
    MAX_METADATA_TEXT_LENGTH,
    CorpusPartition,
    DemonstrationEvidenceSet,
)
from .errors import CandidatePolicyIntegrityError


CANDIDATE_POLICY_SCHEMA_ID = 'ayyo.learning-evaluation.candidate-policy.v1'
CANDIDATE_POLICY_SCHEMA_VERSION = '1.0.0'
MAX_SERIALIZED_CANDIDATE_BYTES = 16_384

_IDENTIFIER = re.compile(r'^[a-z0-9]+(?:[._-][a-z0-9]+)*$')
_SEMVER = re.compile(r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
_FINGERPRINT = re.compile(
    r'^[a-z0-9]+(?:[._-][a-z0-9]+)*-sha256-[0-9a-f]{64}$'
)


def _identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise CandidatePolicyIntegrityError(f'{field_name} must be a bounded identifier')
    return value


def _fingerprint(value: object, field_name: str) -> str:
    value = _identifier(value, field_name)
    if _FINGERPRINT.fullmatch(value) is None:
        raise CandidatePolicyIntegrityError(f'{field_name} must be a SHA-256 identity')
    return value


def _text(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise CandidatePolicyIntegrityError(f'{field_name} must be text')
    normalized = unicodedata.normalize('NFC', value)
    if (
        not normalized
        or normalized != normalized.strip()
        or len(normalized) > MAX_METADATA_TEXT_LENGTH
        or any(unicodedata.category(character) in {'Cc', 'Cs'} for character in normalized)
    ):
        raise CandidatePolicyIntegrityError(f'{field_name} violates the v1 text bound')
    return normalized


def _semantic_version(value: object, field_name: str) -> str:
    if type(value) is not str or _SEMVER.fullmatch(value) is None:
        raise CandidatePolicyIntegrityError(f'{field_name} must be a semantic version')
    return value


@dataclass(frozen=True, slots=True)
class InertArtifactReference:
    artifact_id: str
    artifact_kind: str
    content_fingerprint: str

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, 'artifact_id')
        _identifier(self.artifact_kind, 'artifact_kind')
        _fingerprint(self.content_fingerprint, 'artifact content_fingerprint')

    def as_dict(self) -> dict[str, str]:
        return {
            'artifact_id': self.artifact_id,
            'artifact_kind': self.artifact_kind,
            'content_fingerprint': self.content_fingerprint,
        }


@dataclass(frozen=True, slots=True, init=False)
class CandidatePolicyManifest:
    schema_id: str
    schema_version: str
    candidate_id: str
    candidate_fingerprint: str
    semantic_version: str
    policy_family_id: str
    candidate_evidence_set_id: str
    candidate_evidence_set_fingerprint: str
    input_contract_id: str
    input_contract_version: str
    output_contract_id: str
    output_contract_version: str
    provenance_ref: str
    provenance_fingerprint: str
    description: str
    parent_candidate_id: str | None
    parent_candidate_fingerprint: str | None
    artifact: InertArtifactReference | None

    def __init__(
        self,
        *,
        candidate_evidence: DemonstrationEvidenceSet,
        semantic_version: str,
        policy_family_id: str,
        input_contract_id: str,
        input_contract_version: str,
        output_contract_id: str,
        output_contract_version: str,
        description: str,
        parent_candidate_id: str | None = None,
        parent_candidate_fingerprint: str | None = None,
        artifact: InertArtifactReference | None = None,
    ) -> None:
        if type(candidate_evidence) is not DemonstrationEvidenceSet:
            raise CandidatePolicyIntegrityError('candidate requires one evidence set')
        if candidate_evidence.partition is not CorpusPartition.CANDIDATE_EVIDENCE:
            raise CandidatePolicyIntegrityError('candidate cannot bind a holdout evidence set')
        if (
            candidate_evidence.evidence_set_fingerprint
            != candidate_evidence.recompute_fingerprint()
            or candidate_evidence.evidence_set_id
            != candidate_evidence.recompute_evidence_set_id()
        ):
            raise CandidatePolicyIntegrityError('candidate evidence-set integrity failed')
        self._initialize(
            semantic_version=semantic_version,
            policy_family_id=policy_family_id,
            candidate_evidence_set_id=candidate_evidence.evidence_set_id,
            candidate_evidence_set_fingerprint=candidate_evidence.evidence_set_fingerprint,
            input_contract_id=input_contract_id,
            input_contract_version=input_contract_version,
            output_contract_id=output_contract_id,
            output_contract_version=output_contract_version,
            description=description,
            parent_candidate_id=parent_candidate_id,
            parent_candidate_fingerprint=parent_candidate_fingerprint,
            artifact=artifact,
        )

    @classmethod
    def _from_fields(cls, **fields) -> CandidatePolicyManifest:
        instance = object.__new__(cls)
        instance._initialize(**fields)
        return instance

    def _initialize(
        self,
        *,
        semantic_version: str,
        policy_family_id: str,
        candidate_evidence_set_id: str,
        candidate_evidence_set_fingerprint: str,
        input_contract_id: str,
        input_contract_version: str,
        output_contract_id: str,
        output_contract_version: str,
        description: str,
        parent_candidate_id: str | None,
        parent_candidate_fingerprint: str | None,
        artifact: InertArtifactReference | None,
    ) -> None:
        semantic_version = _semantic_version(semantic_version, 'candidate semantic_version')
        policy_family_id = _identifier(policy_family_id, 'policy_family_id')
        candidate_evidence_set_id = _identifier(
            candidate_evidence_set_id, 'candidate_evidence_set_id'
        )
        candidate_evidence_set_fingerprint = _fingerprint(
            candidate_evidence_set_fingerprint, 'candidate_evidence_set_fingerprint'
        )
        input_contract_id = _identifier(input_contract_id, 'input_contract_id')
        input_contract_version = _semantic_version(
            input_contract_version, 'input_contract_version'
        )
        output_contract_id = _identifier(output_contract_id, 'output_contract_id')
        output_contract_version = _semantic_version(
            output_contract_version, 'output_contract_version'
        )
        if (parent_candidate_id is None) != (parent_candidate_fingerprint is None):
            raise CandidatePolicyIntegrityError(
                'parent candidate ID and fingerprint must be supplied together'
            )
        if parent_candidate_id is not None:
            parent_candidate_id = _identifier(parent_candidate_id, 'parent_candidate_id')
            parent_candidate_fingerprint = _fingerprint(
                parent_candidate_fingerprint, 'parent_candidate_fingerprint'
            )
        if artifact is not None and type(artifact) is not InertArtifactReference:
            raise CandidatePolicyIntegrityError('artifact must be an inert reference')
        object.__setattr__(self, 'schema_id', CANDIDATE_POLICY_SCHEMA_ID)
        object.__setattr__(self, 'schema_version', CANDIDATE_POLICY_SCHEMA_VERSION)
        object.__setattr__(self, 'semantic_version', semantic_version)
        object.__setattr__(self, 'policy_family_id', policy_family_id)
        object.__setattr__(self, 'candidate_evidence_set_id', candidate_evidence_set_id)
        object.__setattr__(
            self, 'candidate_evidence_set_fingerprint', candidate_evidence_set_fingerprint
        )
        object.__setattr__(self, 'input_contract_id', input_contract_id)
        object.__setattr__(self, 'input_contract_version', input_contract_version)
        object.__setattr__(self, 'output_contract_id', output_contract_id)
        object.__setattr__(self, 'output_contract_version', output_contract_version)
        object.__setattr__(self, 'provenance_ref', candidate_evidence_set_id)
        object.__setattr__(self, 'provenance_fingerprint', candidate_evidence_set_fingerprint)
        object.__setattr__(self, 'description', _text(description, 'candidate description'))
        object.__setattr__(self, 'parent_candidate_id', parent_candidate_id)
        object.__setattr__(self, 'parent_candidate_fingerprint', parent_candidate_fingerprint)
        object.__setattr__(self, 'artifact', artifact)
        fingerprint = self.recompute_fingerprint()
        object.__setattr__(self, 'candidate_fingerprint', fingerprint)
        object.__setattr__(
            self,
            'candidate_id',
            semantic_sha256(
                'candidate-policy',
                {
                    'candidate_fingerprint': fingerprint,
                    'schema_id': self.schema_id,
                    'schema_version': self.schema_version,
                },
            ),
        )
        if len(canonical_json(self.as_dict()).encode('utf-8')) > MAX_SERIALIZED_CANDIDATE_BYTES:
            raise CandidatePolicyIntegrityError('serialized candidate exceeds its v1 bound')

    def semantic_document(self) -> dict[str, object]:
        return {
            'artifact': self.artifact.as_dict() if self.artifact else None,
            'candidate_evidence': {
                'fingerprint': self.candidate_evidence_set_fingerprint,
                'id': self.candidate_evidence_set_id,
            },
            'contracts': {
                'input': {'id': self.input_contract_id, 'version': self.input_contract_version},
                'output': {
                    'id': self.output_contract_id,
                    'version': self.output_contract_version,
                },
            },
            'description': self.description,
            'parent_candidate': (
                {
                    'fingerprint': self.parent_candidate_fingerprint,
                    'id': self.parent_candidate_id,
                }
                if self.parent_candidate_id is not None
                else None
            ),
            'policy_family_id': self.policy_family_id,
            'provenance': {
                'fingerprint': self.provenance_fingerprint,
                'source_ref': self.provenance_ref,
            },
            'schema': {'id': self.schema_id, 'version': self.schema_version},
            'semantic_version': self.semantic_version,
        }

    def recompute_fingerprint(self) -> str:
        return semantic_sha256('candidate-policy-content', self.semantic_document())

    def recompute_candidate_id(self) -> str:
        return semantic_sha256(
            'candidate-policy',
            {
                'candidate_fingerprint': self.recompute_fingerprint(),
                'schema_id': self.schema_id,
                'schema_version': self.schema_version,
            },
        )

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_document(),
            'candidate_fingerprint': self.candidate_fingerprint,
            'candidate_id': self.candidate_id,
        }


def verify_candidate_policy(candidate: object) -> bool:
    if type(candidate) is not CandidatePolicyManifest:
        return False
    try:
        rebuilt = CandidatePolicyManifest._from_fields(
            semantic_version=candidate.semantic_version,
            policy_family_id=candidate.policy_family_id,
            candidate_evidence_set_id=candidate.candidate_evidence_set_id,
            candidate_evidence_set_fingerprint=candidate.candidate_evidence_set_fingerprint,
            input_contract_id=candidate.input_contract_id,
            input_contract_version=candidate.input_contract_version,
            output_contract_id=candidate.output_contract_id,
            output_contract_version=candidate.output_contract_version,
            description=candidate.description,
            parent_candidate_id=candidate.parent_candidate_id,
            parent_candidate_fingerprint=candidate.parent_candidate_fingerprint,
            artifact=candidate.artifact,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return rebuilt == candidate
