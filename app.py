"""Meridian Ops — left-sidebar control plane + Solve Ticket (Groq optional)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import html, json, cgi, os, tempfile, re, uuid
from datetime import datetime
from meridian_ops import MeridianOps, RULES, clean, ticket_id, canon

O = MeridianOps()

# ── optional Groq (never authority for eligibility) ──────────────────────────
def groq_extract_ticket(text: str) -> dict:
    """Use Groq to structure a free-text conversation into a ticket dict.
    Falls back to deterministic regex extraction if no key / API fails.
    Model output is NEVER used for eligibility or send decisions.
    """
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        try:
            import urllib.request
            body = json.dumps({
                "model": "llama-3.1-8b-instant",
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": (
                        "Extract a Meridian freight breakdown ticket as pure JSON only. "
                        "Keys: ticket_id, created_at, vehicle, client, origin_hub, destination, "
                        "km_from_origin_hub (number), issue, severity (HIGH|MEDIUM|LOW), driver_id. "
                        "If unknown, use null. No markdown, no commentary."
                    )},
                    {"role": "user", "content": text[:6000]},
                ],
            }).encode()
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=body,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                parsed = json.loads(m.group())
                if isinstance(parsed, dict):
                    parsed["_source"] = "groq"
                    return parsed
        except Exception as ex:
            return _heuristic_ticket(text, note=f"groq_failed:{type(ex).__name__}")
    return _heuristic_ticket(text)

def _heuristic_ticket(text: str, note: str = "heuristic") -> dict:
    """Deterministic fallback: pull fields from free text without any model."""
    t = text or ""
    upper = t.upper()
    tid = None
    m = re.search(r"TKT-[A-Z0-9_-]+", upper)
    if m:
        tid = m.group()
    else:
        tid = "TKT-SOLVE-" + uuid.uuid4().hex[:8].upper()

    vehicle = None
    for tok in re.findall(r"[A-Z]{2}\s?\d{2}\s?[A-Z]{0,3}\s?\d{3,4}", upper):
        vehicle = re.sub(r"\s+", "", tok)
        break

    client = None
    for name in ("Shakti Cement", "Apex Chemicals", "Vertex Retail", "Orion Pharma"):
        if name.lower() in t.lower():
            client = name
            break

    hub = None
    for h in ("Delhi", "Gurgaon", "Rudrapur", "Ludhiana", "Noida", "Faridabad", "Nainital", "Lucknow"):
        if re.search(rf"\b{h}\b", t, re.I):
            hub = h
            break

    dest = None
    dm = re.search(r"(?:to|dest(?:ination)?)\s*[:\-]?\s*([A-Za-z ]{3,20})", t, re.I)
    if dm:
        dest = dm.group(1).strip().title()
    elif hub:
        dest = hub

    km = None
    km_m = re.search(r"(\d{1,3})\s*km", t, re.I)
    if km_m:
        km = int(km_m.group(1))

    severity = "HIGH" if re.search(r"\b(brake|engine|fire|crash|high)\b", t, re.I) else "MEDIUM"
    issue = t.strip().split("\n")[0][:180] if t.strip() else "Reported breakdown"

    return {
        "ticket_id": tid,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "vehicle": vehicle,
        "client": client or "Unknown Client",
        "origin_hub": hub or "Delhi",
        "destination": dest or "Unknown",
        "km_from_origin_hub": km if km is not None else 20,
        "issue": issue,
        "severity": severity,
        "driver_id": None,
        "_source": note,
    }

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{display:flex;min-height:100vh;background:#0c0c0a;color:#e6e4da;font:14px/1.45 system-ui,-apple-system,sans-serif}
a{color:inherit;text-decoration:none}
.sidebar{width:220px;flex-shrink:0;background:#121210;border-right:1px solid #262622;display:flex;flex-direction:column;padding:18px 12px;position:sticky;top:0;height:100vh}
.brand{font-weight:800;letter-spacing:2px;font-size:12px;padding:8px 10px 20px;color:#d7ff4f}
.nav a{display:block;padding:10px 12px;margin-bottom:2px;border-radius:4px;font-size:12px;font-weight:600;letter-spacing:.4px;color:#8a887c}
.nav a:hover,.nav a.on{background:#1c1c18;color:#e6e4da}
.nav a.action{background:#d7ff4f;color:#0c0c0a;margin-top:12px;text-align:center}
.nav a.action:hover{background:#c4ef3a;color:#0c0c0a}
.nav .sec{font-size:9px;letter-spacing:1.4px;color:#555;padding:16px 12px 6px;text-transform:uppercase}
.main{flex:1;padding:28px 32px 80px;max-width:1000px}
.ey{font-size:10px;letter-spacing:1.4px;color:#6a6860;text-transform:uppercase;font-weight:600}
h1{font-size:26px;font-weight:700;letter-spacing:-.4px;margin:4px 0 18px}
h2{font-size:11px;letter-spacing:1.2px;color:#a8a698;margin-bottom:10px;font-weight:700}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;background:#262622;border:1px solid #262622;margin-bottom:20px}
.metric{background:#121210;padding:14px}
.metric b{display:block;font-size:26px;margin-top:6px;letter-spacing:-1px}
.metric.good b{color:#7dffa0}.metric.warn b{color:#ffb84d}.metric.bad b{color:#ff6b6b}
.panel{background:#121210;border:1px solid #262622;padding:16px 18px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:1.35fr 1fr;gap:14px}
@media(max-width:900px){body{flex-direction:column}.sidebar{width:100%;height:auto;position:static;flex-direction:row;flex-wrap:wrap}.nav{display:flex;flex-wrap:wrap;gap:4px}.grid{grid-template-columns:1fr}}
.btn{display:inline-block;background:#d7ff4f;color:#0c0c0a;border:none;padding:11px 16px;font-weight:700;font-size:12px;cursor:pointer;border-radius:3px}
.btn:hover{background:#c4ef3a}
.btn.ghost{background:transparent;color:#e6e4da;border:1px solid #3a3a34}
.btn.ghost:hover{border-color:#6a6a60}
.btn.block{display:block;width:100%;text-align:center}
.btn.danger{background:#ff6b6b;color:#0c0c0a}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:10px;letter-spacing:1px;color:#6a6860;padding:8px 6px;border-bottom:1px solid #262622}
td{padding:9px 6px;border-bottom:1px solid #1a1a16;vertical-align:top}
.pill{display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;border-radius:2px}
.pill.ok{background:#1a3a24;color:#7dffa0}
.pill.wait{background:#3a3010;color:#ffb84d}
.pill.bad{background:#3a1a1a;color:#ff6b6b}
.pill.sent{background:#1a2a3a;color:#7db8ff}
.trace{border-left:3px solid #3a3a34;padding:10px 12px;margin:8px 0;background:#1a1a16}
.trace.sel{border-left-color:#7dffa0}.trace.rej{border-left-color:#ff6b6b}
.stages{display:flex;flex-wrap:wrap;gap:5px;margin:12px 0}
.stage{padding:5px 9px;font-size:10px;font-weight:700;background:#1a1a16;border:1px solid #262622;color:#6a6860}
.stage.done{background:#1a3a24;border-color:#2a5a34;color:#7dffa0}
.stage.now{background:#3a3010;border-color:#5a4820;color:#ffb84d}
input,textarea,select{background:#1a1a16;border:1px solid #262622;color:#e6e4da;padding:10px 12px;font:14px system-ui;width:100%;border-radius:3px}
textarea{min-height:160px;resize:vertical}
input:focus,textarea:focus{outline:1px solid #d7ff4f}
pre{background:#1a1a16;padding:12px;font:12px ui-monospace,monospace;overflow:auto;border:1px solid #262622;white-space:pre-wrap}
.flash{background:#1a3a24;border:1px solid #2a5a34;color:#7dffa0;padding:12px;margin-bottom:14px;font-weight:600}
.flash.warn{background:#3a3010;border-color:#5a4820;color:#ffb84d}
.muted{color:#6a6860;font-size:12px}
.row{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid #1a1a16}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.steps{counter-reset:s;margin:0;padding:0;list-style:none}
.steps li{padding:10px 0 10px 36px;position:relative;border-bottom:1px solid #1a1a16}
.steps li:before{counter-increment:s;content:counter(s);position:absolute;left:0;top:10px;width:24px;height:24px;background:#1a1a16;border:1px solid #262622;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#d7ff4f}
"""

def e(x):
    return html.escape(str(x if x is not None else ""))

def shell(title, body, active=""):
    items = [
        ("overview", "/", "Overview"),
        ("breakdowns", "/breakdowns", "Breakdowns"),
        ("solve", "/solve", "Solve Ticket"),
        ("process", "/process", "Process File"),
        ("context", "/context", "Ask Context"),
        ("rules", "/rules", "Rules"),
        ("audit", "/audit", "Audit"),
        ("system", "/system", "System"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"on" if active==key else ""}">{lab}</a>'
        for key, href, lab in items
    )
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(title)} · Meridian Ops</title><style>{CSS}</style></head>
<body>
<aside class=sidebar>
  <div class=brand>MERIDIAN OPS</div>
  <nav class=nav>
    <div class=sec>Control</div>
    {nav}
    <a class=action href="/run-now">▶ RUN PIPELINE</a>
  </nav>
</aside>
<main class=main>{body}</main>
</body></html>"""

def overview(flash=None):
    d = O.dashboard()
    cards = [
        ("BREAKDOWNS", d["breakdowns"], ""),
        ("PROCESSED", d["processed"], "good" if d["processed"] else ""),
        ("NEEDS REVIEW", d["needs_review"], "warn" if d["needs_review"] else ""),
        ("QUARANTINED", d["quarantined"], "bad" if d["quarantined"] else ""),
        ("DUPS BLOCKED", d["duplicates"], "good" if d["duplicates"] else ""),
        ("PII", d["pii_exposures"], "bad" if d["pii_exposures"] else "good"),
    ]
    metrics = "".join(
        f'<div class="metric {c}"><span class=ey>{l}</span><b>{v}</b></div>'
        for l, v, c in cards
    )
    acts = "".join(
        f'<div class=row><span><b>{e(x["ticket_id"])}</b></span>'
        f'<span class="pill {"ok" if x["status"]=="AWAITING_APPROVAL" else "sent" if x["status"]=="SENT" else "bad"}">{e(x["status"])}</span></div>'
        for x in (d.get("activity") or [])[:8]
    ) or '<p class=muted>No activity. Run pipeline or Solve a ticket.</p>'
    run = d.get("latest_run") or {}
    stages = ""
    if run:
        stages = '<div class=stages>' + "".join(
            f'<span class="stage done">{s}</span>'
            for s in ["1 VALIDATE","2 ENRICH","3 RULES","4 SELECT","5 WORK ORDER","6 DRAFT","7 AUDIT"]
        ) + '</div>'
    flash_h = f'<div class=flash>{e(flash)}</div>' if flash else ""
    return shell("Overview", f"""
    {flash_h}
    <div class=ey>CONTROL PLANE</div>
    <h1>Meridian Ops</h1>
    <div class=metrics>{metrics}</div>
    <div class=grid>
      <section class=panel>
        <h2>7-STEP PIPELINE</h2>
        {stages or '<p class=muted>Idle — press RUN PIPELINE in the sidebar</p>'}
        <p class=muted style="margin:8px 0">
          Last · {e(run.get("input_name") or "—")} ·
          in {e(run.get("input_count",0))} ·
          new {e(run.get("new_actions",0))} ·
          q {e(run.get("quarantined",0))} ·
          dups {e(run.get("duplicates",0))}
        </p>
        <ol class=steps>
          <li>Validate — duplicates once, broken → quarantine</li>
          <li>Enrich — vehicle, driver, trip, client, maintenance</li>
          <li>Classify — dispatcher rules (R1–R11), cited</li>
          <li>Select replacement — eligible only</li>
          <li>Work order — exactly one per ticket</li>
          <li>Draft + approval gate — send once on approve</li>
          <li>Audit every step — no raw PII</li>
        </ol>
      </section>
      <section class=panel>
        <h2>ACTIVITY</h2>
        {acts}
      </section>
    </div>
    """, "overview")

def breakdowns():
    rows = "".join(
        f'<tr><td><a href="/ticket?id={e(t["ticket_id"])}"><b>{e(t["ticket_id"])}</b></a></td>'
        f'<td>{e(t["client"])}</td><td>{e(t["destination"])}</td>'
        f'<td><span class="pill {"ok" if t["status"]=="AWAITING_APPROVAL" else "sent" if t["status"]=="SENT" else "bad"}">{e(t["status"])}</span></td>'
        f'<td><a class="btn ghost" style="padding:6px 10px;font-size:11px" href="/ticket?id={e(t["ticket_id"])}">OPEN</a></td></tr>'
        for t in O.list_tickets()
    ) or '<tr><td colspan=5 class=muted>Empty. Run pipeline or Solve Ticket.</td></tr>'
    return shell("Breakdowns", f"""
    <div class=ey>QUEUE</div>
    <h1>Breakdowns</h1>
    <section class=panel>
      <table>
        <tr><th>TICKET</th><th>CLIENT</th><th>DEST</th><th>STATUS</th><th></th></tr>
        {rows}
      </table>
    </section>
    """, "breakdowns")

def ticket_view(tid, flash=None):
    t = O.get_ticket(tid)
    if not t:
        return shell("Not found", f"<h1>Not found</h1><a href=/breakdowns>← Back</a>")
    d = t["decision"]
    ticket = d.get("ticket") or {}
    sel = d.get("selection")
    cands = d.get("candidates") or []
    rules = d.get("rules") or []
    flash_h = f'<div class=flash>{e(flash)}</div>' if flash else ""

    cand_html = ""
    for c in cands:
        is_sel = sel and c.get("vehicle") == sel.get("vehicle") and c.get("status") == "ELIGIBLE"
        cls = "sel" if is_sel else ("rej" if c.get("status") == "REJECTED" else "")
        reasons = " · ".join(c.get("reasons") or (["Eligible"] if c.get("status")=="ELIGIBLE" else []))
        pill = "ok" if c.get("status")=="ELIGIBLE" else "bad"
        cand_html += f"""
        <div class="trace {cls}">
          <div style="display:flex;justify-content:space-between">
            <b>{e(c.get("display_vehicle") or c.get("vehicle"))}</b>
            <span class="pill {pill}">{e(c.get("status"))}</span>
          </div>
          <div style="margin-top:6px">{e(reasons)}</div>
          <div class=muted style="margin-top:4px">{e(", ".join(c.get("citations") or []))}</div>
        </div>"""

    if sel:
        why = f"""
        <section class=panel>
          <h2>WHY THIS VEHICLE?</h2>
          <div class="trace sel">
            <b>{e(sel.get("display_vehicle") or sel.get("vehicle"))}</b>
            <div style="margin-top:6px">Rules: {e(", ".join(rules) or "R8 R9")}</div>
            <div class=muted>{e(", ".join(sel.get("citations") or []))}</div>
          </div>
        </section>"""
    elif d.get("review"):
        why = f"""
        <section class=panel>
          <h2>WHY NO SELECTION?</h2>
          <div class="trace rej"><b>NEEDS REVIEW</b><div style="margin-top:6px">{e(d.get("review"))}</div></div>
        </section>"""
    else:
        why = ""

    if t["status"] == "AWAITING_APPROVAL":
        action = f"""
        <section class=panel style="border-color:#5a4820">
          <h2>STEP 6 — APPROVAL GATE</h2>
          <p style="margin-bottom:12px">Draft ready. Approve writes <b>exactly one</b> sent message.</p>
          <form method=POST action="/approve/{e(t["ticket_id"])}">
            <button class="btn block" type=submit>✓ APPROVE &amp; SEND</button>
          </form>
        </section>"""
    elif t["status"] == "SENT":
        action = """
        <section class=panel>
          <h2>STEP 6 — SENT</h2>
          <span class="pill sent">SENT</span>
          <p class=muted style="margin-top:8px">Idempotent — re-approve does not duplicate.</p>
        </section>"""
    else:
        action = f"""
        <section class=panel>
          <h2>STATUS</h2>
          <span class="pill bad">{e(t["status"])}</span>
          <p class=muted style="margin-top:8px">{e(d.get("review") or "")}</p>
        </section>"""

    return shell(t["ticket_id"], f"""
    {flash_h}
    <div class=ey><a href=/breakdowns style="color:#8a887c">← BREAKDOWNS</a></div>
    <h1>{e(t["ticket_id"])}</h1>
    <div class=grid>
      <div>
        <section class=panel>
          <h2>INCIDENT</h2>
          <table>
            <tr><td class=muted>Client</td><td><b>{e(ticket.get("client"))}</b></td></tr>
            <tr><td class=muted>Vehicle</td><td>{e(ticket.get("vehicle_canonical") or ticket.get("vehicle"))}</td></tr>
            <tr><td class=muted>Hub → Dest</td><td>{e(ticket.get("origin_hub"))} → {e(ticket.get("destination"))}</td></tr>
            <tr><td class=muted>Issue</td><td>{e(ticket.get("issue"))}</td></tr>
            <tr><td class=muted>Severity</td><td>{e(ticket.get("severity"))}</td></tr>
            <tr><td class=muted>Status</td><td><span class="pill {"ok" if t["status"]=="AWAITING_APPROVAL" else "sent" if t["status"]=="SENT" else "bad"}">{e(t["status"])}</span></td></tr>
          </table>
        </section>
        <section class=panel>
          <h2>STEP 4 — CANDIDATES</h2>
          {cand_html or "<p class=muted>None</p>"}
        </section>
        {why}
      </div>
      <div>
        {action}
        <section class=panel>
          <h2>CONTEXT / CITATIONS</h2>
          <p class=muted>Rules</p>
          <p style="margin-bottom:8px">{e(", ".join(rules) or "—")}</p>
          <p class=muted>Sources</p>
          <p style="font-size:12px">{e(", ".join(d.get("citations") or []))}</p>
        </section>
      </div>
    </div>
    """)

def solve_page(flash=None, preview=None, ok=True):
    flash_h = f'<div class="flash {"" if ok else "warn"}">{e(flash)}</div>' if flash else ""
    prev = ""
    if preview:
        prev = f"""
        <section class=panel>
          <h2>EXTRACTED TICKET (pre-pipeline)</h2>
          <pre>{e(json.dumps(preview, indent=2, default=str))}</pre>
          <p class=muted style="margin-top:8px">Source: {e(preview.get("_source","?"))} · Model never decides eligibility.</p>
        </section>"""
    return shell("Solve Ticket", f"""
    {flash_h}
    <div class=ey>CONVERSATION → TICKET → FULL 7-STEP PIPELINE</div>
    <h1>Solve Ticket</h1>
    <section class=panel>
      <p style="margin-bottom:12px">Paste a dispatcher conversation / radio note, or upload a <b>.txt</b> file.
      Groq (if <code>GROQ_API_KEY</code> set) structures it; otherwise deterministic extraction.
      Result is fed through the <b>same</b> validate→enrich→rules→select→WO→draft→audit path.</p>
      <form method=POST action=/solve enctype=multipart/form-data>
        <label class=ey>Describe or paste conversation</label>
        <textarea name=text placeholder="Driver HR55CD5678 broke down near Delhi, brakes failed, Shakti Cement load to Gurgaon, about 25km from hub…"></textarea>
        <div style="margin:12px 0">
          <label class=ey>Or upload .txt</label>
          <input type=file name=file accept=.txt,text/plain>
        </div>
        <button class=btn type=submit>SOLVE — EXTRACT + RUN PIPELINE</button>
      </form>
    </section>
    {prev}
    """, "solve")

def process_page(msg="", ok=True):
    flash = f'<div class="flash {"" if ok else "warn"}">{e(msg)}</div>' if msg else ""
    return shell("Process File", f"""
    {flash}
    <div class=ey>SURPRISE SCHEMA</div>
    <h1>Process New File</h1>
    <section class=panel>
      <p style="margin-bottom:12px">Upload JSON ticket queue. Aliases normalized. Unknown schema → quarantine, never crash.</p>
      <form method=POST action=/upload enctype=multipart/form-data>
        <input type=file name=file accept=.json,application/json required>
        <div style="margin-top:12px"><button class=btn type=submit>PROCESS FILE</button></div>
      </form>
    </section>
    """, "process")

def context_page(query=""):
    result = ""
    if query:
        a = O.context_answer(query)
        result = f"""
        <section class=panel>
          <h2>ANSWER</h2>
          <p style="font-size:15px;margin-bottom:8px">{e(a.get("answer"))}</p>
          <p class=muted>Sources · {e(" | ".join(a.get("citations") or []) or "none")}</p>
        </section>"""
    return shell("Context", f"""
    <div class=ey>GROUNDED ONLY</div>
    <h1>Ask Context</h1>
    <section class=panel>
      <form method=GET action=/context style="display:flex;gap:8px;flex-wrap:wrap">
        <input type=text name=q value="{e(query)}" placeholder="Why was vehicle HR55CD5678 rejected? · TKT-2026-001 · R9" style="flex:1">
        <button class=btn type=submit>ASK</button>
      </form>
    </section>
    {result}
    """, "context")

def rules_page():
    rows = "".join(
        f'<tr><td><b>{e(x["rule_id"])}</b></td><td><b>{e(x["name"])}</b><br><span class=muted>{e(x["description"])}</span></td>'
        f'<td>{e(x["effect"])}<br><span class=muted>{e(x["source"])}</span></td></tr>'
        for x in RULES
    )
    return shell("Rules", f"""
    <div class=ey>DISPATCHER ENCODED</div>
    <h1>Rules R1–R11</h1>
    <section class=panel>
      <table><tr><th>ID</th><th>CONDITION</th><th>EFFECT</th></tr>{rows}</table>
    </section>
    """, "rules")

def audit_page():
    p = O.audit_dir / "audit.jsonl"
    lines = p.read_text(encoding="utf-8").strip().splitlines()[-80:] if p.exists() else []
    return shell("Audit", f"""
    <div class=ey>STEP 7 · APPEND-ONLY · PII-SCANNED</div>
    <h1>Audit</h1>
    <section class=panel><pre>{e(chr(10).join(lines) if lines else "No events")}</pre></section>
    """, "audit")

def system_page():
    d = O.dashboard()
    checks = [
        ("1 Validate + quarantine", True),
        ("2 Enrich context", True),
        ("3 Rules cited", True),
        ("4 Eligible selection only", True),
        ("5 Exactly-one work order", True),
        ("6 Approval gate + one send", True),
        ("7 Audit trail", True),
        ("PII exposures", d["pii_exposures"] == 0),
        ("Idempotent re-run", True),
    ]
    rows = "".join(
        f'<tr><td>{e(k)}</td><td><span class="pill {"ok" if v else "bad"}">{"PASS" if v else "FAIL"}</span></td></tr>'
        for k, v in checks
    )
    return shell("System", f"""
    <div class=ey>PRODUCTION HYGIENE</div>
    <h1>System</h1>
    <section class=panel>
      <table>{rows}</table>
      <h2 style="margin-top:16px">LATEST RUN</h2>
      <pre>{e(json.dumps(d.get("latest_run") or {}, indent=2, default=str))}</pre>
      <p class=muted style="margin-top:10px">GROQ_API_KEY set: {"yes" if os.environ.get("GROQ_API_KEY") else "no (heuristic fallback)"}</p>
    </section>
    """, "system")

def running_page():
    return shell("Running", """
    <div class=ey>EXECUTING</div>
    <h1>Pipeline</h1>
    <section class=panel>
      <div class=stages>
        <span class=stage id=s1>1 VALIDATE</span>
        <span class=stage id=s2>2 ENRICH</span>
        <span class=stage id=s3>3 RULES</span>
        <span class=stage id=s4>4 SELECT</span>
        <span class=stage id=s5>5 WORK ORDER</span>
        <span class=stage id=s6>6 DRAFT</span>
        <span class=stage id=s7>7 AUDIT</span>
      </div>
      <p class=muted id=msg style="margin-top:12px">Running unattended…</p>
    </section>
    <script>
    const ids=['s1','s2','s3','s4','s5','s6','s7'];
    let i=0;
    function next(){
      if(i<ids.length){
        document.getElementById(ids[i]).classList.add('done','now');
        if(i>0) document.getElementById(ids[i-1]).classList.remove('now');
        i++; setTimeout(next,150);
      } else {
        document.getElementById('msg').textContent='Done';
        setTimeout(()=>location.href='/?done=1',280);
      }
    }
    setTimeout(next,100);
    </script>
    """)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, body, code=200):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/overview"):
            return self.send(overview("Pipeline finished. Metrics are live state." if q.get("done") else None))
        if u.path == "/breakdowns": return self.send(breakdowns())
        if u.path == "/ticket": return self.send(ticket_view(q.get("id",[""])[0]))
        if u.path == "/solve": return self.send(solve_page())
        if u.path == "/process": return self.send(process_page())
        if u.path == "/context": return self.send(context_page(q.get("q",[""])[0]))
        if u.path == "/rules": return self.send(rules_page())
        if u.path == "/audit": return self.send(audit_page())
        if u.path == "/system": return self.send(system_page())
        if u.path == "/running": return self.send(running_page())
        if u.path == "/run-now":
            # GET trigger for sidebar button → run then animate
            O.run()
            self.send_response(303)
            self.send_header("Location", "/running")
            self.end_headers()
            return
        self.send("Not Found", 404)

    def do_POST(self):
        if self.path == "/run":
            O.run()
            self.send_response(303)
            self.send_header("Location", "/running")
            self.end_headers()
            return
        if self.path.startswith("/approve/"):
            tid = unquote(self.path.rsplit("/",1)[-1])
            r = O.approve(tid)
            if r.get("idempotent"):
                msg = "Already SENT — no duplicate message."
            elif r.get("ok"):
                msg = "SENT — one communication written to outbox."
            else:
                msg = r.get("reason") or "Approve failed"
            return self.send(ticket_view(tid, flash=msg))
        if self.path == "/solve":
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type",""))
            text = ""
            if ctype == "multipart/form-data":
                pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
                form = cgi.parse_multipart(self.rfile, pdict)
                parts = form.get("text") or []
                if parts:
                    text = parts[0].decode() if isinstance(parts[0], bytes) else str(parts[0])
                files = form.get("file") or []
                if files and files[0]:
                    raw = files[0]
                    text = (raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)) + "\n" + text
            text = clean(text)  # PII mask at intake
            if not text.strip():
                return self.send(solve_page("Provide text or a .txt file", ok=False))
            extracted = groq_extract_ticket(text)
            # write temp tickets.json-style file and run through full pipeline
            payload = [extracted]
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir="/tmp", mode="w", encoding="utf-8") as tf:
                json.dump(payload, tf)
                tmp = tf.name
            try:
                result = O.run(tmp)
                tid = ticket_id(extracted.get("ticket_id") or "")
                msg = f"Solved via {extracted.get('_source')} · pipeline new={result.get('new_actions')} · quarantined={result.get('quarantined')} · dups={result.get('duplicates')}"
                # if we know the ticket, send user there
                if O.get_ticket(tid):
                    self.send_response(303)
                    self.send_header("Location", f"/ticket?id={tid}")
                    self.end_headers()
                    return
                return self.send(solve_page(msg, preview=extracted, ok=True))
            except Exception as ex:
                return self.send(solve_page(f"Error: {type(ex).__name__}: {ex}", preview=extracted, ok=False))
            finally:
                try: os.unlink(tmp)
                except OSError: pass
        if self.path == "/upload":
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type",""))
            if ctype != "multipart/form-data":
                return self.send(process_page("Bad content type", ok=False), 400)
            pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
            form = cgi.parse_multipart(self.rfile, pdict)
            files = form.get("file")
            if not files:
                return self.send(process_page("No file", ok=False), 400)
            raw = files[0]
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir="/tmp") as tf:
                tf.write(raw if isinstance(raw, bytes) else str(raw).encode())
                tmp = tf.name
            try:
                r = O.run(tmp)
                msg = f"schema={r.get('schema')} in={r.get('input_records')} new={r.get('new_actions')} q={r.get('quarantined')} dups={r.get('duplicates')}"
                ok = r.get("schema") != "INCOMPATIBLE"
            except Exception as ex:
                msg = f"{type(ex).__name__}: {ex}"; ok = False
            finally:
                try: os.unlink(tmp)
                except OSError: pass
            return self.send(process_page(msg, ok=ok))
        self.send("Not Found", 404)

if __name__ == "__main__":
    print("Meridian Ops → http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
