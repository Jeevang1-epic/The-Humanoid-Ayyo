#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Normalize bounded ROS audio transport into compact untrusted core evidence."""

from __future__ import annotations

from ayyo_head_audio import AudioSourceManifest, summarize_audio_payload
from ayyo_interfaces.msg import AudioFrame


class HeadAudioRosAdapterError(ValueError):
    """A ROS message cannot satisfy the reviewed microphone transport contract."""


def _time_ns(stamp) -> int:
    if (
        type(stamp.sec) is not int
        or type(stamp.nanosec) is not int
        or stamp.sec < 0
        or not 0 <= stamp.nanosec < 1_000_000_000
    ):
        raise HeadAudioRosAdapterError('audio timestamp is malformed')
    value = stamp.sec * 1_000_000_000 + stamp.nanosec
    if value <= 0:
        raise HeadAudioRosAdapterError('audio timestamp must be positive')
    return value


def normalize_audio_frame(
    message: AudioFrame,
    source: AudioSourceManifest,
    session_id: str,
):
    """Validate ROS fields and compact raw PCM bytes without retaining them."""
    if not isinstance(message, AudioFrame):
        raise HeadAudioRosAdapterError(
            'audio evidence must be ayyo_interfaces/AudioFrame'
        )
    if message.header.frame_id != source.microphone.frame_id:
        raise HeadAudioRosAdapterError(
            'audio frame does not match the reviewed microphone frame'
        )
    if (
        message.source_id != source.source_id
        or message.producer_id != source.producer_id
        or message.microphone_id != source.microphone.sensor_id
    ):
        raise HeadAudioRosAdapterError(
            'audio message identity conflicts with its reviewed source'
        )
    try:
        return summarize_audio_payload(
            source=source,
            session_id=session_id,
            observed_at_ns=_time_ns(message.header.stamp),
            result_at_ns=_time_ns(message.result_stamp),
            frame_count=message.frame_count,
            data=bytes(message.data),
            frame_id=message.header.frame_id,
            source_id=message.source_id,
            producer_id=message.producer_id,
            microphone=source.microphone,
            sample_rate_hz=message.sample_rate_hz,
            channel_count=message.channel_count,
            encoding=message.encoding,
            claimed_payload_sha256=message.payload_sha256,
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, HeadAudioRosAdapterError):
            raise
        raise HeadAudioRosAdapterError(str(error)) from error
