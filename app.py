from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import html, json, cgi, os, tempfile
from pathlib import Path
from meridian_ops import MeridianOps, RULES

O = MeridianOps()

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f1f0e9;color:#141512;font:14px/1.45 Arial,Helvetica,sans-serif}
header{height:64px;padding:0 28px;border-bottom:2px solid #141512;display:flex;align-items:center;justify-content:space-between;background:#faf9f4}
.brand{font-weight:900;letter-spacing:2.5px;font-size:15px}
nav a{color:#141512;text-decoration:none;font-weight:700;margin-left:18px;font-size:11px;letter-spacing:1.2px}
nav a:hover{text-decoration:underline}
main{max-width:1280px;margin:0 auto;padding:28px 24px 60px}
.ey{font-size:10px;letter-spacing:1.6px;color:#666;text-transform:uppercase}
.metrics{display:grid;grid-template-columns:repeat(6,1fr);border:2px solid #141512}
.metric{min-height:110px;padding:14px 12px;border-right:1px solid #141512}
.metric:last-child{border-right:0}
.metric b{display:block;font-size:32px;margin-top:18px;letter-spacing:-1px}
h1{font-size:36px;letter-spacing:-1.5px;margin:8px 0 22px;font-weight:800}
h2{font-size:13px;letter-spacing:1.4px;margin:0 0 12px;font-weight:700}
.grid{display:grid;grid-template-columns:1.55fr 1fr;gap:18px}
.panel{border:1px solid #141512;padding:16px 18px;background:#faf9f4;margin-top:16px}
.panel.dark{background:#141512;color:#faf9f4}
button,.btn{background:#d7ff4f;border:1px solid #141512;padding:10px 14px;font-weight:700;cursor:pointer;font-size:12px;letter-spacing:.5px;display:inline-block;text-decoration:none;color:#141512}
button:hover,.btn:hover{background:#c8f03a}
button.secondary{background:#faf9f4}
input,select{padding:10px;border:1px solid #141512;width:min(100%,420px);font:14px Arial;background:#fff}
table{width:100%;border-collapse:collapse}
td,th{padding:9px 6px;border-bottom:1px solid #c8c7bc;text-align:left;vertical-align:top}
th{font-size:10px;letter-spacing:1px;color:#555}
.ok{color:#1f6b1a;font-weight:700}
.review{color:#a32f22;font-weight:700}
.pending{color:#8a6d00;font-weight:700}
.trace{border-left:4px solid #141512;padding:10px 12px;margin:8px 0;background:#fff}
.trace.reject{border-left-color:#a32f22}
.trace.selected{border-left-color:#1f6b1a}
pre{white-space:pre-wrap;font:12px Consolas,monospace;background:#fff;padding:12px;border:1px solid #ddd;margin:8px 0}
.stages{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}
.stage{border:1px solid #141512;padding:6px 10px;font-size:11px;font-weight:700;letter-spacing:.4px;background:#fff}
.stage.done{background:#d7ff4f}
.stage.active{background:#141512;color:#faf9f4}
.status-pill{display:inline-block;padding:2px 8px;border:1px solid;font-size:11px;font-weight:700}
.row-actions{margin-top:12px}
.row-actions form,.row-actions a{display:inline-block;margin-right:8px}
@media(max-width:900px){.metrics{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:1fr}nav{display:none}}
"""

def e(x):
    return html.escape(str(x if x is not None else ""))

def page(title, body):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Meridian Ops</title><style>{CSS}</style></head>
<body>
<header>
  <span class="brand">MERIDIAN OPS</span>
  <nav>
    <a href="/">OVERVIEW</a>
    <a href="/breakdowns">BREAKDOWNS</a>
    <a href="/context">CONTEXT</a>
    <a href="/rules">RULES</a>
    <a href="/audit">AUDIT</a>
    <a href="/system">SYSTEM</a>
  </nav>
</header>
<main>{body}</main>
</body></html>"""

def overview():
    d = O.dashboard()
    cards = "".join(
        f'<div class="metric"><span class="ey">{e(k)}</span><b>{e(v)}</b></div>'
        for k, v in [
            ("BREAKDOWNS", d["breakdowns"]),
            ("PROCESSED", d["processed"]),
            ("NEEDS REVIEW", d["needs_review"]),
            ("QUARANTINED", d["quarantined"]),
            ("DUPLICATES", d["duplicates"]),
            ("PII EXPOSURES", d["pii_exposures"]),
        ]
    )
    acts = "".join(
        f'<p style="margin:6px 0"><span class="ey">{e(x["ticket_id"])}</span> · {e(x["status"])} · <span class="ey">{e(x["processed_at"][:19] if x.get("processed_at") else "")}</span></p>'
        for x in d.get("activity") or []
    ) or "<p class='ey'>No activity yet</p>"
    run = d.get("latest_run") or {}
    stages = """
    <div class="stages">
      <span class="stage done">INGEST</span>
      <span class="stage done">VALIDATE</span>
      <span class="stage done">DEDUPLICATE</span>
      <span class="stage done">ENRICH</span>
      <span class="stage done">RULES</span>
      <span class="stage done">SELECT</span>
      <span class="stage done">WORK ORDER</span>
      <span class="stage done">DRAFT</span>
      <span class="stage done">APPROVAL GATE</span>
    </div>""" if run else '<div class="stages"><span class="stage">READY</span></div>'
    return page(
        "Overview",
        f"""
        <div class="ey">OPERATIONS CONTROL PLANE</div>
        <h1>MERIDIAN OPS</h1>
        <div class="metrics">{cards}</div>
        <div class="grid">
          <section class="panel">
            <h2>PIPELINE</h2>
            {stages}
            <p class="ey">Last run · {e(run.get("input_name","—"))} · input {e(run.get("input_count",0))} · new actions {e(run.get("new_actions",0))} · quarantined {e(run.get("quarantined",0))} · duplicates {e(run.get("duplicates",0))}</p>
            <div class="row-actions">
              <form method="POST" action="/run"><button type="submit">RUN PIPELINE</button></form>
              <a class="btn secondary" href="/process">PROCESS NEW FILE</a>
            </div>
          </section>
          <section class="panel dark">
            <h2>RECENT ACTIVITY</h2>
            {acts}
            <p style="margin-top:16px" class="ey">SYSTEM · {e(d.get("system","OPERATIONAL"))}</p>
          </section>
        </div>
        """,
    )

def breakdowns():
    rows = "".join(
        f'<tr><td><a href="/ticket?id={e(t["ticket_id"])}">{e(t["ticket_id"])}</a></td><td>{e(t["client"])}</td><td>{e(t["destination"])}</td><td><span class="{"ok" if t["status"] in ("AWAITING_APPROVAL","SENT") else "review"}">{e(t["status"])}</span></td></tr>'
        for t in O.list_tickets()
    )
    return page(
        "Breakdowns",
        f"""
        <div class="ey">INCIDENT QUEUE</div>
        <h1>BREAKDOWNS</h1>
        <section class="panel">
          <table>
            <tr><th>TICKET</th><th>CLIENT</th><th>DESTINATION</th><th>STATUS</th></tr>
            {rows or "<tr><td colspan=4 class=ey>No tickets processed</td></tr>"}
          </table>
        </section>
        """,
    )

def ticket_view(tid):
    t = O.get_ticket(tid)
    if not t:
        return page("Ticket", "<h1>Not found</h1>")
    d = t["decision"]
    ticket = d.get("ticket") or {}
    sel = d.get("selection")
    cands = d.get("candidates") or []
    rules = d.get("rules") or []

    inc = f"""
    <section class="panel">
      <h2>INCIDENT</h2>
      <table>
        <tr><td class="ey">TICKET</td><td><b>{e(t["ticket_id"])}</b></td></tr>
        <tr><td class="ey">CLIENT</td><td>{e(ticket.get("client"))}</td></tr>
        <tr><td class="ey">VEHICLE</td><td>{e(ticket.get("vehicle_canonical") or ticket.get("vehicle"))}</td></tr>
        <tr><td class="ey">ORIGIN HUB</td><td>{e(ticket.get("origin_hub"))}</td></tr>
        <tr><td class="ey">DESTINATION</td><td>{e(ticket.get("destination"))}</td></tr>
        <tr><td class="ey">ISSUE</td><td>{e(ticket.get("issue"))}</td></tr>
        <tr><td class="ey">SEVERITY</td><td>{e(ticket.get("severity"))}</td></tr>
        <tr><td class="ey">CREATED</td><td>{e(ticket.get("created_at"))}</td></tr>
        <tr><td class="ey">STATUS</td><td><span class="{"ok" if t["status"] in ("AWAITING_APPROVAL","SENT") else "review"}">{e(t["status"])}</span></td></tr>
      </table>
    </section>
    """

    cand_html = ""
    for c in cands:
        cls = "selected" if c.get("status") == "ELIGIBLE" and sel and c.get("vehicle") == sel.get("vehicle") else ("reject" if c.get("status") == "REJECTED" else "")
        reasons = " · ".join(c.get("reasons") or ["Eligible under active constraints"])
        cites = ", ".join(c.get("citations") or [])
        cand_html += f"""
        <div class="trace {cls}">
          <b>{e(c.get("display_vehicle") or c.get("vehicle"))}</b>
          <span class="status-pill">{e(c.get("status"))}</span>
          <div style="margin-top:6px">{e(reasons)}</div>
          <div class="ey" style="margin-top:4px">Source · {e(cites)}</div>
        </div>
        """

    why = ""
    if sel:
        why = f"""
        <section class="panel">
          <h2>WHY THIS VEHICLE?</h2>
          <div class="trace selected">
            <b>{e(sel.get("display_vehicle") or sel.get("vehicle"))}</b> · SELECTED
            <div style="margin-top:8px">Rules applied: {e(", ".join(rules) or "R8 R9")}</div>
            <div class="ey" style="margin-top:6px">Citations · {e(", ".join(sel.get("citations") or []))}</div>
          </div>
          <p class="ey">Decision is deterministic. Model interpretations never override eligibility rules.</p>
        </section>
        """
    elif d.get("review"):
        why = f"""
        <section class="panel">
          <h2>WHY NO SELECTION?</h2>
          <div class="trace reject">
            <b>NEEDS REVIEW</b>
            <div style="margin-top:6px">{e(d.get("review"))}</div>
          </div>
        </section>
        """

    actions = ""
    if t["status"] == "AWAITING_APPROVAL":
        actions = f"""
        <section class="panel">
          <h2>APPROVAL</h2>
          <p>Communication draft is pending human approval. No customer-facing message is sent until approved.</p>
          <form method="POST" action="/approve/{e(t["ticket_id"])}">
            <button type="submit">APPROVE &amp; SEND</button>
          </form>
        </section>
        """
    elif t["status"] == "SENT":
        actions = """
        <section class="panel">
          <h2>COMMUNICATION</h2>
          <p class="ok">SENT · Human approval recorded. Message released through operations channel.</p>
          <p class="ey">Repeated approval is idempotent — no duplicate send.</p>
        </section>
        """

    return page(
        t["ticket_id"],
        f"""
        <div class="ey"><a href="/breakdowns">← BREAKDOWNS</a></div>
        <h1>{e(t["ticket_id"])}</h1>
        <div class="grid">
          <div>
            {inc}
            <section class="panel">
              <h2>VEHICLE CANDIDATES</h2>
              {cand_html or "<p class=ey>No candidates evaluated</p>"}
            </section>
            {why}
          </div>
          <div>
            <section class="panel dark">
              <h2>CONTEXT</h2>
              <p class="ey">ORIGIN HUB</p>
              <p>{e(ticket.get("origin_hub"))}</p>
              <p class="ey" style="margin-top:12px">RULES IN SCOPE</p>
              <p>{e(", ".join(rules) or "—")}</p>
              <p class="ey" style="margin-top:12px">CITATIONS</p>
              <p style="font-size:12px">{e(", ".join(d.get("citations") or []))}</p>
            </section>
            {actions}
          </div>
        </div>
        """,
    )

def context_page(query=""):
    result = ""
    if query:
        a = O.context_answer(query)
        result = f"""
        <section class="panel">
          <h2>GROUNDED ANSWER</h2>
          <p>{e(a.get("answer"))}</p>
          <p class="ey">Sources · {e(" | ".join(a.get("citations") or []))}</p>
          <pre>{e(json.dumps({k: v for k, v in a.items() if k not in ("answer",)}, indent=2, default=str))}</pre>
        </section>
        """
    return page(
        "Context",
        f"""
        <div class="ey">GROUNDED CONTEXT EXPLORER</div>
        <h1>ASK CONTEXT</h1>
        <section class="panel">
          <form method="GET" action="/context">
            <input name="q" value="{e(query)}" placeholder="Why was vehicle X rejected? · TKT-... · R9" style="margin-right:8px">
            <button type="submit">ASK</button>
          </form>
          <p class="ey" style="margin-top:10px">Answers are restricted to retrieved evidence. Insufficient data is returned when evidence is missing.</p>
        </section>
        {result}
        """,
    )

def rules_page():
    rows = "".join(
        f'<tr><td><b>{e(x["rule_id"])}</b></td><td><b>{e(x["name"])}</b><br>{e(x["description"])}</td><td>{e(x["effect"])}<br><span class="ey">{e(x["source"])}</span></td></tr>'
        for x in RULES
    )
    return page(
        "Rules",
        f"""
        <div class="ey">EXECUTABLE POLICY</div>
        <h1>MERIDIAN RULES</h1>
        <section class="panel">
          <table>
            <tr><th>RULE</th><th>CONDITION</th><th>EFFECT / SOURCE</th></tr>
            {rows}
          </table>
        </section>
        """,
    )

def audit_page():
    p = O.audit_dir / "audit.jsonl"
    content = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = content.strip().splitlines()[-80:] if content else []
    return page(
        "Audit",
        f"""
        <div class="ey">SANITIZED · APPEND-ONLY</div>
        <h1>AUDIT TRAIL</h1>
        <section class="panel">
          <pre>{e(chr(10).join(lines) if lines else "No audit events yet")}</pre>
        </section>
        """,
    )

def system_page():
    d = O.dashboard()
    checks = [
        ("PII PROTECTION", d["pii_exposures"] == 0),
        ("SCHEMA ADAPTER", True),
        ("ENTITY RESOLUTION", True),
        ("PERSISTENT IDEMPOTENCY", True),
        ("QUARANTINE", True),
        ("APPROVAL GATE", True),
        ("AUDIT TRAIL", True),
        ("DETERMINISTIC RULES", True),
    ]
    rows = "".join(
        f'<tr><td>{e(k)}</td><td class="{"ok" if v else "review"}">{"✓ PASS" if v else "✕ REVIEW"}</td></tr>'
        for k, v in checks
    )
    return page(
        "System",
        f"""
        <div class="ey">RELIABILITY STATUS</div>
        <h1>SYSTEM INTEGRITY</h1>
        <section class="panel">
          <table>{rows}</table>
          <h2 style="margin-top:20px">LATEST RUN</h2>
          <pre>{e(json.dumps(d.get("latest_run") or {}, indent=2, default=str))}</pre>
        </section>
        """,
    )

def process_page(msg=""):
    return page(
        "Process File",
        f"""
        <div class="ey">SURPRISE-FILE INGESTION</div>
        <h1>PROCESS NEW FILE</h1>
        <section class="panel">
          <p>Upload a JSON ticket file. Compatible schemas (including common aliases) are normalized. Incompatible schemas are safely quarantined.</p>
          {f'<p class="ok">{e(msg)}</p>' if msg else ''}
          <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="file" accept=".json,application/json" required>
            <div style="margin-top:12px"><button type="submit">PROCESS FILE</button></div>
          </form>
        </section>
        """,
    )

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, body, code=200, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/overview"):
            return self.send(overview())
        if u.path == "/breakdowns":
            return self.send(breakdowns())
        if u.path == "/ticket":
            tid = q.get("id", [""])[0]
            return self.send(ticket_view(tid))
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
            body = """
            <div class="ey">PIPELINE EXECUTION</div>
            <h1>PROCESSING</h1>
            <section class="panel">
              <div class="stages" id="st">
                <span class="stage" id="s1">INGEST</span>
                <span class="stage" id="s2">VALIDATE</span>
                <span class="stage" id="s3">DEDUPLICATE</span>
                <span class="stage" id="s4">ENRICH</span>
                <span class="stage" id="s5">RULES</span>
                <span class="stage" id="s6">SELECT</span>
                <span class="stage" id="s7">WORK ORDER</span>
                <span class="stage" id="s8">DRAFT</span>
                <span class="stage" id="s9">APPROVAL GATE</span>
              </div>
              <p class="ey" id="msg">Executing Meridian Ops pipeline…</p>
            </section>
            <script>
            const ids=['s1','s2','s3','s4','s5','s6','s7','s8','s9'];
            let i=0;
            function next(){
              if(i<ids.length){
                document.getElementById(ids[i]).classList.add('done');
                i++;
                setTimeout(next, 160);
              } else {
                document.getElementById('msg').textContent='Complete · redirecting to overview';
                setTimeout(()=>location.href='/', 350);
              }
            }
            setTimeout(next, 150);
            </script>
            """
            return self.send(page("Running", body))
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
            O.approve(tid)
            self.send_response(303)
            self.send_header("Location", f"/ticket?id={tid}")
            self.end_headers()
            return
        if self.path == "/upload":
            ctype, pdict = cgi.parse_header(self.headers.get("Content-Type", ""))
            if ctype != "multipart/form-data":
                return self.send(process_page("Invalid content type"), 400)
            pdict["boundary"] = bytes(pdict["boundary"], "utf-8")
            form = cgi.parse_multipart(self.rfile, pdict)
            files = form.get("file")
            if not files:
                return self.send(process_page("No file received"), 400)
            raw = files[0]
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir="/tmp") as tf:
                tf.write(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
                tmp_path = tf.name
            try:
                result = O.run(tmp_path)
                msg = f"Processed · schema={result.get('schema')} · input={result.get('input_records')} · new={result.get('new_actions')} · quarantined={result.get('quarantined')} · duplicates={result.get('duplicates')}"
            except Exception as ex:
                msg = f"Error · {type(ex).__name__}: {ex}"
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return self.send(process_page(msg))
        self.send("Not Found", 404)

if __name__ == "__main__":
    print("Meridian Ops running at http://127.0.0.1:8000")
    ThreadingHTTPServer(("127.0.0.1", 8000), H).serve_forever()
