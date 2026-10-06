# Short bilingual usage-example feasibility result — 2026-10-06

## Decision

**NO_GO: the frozen example prefix fails its real-token budget and coverage prerequisite.** No translation completion was issued. Retain the existing optional Hy-MT2-1.8B Q4 baseline and defaults. This result establishes neither a translation improvement nor a translation-quality regression.

The single [GitHub CPU run](https://github.com/yuxixi311/LunaTranslator-UI-Custom/actions/runs/37519430542) used source commit `d8d4501722a5b7177c5bcf1a309fd2ea5cc54e03` and activation commit `0e9af3bccda4ac162e181fa8b17026a2b3cc8d76`. The run ended with GitHub status `failure`. Its raw terminal record is retained as operationally incomplete; the independently reproduced token-feasibility rejection and a separate cleanup-reporting uncertainty are described below.

## Frozen question and scope

The candidate prepended at most one intact, attributed Japanese–Chinese usage example to the unchanged translation prompt. Eight fixed educational examples and a literal contextual-anchor matcher were frozen before the new cases were authored. Matching did not infer a correct sense or require copying the example's translation. The licensed examples and their adaptation notices remain in the [published experiment source](https://github.com/yuxixi311/LunaTranslator-UI-Custom/tree/d8d4501722a5b7177c5bcf1a309fd2ea5cc54e03/tools/local_eval/actions-usage-cpu-v1); they were not weight training or a larger model.

The corpus contained 87 pairs: 40 historical regressions, 15 previously seen regressions selected before candidate evaluation, and 32 independently authored fictional cases. The new set contained eight families, each with two carrier cases, one challenge and one control. Private semantic criteria were kept separate. The complete planned experiment had 174 completions and 398 loopback requests; no automatic retry was allowed.

Before generation, every baseline and prospective candidate prompt required a valid positive full-chat token count. Baseline and candidate counts each had a 384-token ceiling. Added tokens could not exceed `min(16, floor(0.40 × baseline_tokens))`. A valid over-budget example caused abstention to the byte-identical baseline prompt. Invalid counts would stop the batch. Generation also required at least 12 active carriers, both carriers active in at least six families, and active coverage of all six preregistered challenge types.

## Observed feasibility

Both fixed assets were downloaded once and verified against their pinned sizes and SHA-256 values: the 1,133,080,448-byte model and 17,551,895-byte runtime. The server reached readiness and returned all 174 preflight counts. Together with two readiness requests, **176 requests were consumed and validated**. The remaining 222 planned requests were unissued, including all 174 completions. Final translation slots have no observed text or generation usage.

Of 87 sources, 24 were eligible for a prospective example under the frozen surface policy. Of those 24:

- 21 exceeded the absolute 16-added-token limit
- One additional case added 16 tokens but had a 39-token baseline, whose relative allowance was 15
- Only two cases were admitted; both belonged to the same example family

Eligible baseline prompts ranged from 36 to 49 tokens and prospective candidate prompts from 54 to 72. Added tokens ranged from 16 to 25. No prospective prompt exceeded the absolute 384-token ceiling. Seven of the eight intact examples required more than 16 added tokens in the tested format.

| Frozen coverage requirement | Required | Observed |
| --- | ---: | ---: |
| Active new carrier cases | 12 | 2 |
| Families with both carriers active | 6 | 1 |
| Distinct active challenge types | 6 | 0 |

The candidate therefore fails the prerequisite independently of downstream reporting. No cases were removed, reclassified or lengthened, and no example or token limit was changed to rescue this round. No repeated attempt followed the failure.

An independent audit reproduced all 87 admission decisions and all 261 baseline/prospective/actual request-hash bindings from the public evidence. This checked the arithmetic and exact requests using the server-reported counts; it did not rerun the tokenizer. The final five public evidence payloads matched their manifest hashes.

## Operational reporting and limitations

The raw terminal record reports `incomplete`, `OPERATIONAL_FAILURE`, first failure `preflight/OWNER_FAILURE`, and aggregate `cleanup_confirmed=false`, with `CONTROLLER_RESULT_REJECTED`. Earlier collector accounting and per-child cleanup records report confirmation. The helper record also says its launch was not entered while reporting an exited child, which conflicts with the executed preflight protocol.

Source inspection explains a reporting path in which rejection of coverage aborts the helper and cancels the controller before the more specific failure is retained. It also identifies missing helper launch/adoption diagnostic transitions. These are reporting defects; they do not overturn the reproduced feasibility rejection. The raw records have not been rewritten. **Overall confirmed clean completion is not established**, and the aggregate false flag alone does not prove a leaked process. Standard ephemeral hosted-runner teardown is an outer containment measure, not an observed exact cleanup time.

Observed runner peak RSS was 31,866,880 bytes and server peak RSS was 2,077,278,208 bytes. The final helper-lifecycle field is null and there are no measured helper samples. These observations do not establish the helper's memory/latency gates, paired translation costs, Windows/GPU behavior, or semantic accuracy. There were zero generated tokens and no semantic review of nonexistent translations.

## Evidence bindings

- Kit manifest SHA-256: `321b4743c3cf7610324b62e3dfeb6ab5c6403db36becd599c3ca55b01ca83739`
- Frozen source-plan commitment: `da7707839e131635a03697a5eba1d13926720ab23194b8607c057287f97b8c3b`
- Runtime example-bank SHA-256: `9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a`
- Final public evidence manifest SHA-256: `3c9bb8dfbb8c82f71ac06323c0ac946824d8dd49da8bce1c13fe31b1255e9bb2`
- Independent result audit SHA-256: `efcc69068bc94ec24a2b1c3023648397dda100eef47e1755305b87b7fc3d9601`

The source and result record preserve the original claim and failed attempt. This summary excludes private criteria, full fresh case text, private paths and raw host logs.

## Next-method decision

Do not rerun this candidate under relaxed limits or substitute shorter examples after observing these results. A separate reporting repair may preserve more precise failure and lifecycle evidence, but cannot convert this candidate into a pass.

The next source-only review considered a genuine same-record speaker label. Inspected hook, OCR, file and HTTP paths do not establish a reliable speaker/body provenance contract; generic hook subcontext and asynchronous arrival are insufficient. Existing translated history is not a trustworthy source record. Consequently, another grounded-context/speaker experiment is currently **NO_GO pending a useful verified structured source**, rather than a measured quality failure. The earlier unsuccessful short-context trial remains in the history; no native transport overhaul is proposed to manufacture a new test.

The next bounded design question is deterministic consistency for explicitly supplied, unambiguous terminology. It must distinguish known proper names/terms from ordinary-word ambiguity and demonstrate a mechanism materially different from the earlier inconclusive glossary round. Any later test needs a frozen method, new independent criteria, retained seen regressions, and the existing quality and resource safeguards. No implementation default, new inference, model growth or training follows from this checkpoint.
