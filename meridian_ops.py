"""PII-safe deterministic Meridian Ops pipeline."""
from __future__ import annotations
import csv, hashlib, json, re, sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from openpyxl import load_workbook

ROOT=Path(__file__).parent
TKT=re.compile(r"^TKT-[A-Z0-9_-]{1,40}$",re.I)
PHONE=re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b"); AAD=re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"); DL=re.compile(r"\b[A-Z]{2}\d{2}\s?\d{11,}\b",re.I)
RULES=[
 {"rule_id":"R1","name":"Delhi NCR winter emissions","description":"October-February routes touching Delhi, Gurgaon, Faridabad or Noida require BS6.","effect":"Hard eligibility constraint","source":"dispatcher_interview.txt:routes"},
 {"rule_id":"R2","name":"Winter hill safety","description":"November-February Rudrapur/Nainital routes require engine heater and no brake work in prior 30 days.","effect":"Hard eligibility constraint","source":"dispatcher_interview.txt:hill routes"},
 {"rule_id":"R3","name":"Shakti operating SLA","description":"Plan Shakti loads to a 36-hour operating window, not legacy 48-hour contract language.","effect":"Communication/context","source":"dispatcher_interview.txt:clients; emails/thread_01_shakti_sla.txt"},
 {"rule_id":"R4","name":"Vertex Ludhiana gate","description":"After 18:00, hold for scheduled 08:00 delivery; never record failed delivery.","effect":"Communication/delivery status","source":"dispatcher_interview.txt:clients; emails/thread_09_vertex_gate.txt"},
 {"rule_id":"R5","name":"Apex vehicle rotation","description":"After an Apex incident, that vehicle cannot serve the immediately next Apex dispatch.","effect":"Hard eligibility constraint","source":"dispatcher_interview.txt:clients; emails/thread_13_apex_rotation.txt"},
 {"rule_id":"R6","name":"Orion compliant newest vehicle","description":"Orion requires model year 2020+ and the newest eligible vehicle; unrefrigerated overnight waits are prohibited.","effect":"Hard year constraint; cold chain review","source":"dispatcher_interview.txt:clients; emails/thread_17_orion_age.txt"},
 {"rule_id":"R7","name":"Monsoon eastern ETA","description":"July-September, routes east of Lucknow get 20% ETA padding and no standard SLA promise.","effect":"Communication/context","source":"dispatcher_interview.txt:monsoon; emails/thread_23_internal_monsoon.txt"},
 {"rule_id":"R8","name":"Breakdown replacement hub","description":"Within 50km of origin, source origin hub; beyond 50km use nearest eligible hub.","effect":"Hard sourcing constraint","source":"dispatcher_interview.txt:breakdowns"},
 {"rule_id":"R9","name":"Service grounding","description":"Vehicle over 30 days past an explicitly recorded service due date is grounded.","effect":"Hard eligibility constraint","source":"dispatcher_interview.txt:breakdowns; maintenance_log.xlsx"},
 {"rule_id":"R10","name":"Temporary repair containment","description":"Guddu/temporary repairs have seven-day permanent-repair clock and cannot leave home region while active.","effect":"Hard eligibility constraint","source":"dispatcher_interview.txt:breakdowns; emails/thread_25_internal_jugaad.txt"},
 {"rule_id":"R11","name":"New-driver night pairing","description":"Drivers with less than six months tenure cannot run solo at night.","effect":"Roster review constraint","source":"dispatcher_interview.txt:drivers; emails/thread_24_internal_nightroster.txt"},]
def now(): return datetime.now().replace(microsecond=0).isoformat()
def canon(x): return re.sub(r"[^A-Z0-9]","",str(x or "").upper())
canonical_vehicle=canon
def ticket_id(x):
 s=str(x or "").strip().upper(); return s if TKT.fullmatch(s) else "TKT-QUAR-"+hashlib.sha256(s.encode()).hexdigest()[:10].upper()
def date(x):
 if isinstance(x,datetime): return x.replace(tzinfo=None)
 s=str(x or "").replace("Z","+00:00")
 try:return datetime.fromisoformat(s).replace(tzinfo=None)
 except ValueError:
  for f in ("%Y-%m-%d","%d-%m-%Y","%d/%m/%Y"):
   try:return datetime.strptime(s,f)
   except ValueError:pass
 return None
def clean(x): return DL.sub("[MASKED-DL]",AAD.sub("[MASKED-ID]",PHONE.sub("[MASKED-PHONE]",str(x or ""))))
def write(path,rec):
 path.parent.mkdir(exist_ok=True)
 with path.open("a",encoding="utf8") as f:f.write(json.dumps(rec,separators=(",",":"))+"\n")

class MeridianOps:
 def __init__(self,root=ROOT):
  self.root=Path(root)
  # Use /tmp for durable state to avoid sandbox FS quirks on artifacts
  state = Path("/tmp/meridian_ops_state"); state.mkdir(exist_ok=True)
  self.out=state/"outputs";self.audit_dir=state/"audit";self.out.mkdir(exist_ok=True);self.audit_dir.mkdir(exist_ok=True)
  self.db=sqlite3.connect(str(state/"meridian_state.db"),check_same_thread=False);self.db.row_factory=sqlite3.Row
  self.db.executescript("""CREATE TABLE IF NOT EXISTS tickets(ticket_id TEXT PRIMARY KEY,status TEXT,decision_json TEXT,processed_at TEXT);CREATE TABLE IF NOT EXISTS actions(action_id TEXT PRIMARY KEY,ticket_id TEXT,action_type TEXT,payload_json TEXT,created_at TEXT,UNIQUE(ticket_id,action_type));CREATE TABLE IF NOT EXISTS runs(run_id INTEGER PRIMARY KEY AUTOINCREMENT,input_name TEXT,input_count INTEGER,new_actions INTEGER,quarantined INTEGER,duplicates INTEGER,adapted INTEGER DEFAULT 0,created_at TEXT);""")
  if "adapted" not in {x[1] for x in self.db.execute("pragma table_info(runs)")}:self.db.execute("alter table runs add column adapted integer default 0")
  self.db.commit();self.load_context()
 def close(self):self.db.close()
 def load_context(self):
  self.fleet=[];self.fleet_map={}
  with (self.root/"fleet_master.csv").open(encoding="utf-8-sig",newline="") as f:
   for n,r in enumerate(csv.DictReader(f),2):
    v={"vehicle":canon(r["registration_number"]),"display":r["registration_number"],"year":int(r["year"]),"bs":r["bs_stage"],"heater":r["engine_heater"],"hub":r["home_hub"],"status":r["status"],"citation":f"fleet_master.csv:row {n}"};self.fleet.append(v);self.fleet_map[v["vehicle"]]=v
  self.drivers={}
  with (self.root/"drivers_roster.csv").open(encoding="utf-8-sig",newline="") as f:
   for n,r in enumerate(csv.DictReader(f),2):self.drivers[r["driver_id"]]={"joined":r["joining_date"],"hub":r["home_hub"],"citation":f"drivers_roster.csv:row {n}"} # raw PII discarded
  self.maint=defaultdict(list);sheet=load_workbook(self.root/"maintenance_log.xlsx",data_only=True).active
  for n,(d,v,o,_m,note) in enumerate(list(sheet.values)[1:],2):
   note=str(note or "");due=re.search(r"(?:service due|due|service by)\s*(?:on\s*)?(20\d\d-\d\d-\d\d)",note.lower());self.maint[canon(v)].append({"date":date(d),"brake":"brake" in note.lower(),"temp":any(x in note.lower() for x in ("jugaad","temporary")),"due":date(due.group(1)) if due else None,"citation":f"maintenance_log.xlsx:Maintenance Log row {n}"})
  for x in self.maint.values():x.sort(key=lambda r:r["date"] or datetime.min)
  self.trips=defaultdict(list)
  with (self.root/"meridian_trips.csv").open(encoding="utf-8-sig",newline="") as f:
   for n,r in enumerate(csv.DictReader(f),2):self.trips[canon(r["vehicle_reg"])].append({"trip_id":r["trip_id"],"client":r["client"],"origin":r["origin_name"],"destination":r["dest_name"],"citation":f"meridian_trips.csv:row {n}"})
 def audit(self,tid,event,result,cites=[],rule=None,meta={}):write(self.audit_dir/"audit.jsonl",{"timestamp":now(),"ticket_id":ticket_id(tid),"event":event,"result":result,"rule":rule,"citations":cites,"metadata":{str(k):clean(v) for k,v in meta.items()}})
 def adapt(self,raw):
  if not isinstance(raw,dict):return None,["record must be an object"],0
  aliases={"id":"ticket_id","ticket":"ticket_id","incident_id":"ticket_id","timestamp":"created_at","created":"created_at","vehicle_reg":"vehicle","registration":"vehicle","truck":"vehicle","origin":"origin_hub","hub":"origin_hub","distance_from_origin_km":"km_from_origin_hub","distance_km":"km_from_origin_hub","distance":"km_from_origin_hub","destination_city":"destination","dest":"destination","problem":"issue","customer":"client"}
  m={aliases.get(str(k).lower(),str(k).lower()):v for k,v in raw.items()};changed=sum(1 for k in raw if str(k).lower() in aliases);req=["ticket_id","created_at","vehicle","origin_hub","km_from_origin_hub","destination","issue","client"];err=[k for k in req if m.get(k) in (None,"")]
  if not TKT.fullmatch(str(m.get("ticket_id","")).upper().strip()):err.append("ticket_id has incompatible format")
  dt=date(m.get("created_at"));
  if not dt:err.append("created_at must be ISO date/time")
  try:m["km_from_origin_hub"]=float(m.get("km_from_origin_hub"));assert m["km_from_origin_hub"]>=0
  except (ValueError,TypeError,AssertionError):err.append("km_from_origin_hub must be non-negative numeric")
  if err:return None,sorted(set(err)),changed
  m={k:clean(v).strip() if isinstance(v,str) else v for k,v in m.items()};m["ticket_id"]=ticket_id(m["ticket_id"]);m["vehicle_canonical"]=canon(m["vehicle"]);m["created_at"]=dt.isoformat();return m,[],changed
 def mstate(self,v,when):
  rs=[r for r in self.maint[v] if r["date"] and r["date"]<=when];last=rs[-1] if rs else None;brake=max((r["date"] for r in rs if r["brake"]),default=None);tmp=max((r["date"] for r in rs if r["temp"]),default=None);due=max((r["due"] for r in rs if r["due"]),default=None)
  return {"brake":bool(brake and when-brake<=timedelta(days=30)),"temp":bool(tmp and when-tmp<=timedelta(days=7)),"overdue":bool(due and when>due+timedelta(days=30)),"latest":last["date"].date().isoformat() if last else None,"citation":last["citation"] if last else "maintenance_log.xlsx:no prior record"}
 def choose(self,t,reserved):
  when=date(t["created_at"]);month=when.month;client=t["client"].lower();dest=t["destination"].lower();origin=t["origin_hub"];cites=[f"{t['_source']}:ticket {t['ticket_id']}","fleet_master.csv","maintenance_log.xlsx","dispatcher_interview.txt"]
  drv=self.drivers.get(t.get("driver_id"));night=bool(drv and (when.hour>=20 or when.hour<6) and date(drv["joined"])+timedelta(days=183)>when)
  if t["km_from_origin_hub"]>50:return {"status":"NEEDS_REVIEW","selection":None,"candidates":[],"target_hub":None,"citations":cites,"rules":["R8"],"review":"Nearest-hub distance is unavailable in supplied context; cannot safely satisfy R8.","night":night,"driver_citation":drv["citation"] if drv else None}
  cs=[];hill=any(x in dest for x in ("rudrapur","nainital"));delhi=any(x in dest for x in ("delhi","gurgaon","faridabad","noida"))
  for v in self.fleet:
   m=self.mstate(v["vehicle"],when);why=[]
   if v["status"].lower()!="active":why.append("R8: fleet snapshot not active")
   if v["hub"]!=origin:why.append("R8: within 50km requires origin-hub replacement")
   if v["vehicle"]==t["vehicle_canonical"]:why.append("R8: incident vehicle cannot replace itself")
   if v["vehicle"] in reserved:why.append("R8: vehicle already reserved")
   if month in (10,11,12,1,2) and delhi and v["bs"].upper()!="BS6":why.append("R1: Delhi NCR winter requires BS6")
   if month in (11,12,1,2) and hill and v["heater"].lower()!="yes":why.append("R2: winter hill route requires engine heater")
   if month in (11,12,1,2) and hill and m["brake"]:why.append("R2: brake work in previous 30 days")
   if m["overdue"]:why.append("R9: service overdue >30 days")
   if m["temp"] and v["hub"]!=origin:why.append("R10: temporary repair cannot leave home region")
   if client=="apex chemicals" and v["vehicle"]==t["vehicle_canonical"]:why.append("R5: Apex incident vehicle must rotate")
   if client=="orion pharma" and v["year"]<2020:why.append("R6: Orion requires model year 2020+")
   cs.append({"vehicle":v["vehicle"],"display_vehicle":v["display"],"year":v["year"],"status":"REJECTED" if why else "ELIGIBLE","reasons":why,"citations":[v["citation"],m["citation"]]})
  ok=[x for x in cs if x["status"]=="ELIGIBLE"];ok.sort(key=lambda x:((-x["year"] if client=="orion pharma" else 0),x["vehicle"]));sel=ok[0] if ok else None
  rules=["R8","R9"]+(["R1"] if delhi else [])+(["R2"] if hill else [])+(["R5"] if client=="apex chemicals" else [])+(["R6"] if client=="orion pharma" else [])
  return {"status":"AWAITING_APPROVAL" if sel else "NEEDS_REVIEW","selection":sel,"candidates":cs,"target_hub":origin,"citations":cites,"rules":rules,"review":None if sel else "No eligible origin-hub replacement after hard constraints.","night":night,"driver_citation":drv["citation"] if drv else None}
 def action(self,tid,kind,payload):
  try:self.db.execute("insert into actions values(?,?,?,?,?)",(f"{kind.upper()}-{tid}",tid,kind,json.dumps(payload,separators=(",",":")),now()));self.db.commit();return True
  except sqlite3.IntegrityError:return False
 def run(self,input_file="tickets.json"):
  src=Path(input_file);src=src if src.is_absolute() else self.root/src;name=clean(src.name);new=bad=dups=adapted=0
  try:
   content=json.loads(src.read_text(encoding="utf8"));raw=content if isinstance(content,list) else next((content[x] for x in ("tickets","records","data","items") if isinstance(content.get(x),list)),None)
   if raw is None:raise ValueError("incompatible schema")
  except Exception as e:
   tid="TKT-FILE-"+hashlib.sha256(name.encode()).hexdigest()[:10].upper();q={"ticket_id":tid,"status":"QUARANTINED","severity":"HIGH","reason":"incompatible input file","validation_failures":["schema/read failure"],"source":name}
   if self.action(tid,"quarantine",q):write(self.out/"quarantine.jsonl",q)
   self.audit(tid,"SCHEMA_ALERT","QUARANTINED",[name],meta={"reason":type(e).__name__});self.db.execute("insert into runs(input_name,input_count,new_actions,quarantined,duplicates,adapted,created_at) values(?,?,?,?,?,?,?)",(name,0,0,1,0,0,now()));self.db.commit();return {"input_records":0,"new_actions":0,"quarantined":1,"duplicates":0,"adapted_fields":0,"schema":"INCOMPATIBLE","source":name}
  staged=[];seen=set()
  for n,r in enumerate(raw,1):
   t,errs,ch=self.adapt(r);adapted+=ch;tid=ticket_id(r.get("ticket_id",r.get("id",r.get("ticket",""))) if isinstance(r,dict) else "")
   if errs:
    bad+=1;q={"ticket_id":tid,"status":"QUARANTINED","severity":"HIGH","reason":"ticket validation failed","validation_failures":errs,"source":name,"record":n}
    if self.action(tid,"quarantine",q):write(self.out/"quarantine.jsonl",q)
    self.audit(tid,"QUARANTINED","INVALID",[f"{name}:record {n}"],meta={"failure_count":len(errs)});continue
   if t["ticket_id"] in seen or self.db.execute("select 1 from tickets where ticket_id=?",(t["ticket_id"],)).fetchone():dups+=1;self.audit(t["ticket_id"],"DUPLICATE_DETECTED","ALREADY_PROCESSED",[f"{name}:record {n}"]);continue
   seen.add(t["ticket_id"]);t["_source"]=name;staged.append(t)
  reserved={json.loads(x[0]).get("vehicle_reg") for x in self.db.execute("select payload_json from actions where action_type='work_order'")}
  for t in sorted(staged,key=lambda x:(x["created_at"],x["ticket_id"])):
   tid=t["ticket_id"];self.audit(tid,"INGESTED","PII_MASKED",[f"{name}:ticket {tid}"]);self.audit(tid,"ENTITY_RESOLVED","NORMALIZED",["fleet_master.csv","maintenance_log.xlsx"],meta={"vehicle":t["vehicle_canonical"]});d=self.choose(t,reserved)
   for c in d["candidates"]:
    if c["status"]=="REJECTED":self.audit(tid,"VEHICLE_REJECTED","REJECTED",c["citations"],c["reasons"][0].split(":")[0],{"vehicle":c["vehicle"],"reason_count":len(c["reasons"])})
   if d["night"]:self.audit(tid,"RULE_EVALUATED","ROSTER_REVIEW",[d["driver_citation"],"dispatcher_interview.txt:drivers"],"R11",{"reason":"new driver on night incident; pairing required"})
   d["ticket"]={k:t.get(k) for k in ("ticket_id","created_at","origin_hub","destination","issue","severity","client","vehicle_canonical")};self.db.execute("insert into tickets values(?,?,?,?)",(tid,d["status"],json.dumps(d,separators=(",",":")),now()));self.db.commit()
   if not d["selection"]:self.audit(tid,"RULE_EVALUATED","NEEDS_REVIEW",d["citations"],"R8",{"reason":d["review"]});continue
   sel=d["selection"];reserved.add(sel["vehicle"]);wo={"work_order_id":f"WO-{tid}","ticket_id":tid,"vehicle_reg":sel["vehicle"],"created_at":now(),"status":"CREATED","decision_ref":f"DEC-{tid}","citations":d["citations"]+sel["citations"]}
   if self.action(tid,"work_order",wo):write(self.out/"work_orders.jsonl",wo);new+=1
   note=" Operating planning uses Meridian's 36-hour Shakti window." if t["client"].lower()=="shakti cement" else " Any after-hours arrival is scheduled next 08:00, not failed." if t["client"].lower()=="vertex retail" and t["destination"].lower()=="ludhiana" else " Cold-chain overnight handling requires dispatch confirmation." if t["client"].lower()=="orion pharma" else ""
   draft={"message_id":f"MSG-{tid}","ticket_id":tid,"recipient":"client-operations@meridian.example","status":"PENDING_APPROVAL","body":f"Meridian Ops has prepared a replacement for incident {tid}. The operational plan awaits human approval before customer-facing confirmation.{note}","citations":d["citations"]+["dispatcher_interview.txt"]}
   if self.action(tid,"comm_draft",draft):write(self.out/"comms_pending.jsonl",draft);new+=1
   self.audit(tid,"VEHICLE_SELECTED","SELECTED",wo["citations"],"R8",{"vehicle":sel["vehicle"],"decision":f"DEC-{tid}"});self.audit(tid,"WORK_ORDER_CREATED","CREATED",wo["citations"]);self.audit(tid,"APPROVAL_REQUESTED","PENDING",draft["citations"])
  self.db.execute("insert into runs(input_name,input_count,new_actions,quarantined,duplicates,adapted,created_at) values(?,?,?,?,?,?,?)",(name,len(raw),new,bad,dups,adapted,now()));self.db.commit();return {"input_records":len(raw),"new_actions":new,"quarantined":bad,"duplicates":dups,"adapted_fields":adapted,"schema":"ARRAY","source":name}
 def approve(self,tid,approved_by="OPS-APPROVER"):
  tid=ticket_id(tid);r=self.db.execute("select status from tickets where ticket_id=?",(tid,)).fetchone()
  if not r:return {"ok":False,"reason":"Unknown ticket"}
  if self.db.execute("select 1 from actions where ticket_id=? and action_type='comm_sent'",(tid,)).fetchone():return {"ok":True,"idempotent":True,"message_id":f"MSG-{tid}"}
  if r["status"]!="AWAITING_APPROVAL":return {"ok":False,"reason":"Ticket is not awaiting eligible dispatch"}
  sent={"message_id":f"MSG-{tid}","ticket_id":tid,"recipient":"client-operations@meridian.example","body":f"Meridian Ops: human approval recorded for incident {tid}. A replacement plan is released through the normal operations channel.","approved_by":"OPS-APPROVER","sent_at":now()}
  if self.action(tid,"comm_sent",sent):write(self.out/"comms_sent.jsonl",sent);self.db.execute("update tickets set status='SENT' where ticket_id=?",(tid,));self.db.commit();self.audit(tid,"COMM_APPROVED","APPROVED",["approval gate"],meta={"approver":"OPS-APPROVER"});self.audit(tid,"COMM_SENT","SENT",["approval gate"])
  return {"ok":True,"idempotent":False,"message_id":sent["message_id"]}
 def pii_scan(self):
  found=[]
  for d in (self.out,self.audit_dir):
   for p in d.glob("*.jsonl"):
    x=p.read_text(encoding="utf8")
    if PHONE.search(x) or AAD.search(x) or DL.search(x):found.append(p.name)
  return {"findings":len(found),"files":found}
 def dashboard(self):
  c={x["status"]:x["n"] for x in self.db.execute("select status,count(*) n from tickets group by status")};last=self.db.execute("select * from runs order by run_id desc limit 1").fetchone();activity=[dict(x) for x in self.db.execute("select ticket_id,status,processed_at from tickets order by processed_at desc limit 8")]
  return {"breakdowns":sum(c.values()),"processed":c.get("AWAITING_APPROVAL",0)+c.get("SENT",0),"needs_review":c.get("NEEDS_REVIEW",0),"quarantined":sum(1 for _ in self.db.execute("select 1 from actions where action_type='quarantine'")),"duplicates":last["duplicates"] if last else 0,"pii_exposures":self.pii_scan()["findings"],"system":"OPERATIONAL","latest_run":dict(last) if last else None,"activity":activity}
 def get_ticket(self,tid):
  r=self.db.execute("select * from tickets where ticket_id=?",(ticket_id(tid),)).fetchone()
  if not r:return None
  d=dict(r);d["decision"]=json.loads(d.pop("decision_json"));return d
 def list_tickets(self):
  return [{"ticket_id":r["ticket_id"],"status":r["status"],"client":json.loads(r["decision_json"])["ticket"]["client"],"destination":json.loads(r["decision_json"])["ticket"]["destination"]} for r in self.db.execute("select * from tickets order by processed_at desc")]
 def context_answer(self,q):
  m=re.search(r"TKT-[A-Z0-9_-]+",q.upper())
  if m and (r:=self.get_ticket(m.group())):
   d=r["decision"];return {"answer":f"{r['ticket_id']} is {r['status']}. "+(f"Selected replacement: {d['selection']['vehicle']}." if d["selection"] else f"Needs review: {d['review']}"),"citations":d["citations"],"decision":d}
  v=self.fleet_map.get(canon(q))
  if v:
   rej=[]
   for r in self.db.execute("select ticket_id,decision_json from tickets"):
    for c in json.loads(r["decision_json"])["candidates"]:
     if c["vehicle"]==v["vehicle"] and c["status"]=="REJECTED":rej.append({"ticket_id":r["ticket_id"],"reasons":c["reasons"],"citations":c["citations"]})
   ms=self.mstate(v["vehicle"],datetime.now());return {"answer":f"{v['vehicle']}: fleet status {v['status']}; BS stage {v['bs']}; home hub {v['hub']}."+(" Rejection evidence exists." if rej else " No rejection evidence found."),"citations":[v["citation"],ms["citation"]],"maintenance":ms,"rejections":rej}
  rm=re.search(r"\bR(\d+)\b",q.upper());rule=next((x for x in RULES if rm and x["rule_id"]=="R"+rm.group(1)),None)
  return {"answer":rule["description"],"citations":[rule["source"]],"rule":rule} if rule else {"answer":"Insufficient data","citations":[]}
