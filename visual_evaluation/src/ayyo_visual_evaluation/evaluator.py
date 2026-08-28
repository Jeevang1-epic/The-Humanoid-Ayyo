"""Deterministic mechanical evaluation and sealed admission issuance."""

from __future__ import annotations

from collections import Counter
import time
import tracemalloc
from typing import Callable

from ayyo_world_model import (
    ImageRegion2D,
    SensorAvailability,
    VisualDetection,
    VisualEvaluationDecision,
    VisualEvaluationReference,
    VisualEvaluationRequirement,
    VisualInterpretationObservation,
    VisualInterpretationProducer,
    VisualFrameObservation,
    rebuild_observation,
)

from .dataset import VisualRecordedSource
from .errors import (
    VisualDatasetError,
    VisualEvaluationConfigurationError,
)
from .invocation import VisualProducerInvoker
from .models import (
    MAX_VISUAL_LABEL_LENGTH,
    MAX_RESULTS_PER_SAMPLE,
    EvaluatedVisualAdmission,
    VisualAdmissionEvidenceKind,
    VisualConfidenceSemantics,
    VisualEvaluationDatasetManifest,
    VisualEvaluationInput,
    VisualEvaluationMetrics,
    VisualEvaluationOutcome,
    VisualEvaluationPolicy,
    VisualEvaluationReason,
    VisualEvaluationReport,
    VisualInvocationStatus,
    VisualProducerResult,
    VisualProducerResultBatch,
    VisualReasonCount,
    VisualSampleEvaluationRecord,
    VisualSampleEvaluationStatus,
    _issue_evaluated_admission,
)
from .registry import RegisteredVisualProducer, VisualProducerRegistry


def _rebuild_result(candidate: object) -> VisualProducerResult:
    """Reconstruct every nested value after the process/untrusted adapter seam."""
    if type(candidate) is not VisualProducerResult:
        raise VisualEvaluationConfigurationError("producer result is untyped")
    source = rebuild_observation(candidate.source_frame)
    if type(source) is not VisualFrameObservation:
        raise VisualEvaluationConfigurationError("producer source is not a visual frame")
    producer = VisualInterpretationProducer(
        candidate.producer.producer_id,
        candidate.producer.kind,
        candidate.producer.model_id,
        candidate.producer.adapter_id,
        candidate.producer.interface,
    )
    detections = []
    for detection in candidate.detections:
        if type(detection) is not VisualDetection:
            raise VisualEvaluationConfigurationError("producer detection is untyped")
        region = ImageRegion2D(
            x_min=detection.region.x_min,
            y_min=detection.region.y_min,
            x_max=detection.region.x_max,
            y_max=detection.region.y_max,
            coordinate_space=detection.region.coordinate_space,
        )
        detections.append(
            VisualDetection(
                source_visual_observation_id=(
                    detection.source_visual_observation_id
                ),
                category=detection.category,
                label=detection.label,
                region=region,
                confidence=detection.confidence,
                detection_id=detection.detection_id,
            )
        )
    return VisualProducerResult(
        source_frame=source,
        producer=producer,
        model_provenance_sha256=candidate.model_provenance_sha256,
        result_schema_version=candidate.result_schema_version,
        result_at_ns=candidate.result_at_ns,
        detections=tuple(detections),
        result_sha256=candidate.result_sha256,
    )


def _rebuild_batch(batch: object) -> tuple[VisualProducerResult, ...]:
    if type(batch) is not VisualProducerResultBatch:
        raise VisualEvaluationConfigurationError("producer result batch is untyped")
    if (
        type(batch.results) is not tuple
        or len(batch.results) > MAX_RESULTS_PER_SAMPLE
    ):
        raise VisualEvaluationConfigurationError(
            "producer result batch exceeds its hard bound"
        )
    return tuple(_rebuild_result(item) for item in batch.results)


def _percentile(values: tuple[int, ...], percent: int) -> int:
    index = max(0, (percent * len(values) + 99) // 100 - 1)
    return values[index]


def _validate_configuration(
    registration: RegisteredVisualProducer,
    dataset: VisualEvaluationDatasetManifest,
    policy: VisualEvaluationPolicy,
) -> None:
    manifest = registration.manifest
    if (
        policy.required_producer_manifest_sha256 != manifest.manifest_sha256
        or policy.required_model_provenance_sha256
        != manifest.model.provenance_sha256
        or policy.required_dataset_id != dataset.dataset_id
        or policy.required_dataset_version != dataset.dataset_version
        or policy.required_dataset_manifest_sha256 != dataset.manifest_sha256
        or policy.required_result_schema_version != manifest.result_schema_version
    ):
        raise VisualEvaluationConfigurationError(
            "producer, model, dataset, policy, and result schema must bind exactly"
        )
    if (
        dataset.sensor.sensor_id not in manifest.allowed_sensor_ids
        or dataset.source_profile not in manifest.allowed_source_profiles
        or dataset.encoding not in manifest.expected_encodings
        or dataset.width != manifest.dimensions.width
        or dataset.height != manifest.dimensions.height
    ):
        raise VisualEvaluationConfigurationError(
            "dataset source contract is outside the producer manifest"
        )
    if any(
        sample.asset_size_bytes > manifest.resources.maximum_input_bytes
        for sample in dataset.samples
    ):
        raise VisualEvaluationConfigurationError(
            "dataset input exceeds the producer resource policy"
        )
    if (
        policy.maximum_results_per_sample
        > manifest.resources.maximum_results_per_sample
        or policy.maximum_detections_per_result
        > manifest.resources.maximum_detections_per_result
        or policy.maximum_label_length > manifest.resources.maximum_label_length
        or not set(policy.allowed_categories) <= set(manifest.supported_categories)
        or policy.confidence_semantics is not manifest.confidence_semantics
    ):
        raise VisualEvaluationConfigurationError(
            "evaluation policy is weaker than or conflicts with the producer manifest"
        )


def _result_reason(
    result: VisualProducerResult,
    registration: RegisteredVisualProducer,
    dataset_sample,
    policy: VisualEvaluationPolicy,
) -> VisualEvaluationReason | None:
    manifest = registration.manifest
    if result.producer != manifest.producer:
        return VisualEvaluationReason.PRODUCER_IDENTITY_MISMATCH
    if result.model_provenance_sha256 != manifest.model.provenance_sha256:
        return VisualEvaluationReason.MODEL_PROVENANCE_MISMATCH
    if result.result_schema_version != manifest.result_schema_version:
        return VisualEvaluationReason.RESULT_SCHEMA_MISMATCH
    if result.source_frame != dataset_sample.frame:
        return VisualEvaluationReason.SOURCE_OBSERVATION_MISMATCH
    if (
        result.result_at_ns < result.source_frame.observed_at_ns
        or result.result_at_ns
        > result.source_frame.observed_at_ns + manifest.resources.timeout_ns
    ):
        return VisualEvaluationReason.RESULT_TIME_INVALID
    if len(result.detections) > min(
        manifest.resources.maximum_detections_per_result,
        policy.maximum_detections_per_result,
    ):
        return VisualEvaluationReason.DETECTION_COUNT_EXCEEDED
    for detection in result.detections:
        if detection.category not in policy.allowed_categories:
            return VisualEvaluationReason.CATEGORY_NOT_ALLOWED
        if len(detection.label) > min(
            manifest.resources.maximum_label_length,
            policy.maximum_label_length,
            MAX_VISUAL_LABEL_LENGTH,
        ):
            return VisualEvaluationReason.LABEL_LENGTH_EXCEEDED
        confidence = detection.confidence
        if (
            policy.confidence_semantics is VisualConfidenceSemantics.ABSENT
            and confidence is not None
        ) or (
            policy.confidence_semantics
            is VisualConfidenceSemantics.REQUIRED_UNIT_INTERVAL
            and confidence is None
        ):
            return VisualEvaluationReason.CONFIDENCE_SEMANTICS_MISMATCH
    return None


class VisualProducerEvaluator:
    """Evaluate one registered producer; issue admissions only after full pass."""

    __slots__ = (
        "_clock",
        "_invoker",
        "_qualified_reports",
        "_registry",
        "_software_identities",
    )

    def __init__(
        self,
        registry: VisualProducerRegistry,
        invoker: VisualProducerInvoker,
        *,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        software_identities: tuple[str, ...] = (
            "ayyo.visual-evaluation.core.v1",
        ),
    ) -> None:
        if type(registry) is not VisualProducerRegistry:
            raise VisualEvaluationConfigurationError("evaluator registry must be typed")
        if not callable(getattr(invoker, "invoke", None)):
            raise VisualEvaluationConfigurationError("evaluator invoker must be fixed")
        if not callable(monotonic_ns):
            raise VisualEvaluationConfigurationError("monotonic clock must be callable")
        if type(software_identities) is not tuple or not software_identities:
            raise VisualEvaluationConfigurationError(
                "evaluator software provenance must be nonempty"
            )
        self._registry = registry
        self._invoker = invoker
        self._clock = monotonic_ns
        self._software_identities = software_identities
        self._qualified_reports: dict[str, VisualEvaluationReport] = {}

    def evaluate(
        self,
        *,
        producer_id: str,
        dataset: VisualEvaluationDatasetManifest,
        source: VisualRecordedSource,
        policy: VisualEvaluationPolicy,
        run_id: str,
        traced_python_memory: tuple[int, int] | None = None,
    ) -> VisualEvaluationOutcome:
        registration = self._registry.require(producer_id)
        if type(dataset) is not VisualEvaluationDatasetManifest:
            raise VisualEvaluationConfigurationError("dataset manifest must be typed")
        if type(policy) is not VisualEvaluationPolicy:
            raise VisualEvaluationConfigurationError("evaluation policy must be typed")
        if not callable(getattr(source, "load", None)):
            raise VisualEvaluationConfigurationError("recorded source must be fixed")
        _validate_configuration(registration, dataset, policy)
        if traced_python_memory is not None and (
            type(traced_python_memory) is not tuple
            or len(traced_python_memory) != 2
            or any(type(item) is not int or item < 0 for item in traced_python_memory)
            or traced_python_memory[0] > traced_python_memory[1]
        ):
            raise VisualEvaluationConfigurationError(
                "traced Python memory must be an exact current/peak byte pair"
            )

        started = self._clock()
        records: list[VisualSampleEvaluationRecord] = []
        valid_results: list[VisualProducerResult] = []
        for sample in dataset.samples:
            try:
                evaluation_input = source.load(dataset, sample)
            except (VisualDatasetError, ValueError, OSError):
                records.append(
                    VisualSampleEvaluationRecord(
                        sample_id=sample.sample_id,
                        sample_sha256=sample.sample_sha256,
                        source_visual_observation_id=sample.frame.observation_id,
                        status=VisualSampleEvaluationStatus.REJECTED,
                        reason=VisualEvaluationReason.SOURCE_LOAD_FAILED,
                        latency_ns=0,
                        result_count=0,
                        result_sha256s=(),
                        annotation_matched=False,
                    )
                )
                continue
            invocation = self._invoker.invoke(registration, evaluation_input)
            if invocation.status is not VisualInvocationStatus.COMPLETED:
                reason = {
                    VisualInvocationStatus.TIMED_OUT: VisualEvaluationReason.PRODUCER_TIMEOUT,
                    VisualInvocationStatus.PRODUCER_FAILED: VisualEvaluationReason.PRODUCER_FAILURE,
                    VisualInvocationStatus.CLEANUP_FAILED: VisualEvaluationReason.PROCESS_CLEANUP_FAILED,
                }[invocation.status]
                records.append(
                    VisualSampleEvaluationRecord(
                        sample_id=sample.sample_id,
                        sample_sha256=sample.sample_sha256,
                        source_visual_observation_id=sample.frame.observation_id,
                        status=VisualSampleEvaluationStatus.REJECTED,
                        reason=reason,
                        latency_ns=invocation.latency_ns,
                        result_count=0,
                        result_sha256s=(),
                        annotation_matched=False,
                    )
                )
                continue
            assert invocation.batch is not None
            try:
                results = _rebuild_batch(invocation.batch)
            except (AttributeError, TypeError, ValueError):
                records.append(
                    VisualSampleEvaluationRecord(
                        sample_id=sample.sample_id,
                        sample_sha256=sample.sample_sha256,
                        source_visual_observation_id=sample.frame.observation_id,
                        status=VisualSampleEvaluationStatus.REJECTED,
                        reason=VisualEvaluationReason.MALFORMED_RESULT,
                        latency_ns=invocation.latency_ns,
                        result_count=0,
                        result_sha256s=(),
                        annotation_matched=False,
                    )
                )
                continue
            hashes = tuple(sorted(item.result_sha256 for item in results))
            if not results:
                reason = VisualEvaluationReason.MALFORMED_RESULT
            elif len(results) > min(
                registration.manifest.resources.maximum_results_per_sample,
                policy.maximum_results_per_sample,
            ):
                reason = VisualEvaluationReason.RESULT_COLLECTION_OVERSIZED
            elif len(set(hashes)) != len(hashes):
                reason = VisualEvaluationReason.DUPLICATE_RESULT
            else:
                reason = next(
                    (
                        candidate_reason
                        for result in results
                        if (
                            candidate_reason := _result_reason(
                                result,
                                registration,
                                sample,
                                policy,
                            )
                        )
                        is not None
                    ),
                    None,
                )
            if reason is not None:
                records.append(
                    VisualSampleEvaluationRecord(
                        sample_id=sample.sample_id,
                        sample_sha256=sample.sample_sha256,
                        source_visual_observation_id=sample.frame.observation_id,
                        status=VisualSampleEvaluationStatus.REJECTED,
                        reason=reason,
                        latency_ns=invocation.latency_ns,
                        result_count=len(results),
                        result_sha256s=hashes,
                        annotation_matched=False,
                    )
                )
                continue
            # The current interpreted-state contract represents one result with
            # a bounded detection collection per source frame.
            if len(results) != 1:
                records.append(
                    VisualSampleEvaluationRecord(
                        sample_id=sample.sample_id,
                        sample_sha256=sample.sample_sha256,
                        source_visual_observation_id=sample.frame.observation_id,
                        status=VisualSampleEvaluationStatus.REJECTED,
                        reason=VisualEvaluationReason.RESULT_COLLECTION_OVERSIZED,
                        latency_ns=invocation.latency_ns,
                        result_count=len(results),
                        result_sha256s=hashes,
                        annotation_matched=False,
                    )
                )
                continue
            result = results[0]
            annotation_matched = result.detections == sample.expected_detections
            valid_results.append(result)
            records.append(
                VisualSampleEvaluationRecord(
                    sample_id=sample.sample_id,
                    sample_sha256=sample.sample_sha256,
                    source_visual_observation_id=sample.frame.observation_id,
                    status=VisualSampleEvaluationStatus.VALID,
                    reason=VisualEvaluationReason.ACCEPTED,
                    latency_ns=invocation.latency_ns,
                    result_count=1,
                    result_sha256s=hashes,
                    annotation_matched=annotation_matched,
                )
            )

        completed = self._clock()
        if completed < started:
            raise VisualEvaluationConfigurationError(
                "evaluation monotonic clock regressed"
            )
        records_tuple = tuple(sorted(records, key=lambda item: item.sample_id))
        latencies = tuple(sorted(item.latency_ns for item in records_tuple))
        reason_counter = Counter(item.reason for item in records_tuple)
        valid_count = len(valid_results)
        annotation_match_count = sum(item.annotation_matched for item in records_tuple)
        timeout_count = reason_counter[VisualEvaluationReason.PRODUCER_TIMEOUT]
        failure_count = (
            reason_counter[VisualEvaluationReason.PRODUCER_FAILURE]
            + reason_counter[VisualEvaluationReason.PROCESS_CLEANUP_FAILED]
        )
        duplicate_count = reason_counter[VisualEvaluationReason.DUPLICATE_RESULT]
        malformed_reasons = {
            VisualEvaluationReason.PRODUCER_IDENTITY_MISMATCH,
            VisualEvaluationReason.MODEL_PROVENANCE_MISMATCH,
            VisualEvaluationReason.MALFORMED_RESULT,
            VisualEvaluationReason.RESULT_COLLECTION_OVERSIZED,
            VisualEvaluationReason.SOURCE_OBSERVATION_MISMATCH,
            VisualEvaluationReason.RESULT_TIME_INVALID,
            VisualEvaluationReason.RESULT_SCHEMA_MISMATCH,
            VisualEvaluationReason.CATEGORY_NOT_ALLOWED,
            VisualEvaluationReason.CONFIDENCE_SEMANTICS_MISMATCH,
            VisualEvaluationReason.DETECTION_COUNT_EXCEEDED,
            VisualEvaluationReason.LABEL_LENGTH_EXCEEDED,
        }
        malformed_count = sum(reason_counter[item] for item in malformed_reasons)
        valid_basis_points = valid_count * 10_000 // dataset.sample_count
        annotation_basis_points = (
            annotation_match_count * 10_000 // valid_count if valid_count else 0
        )
        decision_reasons: list[VisualEvaluationReason] = []
        if valid_basis_points < policy.minimum_valid_result_basis_points:
            decision_reasons.append(
                VisualEvaluationReason.VALID_RESULT_PERCENTAGE_BELOW_MINIMUM
            )
        if (
            annotation_basis_points
            < policy.minimum_annotation_match_basis_points
        ):
            decision_reasons.append(
                VisualEvaluationReason.ANNOTATION_MATCH_PERCENTAGE_BELOW_MINIMUM
            )
        if malformed_count > policy.maximum_malformed_result_count:
            decision_reasons.append(
                VisualEvaluationReason.MALFORMED_RESULT_LIMIT_EXCEEDED
            )
        if timeout_count > policy.maximum_timeout_count:
            decision_reasons.append(VisualEvaluationReason.TIMEOUT_LIMIT_EXCEEDED)
        if failure_count > policy.maximum_producer_failure_count:
            decision_reasons.append(
                VisualEvaluationReason.PRODUCER_FAILURE_LIMIT_EXCEEDED
            )
        if duplicate_count > policy.maximum_duplicate_result_count:
            decision_reasons.append(
                VisualEvaluationReason.DUPLICATE_RESULT_LIMIT_EXCEEDED
            )
        if _percentile(latencies, 95) > policy.maximum_p95_latency_ns:
            decision_reasons.append(VisualEvaluationReason.P95_LATENCY_EXCEEDED)
        decision_reasons_tuple = tuple(
            sorted(set(decision_reasons), key=lambda item: item.value)
        )
        decision = (
            VisualEvaluationDecision.MEETS_MECHANICAL_POLICY
            if not decision_reasons_tuple
            else VisualEvaluationDecision.DOES_NOT_MEET_MECHANICAL_POLICY
        )
        admitted_count = valid_count if decision is VisualEvaluationDecision.MEETS_MECHANICAL_POLICY else 0
        measured_memory = traced_python_memory
        if measured_memory is None and tracemalloc.is_tracing():
            measured_memory = tracemalloc.get_traced_memory()
        metrics = VisualEvaluationMetrics(
            source_sample_count=dataset.sample_count,
            attempted_count=dataset.sample_count,
            admitted_count=admitted_count,
            rejected_count=dataset.sample_count - admitted_count,
            valid_result_count=valid_count,
            annotation_match_count=annotation_match_count,
            producer_failure_count=failure_count,
            timeout_count=timeout_count,
            malformed_result_count=malformed_count,
            duplicate_result_count=duplicate_count,
            result_count=sum(item.result_count for item in records_tuple),
            minimum_latency_ns=latencies[0],
            maximum_latency_ns=latencies[-1],
            mean_latency_ns=sum(latencies) // len(latencies),
            p50_latency_ns=_percentile(latencies, 50),
            p95_latency_ns=_percentile(latencies, 95),
            p99_latency_ns=_percentile(latencies, 99),
            throughput_sample_count=dataset.sample_count,
            throughput_elapsed_ns=completed - started,
            reason_counts=tuple(
                VisualReasonCount(reason, count)
                for reason, count in sorted(
                    reason_counter.items(), key=lambda item: item[0].value
                )
            ),
            traced_python_current_bytes=(
                None if measured_memory is None else measured_memory[0]
            ),
            traced_python_peak_bytes=(
                None if measured_memory is None else measured_memory[1]
            ),
        )
        manifest = registration.manifest
        report = VisualEvaluationReport(
            run_id=run_id,
            producer_id=manifest.producer.producer_id,
            producer_version=manifest.producer_version,
            producer_implementation_sha256=(
                manifest.producer_implementation_sha256
            ),
            producer_manifest_sha256=manifest.manifest_sha256,
            model=manifest.model,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_manifest_sha256=dataset.manifest_sha256,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_sha256=policy.policy_sha256,
            result_schema_version=manifest.result_schema_version,
            started_at_monotonic_ns=started,
            completed_at_monotonic_ns=completed,
            metrics=metrics,
            records=records_tuple,
            decision=decision,
            decision_reasons=decision_reasons_tuple,
            software_identities=self._software_identities,
        )
        if decision is not VisualEvaluationDecision.MEETS_MECHANICAL_POLICY:
            return VisualEvaluationOutcome(report=report, admissions=())

        self._qualified_reports[report.semantic_sha256] = report
        while len(self._qualified_reports) > 16:
            del self._qualified_reports[min(self._qualified_reports)]

        reference = VisualEvaluationReference(
            producer_version=manifest.producer_version,
            producer_implementation_sha256=(
                manifest.producer_implementation_sha256
            ),
            producer_manifest_sha256=manifest.manifest_sha256,
            model=manifest.model,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_manifest_sha256=dataset.manifest_sha256,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_sha256=policy.policy_sha256,
            report_semantic_sha256=report.semantic_sha256,
            result_schema_version=manifest.result_schema_version,
            decision=decision,
        )
        requirement = VisualEvaluationRequirement(
            producer_id=manifest.producer.producer_id,
            producer_version=manifest.producer_version,
            producer_implementation_sha256=(
                manifest.producer_implementation_sha256
            ),
            producer_manifest_sha256=manifest.manifest_sha256,
            model_provenance_sha256=manifest.model.provenance_sha256,
            model_artifact_sha256=manifest.model.artifact_sha256,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            dataset_manifest_sha256=dataset.manifest_sha256,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_sha256=policy.policy_sha256,
            report_semantic_sha256=report.semantic_sha256,
            result_schema_version=manifest.result_schema_version,
        )
        admissions = []
        for result in valid_results:
            source_frame = result.source_frame
            observation = VisualInterpretationObservation(
                robot_id=source_frame.robot_id,
                sensor=source_frame.sensor,
                reference_frame_id=source_frame.sensor.frame_id,
                source_visual_observation_id=source_frame.observation_id,
                source_visual_fingerprint=source_frame.fingerprint,
                observed_at_ns=source_frame.observed_at_ns,
                result_at_ns=result.result_at_ns,
                producer=result.producer,
                detections=result.detections,
                provenance=source_frame.provenance,
                availability=SensorAvailability.AVAILABLE,
                evaluation_reference=reference,
            )
            admissions.append(
                _issue_evaluated_admission(
                    observation=observation,
                    producer_result=result,
                    report=report,
                    reference=reference,
                    requirement=requirement,
                    evidence_kind=(
                        VisualAdmissionEvidenceKind.RECORDED_EVALUATION_SAMPLE
                    ),
                )
            )
        return VisualEvaluationOutcome(
            report=report,
            admissions=tuple(
                sorted(
                    admissions,
                    key=lambda item: item.observation.observation_id,
                )
            ),
        )

    def invoke_qualified_input(
        self,
        *,
        producer_id: str,
        evaluation_input: VisualEvaluationInput,
        policy: VisualEvaluationPolicy,
        qualified_report: VisualEvaluationReport,
    ) -> EvaluatedVisualAdmission:
        """Run one new frame under a prior evaluator-issued mechanical report.

        The new frame is not represented as a recorded-dataset sample in the
        report. The report qualifies the exact producer/model/policy; this call
        separately validates the current input and output before issuing one
        sealed live-frame admission.
        """
        if type(evaluation_input) is not VisualEvaluationInput:
            raise VisualEvaluationConfigurationError(
                "qualified invocation input must be typed"
            )
        if type(policy) is not VisualEvaluationPolicy:
            raise VisualEvaluationConfigurationError(
                "qualified invocation policy must be typed"
            )
        if type(qualified_report) is not VisualEvaluationReport:
            raise VisualEvaluationConfigurationError(
                "qualified invocation report must be typed"
            )
        if (
            qualified_report.decision
            is not VisualEvaluationDecision.MEETS_MECHANICAL_POLICY
            or self._qualified_reports.get(qualified_report.semantic_sha256)
            is not qualified_report
        ):
            raise VisualEvaluationConfigurationError(
                "report was not issued as a successful evaluation by this harness"
            )
        registration = self._registry.require(producer_id)
        manifest = registration.manifest
        if (
            qualified_report.producer_id != manifest.producer.producer_id
            or qualified_report.producer_version != manifest.producer_version
            or qualified_report.producer_implementation_sha256
            != manifest.producer_implementation_sha256
            or qualified_report.producer_manifest_sha256
            != manifest.manifest_sha256
            or qualified_report.model != manifest.model
            or qualified_report.policy_id != policy.policy_id
            or qualified_report.policy_version != policy.policy_version
            or qualified_report.policy_sha256 != policy.policy_sha256
            or qualified_report.dataset_id != policy.required_dataset_id
            or qualified_report.dataset_version != policy.required_dataset_version
            or qualified_report.dataset_manifest_sha256
            != policy.required_dataset_manifest_sha256
            or qualified_report.result_schema_version
            != manifest.result_schema_version
        ):
            raise VisualEvaluationConfigurationError(
                "qualified report, registration, and policy do not bind exactly"
            )
        frame = evaluation_input.sample.frame
        if (
            frame.sensor.sensor_id not in manifest.allowed_sensor_ids
            or frame.provenance not in manifest.allowed_source_profiles
            or frame.encoding not in manifest.expected_encodings
            or frame.width != manifest.dimensions.width
            or frame.height != manifest.dimensions.height
            or frame.data_size_bytes > manifest.resources.maximum_input_bytes
        ):
            raise VisualEvaluationConfigurationError(
                "qualified live frame is outside the producer input contract"
            )
        invocation = self._invoker.invoke(registration, evaluation_input)
        if invocation.status is not VisualInvocationStatus.COMPLETED:
            raise VisualEvaluationConfigurationError(
                f"qualified producer invocation failed closed: {invocation.status.value}"
            )
        try:
            results = _rebuild_batch(invocation.batch)
        except (AttributeError, TypeError, ValueError) as error:
            raise VisualEvaluationConfigurationError(
                "qualified producer returned a malformed result"
            ) from error
        if len(results) != 1:
            raise VisualEvaluationConfigurationError(
                "qualified producer must return exactly one bounded result"
            )
        result = results[0]
        reason = _result_reason(
            result,
            registration,
            evaluation_input.sample,
            policy,
        )
        if reason is not None:
            raise VisualEvaluationConfigurationError(
                f"qualified producer result rejected: {reason.value}"
            )
        reference = VisualEvaluationReference(
            producer_version=manifest.producer_version,
            producer_implementation_sha256=(
                manifest.producer_implementation_sha256
            ),
            producer_manifest_sha256=manifest.manifest_sha256,
            model=manifest.model,
            dataset_id=qualified_report.dataset_id,
            dataset_version=qualified_report.dataset_version,
            dataset_manifest_sha256=qualified_report.dataset_manifest_sha256,
            policy_id=qualified_report.policy_id,
            policy_version=qualified_report.policy_version,
            policy_sha256=qualified_report.policy_sha256,
            report_semantic_sha256=qualified_report.semantic_sha256,
            result_schema_version=manifest.result_schema_version,
            decision=qualified_report.decision,
        )
        requirement = VisualEvaluationRequirement(
            producer_id=manifest.producer.producer_id,
            producer_version=manifest.producer_version,
            producer_implementation_sha256=(
                manifest.producer_implementation_sha256
            ),
            producer_manifest_sha256=manifest.manifest_sha256,
            model_provenance_sha256=manifest.model.provenance_sha256,
            model_artifact_sha256=manifest.model.artifact_sha256,
            dataset_id=qualified_report.dataset_id,
            dataset_version=qualified_report.dataset_version,
            dataset_manifest_sha256=qualified_report.dataset_manifest_sha256,
            policy_id=qualified_report.policy_id,
            policy_version=qualified_report.policy_version,
            policy_sha256=qualified_report.policy_sha256,
            report_semantic_sha256=qualified_report.semantic_sha256,
            result_schema_version=manifest.result_schema_version,
        )
        observation = VisualInterpretationObservation(
            robot_id=frame.robot_id,
            sensor=frame.sensor,
            reference_frame_id=frame.sensor.frame_id,
            source_visual_observation_id=frame.observation_id,
            source_visual_fingerprint=frame.fingerprint,
            observed_at_ns=frame.observed_at_ns,
            result_at_ns=result.result_at_ns,
            producer=result.producer,
            detections=result.detections,
            provenance=frame.provenance,
            availability=frame.availability,
            evaluation_reference=reference,
        )
        return _issue_evaluated_admission(
            observation=observation,
            producer_result=result,
            report=qualified_report,
            reference=reference,
            requirement=requirement,
            evidence_kind=VisualAdmissionEvidenceKind.QUALIFIED_LIVE_FRAME,
        )
