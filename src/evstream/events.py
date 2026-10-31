# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Convert instructor CSVs to deterministic, chronologically ordered JSON events."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter
from .common import ROOT

NUMERIC = {'price_per_kwh','wholesale_per_kwh','charge_minutes','energy_kwh','avg_kw',
           'peak_kw','cost_aud','voltage_v','current_a','power_kw','soc_pct'}
PRIORITY = {'price_update':0,'session_end':1,'session_start':2,'meter':3}


def typed(row):
    return {k:float(v) if k in NUMERIC else int(v) if k=='connector_id' else v for k,v in row.items()}


def convert(folder, destination):
    events=[]
    def add(kind,ts,row):
        payload=typed(row)
        events.append({'schema_version':1,'type':kind,'event_time':ts+'+10:00',
                       'station_id':row['station_id'],'payload':payload})
    def rows(name):
        with (folder/name).open(newline='') as f:
            yield from csv.DictReader(f)
    last={}
    prices=sorted(rows('prices_hourly.csv'),key=lambda r:(r['ts'],r['station_id']))
    for r in prices:
        price=float(r['price_per_kwh'])
        if last.get(r['station_id'])!=price:
            add('price_update',r['ts'],r);last[r['station_id']]=price
    for r in rows('sessions.csv'):
        # Future outcomes are deliberately excluded from start messages.
        start={k:r[k] for k in ['station_id','session_id','connector_id','vehicle_model','start_ts','price_per_kwh']}
        add('session_start',r['start_ts'],start)
        add('session_end',r['end_ts'],r)
    for r in rows('session_metering.csv'):
        add('meter',r['ts'],{k:v for k,v in r.items() if k!='type'})
    events.sort(key=lambda e:(e['event_time'],PRIORITY[e['type']],e['station_id'],e['payload'].get('session_id','')))
    # Dataset identity prevents collisions between differently generated runs.
    dataset_id=hashlib.sha256(json.dumps(events,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]
    for seq,e in enumerate(events):
        e['sequence']=seq;e['dataset_id']=dataset_id
        e['event_id']=hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(''.join(json.dumps(e,separators=(',',':'))+'\n' for e in events))
    # Three representative devices, chosen deterministically: inexpensive, fast and regional.
    stations=list(rows('stations.csv'))
    selected=[]
    for key in [lambda r:float(r['max_kw']),lambda r:-float(r['max_kw']),lambda r:0 if r['site_type']=='regional' else 1]:
        for r in sorted(stations,key=key):
            if r['station_id'] not in selected:
                selected.append(r['station_id']);break
    demo=[e for e in events if e['station_id'] in selected]
    (destination.parent/'demo_events.jsonl').write_text(''.join(json.dumps(e,separators=(',',':'))+'\n' for e in demo))
    summary={'dataset_id':dataset_id,'events':len(events),'types':dict(Counter(e['type'] for e in events)),
             'suppressed_unchanged_prices':len(prices)-sum(e['type']=='price_update' for e in events),
             'demo_stations':selected,'demo_events':len(demo),'first_event':events[0]['event_time'],
             'last_event':events[-1]['event_time']}
    (destination.parent/'generation_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'data/generated')
    p.add_argument('--output',type=Path,default=ROOT/'data/events.jsonl');a=p.parse_args();convert(a.input,a.output)
