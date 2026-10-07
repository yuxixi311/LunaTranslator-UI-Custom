"""NEW inert stage reconstruction with injected transport, clock and worker."""
from term_runner_core import GENERATION_PROMPT_CAP,GENERATED_CAP

def execute_stage(core,inventory,alias,declarations,hooks,integrity,expected_error):
    h,p=core.h,core.policy
    ledger=core.ledger(inventory,hooks.event);hooks.ledger=ledger
    observations,plans,helper_samples={},[],[];hooks.helper_samples=helper_samples
    hooks.observations=observations  # Retain already-received output if ordinary writes are cancelled.
    totals=dict(generation_prompt_tokens=0,generated_tokens=0,measured_count_requests=0,measured_count_input_tokens=0)
    def exchange(kind,row,arm,body,validate):
        hooks.check();before=ledger.total
        result,elapsed=hooks.exchange(ledger,kind,row,arm,body,validate)
        h.require(ledger.total==before+1 and type(elapsed) is int and elapsed>=0,"one accounted exchange")
        return result,elapsed
    try:
        hooks.ready_marker()
        exchange("health",None,None,None,lambda raw:h.readiness_response("health",raw,alias))
        exchange("models",None,None,None,lambda raw:h.readiness_response("models",raw,alias))
        hooks.postready_limit(600);hooks.phase("preflight",60);hooks.worker.start()
        for row_id in inventory.row_ids:
            sides=iter(("baseline","second"))
            def count(body):return exchange("preflight",row_id,next(sides),body,h.token_response)[0]
            plans.append(core.preflight_pair(row_id,core.row(inventory,row_id),alias,declarations,count,hooks.worker,inventory.prompt_bindings[row_id]))
        try:coverage=core.validate_preflight(inventory,plans)
        except h.TerminalFailure as exc:
            trace=getattr(getattr(hooks,"owner",None),"diagnostic",None)
            if trace:trace.fail(exc)
            coverage=None
        hooks.record("preflight",dict(coverage=coverage,coverage_status="pass" if coverage else "fail",eligible=list(inventory.eligible_ids),
            active=[q.row_id for q in plans if q.active],request_total=inventory.request_total,bindings=dict(inventory.bindings),
            rows=[dict(id=q.row_id,eligible=q.eligible,active=q.active,reason=q.reason,baseline=q.baseline.binding,prospective=q.provisional.binding,actual=q.candidate.binding) for q in plans]))
        hooks.publish_preflight(plans);ledger.seal_preflight(plans)
        hooks.worker.seal(h.digest(h.canonical([dict(id=q.row_id,baseline=q.baseline.binding,prospective=q.provisional.binding,actual=q.candidate.binding) for q in plans])),[q.row_id for q in plans if q.active])
        hooks.resume_postready_limit();by_id={q.row_id:q for q in plans}
        for row_id,arm in inventory.schedule:
            hooks.check();plan,row=by_id[row_id],core.row(inventory,row_id)
            started=hooks.now_ns();original_received=None
            parts=dict(render_and_ipc_ns=0,count_ns=[],completion_ns=0,restoration_and_guard_ns=0)
            try:
                before=hooks.now_ns()
                if arm=="baseline":
                    body=h.serialize_request(core.baseline_messages(row),alias)
                    h.require(body==plan.baseline.body,"baseline rendering drift");receipt=plan.baseline
                else:
                    sides=iter(("baseline","provisional"))
                    def count(body):
                        value,elapsed=exchange("recurring",row_id,next(sides),body,h.token_response)
                        parts["count_ns"].append(elapsed);totals["measured_count_requests"]+=1;totals["measured_count_input_tokens"]+=value
                        return value
                    def on_prepared():helper_samples.append(dict(row=row_id,elapsed_ns=hooks.now_ns()-before))
                    body=core.measured_candidate(plan,row,alias,declarations,count,hooks.worker,on_prepared);receipt=plan.candidate
                parts["render_and_ipc_ns"]=hooks.now_ns()-before
                rendered=dict(final=None,restoration_status="not_checked",restoration_rejection=None)
                def guarded(source,output):
                    nonlocal original_received
                    original_received=output;before_guard=hooks.now_ns()
                    try:
                        if arm=="candidate" and plan.active:
                            response=hooks.worker.restore(row_id,output);rendered["restoration_rejection"]=response["rejection"]
                            if response["rejection"] is not None:raise p.StructuralFailure("bounded worker restoration rejected")
                            rendered["final"]=response["final_output"]
                        else:integrity(source,output);rendered["final"]=output
                        rendered["restoration_status"]="restored" if arm=="candidate" and plan.active else "ordinary_guard_pass"
                    except (expected_error,p.StructuralFailure):
                        rendered["restoration_status"]="rejected";raise
                    finally:parts["restoration_and_guard_ns"]+=hooks.now_ns()-before_guard
                def validate(raw):return h.completion_response(raw,alias,receipt,row["source"],guarded,(expected_error,p.StructuralFailure))
                result,elapsed=exchange("completion",row_id,arm,body,validate)
                h.require(elapsed>=parts["restoration_and_guard_ns"],"completion guard timer")
                parts["completion_ns"]=elapsed-parts["restoration_and_guard_ns"]
                finished=hooks.now_ns();h.require(finished>started,"positive arm interval")
                result.pop("raw_response");original=result.pop("output")
                result.update(original_output=original,final_output=rendered["final"],original_output_sha256=h.digest(original.encode()),
                    final_output_sha256=h.digest(rendered["final"].encode()) if rendered["final"] is not None else None,
                    restoration_status=rendered["restoration_status"],restoration_rejection=rendered["restoration_rejection"])
                record=dict(status="observed",row=row_id,arm=arm,total_ns=finished-started,perf_start_ns=started,perf_end_ns=finished,
                    components=parts,request_sha256=h.digest(body),actual_receipt=receipt.binding,prospective_receipt=plan.provisional.binding if arm=="candidate" else None,
                    source_sha256=h.digest(row["source"].encode()),preflight_active=plan.active,**result)
                observations[(row_id,arm)]=record
                totals["generation_prompt_tokens"]+=result["usage"]["prompt_tokens"];totals["generated_tokens"]+=result["usage"]["completion_tokens"]
                h.require(totals["generation_prompt_tokens"]<=GENERATION_PROMPT_CAP and totals["generated_tokens"]<=GENERATED_CAP,"generation ceilings")
            except BaseException:
                finished=hooks.now_ns()
                record=dict(status="operational_failure",row=row_id,arm=arm,failure="ARM_FAILURE",total_ns=finished-started,
                    perf_start_ns=started,perf_end_ns=finished,timing_scoreable=False,preflight_active=plan.active,
                    original_output=original_received,original_output_sha256=h.digest(original_received.encode()) if original_received is not None else None,
                    final_output=None,final_output_sha256=None)
                observations[(row_id,arm)]=record;ledger.fail("measured_arm_failure");hooks.record("arm",record);raise
            hooks.record("arm",record)
        ledger.assert_complete();hooks.check();hooks.worker.finish()
        metrics=hooks.worker.metrics()
        h.require(type(metrics) is dict and set(metrics)=={"owner_identity","policy_in_owner_process","peak_rss_bytes","cold_start_ns"} and
            metrics["owner_identity"]==hooks.worker.owner_identity and metrics["policy_in_owner_process"] is True and
            type(metrics["peak_rss_bytes"]) is int and 0<metrics["peak_rss_bytes"]<=32*h.MIB and type(metrics["cold_start_ns"]) is int and metrics["cold_start_ns"]>0,"helper owner evidence")
        timing=hooks.worker.timing_metrics()
        h.require(set(timing)=={"active_work_ns","worker_cpu_ns","lifetime_ns","startup_ns","finish_ns","commands","parent_setup_ns","parent_setup_cpu_ns"} and
            all(type(v) is int and v>=0 for v in timing.values()) and timing["commands"]==178+2*len(inventory.eligible_ids)+sum(q.active for q in plans) and
            0<timing["active_work_ns"]<=15_000_000_000 and timing["worker_cpu_ns"]<=15_000_000_000 and 0<timing["lifetime_ns"]<=600_000_000_000 and
            timing["startup_ns"]==metrics["cold_start_ns"] and timing["startup_ns"]+timing["finish_ns"]<=timing["active_work_ns"] and timing["parent_setup_ns"]<=timing["startup_ns"],"helper lifecycle evidence")
        h.require(totals["measured_count_requests"]==2*len(inventory.eligible_ids),"recurring count accounting")
        h.require(len(helper_samples)==88 and tuple(s["row"] for s in helper_samples)==inventory.row_ids and all(type(s["elapsed_ns"]) is int and s["elapsed_ns"]>0 for s in helper_samples) and
            h.quantiles([s["elapsed_ns"] for s in helper_samples])["p95"]<=5_000_000,"nested helper sample gate")
        hooks.record("helper",dict(owner=metrics,lifecycle=timing,candidate_preparation_samples=helper_samples))
        return dict(status="synthetic_or_unreleased_stage_complete",inventory=inventory,plans=tuple(plans),observations=observations,totals=totals,ledger=ledger,helper=dict(owner=metrics,lifecycle=timing),semantic_quality_claim=None)
    except BaseException:
        ledger.fail("stage_terminal_failure");cleanup=hooks.worker.abort()
        hooks.record("helper_terminal",{k:cleanup.get(k) if type(cleanup) is dict and type(cleanup.get(k)) is bool else None for k in ("cleanup_confirmed","reaped","protocol_complete")})
        raise
    finally:hooks.record("all_rows",core.all_row_accounting(inventory,observations))

def run_real(*args,**kwargs):raise RuntimeError("SOURCE_ONLY_NATIVE_DISABLED")
if __name__=="__main__":run_real()
