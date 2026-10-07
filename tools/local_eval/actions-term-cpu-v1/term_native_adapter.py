"""Narrow source wiring to the unchanged owned-runtime transport/evidence.

No acquisition, host check, process, network or model is invoked on import.
Native hooks require exact verified Actions admission in this derivative.
"""
from term_runner_source import execute_stage
from term_evidence_validation import validate_final_evidence


def require_native_release():
    import activation_scope
    grant = activation_scope.require_role("actions")
    activation_scope.require(globals().get("_VERIFIED_BOOTSTRAP_SHA") == grant["manifest_sha"],
                             "verified usage adapter source required")
    return grant


class StageHooks:
    """Injected exact runtime/controller objects; tests may supply inert fakes.

    now_ns is the one monotonic clock, used for measured spans, request stamps
    and deadlines. No independent seconds clock is accepted.
    """
    def __init__(self, core, runtime, owner, transport, evidence, worker, *, now_ns, clock_resolution_seconds):
        self.core, self.runtime, self.owner = core, runtime, owner
        self.transport, self.evidence, self.worker = transport, evidence, worker
        self.now_ns, self.clock_resolution_seconds = now_ns, clock_resolution_seconds
        self.pending, self.transcripts, self.intervals = [], [], []

    def check(self):
        self.owner.check()

    def ready_marker(self):
        while not self.owner.loaded.is_set():
            self.check()
            self.owner.loaded.wait(.05)

    def postready_limit(self, seconds):
        self.core.h.require(seconds == 600, "unchanged postready bound")
        self.owner.postready_end = min(self.now_ns()/1e9 + seconds, self.owner.work_end, self.owner.outer_end)

    def phase(self, name, seconds):
        self.owner.set_phase(name, seconds)

    def resume_postready_limit(self):
        self.owner.phase_end = self.owner.postready_end

    def event(self, event):
        self.owner.record(event)

    def publish_preflight(self, plans):
        self.plans = tuple(plans)
        self.owner.publish_preflight(plans)

    def exchange(self, ledger, kind, row, arm, body, validate):
        h = self.core.h
        self.check()
        start_ns = self.now_ns()
        capture = self.runtime.WireCapture()
        stamps = {}
        failure = None
        previous_total = ledger.total
        def validated(raw):
            result = validate(raw)
            stamps["end_ns"] = self.now_ns()
            return result
        def prepared():
            # checked_exchange creates its absolute deadline before this hook.
            stamps["request_start_ns"] = self.now_ns()
            return body
        try:
            result = h.checked_exchange(ledger, kind, row, arm, prepared, self.transport,
                lambda: self.now_ns()/1e9,
                [v for v in (self.owner.outer_end, self.owner.phase_end, self.owner.work_end,
                             self.owner.postready_end) if v is not None], validated, capture)
            return result, self.now_ns()-start_ns
        except BaseException as exc:
            failure = type(exc).__name__
            raise
        finally:
            wire = bytes(capture.raw)
            deadline = getattr(getattr(self.transport, "deadline", None), "end", None)
            record = dict(kind=kind, row=row, arm=arm, request_body=body, response_wire=wire,
                          request_sha256=h.digest(body) if body is not None else None,
                          response_sha256=h.digest(wire), start=stamps.get("request_start_ns", start_ns)/1e9,
                          validated_end=stamps.get("end_ns", 0)/1e9 if "end_ns" in stamps else None,
                          deadline=deadline, request_number=ledger.total if ledger.total > previous_total else None,
                          attempted=ledger.total > previous_total, status="failed" if failure else "validated", failure=failure)
            self.transcripts.append(record)
            private = {key: value for key, value in record.items() if key not in ("request_body", "response_wire")}
            private.update(request_hex=body.hex() if body is not None else None, response_wire_hex=wire.hex())
            self.pending.append(private)
            if kind in ("health", "models", "preflight"):
                self._flush_wire()

    def _flush_wire(self):
        pending, self.pending = self.pending, []
        for record in pending:
            self.evidence.json("wire.jsonl", record)

    def record(self, name, value):
        if name == "arm":
            self._flush_wire()
            self.intervals.append(value)
            self.evidence.json("results.jsonl", value)
        elif name == "all_rows":
            self._flush_wire()
            self.evidence.json("all_rows.json", value)
        else:
            self.evidence.json("metadata.json", dict(event=name, result=value))


def generation_stage(core, inventory, alias, bank_bytes, hooks, integrity, expected_error):
    """Source adapter after verified acquisition/host/server/owner setup only."""
    require_native_release()
    result = execute_stage(core, inventory, alias, bank_bytes, hooks, integrity, expected_error)
    reconciliation = validate_final_evidence(core, inventory, result["plans"], alias, bank_bytes,
        hooks.transcripts, hooks.intervals, hooks.clock_resolution_seconds, integrity, expected_error,
        guard_source_bytes=hooks.runtime.pinned_file(hooks.runtime.AUDITED/"myutils/local_translation_integrity.py",core.h.PINS["integrity"],65536))
    hooks.evidence.create("protocol_reconciliation.json")
    hooks.evidence.json("protocol_reconciliation.json", reconciliation)
    return result, reconciliation


def bind_native_hooks(core, runtime, owner, controller, transport, evidence, inventory,
                      make_verified_worker_spec, *, now_ns, clock_resolution_seconds):
    """Bind the reviewed controller and private IPC adapter without old globals.

    make_verified_worker_spec runs at helper start, after readiness and the
    post-ready deadline are set. It must create the immutable closure/binding
    packet through the existing exclusive owner-only evidence writer and return
    (spec, closure_sha256, setup_metrics). Host paths, parent identity and packet bytes are
    execution-plan bindings, never guessed or accepted through a CLI switch.
    """
    require_native_release()
    from usage_helper_bridge import BoundedBridge, NativeBackend
    from term_worker import WorkerClient
    import term_worker as protocol

    class DeferredBridge:
        def __init__(self): self.bridge = None
        def start(self):
            core.h.require(self.bridge is None, "one helper only")
            spec, closure_sha, setup = make_verified_worker_spec()
            core.h.require(type(setup) is dict and set(setup) == {"launch_ns", "parent_setup_ns",
                "parent_setup_cpu_ns", "inherited_phase_end_ns"} and
                all(type(v) is int and v >= 0 for v in setup.values()), "complete helper setup timing")
            backend = NativeBackend(protocol, runtime, owner, controller, spec, closure_sha256=closure_sha)
            self.bridge = BoundedBridge(protocol, backend, now_ns=now_ns,
                phase_deadline_ns=lambda: int(owner.phase_end*1e9),
                work_end_ns=int(owner.work_end*1e9), postready_end_ns=int(owner.postready_end*1e9),
                cleanup_end_ns=min(int(owner.outer_end*1e9), int(owner.lifecycle_end*1e9)), expected_commands=178+3*len(inventory.eligible_ids),
                launch_ns=setup["launch_ns"], parent_setup_ns=setup["parent_setup_ns"],
                parent_setup_cpu_ns=setup["parent_setup_cpu_ns"])
            ready = self.bridge.start()
            owner.check()
            # Restore exactly the inherited phase captured before narrowing;
            # bootstrap consumed active budget and never earns extra phase time.
            owner.phase_end = setup["inherited_phase_end_ns"]/1e9
            owner.check()
            return ready
        def request(self, message, validate): return self.bridge.request(message, validate)
        def close(self): return self.bridge.close()
        def abort(self): return self.bridge.abort() if self.bridge is not None else None
        def metrics(self): return self.bridge.metrics()
        def timing_metrics(self): return self.bridge.timing_metrics()
        @property
        def owner_identity(self): return self.bridge.owner_identity

    return StageHooks(core, runtime, owner, transport, evidence,
                      WorkerClient(DeferredBridge(), core.policy, inventory.eligible_ids),
                      now_ns=now_ns, clock_resolution_seconds=clock_resolution_seconds)


def run_real(*args, **kwargs):
    require_native_release()
    raise RuntimeError("verified coordinator stage binding required")
