"""Isolated helper admitted only through its bound owned-worker receipt.

The bootstrap loads only the small helper module set. Pure benchmark tests use
synthetic rows and a fake clock; no real helper measurement ran in preparation.
"""
import json
import os
from pathlib import Path
import sys
import time

# The verified bootstrap preloads these exact modules under Python -I.
# No script/current directory is inserted into the module search path.
import activation_scope
import cpu_harness as h
import frozen_renderer as renderer


def helper_benchmark(rows, alias, lexicon, lexicon_sha, receipts, now):
    h.require(type(rows) is list and [row['id'] for row in rows]==list(h.ROW_IDS),'helper rows')
    h.require(type(receipts) is dict and len(receipts)<=176 and
              all(type(k) is str and len(k)==64 and type(v) is int and v>0 for k,v in receipts.items()),
              'helper receipt table')
    samples=[];renders=0
    def count(messages):
        request=h.serialize_request(messages,alias)
        key=h.digest(request)
        h.require(key in receipts,'helper unbound local count lookup')
        return receipts[key]
    for iteration in range(11):
        for row in rows:
            before=now()
            baseline=renderer.baseline_messages(row['source'])
            decision=renderer.render_candidate(row['source'],baseline,lexicon,
                reviewed_sha256=lexicon_sha,count_prompt_tokens=count)
            h.require(decision.reason==row['reason'] and decision.hint_active==row['active'], 'helper decision drift')
            after=now();renders+=1
            if iteration:
                samples.append(after-before)
    h.require(renders==968 and len(samples)==880,'helper count accounting')
    return dict(priming_renders=88,measured_renders=880,total_renders=968,
                samples_ns=samples,render_ns=h.quantiles(samples))


def validate_helper_result(result, clock_resolution):
    h.require(type(result) is dict and result.get('priming_renders')==88 and
              result.get('measured_renders')==880 and result.get('total_renders')==968 and
              type(result.get('samples_ns')) is list and len(result['samples_ns'])==880,'helper result schema/count')
    quantiles=h.quantiles(result['samples_ns'])
    h.require(quantiles==result.get('render_ns'),'helper quantile drift')
    h.require(type(result.get('peak_rss_bytes')) is int and 0<result['peak_rss_bytes']<=32*h.MIB,'helper RSS gate')
    h.require(quantiles['p95']<=5_000_000,'helper render P95 gate')
    h.require(min(result['samples_ns'])>=100*clock_resolution*1e9,'helper timer resolution')
    return result


def main():
    raise_if_not_released()
    import resource
    h.require(len(sys.argv)==3 and sys.argv[1]=='--input','helper CLI')
    fd=os.open(Path(sys.argv[2]),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        with os.fdopen(fd,'rb',closefd=False) as source:raw=source.read(1024*1024+1)
    finally:os.close(fd)
    h.require(len(raw)<=1024*1024,'helper input cap')
    data=h.strict_json(raw)
    result=helper_benchmark(data['rows'],data['alias'],bytes.fromhex(data['lexicon_hex']),
                            data['lexicon_sha256'],data['receipts'],time.perf_counter_ns)
    result.update(peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                  input_sha256=h.digest(raw),clock=vars(time.get_clock_info('perf_counter')))
    output=h.canonical(result)
    h.require(len(output)<=65536,'helper result cap')
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


def raise_if_not_released():
    try:return activation_scope.require_role('helper')
    except activation_scope.Denied as exc:raise h.Disabled(str(exc)) from None


if __name__=='__main__':main()
