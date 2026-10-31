# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Flask dashboard and durable MQTT subscriber share one DuckDB owner."""
import argparse
from datetime import datetime
from decimal import Decimal
import json
import logging
import threading
from pathlib import Path
import paho.mqtt.client as mqtt
from flask import Flask,Response,send_from_directory
from .common import ROOT,DEFAULT_DB,DEFAULT_TOPIC
from .store import Store


def json_response(obj):
    return Response(json.dumps(obj,default=lambda x:x.isoformat() if isinstance(x,datetime) else float(x) if isinstance(x,Decimal) else str(x)),mimetype='application/json')


def create_app(store,status=None):
    app=Flask(__name__,static_folder=str(ROOT/'static'))
    status=status if status is not None else {'connected':False,'subscribed':False,'last_error':None}
    @app.get('/')
    def index():return send_from_directory(ROOT/'static','index.html')
    @app.get('/api/state')
    def state():
        result=store.snapshot();result['mqtt']=dict(status);return json_response(result)
    @app.get('/api/station/<station>')
    def station(station):
        if station not in store.capacity:return json_response({'error':'Unknown station'}),404
        return json_response(store.detail(station))
    @app.get('/health')
    def health():return json_response({'ok':True,**status})
    return app


def subscribe(store,host,port,topic,status):
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='comp5339-dashboard',
                       clean_session=False,protocol=mqtt.MQTTv311,manual_ack=True)
    client.max_inflight_messages_set(1)
    def connect(c,u,flags,reason,props):
        status['connected']=not reason.is_failure
        if status['connected']:c.subscribe(topic,qos=1)
        else:status['last_error']=str(reason)
    def subscribed(c,u,mid,reasons,props):
        status['subscribed']=all(not r.is_failure for r in reasons)
        print('MQTT subscription ready',flush=True)
    def disconnected(c,u,flags,reason,props):
        status['connected']=False;status['subscribed']=False
    def message(c,u,msg):
        try:
            outcome=store.ingest(msg.payload,msg.topic)
            if outcome=='rejected':logging.warning('Message rejected; inspect rejected_message')
            # Acknowledge only after the event or quarantine record is committed.
            if msg.qos:c.ack(msg.mid,msg.qos)
        except Exception as exc:
            status['last_error']=str(exc);logging.exception('Storage failure; delivery unacknowledged')
            c.disconnect()
    client.on_connect=connect;client.on_subscribe=subscribed;client.on_disconnect=disconnected;client.on_message=message
    client.reconnect_delay_set(1,10);client.connect_async(host,port,60);client.loop_start()
    return client


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=DEFAULT_DB)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=1883)
    p.add_argument('--http-port',type=int,default=8050);p.add_argument('--topic',default=DEFAULT_TOPIC)
    a=p.parse_args();store=Store(a.db);status={'connected':False,'subscribed':False,'last_error':None}
    client=subscribe(store,a.host,a.port,a.topic,status)
    try:create_app(store,status).run(host='127.0.0.1',port=a.http_port,debug=False,use_reloader=False)
    finally:client.disconnect();client.loop_stop();store.close()
