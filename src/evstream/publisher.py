# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""QoS 1 ordered replay. Never publishes faster than one message per 0.1 s."""
import argparse
import json
import math
import threading
import time
from pathlib import Path
import paho.mqtt.client as mqtt
from .common import ROOT,DEFAULT_TOPIC,read_jsonl


def _wait_until(deadline_ns):
    """Recheck a high-resolution deadline after every sleep, including early wakes."""
    while True:
        remaining_ns = deadline_ns - time.perf_counter_ns()
        if remaining_ns <= 0:
            return
        time.sleep(remaining_ns / 1_000_000_000)


def publish(path, host='127.0.0.1', port=1883, topic=DEFAULT_TOPIC,
            delay=.1, limit=None):
    if not math.isfinite(delay) or delay < .1:
        raise ValueError('Assignment requires a finite delay of at least 0.1 seconds')
    interval_ns = math.ceil(delay * 1_000_000_000)
    ready = threading.Event()
    fail = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)

    def connected(c, u, flags, reason, props):
        if reason.is_failure:
            fail.append(str(reason))
        ready.set()

    client.on_connect = connected
    count = 0
    previous = None
    next_allowed_ns = None
    loop_started = False
    try:
        client.connect(host, port, 60)
        client.loop_start()
        loop_started = True
        if not ready.wait(15) or fail:
            raise RuntimeError(f'Broker connection failed: {fail}')

        for event in read_jsonl(path):
            if limit is not None and count >= limit:
                break
            if previous and event['event_time'] < previous:
                raise ValueError('Input is not ordered by event time')
            previous = event['event_time']
            payload = json.dumps(event, separators=(',', ':'))
            if next_allowed_ns is not None:
                _wait_until(next_allowed_ns)

            result = client.publish(topic, payload, qos=1, retain=False)
            result.wait_for_publish(timeout=15)
            if not result.is_published():
                raise TimeoutError('Broker PUBACK not received')
            # Wait a full interval after PUBACK. This conservative anchor also
            # covers queueing and transport delays inside the previous publish.
            # perf_counter_ns avoids coarse Windows Python 3.12 monotonic ticks.
            next_allowed_ns = time.perf_counter_ns() + interval_ns
            count += 1
            if count % 100 == 0:
                print(f'Published {count}: {event["event_time"]} {event["type"]}', flush=True)
    finally:
        client.disconnect()
        if loop_started:
            client.loop_stop()
    print(f'Published {count} events at minimum {delay:g}s intervals', flush=True)
    return count


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--events',type=Path,default=ROOT/'data/events.jsonl')
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--topic',default=DEFAULT_TOPIC);p.add_argument('--delay',type=float,default=.1);p.add_argument('--limit',type=int)
    a=p.parse_args();publish(a.events,a.host,a.port,a.topic,a.delay,a.limit)
