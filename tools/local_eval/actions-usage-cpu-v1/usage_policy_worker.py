"""Pure bounded worker state machine and framing; no native child or I/O.

The future bootstrap must verify exact policy/guard/bank bytes before injecting
them. No network, tokenizer, model, application, process, or filesystem imports.
"""
from hashlib import sha256
import json
import re

FRAME_CAP = 32768
RECEIPT_CAP = 65536
POLICY_SHA256 = "f94a9af78a2c1694f432c4a12850fd0e27e0c6d067180810e1dc87064d650df9"
BANK_SHA256 = "9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a"
GUARD_SHA256 = "7469668c5f4ae87c59508457844a9b68ae965f2f41254e1a10c9f2b1f8c99987"


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
    def __init__(self, policy, bank_bytes, row_ids, expected_eligible_ids, source_hashes):
        require(type(bank_bytes) is bytes and sha256(bank_bytes).hexdigest() == BANK_SHA256, "BINDING")
        require(len(row_ids) == 87 and len(set(row_ids)) == 87 and
                tuple(row for row in row_ids if row in expected_eligible_ids) == tuple(expected_eligible_ids) and
                len(expected_eligible_ids) <= 46 and set(source_hashes) == set(row_ids), "BINDING")
        policy.load_frozen_bank(bank_bytes)
        self.policy, self.bank = policy, bank_bytes
        self.rows, self.eligible = tuple(row_ids), tuple(expected_eligible_ids)
        self.source_hashes = dict(source_hashes)
        self.phase, self.index, self.pending = "preflight", 0, None
        self.receipts, self.commands = {}, 0
        self.expected_commands = 176 + 2*len(self.eligible)
        self.ready_sent = False

    def ready(self):
        require(not self.ready_sent and self.commands == 0, "STATE")
        self.ready_sent = True
        return dict(op="READY", policy_sha256=POLICY_SHA256, bank_sha256=BANK_SHA256,
                    guard_excerpt_sha256=GUARD_SHA256, expected_commands=self.expected_commands)

    def exchange_frame(self, frame):
        try:
            return encode_frame(self.handle(decode_frame(frame)))
        except Exception:
            self.phase, self.pending = "failed", None
            raise WorkerProtocolError("PROTOCOL") from None

    def handle(self, message):
        try:
            require(self.ready_sent and self.phase in ("preflight", "measured") and
                    self.commands < self.expected_commands and type(message) is dict, "STATE")
            self.commands += 1
            op = message.get("op")
            if op == "PREPARE":
                return self._prepare(message)
            if op == "GATE":
                return self._gate(message)
            if op == "SEAL":
                require(set(message) == {"op", "preflight_digest", "eligible_ids"} and
                        self.phase == "preflight" and self.index == 87 and self.pending is None and
                        message["eligible_ids"] == list(self.eligible) and
                        type(message["preflight_digest"]) is str and
                        re.fullmatch(r"[0-9a-f]{64}", message["preflight_digest"]) is not None, "SEAL")
                self.phase, self.index = "measured", 0
                return dict(op="SEALED", preflight_digest=message["preflight_digest"])
            require(op == "FINISH" and set(message) == {"op"} and self.phase == "measured" and
                    self.index == 87 and self.pending is None and self.commands == self.expected_commands, "STATE")
            self.phase = "finished"
            return dict(op="FINISHED", commands=self.commands)
        except Exception:
            self.phase, self.pending = "failed", None
            raise WorkerProtocolError("PROTOCOL") from None

    def _prepare(self, message):
        require(set(message) == {"op", "phase", "row", "source", "baseline_sha256"} and
                self.pending is None and self.index < 87 and message["phase"] == self.phase and
                message["row"] == self.rows[self.index] and type(message["source"]) is str and
                0 < len(message["source"]) <= 4096, "PREPARE")
        row, source = message["row"], message["source"]
        require(sha256(source.encode("utf-8")).hexdigest() == self.source_hashes[row], "BINDING")
        baseline = self.policy.baseline_messages(source)
        require(message["baseline_sha256"] == digest(baseline), "BINDING")
        plan = self.policy.prepare_candidate(source, baseline, self.bank, baseline_in_scope=True)
        require(plan.surface_eligible == (row in self.eligible), "BINDING")
        current = dict(baseline_sha256=digest(baseline), candidate_sha256=digest(plan.messages),
                       eligible=plan.surface_eligible, selection_reason=plan.reason, record_id=plan.record_id)
        if self.phase == "measured":
            require(all(self.receipts[row][key] == value for key, value in current.items()), "DRIFT")
        else:
            self.receipts[row] = current
            require(len(canonical(self.receipts)) <= RECEIPT_CAP, "RECEIPTS")
        if plan.surface_eligible:
            self.pending = (row, plan)
        else:
            self.index += 1
        return dict(op="PREPARED", phase=self.phase, row=row, **current,
                    candidate_messages=plan.messages if plan.surface_eligible else None)

    def _gate(self, message):
        keys = {"op", "phase", "row", "baseline_tokens", "candidate_tokens", "baseline_sha256", "candidate_sha256"}
        require(set(message) == keys and self.pending is not None and message["phase"] == self.phase and
                message["row"] == self.pending[0], "GATE")
        row, plan = self.pending
        receipt = self.receipts[row]
        require(message["baseline_sha256"] == receipt["baseline_sha256"] and
                message["candidate_sha256"] == receipt["candidate_sha256"], "BINDING")
        b, c = message["baseline_tokens"], message["candidate_tokens"]
        decision = self.policy.apply_token_gate(plan, baseline_tokens=b, candidate_tokens=c)
        gated = dict(baseline_tokens=b, candidate_tokens=c, active=decision.example_active,
                     decision_reason=decision.reason, actual_sha256=digest(decision.messages))
        if self.phase == "measured":
            require(all(receipt[key] == value for key, value in gated.items()), "DRIFT")
        else:
            receipt.update(gated)
            require(len(canonical(self.receipts)) <= RECEIPT_CAP, "RECEIPTS")
        self.pending = None
        self.index += 1
        return dict(op="GATED", phase=self.phase, row=row, **gated)


def run_real(*args, **kwargs):
    raise RuntimeError("SOURCE ONLY: worker bootstrap, pipes, monitors and reaping are not released")
