"""Narrow transport boundary and explicit dispatch result semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .binding import RuntimeRequest
from .decision import RuntimeBridge, RuntimeDecision, RuntimeEligibility
from .errors import (
    InvalidRuntimeContractError,
    RuntimeTransportError,
    RuntimeTransportRejectedError,
    RuntimeTransportUnavailableError,
)
from .models import (
    RuntimeFingerprint,
    RuntimeFingerprintKind,
    validate_identifier,
    validate_text,
)


class RuntimeTransportAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class TransportAcceptance(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TransportReceipt:
    """Transport acknowledgement, never a physical-completion claim."""

    transport_id: str
    request_id: str
    request_fingerprint: RuntimeFingerprint
    acceptance: TransportAcceptance
    correlation_id: str
    detail: str

    def __post_init__(self) -> None:
        validate_identifier(self.transport_id, field_name="transport receipt transport_id")
        validate_text(self.request_id, field_name="transport receipt request_id")
        if (
            not isinstance(self.request_fingerprint, RuntimeFingerprint)
            or self.request_fingerprint.kind is not RuntimeFingerprintKind.REQUEST
        ):
            raise InvalidRuntimeContractError(
                "transport receipt request fingerprint is invalid"
            )
        if not isinstance(self.acceptance, TransportAcceptance):
            raise InvalidRuntimeContractError("transport receipt acceptance is invalid")
        validate_text(self.correlation_id, field_name="transport correlation_id")
        validate_text(self.detail, field_name="transport receipt detail")


@runtime_checkable
class RuntimeTransport(Protocol):
    """The only v1 boundary allowed to hand a request to a ROS adapter."""

    @property
    def transport_id(self) -> str:
        ...

    def availability(
        self,
        request: RuntimeRequest,
    ) -> RuntimeTransportAvailability:
        ...

    def dispatch(self, request: RuntimeRequest) -> TransportReceipt:
        ...


class RuntimeResultStatus(StrEnum):
    NOT_ELIGIBLE = "not_eligible"
    NOT_DISPATCHED = "not_dispatched"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    REJECTED_BEFORE_DISPATCH = "rejected_before_dispatch"
    ACCEPTED_BY_TRANSPORT = "accepted_by_transport"
    TRANSPORT_FAILURE = "transport_failure"


class RuntimeFailureCode(StrEnum):
    DECISION_NOT_ELIGIBLE = "decision_not_eligible"
    DISPATCH_NOT_ATTEMPTED = "dispatch_not_attempted"
    STALE_DECISION = "stale_decision"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    TRANSPORT_REJECTED = "transport_rejected"
    TRANSPORT_FAILURE = "transport_failure"


@dataclass(frozen=True, slots=True)
class RuntimeDispatchResult:
    """Outcome at the transport boundary; it never represents physical completion."""

    status: RuntimeResultStatus
    decision_id: str
    decision_fingerprint: RuntimeFingerprint
    request_id: str | None
    request_fingerprint: RuntimeFingerprint | None
    transport_id: str | None
    failure_code: RuntimeFailureCode | None
    detail: str
    receipt: TransportReceipt | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RuntimeResultStatus):
            raise InvalidRuntimeContractError("runtime result status is invalid")
        validate_text(self.decision_id, field_name="runtime result decision_id")
        if (
            not isinstance(self.decision_fingerprint, RuntimeFingerprint)
            or self.decision_fingerprint.kind is not RuntimeFingerprintKind.DECISION
        ):
            raise InvalidRuntimeContractError(
                "runtime result decision fingerprint is invalid"
            )
        if (self.request_id is None) != (self.request_fingerprint is None):
            raise InvalidRuntimeContractError(
                "runtime result request identity must be complete or absent"
            )
        if self.request_id is not None:
            validate_text(self.request_id, field_name="runtime result request_id")
            if (
                not isinstance(self.request_fingerprint, RuntimeFingerprint)
                or self.request_fingerprint.kind is not RuntimeFingerprintKind.REQUEST
            ):
                raise InvalidRuntimeContractError(
                    "runtime result request fingerprint is invalid"
                )
        if self.transport_id is not None:
            validate_identifier(
                self.transport_id,
                field_name="runtime result transport_id",
            )
        if self.failure_code is not None and not isinstance(
            self.failure_code, RuntimeFailureCode
        ):
            raise InvalidRuntimeContractError("runtime result failure code is invalid")
        validate_text(self.detail, field_name="runtime result detail")
        if self.status is RuntimeResultStatus.ACCEPTED_BY_TRANSPORT:
            if (
                self.failure_code is not None
                or not isinstance(self.receipt, TransportReceipt)
                or self.receipt.acceptance is not TransportAcceptance.ACCEPTED
            ):
                raise InvalidRuntimeContractError(
                    "accepted result requires an accepted transport receipt"
                )
        elif self.receipt is not None:
            if not (
                self.status is RuntimeResultStatus.REJECTED_BEFORE_DISPATCH
                and self.receipt.acceptance is TransportAcceptance.REJECTED
            ):
                raise InvalidRuntimeContractError(
                    "only accepted or explicitly rejected results may carry receipts"
                )
        if self.status is not RuntimeResultStatus.ACCEPTED_BY_TRANSPORT:
            if not isinstance(self.failure_code, RuntimeFailureCode):
                raise InvalidRuntimeContractError(
                    "non-accepted runtime result requires a typed failure code"
                )


def _result(
    *,
    status: RuntimeResultStatus,
    decision: RuntimeDecision,
    detail: str,
    failure_code: RuntimeFailureCode | None,
    transport_id: str | None = None,
    receipt: TransportReceipt | None = None,
) -> RuntimeDispatchResult:
    request = decision.request
    return RuntimeDispatchResult(
        status=status,
        decision_id=decision.decision_id,
        decision_fingerprint=decision.fingerprint,
        request_id=None if request is None else request.request_id,
        request_fingerprint=None if request is None else request.fingerprint,
        transport_id=transport_id,
        failure_code=failure_code,
        detail=detail,
        receipt=receipt,
    )


@dataclass(frozen=True, slots=True)
class RuntimeDispatcher:
    """Revalidating gateway from eligibility to one explicitly supplied transport."""

    bridge: RuntimeBridge

    def __post_init__(self) -> None:
        if type(self.bridge) is not RuntimeBridge:
            raise InvalidRuntimeContractError("dispatcher requires a RuntimeBridge")

    def not_dispatched(self, decision: RuntimeDecision) -> RuntimeDispatchResult:
        if type(decision) is not RuntimeDecision:
            raise InvalidRuntimeContractError(
                "not-dispatched result requires a RuntimeDecision"
            )
        if decision.status is not RuntimeEligibility.ELIGIBLE:
            return _result(
                status=RuntimeResultStatus.NOT_ELIGIBLE,
                decision=decision,
                failure_code=RuntimeFailureCode.DECISION_NOT_ELIGIBLE,
                detail="Runtime eligibility was not established; no transport was called.",
            )
        return _result(
            status=RuntimeResultStatus.NOT_DISPATCHED,
            decision=decision,
            failure_code=RuntimeFailureCode.DISPATCH_NOT_ATTEMPTED,
            detail="The eligible request was deliberately not handed to a transport.",
        )

    def dispatch(
        self,
        decision: RuntimeDecision,
        current_binding: object,
        transport: RuntimeTransport,
    ) -> RuntimeDispatchResult:
        if type(decision) is not RuntimeDecision:
            raise InvalidRuntimeContractError(
                "dispatch requires a RuntimeDecision"
            )
        if decision.status is not RuntimeEligibility.ELIGIBLE:
            return _result(
                status=RuntimeResultStatus.NOT_ELIGIBLE,
                decision=decision,
                failure_code=RuntimeFailureCode.DECISION_NOT_ELIGIBLE,
                detail="Runtime eligibility was not established; no transport was called.",
            )
        current = self.bridge.evaluate(current_binding)
        if current != decision:
            return _result(
                status=RuntimeResultStatus.REJECTED_BEFORE_DISPATCH,
                decision=decision,
                failure_code=RuntimeFailureCode.STALE_DECISION,
                detail="Runtime or upstream state changed after eligibility evaluation.",
            )
        if not isinstance(transport, RuntimeTransport):
            raise InvalidRuntimeContractError(
                "dispatch requires a RuntimeTransport implementation"
            )
        transport_id = validate_identifier(
            transport.transport_id,
            field_name="transport_id",
        )
        assert decision.request is not None
        try:
            availability = transport.availability(decision.request)
        except RuntimeTransportUnavailableError as error:
            return _result(
                status=RuntimeResultStatus.TRANSPORT_UNAVAILABLE,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_UNAVAILABLE,
                detail=str(error),
            )
        except RuntimeTransportError as error:
            return _result(
                status=RuntimeResultStatus.TRANSPORT_FAILURE,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_FAILURE,
                detail=str(error),
            )
        if availability is RuntimeTransportAvailability.UNAVAILABLE:
            return _result(
                status=RuntimeResultStatus.TRANSPORT_UNAVAILABLE,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_UNAVAILABLE,
                detail="The configured transport reported itself unavailable.",
            )
        if availability is not RuntimeTransportAvailability.AVAILABLE:
            raise InvalidRuntimeContractError(
                "transport returned an invalid availability state"
            )
        try:
            receipt = transport.dispatch(decision.request)
        except RuntimeTransportUnavailableError as error:
            return _result(
                status=RuntimeResultStatus.TRANSPORT_UNAVAILABLE,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_UNAVAILABLE,
                detail=str(error),
            )
        except RuntimeTransportRejectedError as error:
            return _result(
                status=RuntimeResultStatus.REJECTED_BEFORE_DISPATCH,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_REJECTED,
                detail=str(error),
            )
        except RuntimeTransportError as error:
            return _result(
                status=RuntimeResultStatus.TRANSPORT_FAILURE,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_FAILURE,
                detail=str(error),
            )
        if type(receipt) is not TransportReceipt:
            raise InvalidRuntimeContractError(
                "transport returned an invalid receipt contract"
            )
        if (
            receipt.transport_id != transport_id
            or receipt.request_id != decision.request.request_id
            or receipt.request_fingerprint != decision.request.fingerprint
        ):
            raise InvalidRuntimeContractError(
                "transport receipt does not match the dispatched runtime request"
            )
        if receipt.acceptance is TransportAcceptance.REJECTED:
            return _result(
                status=RuntimeResultStatus.REJECTED_BEFORE_DISPATCH,
                decision=decision,
                transport_id=transport_id,
                failure_code=RuntimeFailureCode.TRANSPORT_REJECTED,
                detail=receipt.detail,
                receipt=receipt,
            )
        return _result(
            status=RuntimeResultStatus.ACCEPTED_BY_TRANSPORT,
            decision=decision,
            transport_id=transport_id,
            failure_code=None,
            detail=(
                "Transport accepted the request; physical or task completion is not established."
            ),
            receipt=receipt,
        )


@dataclass(frozen=True, slots=True)
class UnavailableRosServiceTransport:
    """Explicit production-safe sentinel; it never falls back to a fake transport."""

    transport_id: str = "ros.service.unconfigured"

    def availability(self, request: RuntimeRequest) -> RuntimeTransportAvailability:
        if type(request) is not RuntimeRequest:
            raise InvalidRuntimeContractError(
                "ROS transport availability requires a RuntimeRequest"
            )
        return RuntimeTransportAvailability.UNAVAILABLE

    def dispatch(self, request: RuntimeRequest) -> TransportReceipt:
        if type(request) is not RuntimeRequest:
            raise InvalidRuntimeContractError(
                "ROS transport dispatch requires a RuntimeRequest"
            )
        raise RuntimeTransportUnavailableError(
            "No typed ROS service adapter is configured for this endpoint."
        )
