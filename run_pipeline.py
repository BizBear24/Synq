#!/usr/bin/env python3
"""Run the Meridian Ops pipeline once. Use --fresh to reset durable state."""
import json, sys, shutil
from pathlib import Path
from meridian_ops import MeridianOps

def reset_state():
    state = Path("/tmp/meridian_ops_state")
    if state.exists():
        shutil.rmtree(state)
        print("Reset /tmp/meridian_ops_state")
    # also clean legacy local artifacts if present
    root = Path(__file__).parent
    for name in ("meridian_state.db", "outputs", "audit"):
        p = root / name
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--fresh"]
    if "--fresh" in sys.argv:
        reset_state()
    o = MeridianOps()
    try:
        src = args[0] if args else "tickets.json"
        print(json.dumps(o.run(src), indent=2))
    finally:
        o.close()
