import json,sys
from pathlib import Path
from meridian_ops import MeridianOps
if "--fresh" in sys.argv:
 root=Path(__file__).parent.resolve()
 for relative in ("meridian_state.db","outputs/work_orders.jsonl","outputs/quarantine.jsonl","outputs/comms_pending.jsonl","outputs/comms_sent.jsonl","audit/audit.jsonl"):
  target=(root/relative).resolve()
  if root not in target.parents: raise RuntimeError("unsafe reset target")
  if target.exists(): target.unlink()
 args=[x for x in sys.argv[1:] if x!="--fresh"]
else: args=sys.argv[1:]
o=MeridianOps()
try:print(json.dumps(o.run(args[0] if args else "tickets.json"),indent=2))
finally:o.close()
