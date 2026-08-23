from __future__ import annotations

from dataclasses import dataclass
import unittest

from ayyo_runtime_bridge import (
    InvalidRuntimeContractError,
    RuntimeBridge,
    RuntimeDispatcher,
    RuntimeFailureCode,
    RuntimeResultStatus,
    RuntimeTransportAvailability,
    RuntimeTransportError,
    RuntimeTransportRejectedError,
    RuntimeTransportUnavailableError,
    TransportAcceptance,
    TransportReceipt,
    UnavailableRosServiceTransport,
)

from helpers import proposal, runtime_registry, skill, skill_binding


@dataclass
class FakeTransport:
    transport_id: str = "test.memory.service"
    available: RuntimeTransportAvailability = RuntimeTransportAvailability.AVAILABLE
    acceptance: TransportAcceptance = TransportAcceptance.ACCEPTED
    failure: Exception | None = None
    availability_calls: int = 0
    dispatch_calls: int = 0

    def availability(self, request):
        self.availability_calls += 1
        return self.available

    def dispatch(self, request):
        self.dispatch_calls += 1
        if self.failure is not None:
            raise self.failure
        return TransportReceipt(
            transport_id=self.transport_id,
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            acceptance=self.acceptance,
            correlation_id="fake-receipt-1",
            detail="Accepted only by the deterministic test transport.",
        )


class RuntimeTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = skill()
        self.binding = skill_binding(self.definition)
        self.bridge = RuntimeBridge(runtime_registry(self.definition))
        self.dispatcher = RuntimeDispatcher(self.bridge)
        self.decision = self.bridge.evaluate(self.binding)

    def test_not_dispatched_is_explicit_and_has_no_transport(self) -> None:
        result = self.dispatcher.not_dispatched(self.decision)
        self.assertIs(RuntimeResultStatus.NOT_DISPATCHED, result.status)
        self.assertIs(RuntimeFailureCode.DISPATCH_NOT_ATTEMPTED, result.failure_code)
        self.assertIsNone(result.receipt)

    def test_unavailable_sentinel_never_falls_back_to_fake_behavior(self) -> None:
        result = self.dispatcher.dispatch(
            self.decision,
            self.binding,
            UnavailableRosServiceTransport(),
        )
        self.assertIs(RuntimeResultStatus.TRANSPORT_UNAVAILABLE, result.status)
        self.assertIs(RuntimeFailureCode.TRANSPORT_UNAVAILABLE, result.failure_code)
        self.assertIsNone(result.receipt)

    def test_transport_acceptance_is_not_physical_completion(self) -> None:
        transport = FakeTransport()
        result = self.dispatcher.dispatch(self.decision, self.binding, transport)
        self.assertIs(RuntimeResultStatus.ACCEPTED_BY_TRANSPORT, result.status)
        self.assertIs(TransportAcceptance.ACCEPTED, result.receipt.acceptance)
        self.assertIn("physical or task completion is not established", result.detail)
        self.assertEqual(1, transport.availability_calls)
        self.assertEqual(1, transport.dispatch_calls)

    def test_transport_unavailable_and_rejection_are_distinct(self) -> None:
        unavailable = FakeTransport(
            available=RuntimeTransportAvailability.UNAVAILABLE
        )
        unavailable_result = self.dispatcher.dispatch(
            self.decision,
            self.binding,
            unavailable,
        )
        self.assertIs(
            RuntimeResultStatus.TRANSPORT_UNAVAILABLE,
            unavailable_result.status,
        )
        self.assertEqual(0, unavailable.dispatch_calls)

        rejected = FakeTransport(acceptance=TransportAcceptance.REJECTED)
        rejected_result = self.dispatcher.dispatch(
            self.decision,
            self.binding,
            rejected,
        )
        self.assertIs(
            RuntimeResultStatus.TRANSPORT_REJECTED,
            rejected_result.status,
        )
        self.assertIs(RuntimeFailureCode.TRANSPORT_REJECTED, rejected_result.failure_code)

    def test_typed_transport_failures_are_not_success(self) -> None:
        cases = (
            (
                RuntimeTransportUnavailableError("ROS graph unavailable"),
                RuntimeResultStatus.TRANSPORT_UNAVAILABLE,
            ),
            (
                RuntimeTransportRejectedError("service rejected request"),
                RuntimeResultStatus.TRANSPORT_REJECTED,
            ),
            (
                RuntimeTransportError("runtime transport failure"),
                RuntimeResultStatus.TRANSPORT_FAILURE,
            ),
        )
        for failure, expected in cases:
            with self.subTest(failure=type(failure).__name__):
                result = self.dispatcher.dispatch(
                    self.decision,
                    self.binding,
                    FakeTransport(failure=failure),
                )
                self.assertIs(expected, result.status)
                self.assertIsNone(result.receipt)

    def test_unknown_transport_failure_remains_visible(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "programming defect"):
            self.dispatcher.dispatch(
                self.decision,
                self.binding,
                FakeTransport(failure=RuntimeError("programming defect")),
            )

    def test_stale_upstream_binding_is_rejected_before_transport(self) -> None:
        changed = skill_binding(
            self.definition,
            source_proposal=proposal(request_id="request-2"),
        )
        transport = FakeTransport()
        result = self.dispatcher.dispatch(self.decision, changed, transport)
        self.assertIs(RuntimeResultStatus.REJECTED_BEFORE_DISPATCH, result.status)
        self.assertIs(RuntimeFailureCode.STALE_DECISION, result.failure_code)
        self.assertEqual(0, transport.availability_calls)
        self.assertEqual(0, transport.dispatch_calls)

    def test_tampered_runtime_request_is_rejected_before_transport(self) -> None:
        object.__setattr__(self.decision.request, "_request_fields", {"tampered": True})
        transport = FakeTransport()
        result = self.dispatcher.dispatch(self.decision, self.binding, transport)
        self.assertIs(RuntimeResultStatus.REJECTED_BEFORE_DISPATCH, result.status)
        self.assertIs(RuntimeFailureCode.STALE_DECISION, result.failure_code)
        self.assertEqual(0, transport.availability_calls)
        self.assertEqual(0, transport.dispatch_calls)

    def test_mismatched_receipt_is_rejected(self) -> None:
        class MismatchedReceiptTransport(FakeTransport):
            def dispatch(self, request):
                self.dispatch_calls += 1
                return TransportReceipt(
                    transport_id=self.transport_id,
                    request_id="another-request",
                    request_fingerprint=request.fingerprint,
                    acceptance=TransportAcceptance.ACCEPTED,
                    correlation_id="bad-receipt",
                    detail="Mismatched request identity.",
                )

        with self.assertRaisesRegex(InvalidRuntimeContractError, "does not match"):
            self.dispatcher.dispatch(
                self.decision,
                self.binding,
                MismatchedReceiptTransport(),
            )


if __name__ == "__main__":
    unittest.main()
