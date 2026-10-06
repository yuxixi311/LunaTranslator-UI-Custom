"""Finite diagnostic projection; never serialize exception text or arbitrary data."""
import json
import re

ROLES=('acquire','validate','version','server','helper')
STAGES=('UNKNOWN','COORDINATOR_START','PLAN_CHECK','PRECLAIM_HOST','OUTPUT_PREPARATION','OWNER_ARM','CLAIM_CREATE','CLAIM_WRITE',
 'CLAIM_SYNC','CLAIM_FILE_CLOSE','CLAIM_DIRECTORY_CLOSE','JOURNAL_CLOSE','JOURNAL_CREATE','JOURNAL_SYNC','EVIDENCE_INIT','acquire','validate','version','startup','preflight',
 'helper','generation','RECONCILE','CLEANUP','PUBLIC_EXPORT','MANIFEST','RESOURCE_MONITOR','DEADLINE_MONITOR',
 'WORKER_ADMISSION','WORKER_JOURNAL','ASSET_OPEN','ASSET_DNS','ASSET_CONNECT','ASSET_TLS','ASSET_SEND',
 'ASSET_HEADERS','ASSET_BODY','ASSET_SYNC','ASSET_CLOSE','ASSET_COMPLETE','EXTRACTION','RUNTIME_VALIDATE')
CODES=('UNKNOWN_FAILURE','OS_ERROR','OS_ACCESS_DENIED','OS_NOT_FOUND','OS_STORAGE_FULL','OS_BAD_DESCRIPTOR',
 'WORKER_PARENT_PID','WORKER_PARENT_ARGV','WORKER_EXECUTABLE_CWD','WORKER_SOURCE_BINDING','WORKER_CLAIM_BINDING','VALUE_ERROR','TYPE_ERROR','ASSERTION_ERROR','ADMISSION_REJECTED',
 'DEADLINE_EXPIRED','OWNER_FAILURE','CHILD_EXIT_FAILURE','CHILD_SETUP_FAILURE','RESOURCE_GUARD_FAILED',
 'ASSET_ADDRESS_REJECTED','ASSET_HTTP_STATUS_REJECTED','ASSET_FRAMING_REJECTED','ASSET_DIGEST_REJECTED',
 'ASSET_LENGTH_REJECTED','EVIDENCE_LIMIT','EVIDENCE_FINALIZE_FAILED','PUBLIC_EXPORT_FAILED','MANIFEST_FAILED')
CLEANUP=('CHILD_EXIT_UNCONFIRMED','PENDING_LAUNCH','PIPE_CLOSE_FAILED','SOCKET_CLOSE_FAILED','THREAD_JOIN_UNCONFIRMED',
 'CLAIM_FILE_CLOSE_FAILED','CLAIM_DIRECTORY_CLOSE_FAILED','ASSET_CLOSE_FAILED','JOURNAL_CLOSE_FAILED','EVIDENCE_FINALIZE_FAILED','EVIDENCE_CLOSE_FAILED','DEADLINE_EXPIRED','PUBLIC_EXPORT_FAILED','MANIFEST_FAILED')
EXACT_MESSAGES={
 'nonpublic/unknown asset address':'ASSET_ADDRESS_REJECTED',
 'asset response must be 200':'ASSET_HTTP_STATUS_REJECTED',
 'worker must be direct child of bound coordinator':'WORKER_PARENT_PID',
 'actual parent argv differs from claim':'WORKER_PARENT_ARGV',
 'worker Python/cwd binding':'WORKER_EXECUTABLE_CWD',
 'worker manifest/source binding':'WORKER_SOURCE_BINDING',
 'owner-only fixed claim':'WORKER_CLAIM_BINDING',
 'worker claim drift after activation':'WORKER_CLAIM_BINDING',
 'asset header syntax/duplicates':'ASSET_FRAMING_REJECTED',
 'asset header fields':'ASSET_FRAMING_REJECTED',
 'asset status line':'ASSET_FRAMING_REJECTED',
 'asset encoding/framing/exact size':'ASSET_FRAMING_REJECTED',
 'asset stream length':'ASSET_LENGTH_REJECTED',
 'asset hash mismatch':'ASSET_DIGEST_REJECTED',
 'phase/global deadline':'DEADLINE_EXPIRED',
 'pending Popen deadline':'DEADLINE_EXPIRED',
 'global evidence cap':'EVIDENCE_LIMIT',
 **{'owned '+role+' failed':'CHILD_EXIT_FAILURE' for role in ROLES}}
ASSET_SIZES=(1133080448,17551895)


def category(exc):
    # Exact, internal comparison only. Neither this string nor repr/args escape.
    found=EXACT_MESSAGES.get(str(exc))
    if found:return found
    name=type(exc).__name__
    if name=='Denied':return 'ADMISSION_REJECTED'
    if isinstance(exc,OSError):return {13:'OS_ACCESS_DENIED',2:'OS_NOT_FOUND',28:'OS_STORAGE_FULL',9:'OS_BAD_DESCRIPTOR'}.get(exc.errno,'OS_ERROR')
    if isinstance(exc,TypeError):return 'TYPE_ERROR'
    if isinstance(exc,ValueError):return 'VALUE_ERROR'
    if isinstance(exc,AssertionError):return 'ASSERTION_ERROR'
    return 'UNKNOWN_FAILURE'


class Trace:
    def __init__(self,manifest_sha=None,attempt_id=None,role='actions'):
        self.manifest_sha=manifest_sha if type(manifest_sha) is str and re.fullmatch('[0-9a-f]{64}',manifest_sha) else None
        self.attempt_id=attempt_id if type(attempt_id) is str and re.fullmatch('[0-9a-f]{32}',attempt_id) else None
        self.role=role if role in (*ROLES,'actions') else 'actions'
        self.stage='UNKNOWN';self.first={};self.claim='NOT_ENTERED';self.journal='NOT_ENTERED'
        self.cleanup=[];self.current_asset=None
        self.assets=[dict(attempts=None,exchange_intents=None,verified=None,received_bytes=None,written_bytes=None) for _ in ASSET_SIZES]
        self.children={role:dict(launch='NOT_ENTERED',adopted=False,exit='UNOBSERVED',exit_code=None,
            timeout=False,cleanup='NOT_ENTERED',worker=None) for role in ROLES}
    def enter(self,stage):self.stage=stage if stage in STAGES else 'UNKNOWN'
    def bind_attempt(self,attempt):
        if type(attempt) is str and re.fullmatch('[0-9a-f]{32}',attempt):self.attempt_id=attempt
    def fail(self,exc=None,*,code=None,stage=None):
        value=code if code in CODES else category(exc) if exc is not None else 'UNKNOWN_FAILURE'
        self.first.setdefault('value',dict(stage=stage if stage in STAGES else self.stage,code=value))
    def cleanup_issue(self,code):
        if code in CLEANUP and code not in self.cleanup:self.cleanup.append(code)
    def child(self,role,**values):
        if role in self.children:self.children[role]={**self.children[role],**values}
    def start_assets(self):
        self.assets=[dict(attempts=0,exchange_intents=0,verified=False,received_bytes=0,written_bytes=0) for _ in ASSET_SIZES]
    def asset_event(self,event):
        index=event.get('asset')
        if type(index) is not int or not 0<=index<2:return
        self.current_asset=index;item=dict(self.assets[index]);kind=event.get('event')
        if kind=='asset_attempt':item['attempts']=1
        elif kind=='asset_exchange_intent':item['exchange_intents']=(item['exchange_intents'] or 0)+1
        elif kind=='asset_verified':item['verified']=True
        self.assets[index]=item
    def received(self,count):self._bytes('received_bytes',count)
    def written(self,count):self._bytes('written_bytes',count)
    def _bytes(self,key,count):
        index=self.current_asset
        if index is None or type(count) is not int or count<0:return
        item=dict(self.assets[index]);item[key]=min((item[key] or 0)+count,ASSET_SIZES[index]+65536);self.assets[index]=item
    def worker_snapshot(self):
        result=dict(schema=1,source_manifest_sha256=self.manifest_sha,role=self.role,stage=self.stage,
            first_failure=self.first.get('value'),assets=[dict(item) for item in self.assets],cleanup_categories=list(self.cleanup))
        validate_worker(result);return result
    def merge_worker(self,value):
        validate_worker(value)
        role=value['role']
        if value['source_manifest_sha256']!=self.manifest_sha or role not in self.children:return False
        self.child(role,worker=dict(stage=value['stage'],first_failure=value['first_failure'],cleanup_categories=value['cleanup_categories']))
        for code in value['cleanup_categories']:self.cleanup_issue(code)
        if role=='acquire':self.assets=[dict(item) for item in value['assets']]
        return True
    def snapshot(self):
        result=dict(schema=1,source_manifest_sha256=self.manifest_sha,attempt_id=self.attempt_id,stage=self.stage,
            first_failure=self.first.get('value'),claim_state=self.claim,journal_state=self.journal,
            assets=[dict(item) for item in self.assets],children={key:dict(value) for key,value in self.children.items()},
            cleanup_categories=list(self.cleanup))
        return validate_public(result)


def encode(value):return json.dumps(value,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def validate_worker(value):
    if type(value) is not dict or set(value)!={'schema','source_manifest_sha256','role','stage','first_failure','assets','cleanup_categories'}:raise ValueError('worker diagnostic schema')
    if value['schema']!=1 or value['role'] not in ('acquire','validate','helper') or value['stage'] not in STAGES:raise ValueError('worker diagnostic identity')
    if type(value['source_manifest_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',value['source_manifest_sha256']):raise ValueError('worker diagnostic manifest')
    failure=value['first_failure']
    if failure is not None and (type(failure) is not dict or set(failure)!={'stage','code'} or failure['stage'] not in STAGES or failure['code'] not in CODES):raise ValueError('worker failure category')
    if type(value['assets']) is not list or len(value['assets'])!=2:raise ValueError('worker asset denominator')
    for index,item in enumerate(value['assets']):
        if type(item) is not dict or set(item)!={'attempts','exchange_intents','verified','received_bytes','written_bytes'}:raise ValueError('worker asset schema')
        for key,maximum in (('attempts',1),('exchange_intents',4),('received_bytes',ASSET_SIZES[index]+65536),('written_bytes',ASSET_SIZES[index]+65536)):
            v=item[key]
            if v is not None and (type(v) is not int or not 0<=v<=maximum):raise ValueError('worker counter bound')
        if item['verified'] is not None and type(item['verified']) is not bool:raise ValueError('worker verified state')
    if type(value['cleanup_categories']) is not list or len(value['cleanup_categories'])!=len(set(value['cleanup_categories'])) or not set(value['cleanup_categories'])<=set(CLEANUP):raise ValueError('worker cleanup categories')
    if len(encode(value))>2048:raise ValueError('worker diagnostic cap')
    return value


def worker_line(trace):return b'LUNA_WORKER_DIAGNOSTIC '+encode(trace.worker_snapshot())+b'\n'


def validate_public(value):
    fields={'schema','source_manifest_sha256','attempt_id','stage','first_failure','claim_state','journal_state','assets','children','cleanup_categories'}
    if type(value) is not dict or set(value)!=fields or value['schema']!=1:raise ValueError('public diagnostic schema')
    for key,length in (('source_manifest_sha256',64),('attempt_id',32)):
        if value[key] is not None and (type(value[key]) is not str or not re.fullmatch('[0-9a-f]{'+str(length)+'}',value[key])):raise ValueError('diagnostic binding')
    if value['stage'] not in STAGES or value['claim_state'] not in ('NOT_ENTERED','CREATE_PENDING','CREATED','DURABLE') or value['journal_state'] not in ('NOT_ENTERED','CREATE_PENDING','OPEN','DURABLE'):raise ValueError('diagnostic phase')
    validate_worker(dict(schema=1,source_manifest_sha256=value['source_manifest_sha256'] or '0'*64,role='acquire',stage=value['stage'],first_failure=value['first_failure'],assets=value['assets'],cleanup_categories=value['cleanup_categories']))
    if type(value['children']) is not dict or set(value['children'])!=set(ROLES):raise ValueError('child denominator')
    for role,item in value['children'].items():
        if type(item) is not dict or set(item)!={'launch','adopted','exit','exit_code','timeout','cleanup','worker'}:raise ValueError('child schema')
        if item['launch'] not in ('NOT_ENTERED','INTENT','PENDING','RETURNED','ERROR_UNCONFIRMED') or type(item['adopted']) is not bool or item['exit'] not in ('UNOBSERVED','RUNNING','EXITED','UNKNOWN') or type(item['timeout']) is not bool or item['cleanup'] not in ('NOT_ENTERED','REQUESTED','CONFIRMED','UNCONFIRMED'):raise ValueError('child finite state')
        if item['exit_code'] is not None and (type(item['exit_code']) is not int or not -255<=item['exit_code']<=255):raise ValueError('child exit bound')
        worker=item['worker']
        if worker is not None:
            if type(worker) is not dict or set(worker)!={'stage','first_failure','cleanup_categories'}:raise ValueError('worker state schema')
            validate_worker(dict(schema=1,source_manifest_sha256='0'*64,role='acquire',assets=value['assets'],**worker))
    if type(value['cleanup_categories']) is not list or len(value['cleanup_categories'])!=len(set(value['cleanup_categories'])) or not set(value['cleanup_categories'])<=set(CLEANUP):raise ValueError('cleanup categories')
    if len(encode(value))>4096:raise ValueError('public diagnostic cap')
    return value
