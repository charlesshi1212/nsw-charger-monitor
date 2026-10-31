# USYD CODE CITATION ACKNOWLEDGEMENT
# Developed with extensive assistance from OpenAI Codex.
"""Pacing regressions; run python -m unittest discover -s tests -v."""
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evstream import publisher


class Clock:
    def __init__(self):
        self.ns = 0
        self.sleeps = 0

    def now(self):
        return self.ns

    def sleep(self, seconds):
        self.sleeps += 1
        requested = math.ceil(seconds * 1_000_000_000)
        # Simulate an early wake once; the deadline must still be respected.
        self.ns += max(1, requested // 2) if self.sleeps == 1 else requested


class PublisherTimingTests(unittest.TestCase):
    def test_early_sleep_wake_does_not_publish_before_deadline(self):
        clock = Clock()
        with patch.object(publisher.time, 'perf_counter_ns', clock.now), \
             patch.object(publisher.time, 'sleep', clock.sleep):
            publisher._wait_until(100_000_000)
        self.assertGreaterEqual(clock.ns, 100_000_000)
        self.assertGreaterEqual(clock.sleeps, 2)

    def test_invalid_delays_fail_before_connecting(self):
        with patch.object(publisher.mqtt, 'Client') as factory:
            for delay in (0, .099, -1, float('nan'), float('inf'), -float('inf')):
                with self.subTest(delay=delay), self.assertRaises(ValueError):
                    publisher.publish('unused.jsonl', delay=delay)
            factory.assert_not_called()

    def test_publish_waits_full_interval_after_each_broker_ack(self):
        clock = Clock()
        starts = []
        acknowledgments = []
        payloads = []
        ack_delays = iter((25_000_000, 250_000_000, 1_000_000, 10_000_000))

        class FakeMessage:
            def wait_for_publish(self, timeout):
                clock.ns += next(ack_delays)
                acknowledgments.append(clock.ns)

            def is_published(self):
                return True

        class FakeClient:
            disconnected = False
            stopped = False

            def connect(self, host, port, keepalive):
                self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)

            def loop_start(self):
                pass

            def publish(self, topic, payload, qos, retain):
                starts.append(clock.ns)
                payloads.append(json.loads(payload))
                clock.ns += 5_000_000  # publication/queueing work before return
                return FakeMessage()

            def disconnect(self):
                self.disconnected = True

            def loop_stop(self):
                self.stopped = True

        events = [
            {'event_time': f'2026-09-01T00:00:0{i}+10:00', 'type': kind}
            for i, kind in enumerate(('price_update', 'session_start', 'meter', 'session_end'))
        ]
        client = FakeClient()
        with patch.object(publisher.mqtt, 'Client', return_value=client), \
             patch.object(publisher, 'read_jsonl', return_value=iter(events)), \
             patch.object(publisher.time, 'perf_counter_ns', clock.now), \
             patch.object(publisher.time, 'sleep', clock.sleep):
            self.assertEqual(publisher.publish('unused.jsonl'), len(events))

        self.assertEqual(payloads, events)
        for i in range(1, len(starts)):
            self.assertGreaterEqual(starts[i] - starts[i - 1], 100_000_000)
            self.assertGreaterEqual(starts[i] - acknowledgments[i - 1], 100_000_000)
        self.assertTrue(client.disconnected)
        self.assertTrue(client.stopped)


if __name__ == '__main__':
    unittest.main()
