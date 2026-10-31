# USYD CODE CITATION ACKNOWLEDGEMENT: developed with OpenAI Codex assistance.
import unittest,sys,json,hashlib,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from evstream.store import Store
from evstream.app import create_app

class StorageBoundsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT)
  db=Path(self.tmp.name)/'test.duckdb'
  shutil.copy2(ROOT/'assignment1_reference/database/ev_chargers.duckdb',db)
  self.store=Store(db)
  self.event=next(json.loads(x) for x in (ROOT/'data/demo_events.jsonl').read_text().splitlines() if json.loads(x)['type']=='session_end')
 def tearDown(self):
  self.store.close();self.tmp.cleanup()
 def send(self):
  e=self.event;e['event_id']=hashlib.sha256(json.dumps({k:v for k,v in e.items() if k!='event_id'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
  return self.store.ingest(json.dumps(e))
 def test_oversized_energy_is_quarantined_without_breaking_dashboard(self):
  self.event['payload']['energy_kwh']=1e30
  self.assertEqual(self.send(),'rejected')
  self.assertEqual(create_app(self.store).test_client().get('/api/state').status_code,200)
  self.assertEqual(self.store.snapshot()['metrics']['rejected'],1)
 def test_cost_overflow_rejected_and_decimal_boundary_accepted(self):
  self.event['payload']['cost_aud']=1e10;self.assertEqual(self.send(),'rejected')
  self.event['payload']['cost_aud']=9999999999.99;self.event['payload']['energy_kwh']=999999999.999
  self.assertEqual(self.send(),'stored');self.assertEqual(create_app(self.store).test_client().get('/api/state').status_code,200)
 def test_inconsistent_end_time_rejected(self):
  self.event['payload']['end_ts']='2020-01-01T00:00:00';self.assertEqual(self.send(),'rejected')
 def test_reviewed_address_preserves_original_record(self):
  row=self.store.query("SELECT address,address_source FROM charger_display WHERE charger_id=3")[0]
  self.assertEqual(row['address'],'82 Marsh Street, Armidale, 2350')
  self.assertEqual(row['address_source'],'ocm_reviewed_conflict')
  self.assertIn('Wilcannia',self.store.query('SELECT station_address FROM charger WHERE charger_id=3')[0]['station_address'])
