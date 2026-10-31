#!/usr/bin/env python3
# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Convenience launcher; run `python run.py --help` from the project root."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','generate','serve','demo','publish'])
    parser.add_argument('--demo',action='store_true',help='Publish the 3-device demonstration stream')
    parser.add_argument('--limit',type=int,default=None)
    parser.add_argument('--delay',type=float,default=.1)
    parser.add_argument('--db',type=Path,default=ROOT/'database/ev_stream.duckdb')
    parser.add_argument('--fresh',action='store_true',help='Use a new timestamped demo database, preserving existing databases')
    args=parser.parse_args()
    os.chdir(ROOT)
    env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONUNBUFFERED':'1'}
    def run(module,extra=()):
        return subprocess.run([sys.executable,'-m',module,*extra],env=env,check=True)
    if args.command=='prepare':run('evstream.prepare',['--db',str(args.db)]);return
    if args.command=='generate':
        cache=ROOT/'data/generated/aemo_cache/PRICE_AND_DEMAND_202609_NSW1.csv'
        if not cache.exists():print('AEMO cache absent; instructor generator will download real NSW1 prices.')
        subprocess.run([sys.executable,str(ROOT/'COMP5339_2026s2_Assignment2_data _generator/generate_dataset.py'),
          '--stations','data/stations_input.csv','--start','2026-09-01','--days','1',
          '--meter-every','5','--seed','5339','--out','data/generated'],check=True,env=env)
        run('evstream.events');return
    if args.command=='publish':
        from evstream.publisher import publish
        publish(ROOT/('data/demo_events.jsonl' if args.demo else 'data/events.jsonl'),delay=args.delay,limit=args.limit)
        return
    children=[]
    try:
        database=args.db.resolve()
        if args.fresh:
            from datetime import datetime
            database=ROOT/'database'/f'demo_{datetime.now():%Y%m%d_%H%M%S_%f}.duckdb'
        if not database.exists():
            from evstream.prepare import prepare
            prepare(database)
        for module in ['evstream.broker','evstream.app']:
            extra=['--db',str(database)] if module=='evstream.app' else []
            children.append(subprocess.Popen([sys.executable,'-m',module,*extra],env=env))
            time.sleep(.6)
            if children[-1].poll() is not None:raise RuntimeError(f'{module} failed. Check occupied ports or database locks.')
        for _ in range(50):
            if any(c.poll() is not None for c in children):raise RuntimeError('A service exited')
            try:
                import json
                with urllib.request.urlopen('http://127.0.0.1:8050/health',timeout=1) as r:
                    if json.load(r).get('subscribed'):break
            except (OSError,ValueError):pass
            time.sleep(.2)
        else:raise TimeoutError('MQTT subscriber was not ready')
        print('Dashboard ready: http://127.0.0.1:8050 (Ctrl+C stops services)',flush=True)
        if args.command=='demo':
            from evstream.publisher import publish
            publish(ROOT/'data/demo_events.jsonl',delay=args.delay,limit=args.limit)
            print('Demo replay finished. Dashboard remains available. Replaying identical events is idempotent.')
        while True:
            if any(c.poll() is not None for c in children):raise RuntimeError('A service exited')
            time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for c in reversed(children):
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=8)
            except subprocess.TimeoutExpired:c.kill();c.wait()


if __name__=='__main__':main()
