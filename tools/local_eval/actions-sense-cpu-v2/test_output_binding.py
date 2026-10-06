"""Actions output-policy revision: pure/fake checks only."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import cpu_harness as h
import guarded_runtime as runtime
from test_cpu_harness import Clock
from test_guarded_adapters import doubles,forbidden
from test_actions_wrapper import roots,binding,metadata,owner_identity
import actions_entry as entry


def claim_plan():
    plan=entry.assemble_plan(roots(),binding(),metadata(),'1'*64,'/fake/python',coordinator_identity=owner_identity())
    plan['redirect_policy']=[]
    return plan


class OutputBindingTests(unittest.TestCase):
    def test_complete_revision_bound_without_release(self):
        self.assertEqual(h.validate_claim_plan(claim_plan()),dict(valid_conditional_plan=True,execution_released=False))
        self.assertEqual(h.digest((Path(__file__).parent/'ACTIONS_EXECUTION_AMENDMENT.md').read_bytes()),h.OUTPUT_REVISION_SHA256)
        self.assertLessEqual(len(h.canonical(claim_plan())),32768)
    def test_missing_extra_file_or_changed_schema_rejected(self):
        for kind in ('file','policy','digest','revision'):
            plan=claim_plan()
            if kind=='file':plan['output_files'].remove('public/accounting.json')
            elif kind=='policy':plan['output_policy']['total_retained_bytes']+=1
            elif kind=='digest':plan['commitments']['output_schemas']='0'*64
            else:plan['commitments']['output_binding_revision']='0'*64
            with self.subTest(kind=kind),self.assertRaises(h.TerminalFailure):h.validate_claim_plan(plan)
    def test_public_and_evidence_cannot_escape(self):
        for key in ('public','evidence'):
            plan=claim_plan();plan['paths'][key]='/tmp/alternate'
            with self.assertRaises(h.TerminalFailure):h.validate_claim_plan(plan)
    def test_initial_claim_charge_no_arm_key(self):
        writer=runtime.EvidenceFiles('/fake',initial_claim_size=1000)
        self.assertEqual(writer.budget.retained,1000)
        with self.assertRaises(h.TerminalFailure):runtime.EvidenceFiles('/fake',initial_claim_size=0)
        with self.assertRaises(h.TerminalFailure):runtime.EvidenceFiles('/fake',initial_claim_size=1000,initial_arm_key_size=1)
    def test_unknown_filename_rejected_before_native_create(self):
        with doubles(Clock()):
            writer=runtime.EvidenceFiles('/fake',initial_claim_size=1000)
            with self.assertRaises(h.TerminalFailure):writer.create('unclaimed.json')
    def test_per_file_and_global_budget_stop_before_write(self):
        with doubles(Clock()):
            writer=runtime.EvidenceFiles('/fake',initial_claim_size=1000)
            writer.files={'helper.log':99};writer.file_bytes={'helper.log':65535}
            with patch.object(runtime,'persistent_write',forbidden),self.assertRaises(h.TerminalFailure):writer.append('helper.log',b'xx')
            writer.file_bytes['helper.log']=0;writer.budget.retained=64*h.MIB
            with patch.object(runtime,'persistent_write',forbidden),self.assertRaises(h.TerminalFailure):writer.append('helper.log',b'x')

if __name__=='__main__':unittest.main()
