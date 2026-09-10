# Human / Authority Approval Evidence and Activation Eligibility

## Status

Foundation v1 is implemented as the standalone `ayyo-approval-eligibility`
distribution. It is an inert, transport-neutral evidence boundary. It answers
only whether one exact registered candidate and one exact externally supplied
approval-evidence chain are structurally eligible to proceed to a separately
reviewed future activation stage.

An eligible decision is not activation, installation, deployment, execution,
authentication, training, physical-safety approval, or permission to move.

## Dependency boundary

Repository dependency arrows point from a consumer to the lower package it
uses. The Stage-7 side path is therefore:

```text
approval_eligibility
→ policy_registry
→ promotion_control
→ learning_evaluation
→ teach_mode
```

`ayyo-approval-eligibility` has one exact direct dependency:
`ayyo-policy-registry==0.1.0`. No lower package imports it. It is not connected
to Executive, Safety, Skill Manager, Runtime Bridge, ROS, Gazebo, simulation
control, hardware adapters, or actuator control.

## Contracts

All public artifacts are frozen, content-addressed, schema-versioned, bounded,
and canonically serializable.

- `AuthorityReference` records an opaque authority ID/fingerprint, provenance,
  and a closed verification status. It is a reference to verification evidence,
  not an authenticator.
- `ApprovalRequest` binds an exact registered candidate ID, fingerprint and
  semantic version; registry record ID/fingerprint; registration request
  ID/fingerprint; promotion decision ID/fingerprint and target stage; approval
  scope; and authority ID/reference.
- `AuthorityApprovalEvidence` embeds the exact approval request and exact
  authority reference, plus one closed disposition and one evidence-source
  identity.
- `ActivationEligibilityRequest` embeds the verified registered version,
  approval request, and approval evidence. Construction rechecks the complete
  cross-object chain rather than trusting independent object validity.
- `ActivationEligibilityDecision` embeds the exact eligibility request and a
  closed status/reason set. Verification recomputes the authoritative pure
  evaluation, so a self-consistent forged outer identity cannot convert denied
  evidence into eligibility.

The only approval scope in v1 is `FUTURE_ACTIVATION_REVIEW`. The only positive
status is `ELIGIBLE_FOR_FUTURE_ACTIVATION`.

## Authority verification seam

Foundation v1 deliberately does not implement passwords, biometrics, owner or
teacher recognition, face recognition, cryptographic identity infrastructure,
relationship inference, or a production authentication provider.

Authority state is explicit:

- `UNVERIFIED` carries no verification-provider or verification-evidence
  identity and is always ineligible.
- `EXTERNALLY_VERIFIED` must carry exact provider and evidence reference/
  fingerprint pairs and may be evaluated structurally.
- `REVOKED` must retain those external identities for traceability and is always
  ineligible.

`EXTERNALLY_VERIFIED` is a caller-supplied assertion at this boundary. The
package checks its shape, provenance identity, and exact use throughout the
approval chain; it does not contact or validate the external provider and does
not claim that the referenced human was authenticated. A future production
authority provider must be separately designed and reviewed.

## Eligibility rules

The pure evaluator first verifies the entire request and then applies these
closed rules:

| Authority status | Approval disposition | Result |
| --- | --- | --- |
| `EXTERNALLY_VERIFIED` | `APPROVED` | `ELIGIBLE_FOR_FUTURE_ACTIVATION` |
| `UNVERIFIED` | any | `INELIGIBLE` |
| `REVOKED` | any | `INELIGIBLE` |
| any | `REJECTED` | `INELIGIBLE` |
| any | `REVOKED` | `INELIGIBLE` |

Contradictory concrete evidence remains visible as multiple typed ineligibility
reasons. No count, summary, majority, or aggregate can override it.

Foundation v1 accepts exactly one `AuthorityApprovalEvidence` object. A list or
tuple of duplicate or conflicting approvals is not a valid request. Multi-party
approval policy, quorum, role policy, and conflict resolution require a future
explicit contract rather than an implicit aggregate.

## Exact chain invariants

Each eligibility request requires equality across all applicable ID and
fingerprint components:

```text
RegisteredPolicyVersion candidate/version
  == ApprovalRequest candidate/version

RegisteredPolicyVersion record identity
  == ApprovalRequest registry-record identity

RegisteredPolicyVersion registration-request identity
  == ApprovalRequest registration-request identity

RegisteredPolicyVersion promotion-decision identity and target
  == ApprovalRequest promotion-decision identity and target

ApprovalRequest identity
  == AuthorityApprovalEvidence embedded request identity

ApprovalRequest authority identity/reference
  == AuthorityApprovalEvidence authority identity/reference
```

The models and strict parser reject candidate, registry-record, registration-
request, promotion-decision, approval-request, or authority substitution;
ID-only or fingerprint-only changes; independently valid but unrelated object
composition; unknown schema/version/enum values; duplicate JSON keys; altered
canonical evidence; and recomputed outer identities over inconsistent nested
evidence.

## Serialization and resources

Canonical JSON uses sorted keys, compact separators, UTF-8, and finite JSON
values. Parsing requires byte-for-byte canonical input, rejects duplicate keys
and unknown/missing fields, reconstructs nested registry records through the
public registry parser, and verifies the reconstructed artifact again.

Identifiers, fingerprints, semantic versions, notes, and each serialized
artifact have explicit v1 limits. No artifact contains executable payloads,
model weights, paths, URLs, callbacks, commands, active/latest aliases, or
runtime handles.

## Explicit non-goals

This foundation provides no:

- human, owner, or teacher authentication;
- permission or role administration;
- cryptographic-signature verification or network authority;
- mutable latest, installed, selected, or active policy state;
- persistence, audit database, filesystem write, or background worker;
- candidate generation, learning, training, inference, or model loading;
- policy installation, activation, deployment, rollback application, or
  execution;
- Executive, Safety, Skill Manager, Runtime Bridge, ROS/Gazebo, simulation,
  hardware, actuator, or motion connection;
- physical-safety certification or Safety bypass.

## Validation

Run the focused suite from the repository root:

```bash
PYTHONPATH=memory/src:personal_context/src:executive/src:safety_kernel/src:skill_manager/src:runtime_bridge/src:developmental_scenarios/src:teach_mode/src:learning_evaluation/src:promotion_control/src:policy_registry/src:approval_eligibility/src \
python3 -m pytest -q approval_eligibility/tests
```

The suite constructs the real Teach Mode → Learning Evaluation → Promotion
Control → Policy Registry evidence path and proves the cross-object,
serialization, resource, dependency, wheel-content, and inertness boundaries.

## Future boundary

Before any model runner, sandbox, installation, active-policy state, Runtime
integration, or hardware path exists, the repository still needs separately
reviewed production authority authentication/verification and a distinct
activation policy boundary. That later work must consume eligibility evidence
without treating it as authentication, physical safety, or execution authority,
and it must preserve independent Safety review.
