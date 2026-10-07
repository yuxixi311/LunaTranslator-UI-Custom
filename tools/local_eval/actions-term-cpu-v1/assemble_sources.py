"""Offline NEW runner projection of exactly recovered public inputs only."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"policy"))
import term_lock_policy as p
import cpu_harness as h
from term_runner_core import TermCore,HISTORICAL_IDS,PRIOR_IDS,GLOSSARY_IDS,CONTROL_REASONS

def verified(path,pin):
    raw=(ROOT/path).read_bytes()
    if sha256(raw).hexdigest()!=pin:raise ValueError("public input hash mismatch")
    return json.loads(raw)

def assemble():
    legacy=verified("source_provenance/legacy_glossary/sources.json","29e6d18e8ca8191c87eb2328cf6a4055947d8627cb22ef456199df1fc6bfa092")
    canon=verified("source_provenance/legacy_glossary/canon.json","7cc5bdb3626dd4e781070dca708428c0ef81048d72b067a71f9e15c795814337")
    historical=verified("source_provenance/REGRESSION55_SOURCES.json","7b01d892e62579fd7c592cc8f532a0f7391ef129891021ba60744c2da58529f8")
    fresh=verified("source_provenance/fresh19/fresh19_sources.json","83918221ae47cd7be8e863f0f0f5b3b2af8af146fa117ee663093df9ad84fba8")
    declarations=(ROOT/"policy/global_declarations.json").read_bytes();declared=p.load_declarations(declarations)
    assert fresh["glossary"]==[{k:r[k] for k in ("src","dst")} for r in declared["entries"]]
    assert set(fresh)=={"schema_version","glossary","records"} and len(fresh["records"])==19
    assert all(set(r)=={"id","scope_id","family_id","source"} for r in fresh["records"])
    rows=[]
    for r in historical["rows"]:
        assert sha256(r["source"].encode()).hexdigest()==r["source_sha256"]
        rows.append(dict(id=r["id"],source=r["source"],scope_id="historical-no-glossary-v1",glossary=[],stratum="historical40" if r["id"] in HISTORICAL_IDS else "prior15"))
    assert tuple(r["id"] for r in rows)==HISTORICAL_IDS+PRIOR_IDS
    old={r["id"]:r for r in legacy}
    for i in GLOSSARY_IDS:rows.append(dict(id=i,source=old[i]["source"],scope_id="historical-hy-glossary-v1",glossary=canon["entries"],stratum="glossary14"))
    for r in fresh["records"]:rows.append(dict(id=r["id"],source=r["source"],scope_id=r["scope_id"],glossary=fresh["glossary"],stratum="fresh19"))
    safe=[r["id"] for r in declared["entries"] if r["lock_safe"]];control_order=list(CONTROL_REASONS)
    coverage=[dict(id=r["id"],role="carrier" if n<12 else "control",family=safe[n//2] if n<12 else None,
        control_type=None if n<12 else control_order[n-12]) for n,r in enumerate(fresh["records"])]
    first={}
    for group in (HISTORICAL_IDS,PRIOR_IDS):first.update({i:"A" if n%2==0 else "B" for n,i in enumerate(group)})
    for prefix in ("person","participant","entity","negative","nomatch"):
        first.update({i:"B" if prefix=="nomatch" else "A" if n%2==0 else "B" for n,i in enumerate(i for i in GLOSSARY_IDS if i.startswith(prefix+"-"))})
    for n,r in enumerate(fresh["records"]):first[r["id"]]=("A" if n%2==0 else "B") if n<12 else ("B" if n%2==0 else "A")
    schedule=[dict(id=r["id"],arm_order=[first[r["id"]],"B" if first[r["id"]]=="A" else "A"]) for r in rows]
    bindings={name:h.digest(h.canonical(value)) for name,value in (("sources",rows),("coverage",coverage),("schedule",schedule))}
    bindings["declarations"]=p.DECLARATIONS_SHA256
    core=TermCore(h,p);inventory=core.freeze_inventory(rows,coverage,schedule,declarations,bindings=bindings)
    sys.path.insert(0,str(ROOT/"source_provenance/legacy_glossary"))
    from production_adapter import production_pair
    parity=[]
    for row in rows[55:69]:
        matched,_,glossary=production_pair(row["source"],[SimpleNamespace(**e) for e in canon["entries"]])
        assert core.baseline_messages(row)==glossary
        plan=p.prepare(row["source"],row["scope_id"],row["glossary"],declarations)
        assert not plan.eligible and plan.baseline_prompt==plan.provisional_prompt
        parity.append(dict(id=row["id"],matched_sources=[e["src"] for e in matched],request_sha256=h.digest(h.canonical(glossary))))
    audit=dict(status="NEW_RUNNER_SOURCE_ONLY_PASS_REAL_PREFLIGHT_PENDING",pairs=88,eligible_count=len(inventory.eligible_ids),
        source_eligible_ids=list(inventory.eligible_ids),intended_requests_if_counts_pass=inventory.request_total,
        intended_helper_commands=178+3*len(inventory.eligible_ids),bindings=bindings,legacy_glossary_renderer_parity=parity,
        root_source_review_opaque_sha256="6f6317f929e8b0db7036c0d6842b3c2198ebaa1a09e5637df5b1be21ac37cc47",
        private_criteria_opaque_commitment="8e3afd829bc54ed4f3addd115fad73d5740f8265329d1ea586c54e126d61d8e8",
        real_tokenizer_calls=0,model_calls=0,native_execution_enabled=False,prompt_bindings={i:dict(v) for i,v in inventory.prompt_bindings.items()})
    return rows,coverage,schedule,bindings,audit

if __name__=="__main__":
    values=assemble()
    for name,value in zip(("sources88.json","coverage19.json","schedule88.json","INPUT_BINDINGS.json","SOURCE_ONLY_AUDIT.json"),values):
        (ROOT/"inputs"/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:values[-1][k] for k in ("status","pairs","eligible_count","intended_requests_if_counts_pass","intended_helper_commands")}))
