"""Hash-bound native inventory; parent never imports/runs the actual matcher."""
import cpu_harness as h
from usage_runner_core import UsageCore
from verified_inputs import RAW_PINS, load_runtime_inventory


class BaselineOnlyPolicy:
    FROZEN_BANK_SHA256 = "9ef164ee324785815158ff04025ee3fb14fbf01a461257834060cbd96d257b8a"
    BASELINE_TEMPLATE = "将以下文本翻译为简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{}"

    class PolicyError(ValueError):
        pass

    @classmethod
    def baseline_messages(cls, raw_source):
        h.require(type(raw_source) is str, "plain source string")
        return [{"role": "user", "content": cls.BASELINE_TEMPLATE.format(raw_source)}]

    @staticmethod
    def prepare_candidate(*args, **kwargs):
        raise h.Disabled("Actual selection/rendering is owned by the usage worker")

    @staticmethod
    def apply_token_gate(*args, **kwargs):
        raise h.Disabled("Eligible token gating is owned by the usage worker")


def load(runtime):
    """Use existing admitted capped source reads, with exact public raw pins."""
    runtime.require_activation()
    raw = {name: runtime.pinned_file(runtime.HERE / "inputs" / name, pin, 65536)
           for name, pin in RAW_PINS.items()}
    bank = runtime.pinned_file(runtime.HERE / "policy/runtime_bank.frozen.json", BaselineOnlyPolicy.FROZEN_BANK_SHA256, 16384)
    core = UsageCore(h, BaselineOnlyPolicy)
    inventory = load_runtime_inventory(core, raw, bank)
    h.require(tuple(inventory.sources) == h.ROW_IDS and inventory.schedule == h.SCHEDULE and
              set(inventory.eligible_ids) == set(h.ELIGIBLE_IDS) and inventory.request_total == 398,
              "claim/runtime inventory cross-binding")
    return core, inventory, bank
