"""Closed public schema for authorized fictional sources/model translations.

No host dumps, exception text, headers, URLs, keys, criteria or opaque claim
objects are copied. Public treatment identities are intentional in this protocol.
Root prepares fresh anonymous reviewer packets later; blinding is not guaranteed.
"""
import math
import cpu_harness as h
from actions_policy import REVIEW_MODE


def finite(value):
    h.require(type(value) in (int,float) and math.isfinite(value) and value>=0,'public numeric field')
    return value


def build_public(sources,observations,*,consumed_http,validated_http,accounting_confirmed,
                 status,resource_metrics=None,protocol=None):
    h.require(type(sources) is dict and set(sources)==set(h.ROW_IDS) and
              all(type(text) is str and len(text)<=4096 for text in sources.values()),'public sources')
    h.require(type(observations) is dict and set(observations)<=set(h.SCHEDULE),'public observations')
    h.require(status in ('complete','incomplete','blocked_before_claim'),'public status')
    h.require(type(accounting_confirmed) is bool,'accounting certainty')
    if accounting_confirmed:
        h.require(type(consumed_http) is int and type(validated_http) is int and
                  0<=validated_http<=consumed_http<=442,'public call counters')
    else:
        h.require(consumed_http is None and validated_http is None,'unknown counters must stay unknown')
    source_rows=[dict(id=row,source=sources[row]) for row in h.ROW_IDS]
    translated=[];timings=[];generation_prompt_tokens=generated_tokens=0
    for row,arm in h.SCHEDULE:
        item=observations.get((row,arm))
        state='unobserved' if item is None else item.get('status')
        h.require(state in ('unobserved','operational_failure','observed'),'public observation state')
        public=dict(id=row,arm=arm,state=state,text=None,usage=None,generation_failure_flags=[])
        if state=='observed':
            text=item.get('output');usage=item.get('usage');flags=item.get('flags')
            h.require(type(text) is str and len(text.encode('utf-8'))<=65536,'public exact translation')
            h.require(type(usage) is dict and type(usage.get('prompt_tokens_details')) is dict,'public usage')
            p,c,t=(usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens'))
            cached=usage['prompt_tokens_details'].get('cached_tokens')
            h.require(all(type(v) is int for v in (p,c,t,cached)) and 1<=p<=384 and 0<=c<=512 and
                      cached==0 and t==p+c,'public usage integers/cache')
            h.require(type(flags) is list and len(flags)==len(set(flags)) and
                      set(flags)<= {'empty_output','length_finish','integrity_rejection'},'public generation flags')
            public.update(text=text,usage=dict(prompt_tokens=p,completion_tokens=c,total_tokens=t,cached_tokens=0),
                          generation_failure_flags=flags)
            generation_prompt_tokens+=p;generated_tokens+=c
            total=item.get('total_ns')
            h.require(type(total) is int and total>0,'public authoritative timing')
            timing=dict(id=row,arm=arm,total_ns=total,components=None)
            if item.get('components') is not None:
                parts=item['components'];counter=parts['token_counter_ns']
                h.require(type(counter) is list and len(counter)<=2 and all(type(v) is int and v>=0 for v in counter),
                          'public recurring token-counter elapsed times')
                selected={key:parts[key] for key in ('renderer_ns','construction_ns','completion_ns','integrity_ns')}
                h.require(all(type(v) is int and v>=0 for v in selected.values()),'public measured component nanoseconds')
                timing['components']=dict(token_counter_ns=counter,**selected)
            timings.append(timing)
        translated.append(public)
    h.require(generation_prompt_tokens<=67584 and generated_tokens<=90112,'public token accounting')
    calls=[]
    for index,(kind,row,arm) in enumerate(h.RequestLedger().queue,1):
        state=('validated' if index<=validated_http else 'consumed_unvalidated' if index<=consumed_http else 'unissued') if accounting_confirmed else 'unknown'
        calls.append(dict(number=index,kind=kind,id=row,arm=arm,state=state))
    metrics=resource_metrics or {}
    allowed={'runner_peak_rss_bytes','server_peak_rss_bytes','helper_peak_rss_bytes','helper_render_p95_ns',
             'minimum_available_ram_bytes','minimum_effective_headroom_bytes'}
    h.require(type(metrics) is dict and set(metrics)<=allowed,'public resource allowlist')
    metrics={key:finite(value) for key,value in metrics.items()}
    reconciled=None
    if status=='complete':h.require(protocol is not None,'complete public protocol requires reconciliation')
    if protocol is not None:
        h.require(accounting_confirmed and consumed_http==validated_http==442 and
                  len(observations)==176 and all(item['state']=='observed' for item in translated),
                  'reconciled public protocol must retain every completion and call')
        h.require(protocol.get('status')=='validated_complete_protocol_evidence','public reconciled protocol')
        cost=protocol['cost'];groups={}
        h.require(cost['status'] in ('fail','inconclusive','inconclusive_pending_order_and_noise_review'),'public cost disposition')
        for name in ('all_new','active_new','all_rows','all_active'):
            q=cost['groups'][name]['ratios']
            h.require(type(q['n']) is int and 1<=q['n']<=88,'public cost denominator')
            groups[name]=dict(n=q['n'],median=finite(q['median']),p95=finite(q['p95']))
        active=[dict(id=row['id'],active=row['active']) for row in cost['raw_rows']]
        h.require([r['id'] for r in active]==list(h.ROW_IDS) and all(type(r['active']) is bool for r in active),'public active membership')
        tokens={key:protocol['tokens'][key] for key in ('count_only_requests','count_only_input_tokens','generation_prompt_tokens','generated_tokens')}
        h.require(all(type(v) is int and v>=0 for v in tokens.values()),'public reconciled token totals')
        orders={}
        for order in ('AB','BA'):
            q=cost['order_strata'][order]
            h.require(type(q['n']) is int and q['n']==44,'public order stratum denominator')
            orders[order]=dict(n=q['n'],median=finite(q['median']),p95=finite(q['p95']))
        reconciled=dict(status='validated_complete_protocol_evidence' ,cost_status=cost['status'],row_ratio_groups=groups,
                        active_membership=active,tokens=tokens,order_strata=orders)
    result={
        'sources.json':dict(schema=1,rows=source_rows),
        'translations.json':dict(schema=1,records=translated),
        'accounting.json':dict(schema=1,protocol_status=status,expected_rows=88,expected_completions=176,expected_http=442,
            consumed_http=consumed_http,validated_http=validated_http,accounting_confirmed=accounting_confirmed,
            observed_completions=sum(r['state']=='observed' for r in translated),calls=calls),
        'metrics.json':dict(schema=1,review_mode=REVIEW_MODE,semantic_quality_claim=None,
            generation_prompt_tokens=generation_prompt_tokens,generated_tokens=generated_tokens,
            raw_arm_timings=timings,resources=metrics,reconciled_protocol=reconciled)}
    h.require(sum(len(h.canonical(value)) for value in result.values())<=16*h.MIB,'public export byte cap')
    result['manifest.json']=dict(schema=1,files=[dict(name=name,bytes=len(h.canonical(value)),
        sha256=h.digest(h.canonical(value))) for name,value in result.items()],private_data_included=False,
        treatment_identities_public=True,guaranteed_treatment_blinding=False)
    return result


def safe_terminal(result):
    """Print only selected booleans/enums, never raw causes or exception strings."""
    status=result.get('status') if type(result) is dict else None
    return dict(schema=1,status='complete' if status=='operationally_complete' else 'incomplete',
        cleanup_confirmed=type(result) is dict and result.get('cleanup_confirmed') is True,
        protocol_complete=type(result) is dict and result.get('protocol_complete') is True,
        reason_code='COMPLETE' if status=='operationally_complete' else 'OPERATIONAL_FAILURE',
        review_mode=REVIEW_MODE)


def preflight_receipt(plans,manifest_sha,source_plan_sha):
    """Closed complete-token-preflight projection, before any model output."""
    import re
    h.require(tuple(plan.row_id for plan in plans)==h.ROW_IDS,'no completed receipt for partial preflight')
    h.require(all(re.fullmatch('[0-9a-f]{64}',value) for value in (manifest_sha,source_plan_sha)),
              'public preflight source-plan bindings')
    active={plan.row_id for plan in plans if plan.active}
    rows=[]
    for plan in plans:
        h.require(type(plan.active) is bool and type(plan.eligible) is bool,'public preflight flags')
        values={}
        for side in ('baseline','provisional','candidate'):
            receipt=getattr(plan,side)
            h.require(type(receipt.count) is int and receipt.count>0 and type(receipt.body) is bytes,
                      'public preflight positive integer count')
            if side!='provisional':h.require(receipt.count<=384,'public actual-request token cap')
            values[side]=dict(input_tokens=receipt.count,request_sha256=h.digest(receipt.body))
        rows.append(dict(id=plan.row_id,active=plan.active,eligible=plan.eligible,requests=values))
    contrasts={f'N{n:03d}' for n in range(1,37) if n%3!=0}
    complete=[family for family in range(12) if {f'N{3*family+1:03d}',f'N{3*family+2:03d}'}<=active]
    headwords=[dict(headword_ordinal=i+1,complete_contrast_pairs=sum(f in complete for f in (2*i,2*i+1)),
        active_ambiguous_rows=sum(f'N{3*f+3:03d}' in active for f in (2*i,2*i+1))) for i in range(6)]
    try:h.validate_preflight(plans);coverage='pass'
    except h.TerminalFailure:coverage='fail'
    result=dict(schema=1,component_manifest_sha256=manifest_sha,source_plan_sha256=source_plan_sha,
        source_pins={key:h.PINS[key] for key in ('fresh_sources','legacy_sources','lexicon')},
        schedule_sha256=h.SCHEDULE_SHA256,token_preflight_complete=True,measured_completions_before_receipt=0,
        coverage_status=coverage,coverage=dict(active_contrasts=len(contrasts&active),complete_families=len(complete),
            headwords=headwords,active_controls=sum(f'N{n:03d}' in active for n in range(41,49)),
            inactive_control_violations=sum(f'N{n:03d}' in active for n in range(37,41)),
            active_legacy_rows=sum(row.startswith('R') for row in active)),rows=rows)
    h.require(len(h.canonical(result))<=65536,'public preflight receipt cap')
    return result
