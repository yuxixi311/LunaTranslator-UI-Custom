"""Pure bounded reconciliation of full synthetic/request evidence.

No files, network, process or model calls. It cannot prove that supplied clocks
or bytes originated from a real OS run; provenance remains an execution gate.
It does not grade semantics or read private criteria.
"""
import math
import cpu_harness as h


class MemoryReader:
    def __init__(self, raw):
        self.raw, self.position, self.closed = raw, 0, False
    def read(self, n, remaining):
        result = self.raw[self.position:self.position+n]
        self.position += len(result)
        return result
    def close(self):
        self.closed = True


def finite_time(value):
    h.require(type(value) in (int,float) and math.isfinite(value) and value >= 0, 'invalid timestamp')
    return value


def validate_final_evidence(plans, sources, alias, lexicon, lexicon_sha, renderer,
                            transcripts, arm_intervals, clock_resolution_seconds,
                            integrity, expected_error, *, material_noise=False):
    """Reconstruct every protocol result and derive cost flags from exact evidence.

    transcripts contain the 442 fixed endpoint intents in order, full bounded
    raw HTTP response bytes, exact request bytes and hashes, and request start /
    validated-end / absolute-deadline stamps. arm_intervals are the fixed 176
    measured intervals; all recurring calls must fit within their candidate arm.
    Output qualities are derived again using the unchanged injected checker.
    """
    h.validate_alias(alias)
    h.validate_preflight(plans)
    h.require(type(sources) is dict and set(sources)==set(h.ROW_IDS) and
              all(type(v) is str and len(v)<=4096 for v in sources.values()), 'source identities')
    h.require(type(lexicon) is bytes and len(lexicon)<=8192 and h.digest(lexicon)==lexicon_sha,
              'lexicon binding')
    h.require(type(transcripts) is list and len(transcripts)==442 and
              type(arm_intervals) is list and len(arm_intervals)==176, 'complete evidence denominator')
    by_id={p.row_id:p for p in plans}
    for plan in plans:
        for receipt in (plan.baseline,plan.provisional,plan.candidate):
            h.require(type(receipt.body) is bytes and len(receipt.body)<=32768 and
                      type(receipt.count) is int and receipt.count>0 and
                      (receipt.runtime,receipt.model_tokenizer,receipt.template)==
                      (h.PINS['server'],h.PINS['model'],h.PINS['template']), 'receipt identity')
        responses=iter((plan.baseline.count,plan.provisional.count))
        replay=h.preflight_pair(plan.row_id,sources[plan.row_id],alias,lexicon,lexicon_sha,
                                renderer,lambda _:next(responses))
        h.require(replay==plan,'sealed plan does not match frozen source/renderer')
    intervals={}
    previous_end=0
    previous_perf_end=0
    for expected, interval in zip(h.SCHEDULE,arm_intervals):
        h.require((interval.get('row'),interval.get('arm'))==expected,'arm timing schedule')
        start,end=(finite_time(interval.get(k)) for k in ('start','end'))
        h.require(end>start and start>=previous_end,'invalid/overlapping arm interval')
        perf_start,perf_end,total_ns=(interval.get(k) for k in ('perf_start_ns','perf_end_ns','total_ns'))
        h.require(all(type(v) is int for v in (perf_start,perf_end,total_ns)) and
                  perf_start>=previous_perf_end and perf_end>perf_start and total_ns==perf_end-perf_start,
                  'authoritative perf_counter_ns interval missing/mismatched')
        previous_perf_end=perf_end
        previous_end=end
        intervals[expected]=(start,end,total_ns)
    ledger=h.RequestLedger()
    observations={}
    retained=0
    previous_end=0
    totals=dict(generation_prompt_tokens=0,generated_tokens=0,count_only_requests=0,count_only_input_tokens=0)
    first_arm_start=arm_intervals[0]['start']
    for index,(expected,record) in enumerate(zip(ledger.queue,transcripts)):
        kind,row,arm=expected
        h.require((record.get('kind'),record.get('row'),record.get('arm'))==expected,'transcript order')
        wire=record.get('response_wire');body=record.get('request_body')
        h.require(type(wire) is bytes and len(wire)<=65536+16384+16384,'response evidence cap')
        h.require(body is None or (type(body) is bytes and len(body)<=32768),'request evidence cap')
        retained+=len(wire)+(len(body) if body else 0)
        h.require(retained<=64*h.MIB,'global evidence cap')
        h.require(record.get('request_sha256')==(h.digest(body) if body is not None else None) and
                  record.get('response_sha256')==h.digest(wire),'wire digest mismatch')
        start,end,deadline=(finite_time(record.get(k)) for k in ('start','validated_end','deadline'))
        h.require(start>=previous_end and start<=end<deadline and
                  deadline-start<=h.ENDPOINTS[kind][3],'request absolute deadline evidence')
        previous_end=end
        reader=MemoryReader(wire)
        raw=h.BoundedWire(reader,h.Deadline(lambda:0,1)).response(h.ENDPOINTS[kind][2])
        h.require(reader.position==len(wire),'unconsumed/trailing response evidence')
        if kind in ('health','models'):
            h.require(body is None,'GET request body')
            h.readiness_response(kind,raw,alias)
        else:
            plan=by_id[row]
            if kind=='preflight':
                reference=plan.baseline if arm=='baseline' else plan.provisional
                h.require(end<=first_arm_start,'preflight after generation began')
            elif kind=='recurring':
                reference=plan.baseline if arm=='baseline' else plan.provisional
            else:
                reference=plan.baseline if arm=='baseline' else plan.candidate
            h.require(body==reference.body,'request differs from sealed receipt')
            if kind in ('preflight','recurring'):
                value=h.token_response(raw)
                h.require(value==reference.count,'observed count differs from receipt')
                totals['count_only_requests']+=1;totals['count_only_input_tokens']+=value
            else:
                result=h.completion_response(raw,alias,reference,sources[row],integrity,expected_error)
                totals['generation_prompt_tokens']+=result['usage']['prompt_tokens']
                totals['generated_tokens']+=result['usage']['completion_tokens']
                result.pop('raw_response')
                observations[(row,arm)]=dict(status='observed',**result)
            if kind in ('recurring','completion'):
                interval=intervals[(row,'candidate' if kind=='recurring' else arm)]
                h.require(interval[0]<=start and end<=interval[1], 'request outside measured arm')
        if index==178:
            ledger.seal_preflight(plans)
        ledger.consume(kind,row,arm)
    ledger.assert_complete()
    h.require(totals['count_only_requests']==264 and totals['generation_prompt_tokens']<=67584 and
              totals['generated_tokens']<=90112 and
              totals['generation_prompt_tokens']+totals['generated_tokens']<=157696,'final token accounting')
    rows=[]
    for row in h.ROW_IDS:
        base,candidate=intervals[(row,'baseline')],intervals[(row,'candidate')]
        rows.append(dict(id=row,active=by_id[row].active,complete=True,
                         baseline=base[2]/1e9,candidate=candidate[2]/1e9,
                         baseline_usage=observations[(row,'baseline')]['usage'],
                         candidate_usage=observations[(row,'candidate')]['usage']))
    return dict(status='validated_complete_protocol_evidence',tokens=totals,
                cost=h.paired_cost(rows,clock_resolution_seconds,material_noise=material_noise),
                all_rows=h.all_row_accounting(observations),semantic_quality_claim=None)
