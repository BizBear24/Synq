import json, shutil, tempfile, unittest
from pathlib import Path
from meridian_ops import MeridianOps, canonical_vehicle

class MeridianTests(unittest.TestCase):
 def setUp(self):
  self.tmp=Path(tempfile.mkdtemp()); root=Path(__file__).parent
  for f in ['fleet_master.csv','drivers_roster.csv','maintenance_log.xlsx','meridian_trips.csv','tickets.json'] : shutil.copy(root/f,self.tmp/f)
  self.ops=MeridianOps(self.tmp)
 def tearDown(self): self.ops.close(); shutil.rmtree(self.tmp)
 def test_normalize(self): self.assertEqual(canonical_vehicle('CH-81-AQ-4130'),'CH81AQ4130')
 def test_queue_and_rerun(self):
  a=self.ops.run(); b=self.ops.run(); self.assertEqual(a['input_records'],35); self.assertGreater(a['quarantined'],0); self.assertEqual(b['new_actions'],0)
  orders=(self.tmp/'outputs/work_orders.jsonl').read_text().splitlines(); self.assertEqual(len(orders),len({json.loads(x)['ticket_id'] for x in orders}))
 def test_pii_not_in_outputs(self):
  self.ops.run(); text=''.join(p.read_text() for p in (self.tmp/'outputs').glob('*.jsonl'))
  self.assertNotIn('+91',text); self.assertNotIn('Aadhaar',text)
 def test_unknown_schema_quarantines(self):
  (self.tmp/'surprise.json').write_text(json.dumps([{'what':'nope'}])); r=self.ops.run('surprise.json'); self.assertEqual(r['quarantined'],1)
 def test_alias_schema_adapts(self):
  (self.tmp/'surprise.json').write_text(json.dumps({'records':[{'id':'TKT-Z99','timestamp':'2026-08-22T10:00:00','truck':'CH81AQ4130','hub':'Chandigarh','distance':20,'dest':'Delhi','problem':'tyre','customer':'Internal'}]}))
  r=self.ops.run('surprise.json'); self.assertEqual(r['schema'],'ARRAY'); self.assertGreater(r['adapted_fields'],0)
 def test_beyond_fifty_needs_review(self):
  self.ops.run(); t=self.ops.get_ticket('TKT-0014'); self.assertEqual(t['status'],'NEEDS_REVIEW'); self.assertIn('Nearest-hub distance',t['decision']['review'])
 def test_context_is_grounded(self):
  self.ops.run(); self.assertEqual(self.ops.context_answer('nonsense')['answer'],'Insufficient data'); self.assertIn('R1',self.ops.context_answer('R1')['rule']['rule_id'])
 def test_audit_and_outputs_are_pii_clean(self):
  self.ops.run(); self.assertEqual(self.ops.pii_scan()['findings'],0)
 def test_approval_is_idempotent(self):
  self.ops.run(); ticket=next(iter(json.loads(x)['ticket_id'] for x in (self.tmp/'outputs/work_orders.jsonl').read_text().splitlines()))
  self.assertFalse(self.ops.approve(ticket)['idempotent']); self.assertTrue(self.ops.approve(ticket)['idempotent'])
if __name__=='__main__': unittest.main()
