# USYD CODE CITATION ACKNOWLEDGEMENT
# I declare that this file was developed with extensive assistance from OpenAI Codex.
"""Loopback-only MQTT broker for an isolated, reproducible classroom demo."""
import argparse
import asyncio
import logging
from amqtt.broker import Broker


async def serve(port):
    broker=Broker({'listeners':{'default':{'type':'tcp','bind':f'127.0.0.1:{port}'}},
      'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
    await broker.start()
    print(f'MQTT broker ready on 127.0.0.1:{port}',flush=True)
    try:await asyncio.Future()
    finally:await broker.shutdown()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=1883)
    logging.basicConfig(level=logging.WARNING)
    try:asyncio.run(serve(p.parse_args().port))
    except KeyboardInterrupt:pass
