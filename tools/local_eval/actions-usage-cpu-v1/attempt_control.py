"""Independent source-only controller for the one owned coordinator thread.

It cannot interrupt a blocked syscall. It stops accepting late results and
reports unresolved work explicitly, while cancellation forbids later mutations.
The controller never joins the worker with a positive timeout or takes its locks.
"""
import threading
import time
import cpu_harness as h
import guarded_runtime as runtime


class AttemptControl:
    def __init__(self,now=None,diagnostic=None):
        self.now=now or time.monotonic;self.preclaim_end=self.now()+60
        self.diagnostic=diagnostic
        self.owner=None;self.worker=None;self.result=None;self.error=None
        self.done=threading.Event();self.cancel=threading.Event()
        self.cancelled_at=None;self.cause=None;self.cleanup_started=None;self.worker_finalizing=False

    def bind_owner(self,owner):
        self.owner=owner

    def work_deadline(self):
        owner=self.owner
        if owner is None:return self.preclaim_end
        limits=[owner.outer_end-20,owner.phase_end]
        if owner.work_end is not None:limits.append(owner.work_end)
        if owner.postready_end is not None:limits.append(owner.postready_end)
        if owner.lifecycle_end is not None:limits.append(owner.lifecycle_end-20)
        return min(limits)

    def cleanup_deadline(self):
        times=[t for t in (self.cleanup_started,self.cancelled_at,
               self.owner.failure_at if self.owner is not None else None) if t is not None]
        start=min(times) if times else self.now()
        limits=[start+20]
        if self.owner is not None:
            limits.append(self.owner.outer_end)
            if self.owner.lifecycle_end is not None:limits.append(self.owner.lifecycle_end)
        return min(limits)

    def begin_cleanup(self):
        if self.cleanup_started is None:self.cleanup_started=self.now()
        self.worker_finalizing=True

    def checkpoint(self):
        if self.worker_finalizing:
            h.require(self.now()<self.cleanup_deadline(),'cleanup/final-write deadline')
        else:
            owner_failed=self.owner is not None and (getattr(self.owner,'failure',None) is not None or
                                                     self.owner.failure_at is not None)
            h.require(not owner_failed and not self.cancel.is_set() and self.now()<self.work_deadline(),
                      'work cancelled/owner failure/deadline')

    def expired(self,cause,at=None):
        if not self.cancel.is_set():
            if self.diagnostic:self.diagnostic.fail(code='DEADLINE_EXPIRED' if cause in ('absolute phase/outer deadline','cleanup/finalization deadline') else 'OWNER_FAILURE')
            self.cause=cause;self.cancelled_at=self.now() if at is None else at;self.cancel.set()
        # Existing independent owner monitors see this Event and stop handles.
        # The controller itself never waits on their locks, I/O or process waits.

    def poll(self):
        if self.owner is not None and (getattr(self.owner,'failure',None) is not None or self.owner.failure_at is not None):
            self.expired('owned supervisor failure',self.owner.failure_at)
        finalizing=self.cleanup_started is not None or self.cancel.is_set() or (
            self.owner is not None and self.owner.failure_at is not None)
        deadline=self.cleanup_deadline() if finalizing else self.work_deadline()
        if self.now()>=deadline:
            if not finalizing:
                self.expired('absolute phase/outer deadline',deadline)
                if self.now()<self.cleanup_deadline():return None
            self.expired('cleanup/finalization deadline',deadline)
            return dict(status='incomplete',cleanup_confirmed=False,protocol_complete=False,
                failure=self.cause,unresolved=['owned coordinator thread or blocking OS outcome unconfirmed'])
        if self.done.is_set():
            if self.worker is not None:
                try:
                    self.worker.join(timeout=0)
                    if self.worker.is_alive():return None
                except BaseException:
                    self.expired('worker join state unconfirmed')
            if self.cancel.is_set() or self.error is not None:
                # This explains aggregate false without claiming a resource leak.
                # Keep the existing cancellation/result acceptance policy intact.
                if self.diagnostic:self.diagnostic.cleanup_issue('CONTROLLER_RESULT_REJECTED')
                return dict(status='incomplete',cleanup_confirmed=False,protocol_complete=False,
                    failure=self.cause or type(self.error).__name__,unresolved=['cancelled/failed coordinator result'])
            if type(self.result) is not dict:
                return dict(status='incomplete',cleanup_confirmed=False,protocol_complete=False,
                            failure='coordinator result missing',unresolved=['result unconfirmed'])
            return self.result
        return None

    def run(self,work):
        runtime.require_activation()
        def target():
            try:self.result=work(self)
            except BaseException as exc:
                if self.diagnostic:self.diagnostic.fail(exc)
                self.error=exc
            finally:self.done.set()
        # Registered before start; it is the only additional owned Python thread.
        runtime.COORDINATOR_CANCEL_EVENT=self.cancel
        runtime.PERSISTENCE_CHECKPOINT=self.checkpoint
        try:
            if self.diagnostic:self.diagnostic.enter('COORDINATOR_START')
            self.worker=threading.Thread(target=target,name='owned-attempt-coordinator',daemon=True)
            self.worker.start()
        except BaseException:
            self.expired('coordinator thread start outcome unknown')
            result=dict(status='incomplete',cleanup_confirmed=False,protocol_complete=False,
                        failure=self.cause,unresolved=['coordinator thread start unconfirmed'])
            if self.diagnostic:result['diagnostic']=self.diagnostic.snapshot()
            return result
        while True:
            result=self.poll()
            if result is not None:
                if self.diagnostic:result['diagnostic']=self.diagnostic.snapshot()
                return result
            # Fixed short waits; controller stays effective after owner.finalize().
            self.done.wait(.01)
