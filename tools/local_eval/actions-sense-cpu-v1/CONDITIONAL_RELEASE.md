# Conditional Actions admission, prepared without execution

This narrow operational revision preserves the independently accepted 180-test
Actions manifest b28f49faa2d33255c1486c407aadbf88d4a4f752a82e469d929f3fb42fb12c2b
in accepted-actions-source-b28. It replaces the three unconditional operational
gate failures with conditional admission so reviewed source A can be immutable.
Workflow B executes that source and cannot patch it or replace its manifest.
No native operation, actual claim, download, Git write or workflow run was used
to prepare this revision. Source publication and actual B activation remain root
release decisions for the owner's already approved single Actions attempt.

## Exact path to admission

1. The only public CLI is verified_bootstrap.py, with exactly manifest path,
   manifest SHA, role and fixed role argument. Roles are actions, acquire,
   validate and helper; generic coordinator/run/enable flags are rejected.
   Python must have -I and -B. The manifest path is exactly the adjacent
   KIT_MANIFEST.json. The actions invocation also needs the declared GitHub
   service/run-attempt and manifest context. These checks permit source reads
   only, not acquisition, claims, processes or sockets.
2. The bootstrap hash is fixed in the immutable B template. Its existing
   verified-byte loader verifies and compiles exactly the manifest-bound module
   bytes, without pyc or path imports. It injects a process-bound read-only
   invocation record into activation_scope. Loading that record grants no
   runtime permission. Importing activation_scope separately grants nothing.
3. The actions entry uses that distinct source-read gate for its unchanged exact
   event, A/B parent chain, clean checkout, A inventory, sole-B-workflow diff and
   rendered-template checks. A failed guard cannot reach runtime admission.
   Only after all checks pass does it admit the actions role, binding the source
   manifest/root, real process PID and structured actual bootstrap argv.
4. The immutable claim records coordinator_pid and coordinator_argv along with
   the existing source/provider/plan/resource bindings. Its execution_policy is
   the exact string verified-actions-and-owned-parent-v1. This declaration is
   not an enable switch; pure plan validation cannot install a runtime grant.
   Before the claim, actual PID/Python identity must match. The existing host,
   resource, port, one-shot, output, deadline and cleanup checks still apply.
5. Each existing acquire/validate/helper child enters only through the verified
   bootstrap. Before native work it reads only the fixed canonical owner-only
   claim, checks its canonical bytes, source/manifest/plan pins and role/input
   path, and verifies its actual direct parent PID, exact parent argv as a list,
   parent/self Python executable, output cwd and live outer attempt interval.
   The acquire and validate role arguments are the exact fixed claim path;
   helper uses only the exact owned helper_input.json. Bootstrap role, admitted
   role and worker dispatch must agree. Acquire/validate workers check their reread of the claim
   against the SHA captured on admission. Helper input remains bound to its fixed
   path and the parent-checked input SHA in the existing helper result. Any mismatch stops before its stage.
6. guarded_runtime.require_activation admits only actions/acquire/validate.
   isolated_helper.raise_if_not_released admits only helper. Helper bootstrap
   loads only actions_policy, activation_scope, cpu_harness, frozen_renderer and
   isolated_helper, preserving the separate 32-MiB measurement. Generic
   cpu_harness.run_real, guarded_runtime.claim_once and guarded_runtime.main
   stay unconditionally disabled. No general coordinator CLI remains.

There is no environment boolean, approval CLI switch, inherited credential,
new pipe, dispatcher, install step or extra inference/network/child allowance.
A claim alone is insufficient: it must agree with the real parent process and
verified source invocation. Process grants are local, cannot survive exec into a
fresh interpreter and are checked against the current PID and bootstrap role.
They do not replace or reset any request, phase, resource or cleanup deadline.

## Trust limitation and external activation

This uses the already accepted GitHub service and trusted-checkout policy. It is
not cryptographic attestation or authentication against hostile Python/same-UID
code; such a process can inspect or modify its own memory and files. A PID or an
environment variable alone is not accepted as proof. The exact immutable workflow,
source checks and parent run/job reconciliation remain necessary together.

The final source inventory must include this conditional gate before source A is
published. Root reviews that complete inventory, prepares and reviews immutable
A, renders only the existing source/manifest/bootstrap placeholders in workflow
B, verifies exact objects/current ref/no prior B run, and releases the one normal
A→B push. B never sed-patches Python or rewrites A's manifest. Actual A/B IDs
are not guessed in this package. A reactivation requires a new explicit owner
attempt authorization, not an automatic rerun or repaired claim.

All 88 pairs, 176 completions, 442 requests, model/data/sampling/quality/coverage/
cost gates, resource bounds, 1,475-second inner limit, original phase budgets and
20-second cleanup reserve remain fixed. The new checks use the existing job-setup boundary or owned-worker phase;
no attempt, request, phase or cleanup time allowance is added. Private
criteria remain digest-only and outside the runner. The public evidence policy
and later label-blind review limitation are unchanged.
