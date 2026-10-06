# Proposed narrow native bridge/ownership amendment

Status: source implemented and synthetic failure tests only. This note does not
approve execution, source publication, new permissions, or a new inherited claim.
All native factories, native entry points and direct native adapter operations
remain unconditionally denied with `SOURCE_ONLY`; no environment or CLI flag can
release them. The pure injected algorithms can be tested without native work.

The accepted persistent-helper proposal is
`PERSISTENT_HELPER_AMENDMENT_PROPOSAL.md`, SHA-256
`f5fc65a31677360f5125365d55e5f050aec16ad5c27ed9dfa72543b33d5a65ac`.

## Exact inherited API conflicts

The pinned `guarded_runtime.OwnedSupervisor.launch` uses `stdin=DEVNULL`, merges
stderr into stdout, installs a stdout-to-evidence log reader, and overwrites
`phase_end` with its launch deadline. These semantics cannot carry private framed
persistent IPC or exclude idle time from the aggregate active allowance. The
pinned `verified_bootstrap` and `activation_scope` only recognize the previous
worker closure, claim shape, and role/input binding. Calling those entry points
for this new helper would not establish new authorization or new source pins.
No upstream file was changed. A source search of the pinned published owner,
controller, bootstrap and other Python modules found no process-group creation,
termination or group-gone receipt. The extension explicitly sets
`start_new_session=False`, `process_group=None`, and no `preexec_fn`, preserving
whatever containment the outer coordinator already has. Every helper abort
hands failure to the same inherited controller before sharing its cleanup
ceiling. It cannot manufacture an outer containment proof.

The proposed extension is limited to the existing single `helper` ownership slot:

- Register the exact existing `Intent` in the existing owner's `intents` before
  launch, preserve its durable launch-intent event, and retain the existing
  `AttemptControl` cancellation, owner monitors, inherited phase/work/post-ready,
  lifecycle, cleanup and outer deadlines
- Use a private nonblocking stdin/stdout pair with stderr discarded. Never
  attach a public log reader to IPC. Use bounded four-byte framing, strict JSON,
  one in-flight command, fixed 224 commands at E=24, and no retries
- Add independent helper deadline and resource monitors, registered among the
  owner's owned threads and joined by its cleanup path. They do not change the
  owner's global phase deadline. The coordinator/controller remains independent
  of blocked pipe/resource work
- Share one injected nonblocking wait4 process adapter across the owner and
  bridge. It caches exactly one owned child's exit and final full-process
  ru_maxrss/user+system CPU; inherited owner.poll/wait cannot discard final
  resource facts. Only the same unreaped child PID may be signalled
- Admit the new entry only after a separately reviewed new coordinator/claim
  binding. The new entry independently binds direct parent PID/argv/executable,
  cwd, monotonic deadlines, exact row hashes/E=24 and the immutable closure

`NativeBackend` requires the exact verified upstream runtime/owner/controller to
be supplied by the reviewed assembler. It never imports those dependencies from
ambient search paths. It deliberately refuses to create a new owner/controller
or invoke an old scientific stage. A future release must verify this injection
against the existing upstream manifest and provide the new coordinator admission;
the old Actions release does not authorize it.

## Implemented integration interface

`BoundedBridge(protocol, backend, now_ns=..., phase_deadline_ns=...,
work_end_ns=..., postready_end_ns=..., cleanup_end_ns=...)` accepts the
hash-verified protocol and an injected backend. A native pairing requires the
same `time.monotonic_ns` clock used by native deadlines. Tests use a fake clock.

- `start()` observes launch through completely validated READY, returns only the
  pure worker READY fields, and records actual cold-start elapsed time
- `request(message, validate)` sends one frame and invokes the strict client
  validator before ending active accounting. FINISH remains active through
  `close()`, which confirms successful exit, final RSS/CPU, EOF and reaping
- `abort()` follows the same inherited cleanup ceiling and reports only fixed,
  bounded cleanup/reaping flags. Unknown/late reaping never becomes success; one fixed effective emergency
  deadline spans stop, reap, every stream close and every thread join
- `metrics()` returns exactly owner_identity, policy_in_owner_process,
  peak_rss_bytes and cold_start_ns. `timing_metrics()` adds aggregate active work,
  final worker CPU, idle-inclusive lifetime, startup/finish time and command count

The single READY wire frame also binds worker_identity, closure_sha256,
peak_rss_bytes and cpu_ns. The bridge validates and removes that envelope before
returning READY to the client. There are no extra commands or error frames.

`usage_worker_entry.build_spec` produces the exact isolated `-I -S -B -c`
invocation. The bridge pins both the exact entry source and literal bootstrap
bytes before accepting the spec. A future approved source release must update
these pins, not bypass their checks. The literal bootstrap verifies entry bytes before executing them. Its reviewed
body first arms a child-owned kernel-default SIGALRM at
min(conservative launch anchor +600s, inherited cleanup end), before entry source
reads or policy imports. The anchor and cleanup end are supplied as bounded
argv scalars and later matched to the immutable binding. It unblocks only that
child's SIGALRM, keeps existing stricter CPU limits, disables core dumps, and
rejects startup stdin EOF or data sent before READY. Normal framed reads also
terminate on EOF. The actual literal begins with unconditional SOURCE_ONLY
before any native import/call; tests execute its body using fake kernel modules.
The alarm's remaining duration is recomputed immediately before arming and the
same absolute deadline is checked again immediately afterward. Setup delay is
never added back. This guard begins only once Python reaches the bootstrap body;
it cannot establish pre-exec containment, guarantee timely exit from an
uninterruptible kernel state, or retrospectively confirm an unknown spawn/reap
outcome.
Entry verifies every closure member before module execution: exact production
guard file, frozen policy, frozen bank, and final pinned policy-worker module.
All source paths are explicit, reads bounded and no-follow, and no workspace
path is added to Python's module search path. The worker imports only its exact
three source modules and their explicit standard-library dependencies. It
receives compact row/source-hash metadata, never a source fixture or private
criteria/output file. Actual source arrives in individual PREPARE commands.
Source-bearing response bytes are discarded before the next idle read.

## Unresolved release blocker: interrupted or indefinitely blocked spawn

The inherited controller can stop waiting for a blocked Popen by its shared
absolute deadline and report an unknown OS outcome. That does **not** prove that
a child created inside an indefinitely blocked Popen was terminated or reaped:
the child handle/PID may not yet have returned to Python. The extension registers a single preallocated adoptable handle before spawn,
never publishes raw Popen, applies cancellation queued before adoption, and
kills/reaps late returns; it never calls unknown pending launch cleanup successful. But a truly
never-returning spawn still cannot satisfy a strict "no orphan under blocked
spawn" guarantee with this inherited API alone.

This is a hard execution blocker, not a passing fake-test claim. Resolving it
requires a separately reviewed ownership primitive that can identify/terminate
the child before a potentially blocking spawn returns, or a precisely reviewed
change to the operational requirement. No extra launcher process, cgroup,
permissions, service, external supervisor, or lifetime extension is introduced
by this source. The same incomplete-state treatment applies to an OS operation
or owned monitor that cannot be confirmed finished by the shared deadline.

## Synthetic verification boundary

`python -B -m unittest test_usage_helper_bridge -q` tests pure framing, fake
backpressure, cancellation, deadline charging, exact command exhaustion,
unknown spawn/reap outcomes, identity/resource errors, native-denial paths,
entry binding predicates, and the shared wait4 adapter with a fake kernel.
These tests do not establish actual OS ownership, peak RSS, CPU, syscall
interruptibility, scheduling latency or process cleanup. No real child, pipe,
network, model/tokenizer, source fixture, private criteria or prior output was
used. Actual native execution remains prohibited pending review and release.
