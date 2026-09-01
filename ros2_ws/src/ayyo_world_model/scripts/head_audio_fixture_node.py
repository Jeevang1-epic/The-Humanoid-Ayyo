#!/usr/bin/env python3
# Copyright 2026 Ayyo Project Authors

"""Explicit TEST-only deterministic head microphone publisher."""

from __future__ import annotations

from hashlib import sha256

from ayyo_head_audio import audio_test_fixture_bundle, AUDIO_TOPIC, fixture_audio_bytes
from ayyo_interfaces.msg import AudioFrame
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


class HeadAudioFixtureNode(Node):
    """Publish tiny deterministic PCM frames; this is not hardware health."""

    def __init__(self) -> None:
        super().__init__('ayyo_head_audio_test_fixture')
        self._bundle = audio_test_fixture_bundle()
        self._publisher = self.create_publisher(
            AudioFrame,
            AUDIO_TOPIC,
            qos_profile_sensor_data,
        )
        self._timer = self.create_timer(0.05, self._publish_frame)

    def _publish_frame(self) -> None:
        source = self._bundle.source
        payload = fixture_audio_bytes()
        stamp = self.get_clock().now().to_msg()
        message = AudioFrame()
        message.header.stamp = stamp
        message.header.frame_id = source.microphone.frame_id
        message.result_stamp = stamp
        message.source_id = source.source_id
        message.producer_id = source.producer_id
        message.microphone_id = source.microphone.sensor_id
        message.sample_rate_hz = source.sample_rate_hz
        message.channel_count = source.channel_count
        message.encoding = source.encoding
        message.frame_count = len(payload) // 2
        message.payload_sha256 = sha256(payload).hexdigest()
        message.data = payload
        self._publisher.publish(message)


def main() -> None:
    rclpy.init()
    node = HeadAudioFixtureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
