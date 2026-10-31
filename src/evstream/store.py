# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Single-process DuckDB ownership; validated, transactional, idempotent ingestion."""
from decimal import Decimal
import csv
import hashlib
import json
import math
import threading
import uuid
from datetime import datetime
import duckdb
from .common import ROOT, DEFAULT_DB


class Store:
    def __init__(self,path=DEFAULT_DB):
        self.lock=threading.RLock()
        self.con=duckdb.connect(str(path))
        self.con.execute("SET TimeZone='Australia/Brisbane'")
        self.con.execute((ROOT/'sql/stream_schema.sql').read_text())
        self.con.execute((ROOT/'sql/charger_display.sql').read_text(encoding='utf-8'))
        with (ROOT/'data/stations_input.csv').open(newline='') as f:
            for r in csv.DictReader(f):
                self.con.execute('INSERT INTO stream_station VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING',
                   [r['station_id'],int(r['charger_id']),int(r['connectors']),r['site_type'],float(r['max_kw'])])
        self.capacity=dict(self.con.execute('SELECT station_id,connectors FROM stream_station').fetchall())

    def close(self):
        with self.lock:self.con.close()

    def validate(self,e):
        if not isinstance(e,dict):raise ValueError('Event must be an object')
        required={'event_id','dataset_id','sequence','type','event_time','station_id','payload','schema_version'}
        if not required<=e.keys():raise ValueError('Missing envelope fields')
        if e['schema_version']!=1:raise ValueError('Unsupported schema version')
        if e['type'] not in {'price_update','session_start','session_end','meter'}:raise ValueError('Unknown event type')
        if e['station_id'] not in self.capacity:raise ValueError('Unknown station_id')
        if type(e['sequence']) is not int or e['sequence']<0:raise ValueError('Invalid sequence')
        if not isinstance(e['dataset_id'],str) or not e['dataset_id']:raise ValueError('Invalid dataset_id')
        canonical={k:v for k,v in e.items() if k!='event_id'}
        expected=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if e['event_id']!=expected:raise ValueError('Event ID does not match content')
        ts=datetime.fromisoformat(e['event_time'])
        if ts.tzinfo is None:raise ValueError('Event time requires timezone')
        p=e['payload']
        if not isinstance(p,dict) or p.get('station_id')!=e['station_id']:raise ValueError('Payload station mismatch')
        fields={'price_update':['price_per_kwh','wholesale_per_kwh'],
                'session_start':['session_id','connector_id','start_ts','price_per_kwh','vehicle_model'],
                'session_end':['session_id','connector_id','start_ts','end_ts','energy_kwh','cost_aud','charge_minutes'],
                'meter':['session_id','connector_id','voltage_v','current_a','power_kw','energy_kwh','soc_pct']}[e['type']]
        if any(k not in p for k in fields):raise ValueError('Missing event payload fields')
        for k in ('price_per_kwh','energy_kwh','cost_aud','power_kw','voltage_v','current_a','soc_pct','charge_minutes','wholesale_per_kwh'):
            if k in p and (type(p[k]) not in (int,float) or not math.isfinite(p[k]) or (k!='wholesale_per_kwh' and p[k]<0)):
                raise ValueError(f'Invalid {k}')
        # Validate every value cast by analytical views before committing JSON.
        for field, maximum in [('energy_kwh', '999999999.999'), ('cost_aud', '9999999999.99')]:
            if field in p and Decimal(str(p[field])) > Decimal(maximum):
                raise ValueError(f'{field} exceeds analytical DECIMAL range')
        if e['type'] in {'session_start', 'session_end'}:
            def payload_time(value):
                value = datetime.fromisoformat(value)
                return value.replace(tzinfo=ts.tzinfo) if value.tzinfo is None else value
            start = payload_time(p['start_ts'])
            if e['type'] == 'session_start' and start != ts:
                raise ValueError('Start timestamp differs from event time')
            if e['type'] == 'session_end':
                end = payload_time(p['end_ts'])
                if end < start or end != ts:
                    raise ValueError('Invalid end timestamp or lifecycle ordering')
        if 'soc_pct' in p and p['soc_pct']>100:raise ValueError('Invalid state of charge')
        if e['type']!='price_update':
            if not isinstance(p['session_id'],str) or not p['session_id']:raise ValueError('Missing session ID')
            if type(p['connector_id']) is not int or not 1<=p['connector_id']<=self.capacity[e['station_id']]:raise ValueError('Invalid connector')
        return p

    def ingest(self,raw,topic='offline-validation'):
        if isinstance(raw,bytes):raw=raw.decode('utf-8',errors='replace')
        with self.lock:
            try:
                e=json.loads(raw);p=self.validate(e)
                self.con.execute('BEGIN')
                existing=self.con.execute('SELECT dataset_id FROM stream_event LIMIT 1').fetchone()
                if existing and existing[0]!=e['dataset_id']:
                    raise ValueError('A database stores one generated dataset; use a fresh database for a different run')
                # Duplicate deliveries are acknowledged, but do not inflate metrics.
                if self.con.execute('SELECT 1 FROM stream_event WHERE event_id=?',[e['event_id']]).fetchone():
                    self.con.execute('COMMIT');return 'duplicate'
                self.con.execute('INSERT INTO stream_event(event_id,dataset_id,sequence,event_type,event_time,station_id,session_id,connector_id,payload) VALUES (?,?,?,?,?,?,?,?,?)',
                    [e['event_id'],e['dataset_id'],e['sequence'],e['type'],e['event_time'],e['station_id'],p.get('session_id'),p.get('connector_id'),json.dumps(p)])
                self.con.execute('COMMIT');return 'stored'
            except Exception as exc:
                try:self.con.execute('ROLLBACK')
                except duckdb.Error:pass
                self.con.execute('INSERT INTO rejected_message(receipt_id,topic,raw_payload,reason) VALUES (?,?,?,?)',
                    [uuid.uuid4().hex,topic,raw,str(exc)])
                return 'rejected'

    def query(self,sql,args=None):
        with self.lock:
            cur=self.con.execute(sql,args or []);cols=[d[0] for d in cur.description]
            return [dict(zip(cols,r)) for r in cur.fetchall()]

    def snapshot(self):
        with self.lock:
            return self._snapshot()

    def _snapshot(self):
        stations=self.query("""
         SELECT s.station_id,c.charger_id,l.location_id,d.name,d.name_source,d.address,d.address_source,
         o.source_operator_name AS "operator",l.latitude lat,l.longitude lon,s.connectors,s.max_kw,
         coalesce(p.price_per_kwh,NULL) price, p.event_time price_time,
         coalesce(a.active,0) active,coalesce(h.completed_sessions,0) completed,
         coalesce(h.delivered_kwh,0) delivered_kwh,coalesce(h.revenue_aud,0) revenue_aud,
         d.plug_types,d.plug_types_source,
         (SELECT max(event_time) FROM stream_event e WHERE e.station_id=s.station_id) last_event
         FROM stream_station s JOIN charger c USING(charger_id)
         JOIN charger_display d USING(charger_id)
         JOIN charger_location l USING(location_id) JOIN operator o USING(operator_id)
         LEFT JOIN latest_price p USING(station_id)
         LEFT JOIN (SELECT station_id,count(*) active FROM active_session GROUP BY station_id) a USING(station_id)
         LEFT JOIN station_history h USING(station_id) ORDER BY s.station_id
        """)
        metrics=self.query("""SELECT
          (SELECT count(*) FROM stream_event) events,
          (SELECT count(*) FROM active_session) active,
          (SELECT count(*) FROM charging_session WHERE end_time IS NOT NULL) completed,
          (SELECT coalesce(sum(energy_kwh),0) FROM charging_session WHERE end_time IS NOT NULL) kwh,
          (SELECT count(*) FROM rejected_message) rejected,
          (SELECT max(event_time) FROM stream_event) watermark""")[0]
        metrics['observed_stations']=sum(s['last_event'] is not None for s in stations)
        return {'stations':stations,'metrics':metrics}

    def detail(self,station):
        with self.lock:
            return self._detail(station)

    def _detail(self,station):
        sessions=self.query('SELECT * FROM charging_session WHERE station_id=? ORDER BY start_time DESC NULLS LAST LIMIT 30',[station])
        active=self.query('SELECT * FROM active_session WHERE station_id=? ORDER BY start_time DESC',[station])
        # An older session may remain active while many newer sessions finish.
        # Include every active session even when it lies outside recent history.
        recent_ids={s['session_id'] for s in sessions}
        sessions.extend(s for s in active if s['session_id'] not in recent_ids)
        ids=[s['session_id'] for s in active]
        if not ids and sessions:ids=[sessions[0]['session_id']]
        curves=[]
        for sid in ids:
            curves.append({'session_id':sid,'points':self.query("""
             SELECT event_time,CAST(json_extract(payload,'$.power_kw') AS DOUBLE) power_kw,
             CAST(json_extract(payload,'$.energy_kwh') AS DOUBLE) energy_kwh,
             CAST(json_extract(payload,'$.soc_pct') AS DOUBLE) soc_pct
             FROM stream_event WHERE event_type='meter' AND session_id=? ORDER BY event_time,sequence
            """,[sid])})
        return {'sessions':sessions,'curves':curves}
