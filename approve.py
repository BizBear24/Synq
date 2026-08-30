import json,sys
from meridian_ops import MeridianOps
if len(sys.argv)!=2:raise SystemExit("Usage: python approve.py TKT-0001")
o=MeridianOps()
try:print(json.dumps(o.approve(sys.argv[1]),indent=2))
finally:o.close()
