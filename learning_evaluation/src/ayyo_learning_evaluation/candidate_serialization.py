"""Canonical inspect-only serialization for inert candidate manifests."""

from __future__ import annotations

import json

from .candidate import (
    CANDIDATE_POLICY_SCHEMA_ID,
    CANDIDATE_POLICY_SCHEMA_VERSION,
    MAX_SERIALIZED_CANDIDATE_BYTES,
    CandidatePolicyManifest,
    InertArtifactReference,
    verify_candidate_policy,
)
from .canonical import canonical_json
from .errors import CandidatePolicyIntegrityError


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidatePolicyIntegrityError('candidate JSON contains a duplicate key')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise CandidatePolicyIntegrityError(f'non-finite JSON constant is forbidden: {value}')


def _mapping(value: object, field_name: str, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise CandidatePolicyIntegrityError(f'{field_name} has unknown or missing fields')
    return value


def canonical_candidate_policy_json(candidate: CandidatePolicyManifest) -> str:
    if not verify_candidate_policy(candidate):
        raise CandidatePolicyIntegrityError('candidate identity does not match its content')
    encoded = canonical_json(candidate.as_dict())
    if len(encoded.encode('utf-8')) > MAX_SERIALIZED_CANDIDATE_BYTES:
        raise CandidatePolicyIntegrityError('serialized candidate exceeds its v1 bound')
    return encoded


def candidate_policy_from_canonical_json(payload: str | bytes) -> CandidatePolicyManifest:
    if isinstance(payload, bytes):
        raw = payload
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError as error:
            raise CandidatePolicyIntegrityError('candidate JSON is not valid UTF-8') from error
    elif type(payload) is str:
        text = payload
        raw = payload.encode('utf-8')
    else:
        raise CandidatePolicyIntegrityError('candidate JSON must be text or bytes')
    if not raw or len(raw) > MAX_SERIALIZED_CANDIDATE_BYTES:
        raise CandidatePolicyIntegrityError('candidate JSON is empty or exceeds its v1 bound')
    try:
        document = json.loads(
            text, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except CandidatePolicyIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CandidatePolicyIntegrityError('candidate JSON is malformed') from error
    if canonical_json(document).encode('utf-8') != raw:
        raise CandidatePolicyIntegrityError('candidate JSON is not canonical')
    root = _mapping(
        document,
        'candidate document',
        {
            'artifact',
            'candidate_evidence',
            'candidate_fingerprint',
            'candidate_id',
            'contracts',
            'description',
            'parent_candidate',
            'policy_family_id',
            'provenance',
            'schema',
            'semantic_version',
        },
    )
    schema = _mapping(root['schema'], 'candidate schema', {'id', 'version'})
    if schema != {
        'id': CANDIDATE_POLICY_SCHEMA_ID,
        'version': CANDIDATE_POLICY_SCHEMA_VERSION,
    }:
        raise CandidatePolicyIntegrityError('candidate schema identity is incompatible')
    evidence = _mapping(root['candidate_evidence'], 'candidate evidence', {'fingerprint', 'id'})
    contracts = _mapping(root['contracts'], 'contracts', {'input', 'output'})
    input_contract = _mapping(contracts['input'], 'input contract', {'id', 'version'})
    output_contract = _mapping(contracts['output'], 'output contract', {'id', 'version'})
    provenance = _mapping(root['provenance'], 'provenance', {'fingerprint', 'source_ref'})
    if provenance != {
        'fingerprint': evidence['fingerprint'],
        'source_ref': evidence['id'],
    }:
        raise CandidatePolicyIntegrityError('candidate provenance must be its evidence set')
    parent = root['parent_candidate']
    if parent is not None:
        parent = _mapping(parent, 'parent candidate', {'fingerprint', 'id'})
    artifact = root['artifact']
    if artifact is not None:
        artifact = _mapping(
            artifact, 'artifact', {'artifact_id', 'artifact_kind', 'content_fingerprint'}
        )
        artifact = InertArtifactReference(**artifact)
    try:
        candidate = CandidatePolicyManifest._from_fields(
            semantic_version=root['semantic_version'],
            policy_family_id=root['policy_family_id'],
            candidate_evidence_set_id=evidence['id'],
            candidate_evidence_set_fingerprint=evidence['fingerprint'],
            input_contract_id=input_contract['id'],
            input_contract_version=input_contract['version'],
            output_contract_id=output_contract['id'],
            output_contract_version=output_contract['version'],
            description=root['description'],
            parent_candidate_id=parent['id'] if parent else None,
            parent_candidate_fingerprint=parent['fingerprint'] if parent else None,
            artifact=artifact,
        )
    except (TypeError, ValueError) as error:
        raise CandidatePolicyIntegrityError('candidate content violates the v1 contract') from error
    if candidate.as_dict() != root:
        raise CandidatePolicyIntegrityError('candidate identity or content was tampered')
    return candidate
