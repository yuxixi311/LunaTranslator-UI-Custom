"""Inherited independent deadline-controller regressions, current Actions plan."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import cpu_harness as h
import guarded_runtime as runtime
import final_coordinator as kit
from attempt_control import AttemptControl
from test_cpu_harness import Clock
from test_guarded_adapters import doubles,forbidden
from test_actions_wrapper import roots,binding,metadata,owner_identity
import actions_entry as entry

def kit_plan():return entry.assemble_plan(roots(),binding(),metadata(),'1'*64,'/fake/python',coordinator_identity=owner_identity())

class IndependentControllerTests(unittest.TestCase):
    def owner(self):
        return SimpleNamespace(outer_end=1475.,phase_end=1475.,work_end=None,postready_end=None,
                               lifecycle_end=None,failure_at=None)
    def test_permanent_claim_stall_is_unconfirmed_within_outer_ceiling(self):
        clock=Clock();control=AttemptControl(clock);control.bind_owner(self.owner())
        clock.advance(1455);self.assertIsNone(control.poll());self.assertTrue(control.cancel.is_set())
        clock.advance(20);result=control.poll()
        self.assertEqual(result['status'],'incomplete');self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(control.cleanup_deadline(),1475)
    def test_finalizer_deadline_survives_owner_watchdog_shutdown(self):
        clock=Clock();control=AttemptControl(clock);owner=self.owner();control.bind_owner(owner)
        clock.advance(100);control.begin_cleanup();clock.advance(20)
        result=control.poll();self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(control.cleanup_deadline(),120)
    def test_late_success_is_never_accepted(self):
        clock=Clock();control=AttemptControl(clock);owner=self.owner();owner.phase_end=5;control.bind_owner(owner)
        clock.advance(5);control.poll();control.result=dict(status='operationally_complete',cleanup_confirmed=True)
        control.done.set();result=control.poll()
        self.assertEqual(result['status'],'incomplete')
        with self.assertRaises(h.TerminalFailure):control.checkpoint()
    def test_work_checkpoint_prevents_late_write_followups(self):
        clock=Clock();control=AttemptControl(clock);owner=self.owner();owner.phase_end=5;control.bind_owner(owner)
        written=[]
        def delayed_write(fd,data):
            written.append(bytes(data));clock.advance(5);control.poll();return len(data)
        with doubles(clock),patch.object(runtime,'PERSISTENCE_CHECKPOINT',control.checkpoint),\
             patch.object(runtime.os,'write',delayed_write),patch.object(runtime.os,'fsync',forbidden),\
             self.assertRaises(h.TerminalFailure):runtime.persistent_write(99,b'partial')
        self.assertEqual(written,[b'partial'])
    def test_owner_failure_during_write_blocks_normal_work_immediately(self):
        clock=Clock();control=AttemptControl(clock);owner=self.owner();control.bind_owner(owner)
        def failing_write(fd,data):
            owner.failure='synthetic resource failure';owner.failure_at=clock();return len(data)
        with doubles(clock),patch.object(runtime,'PERSISTENCE_CHECKPOINT',control.checkpoint),\
             patch.object(runtime.os,'write',failing_write),patch.object(runtime.os,'fsync',forbidden),\
             self.assertRaises(h.TerminalFailure):runtime.persistent_write(99,b'partial')
        control.poll();self.assertTrue(control.cancel.is_set())
        control.begin_cleanup();control.checkpoint()
        self.assertEqual(control.cleanup_deadline(),20)
    def test_claim_stall_cannot_create_later_journal(self):
        clock=Clock();control=AttemptControl(clock);control.bind_owner(self.owner());opened=[]
        def opening(path,*args,**kwargs):opened.append(str(path));return len(opened)+10
        def delayed_write(fd,data):clock.advance(1455);control.poll();return len(data)
        with doubles(clock),patch.object(runtime,'PERSISTENCE_CHECKPOINT',control.checkpoint),\
             patch.object(runtime.os,'open',opening),patch.object(runtime.os,'write',delayed_write),\
             patch.object(runtime.os,'close',lambda _:None),patch.object(runtime.os,'fsync',forbidden),\
             self.assertRaises(h.TerminalFailure):kit.claim_once(kit_plan(),'1'*64)
        self.assertFalse(any('EVENTS' in name for name in opened))
    def test_worker_join_is_only_nonblocking(self):
        clock=Clock();control=AttemptControl(clock);joins=[]
        class Worker:
            def join(self,timeout):joins.append(timeout)
            def is_alive(self):return True
        control.worker=Worker();control.done.set()
        self.assertIsNone(control.poll());self.assertEqual(joins,[0])
    def test_cleanup_cannot_restart_twenty_second_clock(self):
        clock=Clock();control=AttemptControl(clock);clock.advance(60);control.poll()
        clock.advance(19);control.begin_cleanup()
        self.assertEqual(control.cleanup_deadline(),80)
        clock.advance(1);self.assertFalse(control.poll()['cleanup_confirmed'])


if __name__=='__main__':unittest.main()
