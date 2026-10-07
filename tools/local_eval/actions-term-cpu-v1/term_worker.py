"""Pure bounded worker state machine and framing; no native child or I/O.

The future bootstrap must verify exact policy/guard/bank bytes before injecting
them. No network, tokenizer, model, application, process, or filesystem imports.
"""
from hashlib import sha256
import json
import re

FRAME_CAP = 32768
RECEIPT_CAP = 65536
POLICY_SHA256 = "f621ddec3e4cb7d449693f1ffb28a169276eabf5e7e49441d973d0868f3c2cca"
BANK_SHA256 = "f7d849ae54ec36d8247aeaadedd633523de92df35313c7bebb3a2073baeccd3b"
GUARD_SHA256 = "74b9e650d51e38f46db25f26b2018ae4dad2a3d4cbaa086110e0e4fffdbd22de"


class WorkerProtocolError(ValueError):
    """Only fixed code strings may cross the worker boundary."""


def require(condition, code="PROTOCOL"):
    if not condition:
        raise WorkerProtocolError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "FRAME")
        result[key] = value
    return result


def encode_frame(value):
    try:
        raw = canonical(value)
        require(0 < len(raw) <= FRAME_CAP, "FRAME")
        return len(raw).to_bytes(4, "big") + raw
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkerProtocolError("FRAME") from None


def decode_frame(frame):
    try:
        require(type(frame) is bytes and 4 < len(frame) <= FRAME_CAP + 4, "FRAME")
        size = int.from_bytes(frame[:4], "big")
        require(0 < size <= FRAME_CAP and len(frame) == size + 4, "FRAME")
        result = json.loads(frame[4:].decode("utf-8"), object_pairs_hook=_keys,
                            parse_constant=lambda _: (_ for _ in ()).throw(WorkerProtocolError("FRAME")))
        require(type(result) is dict, "FRAME")
        canonical(result)  # Reject JSON-escaped lone surrogates/nonfinite overflow.
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WorkerProtocolError("FRAME") from None


class ActiveBudget:
    """Fake-testable absolute deadlines, not OS enforcement or permission."""
    def __init__(self, launch_ns, parent_work_end_ns, parent_postready_end_ns, parent_cleanup_end_ns):
        values = (launch_ns, parent_work_end_ns, parent_postready_end_ns, parent_cleanup_end_ns)
        require(all(type(v) is int and v >= 0 for v in values), "BUDGET")
        self.launch = launch_ns
        self.work_end = min(launch_ns + 580_000_000_000, parent_work_end_ns, parent_postready_end_ns)
        self.cleanup_end = min(launch_ns + 600_000_000_000, parent_cleanup_end_ns)
        self.remaining = 15_000_000_000
        self.active_start = launch_ns  # Bootstrap is active work from launch.
        self.deadline = min(self.work_end, launch_ns + self.remaining)
        self.closed = False

    def finish_roundtrip(self, now_ns):
        require(not self.closed and self.active_start is not None and type(now_ns) is int and
                self.active_start <= now_ns < self.deadline, "BUDGET")
        self.remaining -= now_ns - self.active_start
        self.active_start = None

    def begin_roundtrip(self, now_ns, phase_end_ns):
        require(not self.closed and self.active_start is None and type(now_ns) is int and
                type(phase_end_ns) is int and self.launch <= now_ns < min(self.work_end, phase_end_ns) and
                self.remaining > 0, "BUDGET")
        self.active_start = now_ns
        self.deadline = min(now_ns + self.remaining, self.work_end, phase_end_ns)
        return self.deadline

    def emergency_deadline(self, now_ns):
        require(type(now_ns) is int and now_ns >= self.launch, "BUDGET")
        self.closed = True
        return min(now_ns + 20_000_000_000, self.cleanup_end)


class PolicyWorker:
    """Bounded term policy; native process ownership is outside this module."""
    def __init__(self, policy, declaration_bytes, row_ids, eligible_ids, source_bindings, integrity, expected_error):
        require(type(declaration_bytes) is bytes and sha256(declaration_bytes).hexdigest() == BANK_SHA256, "BINDING")
        policy.load_declarations(declaration_bytes)
        require(len(row_ids) == 88 and len(set(row_ids)) == 88 and
                tuple(i for i in row_ids if i in eligible_ids) == tuple(eligible_ids) and
                len(eligible_ids) <= 22 and set(source_bindings) == set(row_ids), "BINDING")
        self.p, self.declarations = policy, declaration_bytes
        self.integrity, self.expected_error = integrity, expected_error
        self.rows, self.eligible = tuple(row_ids), tuple(eligible_ids)
        self.source_bindings = dict(source_bindings)
        self.phase, self.index, self.pending, self.pending_restore = "preflight", 0, None, None
        self.receipts, self.commands, self.ready_sent = {}, 0, False
        self.expected_commands = 178 + 3 * len(self.eligible)

    def ready(self):
        require(not self.ready_sent and self.commands == 0, "STATE")
        self.ready_sent = True
        return dict(op="READY", policy_sha256=POLICY_SHA256, bank_sha256=BANK_SHA256,
                    guard_excerpt_sha256=GUARD_SHA256, expected_commands=self.expected_commands)

    def exchange_frame(self, frame):
        try:
            return encode_frame(self.handle(decode_frame(frame)))
        except Exception:
            self.phase, self.pending, self.pending_restore = "failed", None, None
            raise WorkerProtocolError("PROTOCOL") from None

    def handle(self, message):
        try:
            require(self.ready_sent and self.phase in ("preflight", "measured") and
                    self.commands < self.expected_commands and type(message) is dict, "STATE")
            self.commands += 1
            op = message.get("op")
            if op == "PREPARE": return self._prepare(message)
            if op == "GATE": return self._gate(message)
            if op == "RESTORE": return self._restore(message)
            if op == "SEAL":
                require(set(message) == {"op", "preflight_digest", "eligible_ids", "active_ids"} and
                    self.phase == "preflight" and self.index == 88 and self.pending is None and self.pending_restore is None and
                    message["eligible_ids"] == message["active_ids"] == list(self.eligible) and
                    all(self.receipts[i].get("gate", {}).get("active") is True for i in self.eligible) and
                    type(message["preflight_digest"]) is str and re.fullmatch(r"[0-9a-f]{64}", message["preflight_digest"]), "SEAL")
                self.phase, self.index = "measured", 0
                return dict(op="SEALED", preflight_digest=message["preflight_digest"])
            require(op == "FINISH" and set(message) == {"op"} and self.phase == "measured" and self.index == 88 and
                    self.pending is None and self.pending_restore is None and self.commands == self.expected_commands, "STATE")
            self.phase = "finished"
            return dict(op="FINISHED", commands=self.commands)
        except Exception:
            self.phase, self.pending, self.pending_restore = "failed", None, None
            raise WorkerProtocolError("PROTOCOL") from None

    def _prepare(self, message):
        from dataclasses import asdict
        require(set(message) == {"op", "phase", "row", "source_input"} and self.pending is None and self.pending_restore is None and
                self.index < 88 and message["phase"] == self.phase and message["row"] == self.rows[self.index], "STATE")
        row, data = message["row"], message["source_input"]
        require(type(data) is dict and set(data) == {"source", "scope_id", "glossary"} and
                digest(data) == self.source_bindings[row], "BINDING")
        plan = self.p.prepare(data["source"], data["scope_id"], data["glossary"], self.declarations)
        require(plan.eligible == (row in self.eligible), "BINDING")
        binding = digest(asdict(plan))
        if self.phase == "measured": require(self.receipts[row]["plan"] == binding, "DRIFT")
        else: self.receipts[row] = dict(plan=binding)
        if plan.eligible: self.pending = (row, plan)
        else: self.index += 1
        require(len(canonical(self.receipts)) <= RECEIPT_CAP, "RECEIPTS")
        return dict(op="PREPARED", phase=self.phase, row=row, plan=asdict(plan), plan_sha256=binding)

    def _gate(self, message):
        require(set(message) == {"op", "phase", "row", "plan_sha256", "baseline_tokens", "provisional_tokens"} and
                self.pending is not None and message["phase"] == self.phase and message["row"] == self.pending[0] and
                message["plan_sha256"] == self.receipts[message["row"]]["plan"], "BINDING")
        row, plan = self.pending
        decision = self.p.apply_token_gate(plan, message["baseline_tokens"], message["provisional_tokens"])
        response = dict(active=decision.active, reason=decision.reason, prompt_sha256=digest(decision.prompt),
                        baseline_tokens=decision.baseline_tokens, provisional_tokens=decision.provisional_tokens)
        if self.phase == "measured":
            require(self.receipts[row]["gate"] == response, "DRIFT")
            if decision.active: self.pending_restore = (row, decision)
        else: self.receipts[row]["gate"] = response
        require(len(canonical(self.receipts)) <= RECEIPT_CAP, "RECEIPTS")
        self.pending = None
        self.index += 1
        return dict(op="GATED", phase=self.phase, row=row, **response)

    def _restore(self, message):
        require(set(message) == {"op", "row", "original_output", "original_output_sha256", "input_frame_bound_rejection"} and
                self.phase == "measured" and self.pending_restore is not None and message["row"] == self.pending_restore[0] and
                type(message["input_frame_bound_rejection"]) is bool and type(message["original_output_sha256"]) is str and
                re.fullmatch(r"[0-9a-f]{64}", message["original_output_sha256"]), "RESTORE")
        if message["input_frame_bound_rejection"]:
            require(message["original_output"] is None, "RESTORE")
            final, rejection = None, "INPUT_FRAME_BOUND"
        else:
            require(type(message["original_output"]) is str and
                    sha256(message["original_output"].encode()).hexdigest() == message["original_output_sha256"], "BINDING")
            try:
                final = self.p.restore(self.pending_restore[1], message["original_output"], self.integrity)
                rejection = None
            except (self.p.StructuralFailure, self.expected_error):
                final, rejection = None, "MARKER_OR_STRUCTURE_REJECTED"
        response = dict(op="RESTORED", row=message["row"], original_output_sha256=message["original_output_sha256"], final_output=final,
            final_output_sha256=sha256(final.encode()).hexdigest() if final is not None else None, rejection=rejection)
        if len(canonical(response)) > FRAME_CAP:
            response.update(final_output=None, final_output_sha256=None, rejection="OUTPUT_FRAME_BOUND")
        self.pending_restore = None
        return response


class WorkerClient:
    def __init__(self, bridge, policy, eligible_ids):
        self.bridge, self.p, self.eligible_ids = bridge, policy, tuple(eligible_ids)
        self.expected_commands, self.started = 178 + 3 * len(self.eligible_ids), False

    def start(self):
        require(self.bridge.start() == dict(op="READY", policy_sha256=POLICY_SHA256, bank_sha256=BANK_SHA256,
            guard_excerpt_sha256=GUARD_SHA256, expected_commands=self.expected_commands), "BINDING")
        self.started = True

    def prepare(self, phase, row_id, row):
        data = {k: row[k] for k in ("source", "scope_id", "glossary")}
        def validate(response):
            require(type(response) is dict and set(response) == {"op", "phase", "row", "plan", "plan_sha256"} and
                (response["op"], response["phase"], response["row"]) == ("PREPARED", phase, row_id) and
                digest(response["plan"]) == response["plan_sha256"], "BINDING")
            plan = self.p.Plan(**response["plan"])
            require(plan.source == row["source"] and plan.scope_id == row["scope_id"] and type(plan.eligible) is bool and
                    plan.eligible == (row_id in self.eligible_ids), "BINDING")
            return plan
        return self.bridge.request(dict(op="PREPARE", phase=phase, row=row_id, source_input=data), validate)

    def gate(self, phase, row, plan, a, b):
        from dataclasses import asdict
        def validate(response):
            require(type(response) is dict and set(response) == {"op", "phase", "row", "active", "reason", "prompt_sha256", "baseline_tokens", "provisional_tokens"} and
                (response["op"], response["phase"], response["row"]) == ("GATED", phase, row) and
                all(type(v) is int and v > 0 for v in (a,b)) and a <= 384 and
                (response["baseline_tokens"],response["provisional_tokens"]) == (a,b) and type(response["active"]) is bool, "BINDING")
            active = b <= 384 and b-a <= min(16,(2*a)//5)
            prompt = plan.provisional_prompt if active else plan.baseline_prompt
            require(plan.eligible and response["active"] is active and response["reason"] == ("active" if active else "token_budget") and
                    response["prompt_sha256"] == digest(prompt), "BINDING")
            return self.p.Decision(plan,active,response["reason"],prompt,a,b)
        return self.bridge.request(dict(op="GATE",phase=phase,row=row,plan_sha256=digest(asdict(plan)),baseline_tokens=a,provisional_tokens=b),validate)

    def seal(self, preflight_digest, active_ids):
        require(tuple(active_ids) == self.eligible_ids, "BINDING")
        def validate(response):
            require(response == dict(op="SEALED",preflight_digest=preflight_digest),"BINDING")
            return response
        return self.bridge.request(dict(op="SEAL",preflight_digest=preflight_digest,eligible_ids=list(self.eligible_ids),active_ids=list(active_ids)),validate)

    def restore(self, row, original_output):
        original_sha = sha256(original_output.encode()).hexdigest()
        request = dict(op="RESTORE",row=row,original_output=original_output,original_output_sha256=original_sha,input_frame_bound_rejection=False)
        if len(canonical(request)) > FRAME_CAP: request.update(original_output=None,input_frame_bound_rejection=True)
        def validate(response):
            require(type(response) is dict and set(response) == {"op","row","original_output_sha256","final_output","final_output_sha256","rejection"} and
                (response["op"],response["row"],response["original_output_sha256"]) == ("RESTORED",row,original_sha) and
                response["rejection"] in (None,"INPUT_FRAME_BOUND","OUTPUT_FRAME_BOUND","MARKER_OR_STRUCTURE_REJECTED"),"BINDING")
            if response["rejection"] is None:
                require(type(response["final_output"]) is str and sha256(response["final_output"].encode()).hexdigest() == response["final_output_sha256"],"BINDING")
            else: require(response["final_output"] is None and response["final_output_sha256"] is None,"RESTORE")
            return response
        return self.bridge.request(request,validate)

    def finish(self):
        def validate(response):
            require(response == dict(op="FINISHED",commands=self.expected_commands),"BINDING")
            return response
        self.bridge.request(dict(op="FINISH"),validate)
        self.bridge.close()

    def abort(self): return self.bridge.abort()
    def metrics(self): return self.bridge.metrics()
    def timing_metrics(self): return self.bridge.timing_metrics()
    @property
    def owner_identity(self): return self.bridge.owner_identity


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE_ONLY_NATIVE_DISABLED")

