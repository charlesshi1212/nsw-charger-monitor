# USYD CODE CITATION ACKNOWLEDGEMENT
# Developed with extensive assistance from OpenAI Codex.
"""Validate real MQTT pacing, storage and duplicate replay in an isolated demo.

Run from the project root: python scripts/validate_mqtt_pacing.py
Requires only requirements.txt; leaves the packaged databases unchanged.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import paho.mqtt.client as mqtt
from evstream.publisher import publish


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def validate(delay, result):
    source = ROOT / 'data/demo_events.jsonl'
    events = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    expected_kwh = sum((Decimal(str(e['payload']['energy_kwh'])) for e in events
                        if e['type'] == 'session_end'), Decimal(0))
    result.update({
        'passed': False,
        'python': sys.version,
        'platform': platform.platform(),
        'delay_seconds': delay,
        'clock': vars(time.get_clock_info('perf_counter')),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_event_types': dict(Counter(e['type'] for e in events)),
        'measurement': 'perf_counter_ns at entry to the real Paho publish wrapper; intervals checked separately for each replay',
    })
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, (str(ROOT / 'src'), env.get('PYTHONPATH'))))
    env['PYTHONUNBUFFERED'] = '1'
    broker_port, http_port = free_port(), free_port()
    while http_port == broker_port:
        http_port = free_port()

    def fetch(path):
        with urllib.request.urlopen(f'http://127.0.0.1:{http_port}{path}', timeout=10) as response:
            return json.load(response)

    original_publish = mqtt.Client.publish
    stamps = []

    def traced_publish(client, *args, **kwargs):
        stamps.append(time.perf_counter_ns())
        return original_publish(client, *args, **kwargs)

    with tempfile.TemporaryDirectory(prefix='comp5339-pacing-') as temporary:
        folder = Path(temporary)
        database = folder / 'validation.duckdb'
        shutil.copy2(ROOT / 'assignment1_reference/database/ev_chargers.duckdb', database)
        children, logs = [], []
        try:
            services = [
                ('evstream.broker', ['--port', str(broker_port)]),
                ('evstream.app', ['--port', str(broker_port), '--http-port', str(http_port),
                                 '--db', str(database)]),
            ]
            for module, args in services:
                log = (folder / f'{module}.log').open('w', encoding='utf-8')
                logs.append(log)
                children.append(subprocess.Popen(
                    [sys.executable, '-m', module, *args], env=env,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                ))
            ready_deadline = time.perf_counter() + 25
            while time.perf_counter() < ready_deadline:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('A validation service exited before readiness')
                try:
                    if fetch('/health')['subscribed']:
                        break
                except OSError:
                    pass
                time.sleep(.1)
            else:
                raise TimeoutError('MQTT subscriber did not become ready')

            initial = fetch('/api/state')['metrics']
            if initial['events'] != 0:
                raise AssertionError('Validation database must start empty')
            mqtt.Client.publish = traced_publish
            started = time.perf_counter_ns()
            published = publish(source, port=broker_port, delay=delay)
            result['elapsed_seconds'] = (time.perf_counter_ns() - started) / 1_000_000_000
            main_stamps = list(stamps)

            receive_deadline = time.perf_counter() + 15
            while time.perf_counter() < receive_deadline:
                received = fetch('/api/state')['metrics']
                if received['events'] == len(events):
                    break
                time.sleep(.1)
            else:
                raise TimeoutError('Not all demo events were committed')

            if published != len(events) or len(main_stamps) != len(events):
                raise AssertionError('Publication count differs from source')
            if received['completed'] != sum(e['type'] == 'session_end' for e in events):
                raise AssertionError('Completed-session total differs from source')
            if Decimal(str(received['kwh'])) != expected_kwh:
                raise AssertionError('Energy total differs from source')
            if received['active'] != 0 or received['rejected'] != 0:
                raise AssertionError('Complete valid demo must have no active/rejected events')

            stamps.clear()
            duplicate_sends = publish(source, port=broker_port, delay=delay, limit=10)
            time.sleep(.5)
            after_duplicates = fetch('/api/state')['metrics']
            if after_duplicates != received:
                raise AssertionError('Duplicate replay changed stored metrics')

            main_intervals = [b - a for a, b in zip(main_stamps, main_stamps[1:])]
            duplicate_intervals = [b - a for a, b in zip(stamps, stamps[1:])]
            required_ns = math.ceil(delay * 1_000_000_000)
            intervals = main_intervals + duplicate_intervals
            result.update({
                'main_sends': published,
                'duplicate_sends': duplicate_sends,
                'minimum_interval_seconds': min(intervals) / 1_000_000_000,
                'intervals_below_requested_delay': sum(value < required_ns for value in intervals),
                'intervals_below_0_1_seconds': sum(value < 100_000_000 for value in intervals),
                'main_publish_times_ns': main_stamps,
                'main_intervals_ns': main_intervals,
                'duplicate_intervals_ns': duplicate_intervals,
                'after_demo': received,
                'after_duplicate_replay': after_duplicates,
                'duplicate_metrics_unchanged': True,
            })
            if any(value < required_ns for value in intervals):
                raise AssertionError('At least one publication interval was too short')
            result['passed'] = True
        except Exception:
            for log in logs:
                log.flush()
            result['service_log_tails'] = {
                path.name: path.read_text(encoding='utf-8', errors='replace')[-4000:]
                for path in folder.glob('*.log')
            }
            raise
        finally:
            mqtt.Client.publish = original_publish
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            for log in logs:
                log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=.1)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/publisher_timing_validation.json')
    args = parser.parse_args()
    result = {}
    try:
        validate(args.delay, result)
    except Exception as exc:
        result.update({'passed': False, 'error': f'{type(exc).__name__}: {exc}'})
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    summary_keys = ('passed', 'main_sends', 'duplicate_sends', 'minimum_interval_seconds',
                    'intervals_below_0_1_seconds', 'after_demo', 'duplicate_metrics_unchanged')
    print(json.dumps({key: result[key] for key in summary_keys}, indent=2))


if __name__ == '__main__':
    main()
