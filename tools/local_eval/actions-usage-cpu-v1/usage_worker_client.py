"""Strict parent-side client; policy execution stays in its owned worker."""
from types import SimpleNamespace
from usage_policy_worker import POLICY_SHA256, BANK_SHA256, GUARD_SHA256, digest, require


class WorkerClient:
    def __init__(self, bridge, eligible_ids):
        self.bridge, self.eligible_ids = bridge, tuple(eligible_ids)
        self.expected_commands = 176 + 2*len(self.eligible_ids)
        self.started = False

    def start(self):
        ready = self.bridge.start()
        require(ready == dict(op="READY", policy_sha256=POLICY_SHA256, bank_sha256=BANK_SHA256,
                             guard_excerpt_sha256=GUARD_SHA256, expected_commands=self.expected_commands), "BINDING")
        self.started = True

    def prepare(self, phase, row, source, baseline):
        request = dict(op="PREPARE", phase=phase, row=row, source=source, baseline_sha256=digest(baseline))
        def validate(response):
            keys = {"op", "phase", "row", "baseline_sha256", "candidate_sha256", "eligible",
                    "selection_reason", "record_id", "candidate_messages"}
            require(type(response) is dict and set(response) == keys and
                    (response["op"], response["phase"], response["row"]) == ("PREPARED", phase, row) and
                    response["baseline_sha256"] == digest(baseline) and
                    type(response["eligible"]) is bool and response["eligible"] == (row in self.eligible_ids), "BINDING")
            candidate = response["candidate_messages"]
            if response["eligible"]:
                require(type(candidate) is list and len(candidate) == 1 and type(candidate[0]) is dict and
                        set(candidate[0]) == {"role", "content"} and candidate[0]["role"] == "user" and
                        type(candidate[0]["content"]) is str and candidate[0]["content"].endswith(baseline[0]["content"]), "BINDING")
            else:
                require(candidate is None, "BINDING")
                candidate = baseline  # Original object, never a deserialized fallback.
            require(digest(candidate) == response["candidate_sha256"], "BINDING")
            return SimpleNamespace(baseline=baseline, messages=candidate, raw_source=source,
                                   surface_eligible=response["eligible"], reason=response["selection_reason"],
                                   record_id=response["record_id"], baseline_sha256=response["baseline_sha256"],
                                   candidate_sha256=response["candidate_sha256"])
        return self.bridge.request(request, validate)

    def gate(self, phase, row, prepared, b, c):
        request = dict(op="GATE", phase=phase, row=row, baseline_tokens=b, candidate_tokens=c,
                       baseline_sha256=prepared.baseline_sha256, candidate_sha256=prepared.candidate_sha256)
        def validate(response):
            keys = {"op", "phase", "row", "baseline_tokens", "candidate_tokens", "active", "decision_reason", "actual_sha256"}
            require(type(response) is dict and set(response) == keys and
                    (response["op"], response["phase"], response["row"]) == ("GATED", phase, row) and
                    (response["baseline_tokens"], response["candidate_tokens"]) == (b, c) and
                    type(response["active"]) is bool, "BINDING")
            actual = prepared.messages if response["active"] else prepared.baseline
            require(response["actual_sha256"] == digest(actual), "BINDING")
            return SimpleNamespace(messages=actual, raw_source=prepared.raw_source, example_active=response["active"],
                                   reason=response["decision_reason"], record_id=prepared.record_id)
        return self.bridge.request(request, validate)

    def seal(self, preflight_digest):
        def validate(response):
            require(response == dict(op="SEALED", preflight_digest=preflight_digest), "BINDING")
            return response
        return self.bridge.request(dict(op="SEAL", preflight_digest=preflight_digest, eligible_ids=list(self.eligible_ids)), validate)

    def finish(self):
        def validate(response):
            require(response == dict(op="FINISHED", commands=self.expected_commands), "BINDING")
            return response
        self.bridge.request(dict(op="FINISH"), validate)
        self.bridge.close()

    def abort(self):
        return self.bridge.abort()

    @property
    def owner_identity(self):
        return self.bridge.owner_identity

    def metrics(self):
        return self.bridge.metrics()

    def timing_metrics(self):
        return self.bridge.timing_metrics()
