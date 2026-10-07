"""NEW exact public runtime loader; candidate matching is child-owned."""
from types import MappingProxyType
import cpu_harness as h
import term_lock_policy as p
from term_runner_core import TermCore,Inventory,SEEN_IDS
RAW_PINS={'sources88.json': 'a98baa95cb520090d21176f03774c63ce5e0d1caca4e5ff6a10e7ed6bd72c9a8', 'coverage19.json': 'c754eb4e34f612034a03e646666dd2f707a8cae182762c5364ae9739bbb8e541', 'schedule88.json': '4aa12fb23ebbc1bb1a2a2fe31f4d4dda400ec0ddb0fc42ed7d11564400e97f2f', 'INPUT_BINDINGS.json': '180b7cea0bf902893180fadad30df8d2bfc22926a6d7c3a692be6eb197906d4f', 'SOURCE_ONLY_AUDIT.json': 'a39c8bb5c57d3e86c759693a1829dac93c46cc2f4373087934a09207177e3178'}
def load_from_bytes(raw_inputs,declaration_bytes):
 h.require(type(raw_inputs) is dict and set(raw_inputs)==set(RAW_PINS),"public input closure")
 data={}
 for name,pin in RAW_PINS.items():
  raw=raw_inputs[name];h.require(type(raw) is bytes and 0<len(raw)<=65536 and h.digest(raw)==pin,"public source byte binding");data[name]=h.strict_json(raw)
 h.require(type(declaration_bytes) is bytes and h.digest(declaration_bytes)==p.DECLARATIONS_SHA256,"declaration identity")
 rows,coverage,schedule,bindings,audit=(data[n] for n in RAW_PINS)
 ids=tuple(r["id"] for r in rows);h.require(len(ids)==88 and ids[:69]==SEEN_IDS and ids==h.ROW_IDS,"exact runtime88 identities")
 for name,value in (("sources",rows),("coverage",coverage),("schedule",schedule)):
  h.require(bindings[name]==h.digest(h.canonical(value)),"canonical input binding")
 h.require(bindings["declarations"]==p.DECLARATIONS_SHA256 and audit["bindings"]==bindings,"source audit closure")
 eligible=tuple(audit["source_eligible_ids"]);h.require(len(eligible)==12 and set(eligible)==set(h.ELIGIBLE_IDS) and audit["intended_requests_if_counts_pass"]==378 and audit["intended_helper_commands"]==214,"audited scope budget")
 ordered=tuple((r["id"],"baseline" if a=="A" else "candidate") for r in schedule for a in r["arm_order"])
 h.require(ordered==h.SCHEDULE and set(audit["prompt_bindings"])==set(ids),"schedule/prompt binding")
 inv=Inventory(MappingProxyType({r["id"]:h.canonical(r) for r in rows}),ids,ids[69:],tuple(MappingProxyType(dict(r)) for r in coverage),eligible,ordered,MappingProxyType(dict(bindings)),378,MappingProxyType({i:MappingProxyType(dict(v)) for i,v in audit["prompt_bindings"].items()}))
 return TermCore(h,p),inv,declaration_bytes
def load(runtime):
 runtime.require_activation()
 raw={n:runtime.pinned_file(runtime.HERE/"inputs"/n,pin,65536) for n,pin in RAW_PINS.items()}
 declarations=runtime.pinned_file(runtime.HERE/"policy/global_declarations.json",p.DECLARATIONS_SHA256,8192)
 return load_from_bytes(raw,declarations)
