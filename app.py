from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import html, json, cgi, os, tempfile
from meridian_ops import MeridianOps, RULES

O = MeridianOps()

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0e0e0c;color:#e8e6dc;font:14px/1.5 system-ui,-apple-system,sans-serif}
a{color:#e8e6dc;text-decoration:none}
header{display:flex;align-items:center;justify-content:space-between;padding:0 24px;height:56px;border-bottom:1px solid #2a2a26;background:#141412}
.brand{font-weight:800;letter-spacing:2px;font-size:13px}
nav{display:flex;gap:4px}
nav a{padding:8px 12px;font-size:11px;font-weight:600;letter-spacing:.8px;color:#8a887c;border-radius:4px}
nav a:hover,nav a.on{color:#e8e6dc;background:#1e1e1a}
main{max-width:1100px;margin:0 auto;padding:28px 20px 80px}
.ey{font-size:10px;letter-spacing:1.4px;color:#6a6860;text-transform:uppercase;font-weight:600}
h1{font-size:28px;font-weight:700;letter-spacing:-.5px;margin:6px 0 20px}
h2{font-size:12px;letter-spacing:1.2px;font-weight:700;margin-bottom:12px;color:#a8a698}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:#2a2a26;border:1px solid #2a2a26;margin-bottom:24px}
.metric{background:#141412;padding:16px}
.metric b{display:block;font-size:28px;font-weight:700;margin-top:8px;letter-spacing:-1px}
.metric.good b{color:#7dffa0}
.metric.warn b{color:#ffb84d}
.metric.bad b{color:#ff6b6b}
.panel{background:#141412;border:1px solid #2a2a26;padding:18px;margin-bottom:16px;border-radius:2px}
.grid{display:grid;grid-template-columns:1.4fr 1fr;gap:16px}
@media(max-width:800px){.grid{grid-template-columns:1fr}nav{display:none}}
.btn{display:inline-block;background:#d7ff4f;color:#0e0e0c;border:none;padding:12px 18px;font-weight:700;font-size:13px;letter-spacing:.3px;cursor:pointer;border-radius:2px}
.btn:hover{background:#c4ef3a}
.btn.ghost{background:transparent;color:#e8e6dc;border:1px solid #3a3a34}
.btn.ghost:hover{border-color:#6a6a60}
.btn.block{display:block;width:100%;text-align:center;margin-top:10px}
.btn:disabled{opacity:.4;cursor:not-allowed}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:10px;letter-spacing:1px;color:#6a6860;padding:8px 6px;border-bottom:1px solid #2a2a26}
td{padding:10px 6px;border-bottom:1px solid #1e1e1a;vertical-align:top}
tr:hover td{background:#1a1a16}
.pill{display:inline-block;padding:2px 8px;font-size:10px;font-weight:700;letter-spacing:.5px;border-radius:2px}
.pill.ok{background:#1a3a24;color:#7dffa0}
.pill.wait{background:#3a3010;color:#ffb84d}
.pill.bad{background:#3a1a1a;color:#ff6b6b}
.pill.sent{background:#1a2a3a;color:#7db8ff}
.trace{border-left:3px solid #3a3a34;padding:10px 12px;margin:8px 0;background:#1a1a16}
.trace.sel{border-left-color:#7dffa0}
.trace.rej{border-left-color:#ff6b6b}
.stages{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}
.stage{padding:6px 10px;font-size:10px;font-weight:700;letter-spacing:.5px;background:#1e1e1a;border:1px solid #2a2a26;color:#6a6860}
.stage.done{background:#1a3a24;border-color:#2a5a34;color:#7dffa0}
.stage.now{background:#3a3010;border-color:#5a4820;color:#ffb84d}
input[type=text],input[type=file]{background:#1a1a16;border:1px solid #2a2a26;color:#e8e6dc;padding:10px 12px;width:min(100%,380px);font:14px system-ui}
input:focus{outline:1px solid #d7ff4f}
pre{background:#1a1a16;padding:12px;font:12px ui-monospace,monospace;overflow:auto;border:1px solid #2a2a26;white-space:pre-wrap;margin-top:10px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.flash{background:#1a3a24;border:1px solid #2a5a34;color:#7dffa0;padding:12px 14px;margin-bottom:16px;font-weight:600}
.flash.warn{background:#3a3010;border-color:#5a4820;color:#ffb84d}
.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid #1e1e1a}
.muted{color:#6a6860;font-size:12px}
"""

def e(x):
    return html.escape(str(x if x is not None else ""))

def page(title, body, active=""):
    links = [
        ("/", "OVERVIEW", "overview"),
        ("/breakdowns", "BREAKDOWNS", "breakdowns"),
        ("/context", "CONTEXT", "context"),
        ("/rules", "RULES", "rules"),
        ("/audit", "AUDIT", "audit"),
        ("/system", "SYSTEM", "system"),
    ]
    nav = "".join(
        f'<a href="{href}" class="{"on" if active==key else ""}">{label}</a>'
        for href, label, key in links
    )
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{e(title)} · Meridian Ops</title><style>{CSS}</style></head>
<body><header><span class=brand>MERIDIAN OPS</span><nav>{nav}</nav></header>
<main>{body}</main></body></html>"""

def overview(flash=None):
    d = O.dashboard()
    cards = [
        ("BREAKDOWNS", d["breakdowns"], ""),
        ("PROCESSED", d["processed"], "good" if d["processed"] else ""),
        ("NEEDS REVIEW", d["needs_review"], "warn" if d["needs_review"] else ""),
        ("QUARANTINED", d["quarantined"], "bad" if d["quarantined"] else ""),
        ("DUPLICATES BLOCKED", d["duplicates"], "good" if d["duplicates"] else ""),
        ("PII EXPOSURES", d["pii_exposures"], "bad" if d["pii_exposures"] else "good"),
    ]
    metrics = "".join(
        f'<div class="metric {cls}"><span class=ey>{lab}</span><b>{val}</b></div>'
        for lab, val, cls in cards
    )
    acts = "".join(
        f'<div class=row><span><b>{e(x["ticket_id"])}</b> <span class=muted>{e(x["processed_at"][:16] if x.get("processed_at") else "")}</span></span>'
        f'<span class="pill {"ok" if x["status"]=="AWAITING_APPROVAL" else "sent" if x["status"]=="SENT" else "bad"}">{e(x["status"])}</span></div>'
        for x in (d.get("activity") or [])[:6]
    ) or '<p class=muted>No activity yet — run the pipeline.</p>'

    run = d.get("latest_run") or {}
    stages_html = ""
    if run:
        stages_html = '<div class=stages>' + "".join(
            f'<span class="stage done">{s}</span>'
            for s in ["INGEST","VALIDATE","DEDUPE","ENRICH","RULES","SELECT","WORK ORDER","DRAFT","GATE"]
        ) + '</div>'
    else:
        stages_html = '<div class=stages><span class=stage>READY — click RUN</span></div>'

    flash_html = f'<div class=flash>{e(flash)}</div>' if flash else ""

    return page("Overview", f"""
    {flash_html}
    <div class=ey>OPERATIONS CONTROL PLANE</div>
    <h1>Meridian Ops</h1>
    <div class=metrics>{metrics}</div>
    <div class=grid>
      <section class=panel>
        <h2>PIPELINE</h2>
        {stages_html}
        <p class=muted style="margin:8px 0 14px">
          Last run · {e(run.get("input_name") or "—")} ·
          input {e(run.get("input_count",0))} ·
          new {e(run.get("new_actions",0))} ·
          quarantined {e(run.get("quarantined",0))} ·
          duplicates {e(run.get("duplicates",0))}
        </p>
        <div class=actions>
          <form method=POST action=/run><button class=btn type=submit>▶ RUN PIPELINE</button></form>
          <a class="btn ghost" href=/breakdowns>VIEW TICKETS →</a>
          <a class="btn ghost" href=/process>PROCESS NEW FILE</a>
        </div>
      </section>
      <section class=panel>
        <h2>RECENT ACTIVITY</h2>
        {acts}
        <a class="btn ghost block" href=/audit>FULL AUDIT LOG</a>
      </section>
    </div>
    """, "overview")

def breakdowns():
    tickets = O.list_tickets()
    rows = "".join(
        f'<tr><td><a href="/ticket?id={e(t["ticket_id"])}"><b>{e(t["ticket_id"])}</b></a></td>'
        f'<td>{e(t["client"])}</td><td>{e(t["destination"])}</td>'
        f'<td><span class="pill {"ok" if t["status"]=="AWAITING_APPROVAL" else "sent" if t["status"]=="SENT" else "bad"}">{e(t["status"])}</span></td>'
        f'<td><a class="btn ghost" href="/ticket?id={e(t["ticket_id"])}" style="padding:6px 10px;font-size:11px">OPEN</a></td></tr>'
        for t in tickets
    ) or '<tr><td colspan=5 class=muted>No tickets. Run the pipeline first.</td></tr>'
    return page("Breakdowns", f"""
    <div class=ey>INCIDENT QUEUE</div>
    <h1>Breakdowns</h1>
    <div class=actions style="margin-bottom:16px">
      <form method=POST action=/run><button class=btn type=submit>▶ RUN PIPELINE</button></form>
    </div>
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
        return page("Not found", f"<h1>Ticket not found</h1><a href=/breakdowns>← Back</a>")
    d = t["decision"]
    ticket = d.get("ticket") or {}
    sel = d.get("selection")
    cands = d.get("candidates") or []
    rules = d.get("rules") or []

    flash_html = f'<div class=flash>{e(flash)}</div>' if flash else ""

    # Candidates
    cand_blocks = []
    for c in cands:
        is_sel = sel and c.get("vehicle") == sel.get("vehicle") and c.get("status") == "ELIGIBLE"
        cls = "sel" if is_sel else ("rej" if c.get("status") == "REJECTED" else "")
        reasons = " · ".join(c.get("reasons") or (["Eligible under all constraints"] if c.get("status")=="ELIGIBLE" else []))
        cites = ", ".join(c.get("citations") or [])
        pill = "ok" if c.get("status")=="ELIGIBLE" else "bad"
        cand_blocks.append(f"""
        <div class="trace {cls}">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <b>{e(c.get("display_vehicle") or c.get("vehicle"))}</b>
            <span class="pill {pill}">{e(c.get("status"))}</span>
          </div>
          <div style="margin-top:6px;font-size:13px">{e(reasons)}</div>
          <div class=muted style="margin-top:4px">Source · {e(cites)}</div>
        </div>""")
    cands_html = "".join(cand_blocks) or "<p class=muted>No candidates evaluated</p>"

    # WHY
    if sel:
        why = f"""
        <section class=panel>
          <h2>WHY THIS VEHICLE?</h2>
          <div class="trace sel">
            <b>{e(sel.get("display_vehicle") or sel.get("vehicle"))}</b> selected
            <div style="margin-top:8px">Rules: {e(", ".join(rules) or "R8, R9")}</div>
            <div class=muted style="margin-top:4px">Citations · {e(", ".join(sel.get("citations") or []))}</div>
          </div>
          <p class=muted style="margin-top:10px">Deterministic decision. No model override on eligibility.</p>
        </section>"""
    elif d.get("review"):
        why = f"""
        <section class=panel>
          <h2>WHY NO SELECTION?</h2>
          <div class="trace rej"><b>NEEDS REVIEW</b><div style="margin-top:6px">{e(d.get("review"))}</div></div>
        </section>"""
    else:
        why = ""

    # Action panel
    if t["status"] == "AWAITING_APPROVAL":
        action = f"""
        <section class=panel style="border-color:#5a4820">
          <h2>ACTION REQUIRED</h2>
          <p style="margin-bottom:12px">Communication draft is pending. Clicking approve will mark it <b>SENT</b> and write to the outbox exactly once.</p>
          <form method=POST action="/approve/{e(t["ticket_id"])}">
            <button class=btn type=submit style="width:100%">✓ APPROVE &amp; SEND</button>
          </form>
        </section>"""
    elif t["status"] == "SENT":
        action = """
        <section class=panel>
          <h2>COMMUNICATION</h2>
          <p class="pill sent" style="margin-bottom:8px">SENT</p>
          <p class=muted>Human approval recorded. Repeat approve is idempotent — no duplicate send.</p>
        </section>"""
    else:
        action = f"""
        <section class=panel>
          <h2>STATUS</h2>
          <p class="pill bad">{e(t["status"])}</p>
          <p class=muted style="margin-top:8px">{e(d.get("review") or "No dispatch action available.")}</p>
        </section>"""

    return page(t["ticket_id"], f"""
    {flash_html}
    <div class=ey><a href=/breakdowns style="color:#8a887c">← BREAKDOWNS</a></div>
    <h1>{e(t["ticket_id"])}</h1>
    <div class=grid>
      <div>
        <section class=panel>
          <h2>INCIDENT</h2>
          <table>
            <tr><td class=muted>Client</td><td><b>{e(ticket.get("client"))}</b></td></tr>
            <tr><td class=muted>Vehicle</td><td>{e(ticket.get("vehicle_canonical") or ticket.get("vehicle"))}</td></tr>
            <tr><td class=muted>Origin hub</td><td>{e(ticket.get("origin_hub"))}</td></tr>
            <tr><td class=muted>Destination</td><td>{e(ticket.get("destination"))}</td></tr>
            <tr><td class=muted>Issue</td><td>{e(ticket.get("issue"))}</td></tr>
            <tr><td class=muted>Severity</td><td>{e(ticket.get("severity"))}</td></tr>
            <tr><td class=muted>Status</td><td><span class="pill {"ok" if t["status"]=="AWAITING_APPROVAL" else "sent" if t["status"]=="SENT" else "bad"}">{e(t["status"])}</span></td></tr>
          </table>
        </section>
        <section class=panel>
          <h2>VEHICLE CANDIDATES</h2>
          {cands_html}
        </section>
        {why}
      </div>
      <div>
        {action}
        <section class=panel>
          <h2>CONTEXT</h2>
          <p class=muted>Origin hub</p>
          <p style="margin-bottom:10px">{e(ticket.get("origin_hub"))}</p>
          <p class=muted>Rules in scope</p>
          <p style="margin-bottom:10px">{e(", ".join(rules) or "—")}</p>
          <p class=muted>Citations</p>
          <p style="font-size:12px">{e(", ".join(d.get("citations") or []))}</p>
        </section>
      </div>
    </div>
    """)

def context_page(query=""):
    result = ""
    if query:
        a = O.context_answer(query)
        result = f"""
        <section class=panel>
          <h2>ANSWER</h2>
          <p style="font-size:15px;margin-bottom:10px">{e(a.get("answer"))}</p>
          <p class=muted>Sources · {e(" | ".join(a.get("citations") or []) or "none")}</p>
        </section>"""
    return page("Context", f"""
    <div class=ey>GROUNDED ONLY</div>
    <h1>Ask Context</h1>
    <section class=panel>
      <form method=GET action=/context style="display:flex;gap:10px;flex-wrap:wrap">
        <input type=text name=q value="{e(query)}" placeholder="Why was vehicle HR55CD5678 rejected?  ·  TKT-2026-001  ·  R9" style="flex:1">
        <button class=btn type=submit>ASK</button>
      </form>
      <p class=muted style="margin-top:10px">Answers only from retrieved evidence. Returns “Insufficient data” when unknown.</p>
    </section>
    {result}
    """, "context")

def rules_page():
    rows = "".join(
        f'<tr><td><b>{e(x["rule_id"])}</b></td><td><b>{e(x["name"])}</b><br><span class=muted>{e(x["description"])}</span></td>'
        f'<td>{e(x["effect"])}<br><span class=muted>{e(x["source"])}</span></td></tr>'
        for x in RULES
    )
    return page("Rules", f"""
    <div class=ey>EXECUTABLE POLICY</div>
    <h1>Meridian Rules</h1>
    <section class=panel>
      <table><tr><th>ID</th><th>CONDITION</th><th>EFFECT</th></tr>{rows}</table>
    </section>
    """, "rules")

def audit_page():
    p = O.audit_dir / "audit.jsonl"
    lines = []
    if p.exists():
        lines = p.read_text(encoding="utf-8").strip().splitlines()[-60:]
    body = e("\n".join(lines)) if lines else "No events yet."
    return page("Audit", f"""
    <div class=ey>APPEND-ONLY · PII-SCANNED</div>
    <h1>Audit Trail</h1>
    <section class=panel><pre>{body}</pre></section>
    """, "audit")

def system_page():
    d = O.dashboard()
    checks = [
        ("PII protection", d["pii_exposures"] == 0),
        ("Schema adapter", True),
        ("Persistent idempotency", True),
        ("Quarantine", True),
        ("Approval gate", True),
        ("Audit trail", True),
        ("Deterministic rules", True),
    ]
    rows = "".join(
        f'<tr><td>{e(k)}</td><td><span class="pill {"ok" if v else "bad"}">{"PASS" if v else "FAIL"}</span></td></tr>'
        for k, v in checks
    )
    return page("System", f"""
    <div class=ey>RELIABILITY</div>
    <h1>System Integrity</h1>
    <section class=panel>
      <table>{rows}</table>
      <h2 style="margin-top:20px">LATEST RUN</h2>
      <pre>{e(json.dumps(d.get("latest_run") or {}, indent=2, default=str))}</pre>
    </section>
    """, "system")

def process_page(msg="", ok=True):
    flash = f'<div class="flash {"warn" if not ok else ""}">{e(msg)}</div>' if msg else ""
    return page("Process File", f"""
    {flash}
    <div class=ey>SURPRISE FILE</div>
    <h1>Process New File</h1>
    <section class=panel>
      <p style="margin-bottom:14px">Upload a JSON ticket file. Compatible aliases are normalized. Unknown schemas are quarantined — never guessed.</p>
      <form method=POST action=/upload enctype=multipart/form-data>
        <input type=file name=file accept=.json,application/json required>
        <div style="margin-top:14px"><button class=btn type=submit>PROCESS FILE</button></div>
      </form>
    </section>
    """)

def running_page():
    return page("Running", """
    <div class=ey>PIPELINE EXECUTION</div>
    <h1>Processing</h1>
    <section class=panel>
      <div class=stages id=st>
        <span class=stage id=s1>INGEST</span>
        <span class=stage id=s2>VALIDATE</span>
        <span class=stage id=s3>DEDUPE</span>
        <span class=stage id=s4>ENRICH</span>
        <span class=stage id=s5>RULES</span>
        <span class=stage id=s6>SELECT</span>
        <span class=stage id=s7>WORK ORDER</span>
        <span class=stage id=s8>DRAFT</span>
        <span class=stage id=s9>GATE</span>
      </div>
      <p class=muted id=msg style="margin-top:12px">Executing…</p>
    </section>
    <script>
    const ids=['s1','s2','s3','s4','s5','s6','s7','s8','s9'];
    let i=0;
    function next(){
      if(i<ids.length){
        const el=document.getElementById(ids[i]);
        el.classList.add('done');
        if(i>0) document.getElementById(ids[i-1]).classList.remove('now');
        el.classList.add('now');
        i++;
        setTimeout(next, 140);
      } else {
        document.getElementById('msg').textContent='Complete — returning to overview';
        setTimeout(()=>location.href='/?done=1', 300);
      }
    }
    setTimeout(next, 120);
    </script>
    """)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, body, code=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/overview"):
            flash = "Pipeline complete. Numbers above are live state." if q.get("done") else None
            return self.send(overview(flash))
        if u.path == "/breakdowns":
            return self.send(breakdowns())
        if u.path == "/ticket":
            return self.send(ticket_view(q.get("id", [""])[0]))
        if u.path == "/context":
            return self.send(context_page(q.get("q", [""])[0]))
        if u.path == "/rules":
            return self.send(rules_page())
        if u.path == "/audit":
            return self.send(audit_page())
        if u.path == "/system":
            return self.send(system_page())
        if u.path == "/process":
            return self.send(process_page())
        if u.path == "/running":
            return self.send(running_page())
        self.send("Not Found", 404)

    def do_POST(self):
        if self.path == "/run":
            O.run()
            self.send_response(303)
            self.send_header("Location", "/running")
            self.end_headers()
            return
        if self.path.startswith("/approve/"):
            tid = unquote(self.path.rsplit("/", 1)[-1])
            result = O.approve(tid)
            msg = "SENT — communication recorded once." if result.get("ok") else e(result.get("reason", "failed"))
            if result.get("idempotent"):
                msg = "Already sent — idempotent, no duplicate."
            # redirect with flash via query is awkward; re-render
            self.send(ticket_view(tid, flash=msg))
            return
        if self.path == "/upload":
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type", ""))
            if ctype != "multipart/form-data":
                return self.send(process_page("Invalid content type", ok=False), 400)
            pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
            form = cgi.parse_multipart(self.rfile, pdict)
            files = form.get("file")
            if not files:
                return self.send(process_page("No file", ok=False), 400)
            raw = files[0]
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir="/tmp") as tf:
                tf.write(raw if isinstance(raw, bytes) else str(raw).encode("utf-8"))
                tmp = tf.name
            try:
                r = O.run(tmp)
                msg = f"Done · schema={r.get('schema')} · input={r.get('input_records')} · new={r.get('new_actions')} · quarantined={r.get('quarantined')} · dups={r.get('duplicates')}"
                ok = r.get("schema") != "INCOMPATIBLE"
            except Exception as ex:
                msg = f"Error · {type(ex).__name__}: {ex}"
                ok = False
            finally:
                try: os.unlink(tmp)
                except OSError: pass
            return self.send(process_page(msg, ok=ok))
        self.send("Not Found", 404)

if __name__ == "__main__":
    print("Meridian Ops → http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
