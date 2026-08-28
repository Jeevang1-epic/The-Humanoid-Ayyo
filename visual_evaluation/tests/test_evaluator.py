from __future__ import annotations

from dataclasses import replace
import multiprocessing
import os
from pathlib import Path
import time
import unittest

from ayyo_visual_evaluation import (
    DeterministicFixtureInvoker,
    DuplicateFixtureProducer,
    EvaluatedVisualAdmission,
    ExceptionFixtureProducer,
    FutureResultFixtureProducer,
    MalformedBoxFixtureProducer,
    MalformedConfidenceFixtureProducer,
    OversizedLabelFixtureProducer,
    OversizedDetectionFixtureProducer,
    OversizedFixtureProducer,
    OwnedProcessVisualProducerInvoker,
    SlowFixtureProducer,
    UnknownCategoryFixtureProducer,
    VisualEvaluationConfigurationError,
    VisualEvaluationOutcome,
    VisualEvaluationInput,
    VISUAL_EVALUATION_INPUT_INTERFACE,
    VisualEvaluationReason,
    VisualInvocationStatus,
    VisualProducerEvaluator,
    VisualProducerRegistry,
    WrongModelFixtureProducer,
    WrongSourceFixtureProducer,
    fixture_bundle,
    fixture_detection,
    fixture_frame,
    fixture_registration,
)
from ayyo_world_model import (
    ObservationProvenance,
    VisualEvaluationDecision,
    VisualFrameObservation,
)


class ScriptedClock:
    def __init__(self, values: tuple[int, ...]) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


def _sleep_unrelated() -> None:
    time.sleep(2.0)


def _evaluation(adapter=None, *, clock=(100, 200)):
    bundle = fixture_bundle(sample_count=2, adapter=adapter)
    registry = VisualProducerRegistry()
    registry.register(bundle.registration)
    evaluator = VisualProducerEvaluator(
        registry,
        DeterministicFixtureInvoker(1_000_000),
        monotonic_ns=ScriptedClock(clock),
    )
    outcome = evaluator.evaluate(
        producer_id=bundle.manifest.producer.producer_id,
        dataset=bundle.dataset,
        source=bundle.source,
        policy=bundle.policy,
        run_id="fixture.evaluation-run.v1",
    )
    return bundle, outcome


class VisualProducerEvaluatorTest(unittest.TestCase):
    def test_good_evaluation_issues_exact_sealed_admissions(self) -> None:
        bundle, outcome = _evaluation()
        self.assertIs(
            VisualEvaluationDecision.MEETS_MECHANICAL_POLICY,
            outcome.report.decision,
        )
        self.assertEqual(2, outcome.report.metrics.admitted_count)
        self.assertEqual(2, len(outcome.admissions))
        for admission in outcome.admissions:
            self.assertIs(type(admission), EvaluatedVisualAdmission)
            self.assertEqual(outcome.report, admission.report)
            self.assertEqual(
                admission.reference,
                admission.observation.evaluation_reference,
            )
            self.assertTrue(
                admission.requirement.matches(
                    admission.observation.producer,
                    admission.reference,
                )
            )
            self.assertEqual(
                bundle.dataset.manifest_sha256,
                admission.requirement.dataset_manifest_sha256,
            )
            self.assertEqual(
                outcome.report.semantic_sha256,
                admission.requirement.report_semantic_sha256,
            )

    def test_two_runs_keep_semantic_and_observation_identity_despite_execution_data(self) -> None:
        _, first = _evaluation(clock=(100, 200))
        bundle = fixture_bundle(sample_count=2)
        registry = VisualProducerRegistry()
        registry.register(bundle.registration)
        second = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(2_000_000),
            monotonic_ns=ScriptedClock((9_000, 19_000)),
        ).evaluate(
            producer_id=bundle.manifest.producer.producer_id,
            dataset=bundle.dataset,
            source=bundle.source,
            policy=bundle.policy,
            run_id="fixture.evaluation-run.v2",
        )
        self.assertNotEqual(
            first.report.metrics.p95_latency_ns,
            second.report.metrics.p95_latency_ns,
        )
        self.assertEqual(first.report.semantic_sha256, second.report.semantic_sha256)
        self.assertEqual(
            tuple(item.observation.observation_id for item in first.admissions),
            tuple(item.observation.observation_id for item in second.admissions),
        )

    def test_wrong_model_source_time_category_duplicate_oversize_and_exception_fail(self) -> None:
        cases = (
            (WrongModelFixtureProducer(), VisualEvaluationReason.MODEL_PROVENANCE_MISMATCH),
            (WrongSourceFixtureProducer(), VisualEvaluationReason.SOURCE_OBSERVATION_MISMATCH),
            (FutureResultFixtureProducer(), VisualEvaluationReason.RESULT_TIME_INVALID),
            (UnknownCategoryFixtureProducer(), VisualEvaluationReason.CATEGORY_NOT_ALLOWED),
            (DuplicateFixtureProducer(), VisualEvaluationReason.DUPLICATE_RESULT),
            (OversizedFixtureProducer(), VisualEvaluationReason.RESULT_COLLECTION_OVERSIZED),
            (ExceptionFixtureProducer(), VisualEvaluationReason.PRODUCER_FAILURE),
            (MalformedBoxFixtureProducer(), VisualEvaluationReason.MALFORMED_RESULT),
            (
                MalformedConfidenceFixtureProducer(),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
            (
                MalformedConfidenceFixtureProducer(float("nan")),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
            (
                MalformedConfidenceFixtureProducer(-0.1),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
            (
                MalformedConfidenceFixtureProducer(1.1),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
            (
                OversizedDetectionFixtureProducer(),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
            (
                OversizedLabelFixtureProducer(),
                VisualEvaluationReason.MALFORMED_RESULT,
            ),
        )
        for adapter, expected in cases:
            with self.subTest(adapter=type(adapter).__name__):
                _, outcome = _evaluation(adapter)
                self.assertIs(
                    VisualEvaluationDecision.DOES_NOT_MEET_MECHANICAL_POLICY,
                    outcome.report.decision,
                )
                self.assertEqual((), outcome.admissions)
                self.assertTrue(
                    all(record.reason is expected for record in outcome.report.records)
                )

    def test_corrupted_sample_fails_closed_and_valid_source_recovers(self) -> None:
        bundle = fixture_bundle(sample_count=1)
        registry = VisualProducerRegistry()
        registry.register(bundle.registration)
        evaluator = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(),
            monotonic_ns=ScriptedClock((100, 200)),
        )
        bad_source = type(bundle.source)(
            {"samples/shared.rgb8": b"x" * 24}
        )
        failed = evaluator.evaluate(
            producer_id=bundle.manifest.producer.producer_id,
            dataset=bundle.dataset,
            source=bad_source,
            policy=bundle.policy,
            run_id="fixture.corrupt.v1",
        )
        self.assertEqual((), failed.admissions)
        recovered = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(),
            monotonic_ns=ScriptedClock((300, 400)),
        ).evaluate(
            producer_id=bundle.manifest.producer.producer_id,
            dataset=bundle.dataset,
            source=bundle.source,
            policy=bundle.policy,
            run_id="fixture.recovered.v1",
        )
        self.assertEqual(1, len(recovered.admissions))

    def test_forged_report_metrics_outcome_and_admission_fail(self) -> None:
        _, outcome = _evaluation()
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(
                outcome.report,
                metrics=replace(
                    outcome.report.metrics,
                    timeout_count=1,
                ),
                semantic_sha256=None,
            )
        with self.assertRaises(VisualEvaluationConfigurationError):
            VisualEvaluationOutcome(
                report=outcome.report,
                admissions=(outcome.observations[0],),  # type: ignore[arg-type]
            )
        admission = outcome.admissions[0]
        with self.assertRaises(VisualEvaluationConfigurationError):
            EvaluatedVisualAdmission(
                observation=admission.observation,
                producer_result=admission.producer_result,
                report=admission.report,
                reference=admission.reference,
                requirement=admission.requirement,
                evidence_kind=admission.evidence_kind,
                _seal=object(),
            )

    def test_owned_process_timeout_cleans_exact_child_and_leaves_unrelated_alive(self) -> None:
        bundle = fixture_bundle(sample_count=1, adapter=SlowFixtureProducer())
        source_input = bundle.source.load(bundle.dataset, bundle.dataset.samples[0])
        context = multiprocessing.get_context("fork")
        unrelated = context.Process(target=_sleep_unrelated)
        unrelated.start()
        try:
            result = OwnedProcessVisualProducerInvoker().invoke(
                bundle.registration,
                source_input,
            )
            self.assertIs(VisualInvocationStatus.TIMED_OUT, result.status)
            self.assertEqual((), result.owned_survivor_pids)
            self.assertTrue(unrelated.is_alive())
            marker_prefix = (
                f"AYYO_VISUAL_EVALUATION_RUN_ID=visual-evaluation-{os.getpid()}-"
            ).encode("ascii")
            leaked = []
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    environment = (entry / "environ").read_bytes().split(b"\0")
                except OSError:
                    continue
                if any(item.startswith(marker_prefix) for item in environment):
                    leaked.append(int(entry.name))
            self.assertEqual([], leaked)
        finally:
            unrelated.terminate()
            unrelated.join(1.0)
            unrelated.close()

    def test_policy_and_normalized_interface_substitution_fail_before_invocation(self) -> None:
        bundle = fixture_bundle(sample_count=1)
        registry = VisualProducerRegistry()
        registry.register(bundle.registration)
        evaluator = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(),
        )
        with self.assertRaises(VisualEvaluationConfigurationError):
            evaluator.evaluate(
                producer_id=bundle.manifest.producer.producer_id,
                dataset=bundle.dataset,
                source=bundle.source,
                policy=replace(
                    bundle.policy,
                    required_dataset_manifest_sha256="0" * 64,
                    policy_sha256=None,
                ),
                run_id="fixture.substitution.v1",
            )
        self.assertEqual(
            "ayyo.visual-evaluation-input.v1",
            VISUAL_EVALUATION_INPUT_INTERFACE,
        )
        with self.assertRaises(VisualEvaluationConfigurationError):
            replace(
                bundle.manifest,
                expected_input_interface=bundle.dataset.source_profile.interface,
                manifest_sha256=None,
            )

    def test_successful_report_qualifies_new_live_frame_without_claiming_dataset_membership(self) -> None:
        bundle = fixture_bundle(sample_count=1)
        registry = VisualProducerRegistry()
        registry.register(bundle.registration)
        evaluator = VisualProducerEvaluator(
            registry,
            DeterministicFixtureInvoker(),
            monotonic_ns=ScriptedClock((100, 200)),
        )
        outcome = evaluator.evaluate(
            producer_id=bundle.manifest.producer.producer_id,
            dataset=bundle.dataset,
            source=bundle.source,
            policy=bundle.policy,
            run_id="fixture.qualification.v1",
        )
        live_frame = fixture_frame(999)
        live_sample = replace(
            bundle.dataset.samples[0],
            sample_id="fixture.live-frame.v1",
            frame=live_frame,
            expected_detections=(fixture_detection(live_frame),),
            sample_sha256=None,
        )
        admission = evaluator.invoke_qualified_input(
            producer_id=bundle.manifest.producer.producer_id,
            evaluation_input=VisualEvaluationInput(
                sample=live_sample,
                rgb8=bytes(range(24)),
            ),
            policy=bundle.policy,
            qualified_report=outcome.report,
        )
        self.assertEqual(
            live_frame.observation_id,
            admission.observation.source_visual_observation_id,
        )
        self.assertNotIn(
            live_frame.observation_id,
            {
                record.source_visual_observation_id
                for record in outcome.report.records
            },
        )
        self.assertEqual(
            "qualified_live_frame",
            admission.evidence_kind.value,
        )
        substituted_provenance = ObservationProvenance(
            live_frame.provenance.source_kind,
            "test.substituted-camera.v1",
            live_frame.provenance.clock,
            live_frame.provenance.transport,
            live_frame.provenance.interface,
        )
        substituted_frame = VisualFrameObservation(
            robot_id=live_frame.robot_id,
            sensor=live_frame.sensor,
            width=live_frame.width,
            height=live_frame.height,
            encoding=live_frame.encoding,
            step=live_frame.step,
            data_size_bytes=live_frame.data_size_bytes,
            is_bigendian=live_frame.is_bigendian,
            calibration_id=live_frame.calibration_id,
            observed_at_ns=live_frame.observed_at_ns + 1,
            provenance=substituted_provenance,
            availability=live_frame.availability,
        )
        substituted_sample = replace(
            live_sample,
            sample_id="fixture.substituted-live-frame.v1",
            frame=substituted_frame,
            expected_detections=(fixture_detection(substituted_frame),),
            sample_sha256=None,
        )
        with self.assertRaises(VisualEvaluationConfigurationError):
            evaluator.invoke_qualified_input(
                producer_id=bundle.manifest.producer.producer_id,
                evaluation_input=VisualEvaluationInput(
                    sample=substituted_sample,
                    rgb8=bytes(range(24)),
                ),
                policy=bundle.policy,
                qualified_report=outcome.report,
            )
        forged_equivalent_report = replace(outcome.report)
        with self.assertRaises(VisualEvaluationConfigurationError):
            evaluator.invoke_qualified_input(
                producer_id=bundle.manifest.producer.producer_id,
                evaluation_input=VisualEvaluationInput(
                    sample=live_sample,
                    rgb8=bytes(range(24)),
                ),
                policy=bundle.policy,
                qualified_report=forged_equivalent_report,
            )


if __name__ == "__main__":
    unittest.main()
