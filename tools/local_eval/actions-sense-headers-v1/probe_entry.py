"""One owned, bounded GET header observation; source admission precedes effects."""
import base64
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import re
import resource
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from header_logic import ProbeFailure,read_headers,classify_response

REPOSITORY='yuxixi311/LunaTranslator-UI-Custom'
BRANCH='experiment/luna-actions-lexical-20261005'
PROJECT='tools/local_eval/actions-sense-headers-v1'
WORKFLOW='.github/workflows/luna-sense-headers-v1.yml'
SOURCE_PARENT='5e7b952ea2a81873ca67390a7cde42df63527356'
PROTOCOL_SHA='258087a02ea74cb8ab8a1daba55af68f68fd273f0c089c51164b52dc81179db2'
HOST_FIELDS_SHA='185aedecfb16392540015cb26078b2f4e687b719b476d724a1978c274d694f01'
INITIAL_URL='https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/b27182d810fa3ceb6ed04e7c324c54e35c0d209c/Hy-MT2-1.8B-Q4_K_M.gguf'
INITIAL_HOST='huggingface.co'
REQUEST=('GET '+urlsplit(INITIAL_URL).path+' HTTP/1.1\r\nHost: huggingface.co\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n').encode('ascii')
REQUEST_SHA=sha256(REQUEST).hexdigest()
WORKER_RSS=128*1024*1024
AGGREGATE_RSS=256*1024*1024
STATUSES=('UNOBSERVED','HTTP_200','HTTP_301','HTTP_302','HTTP_303','HTTP_307','HTTP_308','OTHER_HTTP_STATUS')
FORMS=('UNOBSERVED','ABSENT','RELATIVE','ABSOLUTE','NETWORK_PATH','INVALID')
AUTHORITIES=('UNOBSERVED','IMPLICIT_SAME_ORIGIN','CANONICAL_HTTPS_443','NONCANONICAL_HTTPS_443','REJECTED_AUTHORITY')
OUTCOMES=('UNOBSERVED','NOT_A_REDIRECT','ACCEPTS_EXISTING_HOST_AND_AUTHORITY','REJECTS_HOST','REJECTS_AUTHORITY_SHAPE','REJECTS_OTHER_EXISTING_URL_RULE')
FAILURES=('NONE','DNS_FAILURE','CONNECT_FAILURE','TLS_FAILURE','SEND_FAILURE','HTTP_LINE_LIMIT','HTTP_HEADER_BLOCK_LIMIT',
    'HTTP_CRLF_REJECTED','HTTP_EOF_OR_INVALID_READ','ASSET_STATUS_LINE_REJECTED','ASSET_HEADER_FIELDS_REJECTED',
    'ASSET_HEADER_SYNTAX_REJECTED','RESOURCE_CAP','DEADLINE_EXPIRED','CLEANUP_UNCONFIRMED','UNKNOWN_FAILURE')
BINDING_KEYS=('protocol_sha256','source_manifest_sha256','source_commit','workflow_commit','run_id','run_attempt','request_sha256')
OBSERVATION_KEYS=('status','location_form','host_class','authority','current_policy_outcome')
FRAME_KEYS={'schema',*BINDING_KEYS,*OBSERVATION_KEYS,'failure','cleanup','initial_exchange_intents','request_send_complete',
    'header_block_complete','application_body_read_calls','redirects_followed','loopback_http_requests'}
_GRANT=None


def require(condition):
    if not condition:raise ProbeFailure('UNKNOWN_FAILURE')


def canonical(value):return json.dumps(value,separators=(',',':'),sort_keys=True,ensure_ascii=True,allow_nan=False).encode('ascii')


def strict_json(raw):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))


def require_role(role):
    require(type(_GRANT) is dict and _GRANT.get('role')==role and _GRANT.get('pid')==os.getpid())
    if role=='worker':require(_GRANT.get('parent_pid')==os.getppid())


def bootstrap_bound(mode,argument):
    require(globals().get('_BOOTSTRAP_MODE')==mode and globals().get('_BOOTSTRAP_PID')==os.getpid()
        and globals().get('_BOOTSTRAP_ARGUMENT')==argument and re.fullmatch('[0-9a-f]{64}',globals().get('_MANIFEST_SHA','')))


def host_classes():
    payloads=globals().get('_PAYLOADS',{})
    require(sha256(payloads['PROTOCOL.json']).hexdigest()==PROTOCOL_SHA and
            sha256(payloads['OFFICIAL_HOST_FIELDS.json']).hexdigest()==HOST_FIELDS_SHA)
    protocol=strict_json(payloads['PROTOCOL.json']);fields=strict_json(payloads['OFFICIAL_HOST_FIELDS.json'])['fields']
    names={name for group in fields.values() for name in group};require(len(names)==21)
    result=protocol['exact_host_observation_classes']
    require(set(result)==names|{'cas-bridge.xethub.hf.co'} and len(set(result.values()))==22)
    require(protocol['initial_request']['url']==INITIAL_URL and protocol['initial_request']['method']=='GET')
    return result


def new_frame(binding):
    return dict(schema=1,**binding,status='UNOBSERVED',location_form='UNOBSERVED',host_class=None,
        authority='UNOBSERVED',current_policy_outcome='UNOBSERVED',failure='NONE',cleanup='UNOBSERVED',
        initial_exchange_intents=0,request_send_complete=False,header_block_complete=False,
        application_body_read_calls=0,redirects_followed=0,loopback_http_requests=0)


def validate_binding(value):
    require(type(value) is dict and set(value)==set(BINDING_KEYS))
    require(value['protocol_sha256']==PROTOCOL_SHA and value['request_sha256']==REQUEST_SHA)
    for key in ('source_manifest_sha256',):require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}',value[key]))
    for key in ('source_commit','workflow_commit'):require(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}',value[key]))
    require(value['source_commit']!=value['workflow_commit'] and type(value['run_id']) is str and re.fullmatch('[1-9][0-9]{0,19}',value['run_id']))
    require(type(value['run_attempt']) is int and value['run_attempt']==1)


def validate_frame(value,binding,classes):
    validate_binding(binding);require(type(value) is dict and set(value)==FRAME_KEYS and type(value['schema']) is int and value['schema']==1)
    require(all(value[key]==binding[key] and type(value[key]) is type(binding[key]) for key in BINDING_KEYS))
    require(value['status'] in STATUSES and value['location_form'] in FORMS and value['authority'] in AUTHORITIES and value['current_policy_outcome'] in OUTCOMES)
    require(value['host_class'] is None or value['host_class'] in (*classes.values(),'NO_LOCATION','UNPARSEABLE','OTHER_UNREVIEWED_HOST'))
    require(value['failure'] in FAILURES and value['cleanup'] in ('UNOBSERVED','CONFIRMED','UNCONFIRMED'))
    for key in ('initial_exchange_intents',):require(value[key] is None or type(value[key]) is int and value[key] in (0,1))
    for key in ('request_send_complete','header_block_complete'):require(value[key] is None or type(value[key]) is bool)
    for key in ('application_body_read_calls','redirects_followed','loopback_http_requests'):require(type(value[key]) is int and value[key]==0)
    if value['header_block_complete'] is True:require(value['request_send_complete'] is True and value['initial_exchange_intents']==1 and value['status']!='UNOBSERVED')
    if value['request_send_complete'] is True:require(value['initial_exchange_intents']==1)
    require(len(canonical(value))+1<=2048)
    return value


def fail(frame,code):
    if frame['failure']=='NONE':frame['failure']=code if code in FAILURES else 'UNKNOWN_FAILURE'


def argv_matches(argv,root,workspace,manifest):
    if len(argv)!=7 or argv[:3]!=['/usr/bin/python3','-I','-B'] or argv[4:]!=['owner',manifest,'unused']:return False
    path=Path(argv[3]);path=path if path.is_absolute() else workspace/path
    return path==root/'bootstrap.py'


def own_argv():
    raw=Path('/proc/self/cmdline').read_bytes();require(0<len(raw)<=8192 and raw.endswith(b'\0'))
    return [part.decode('utf-8','strict') for part in raw[:-1].split(b'\0')]


def admit_owner(env,event,git,root,manifest,payloads,argv):
    """Pure exact-service and immutable-source predicates; fake git in tests."""
    def text(*args):
        raw=git(*args);require(type(raw) is bytes and len(raw)<=131072)
        return raw.decode('utf-8','strict').rstrip('\n')
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1')
    require(env['GITHUB_REPOSITORY']==REPOSITORY and env['GITHUB_REF']=='refs/heads/'+BRANCH)
    require(event['repository']['full_name']==REPOSITORY and all(event[k] is False for k in ('created','deleted','forced')) and event['repository']['private'] is False)
    source=env['LUNA_SOURCE_COMMIT'];after=env['GITHUB_SHA'];require(re.fullmatch('[0-9a-f]{40}',source) and re.fullmatch('[0-9a-f]{40}',after) and source!=after)
    require(event['before']==source and event['after']==event['head_commit']['id']==after and event['ref']==env['GITHUB_REF'])
    require(env['GITHUB_WORKFLOW_SHA']==after and env['GITHUB_WORKFLOW_REF']==REPOSITORY+'/'+WORKFLOW+'@refs/heads/'+BRANCH)
    require((env['RUNNER_ENVIRONMENT'],env['RUNNER_OS'],env['RUNNER_ARCH'],env['ImageOS'],env['GITHUB_JOB'])==('github-hosted','Linux','X64','ubuntu24','headers'))
    workspace=Path(env['GITHUB_WORKSPACE']);require(workspace.is_absolute() and root==workspace/PROJECT)
    require(argv_matches(argv,root,workspace,manifest))
    require(text('rev-parse','HEAD')==after and text('show','-s','--format=%P','HEAD')==source and text('show','-s','--format=%P',source)==SOURCE_PARENT)
    require(text('diff-tree','--no-commit-id','--name-only','-r','HEAD').splitlines()==[WORKFLOW])
    expected={PROJECT+'/'+name for name in payloads}|{PROJECT+'/KIT_MANIFEST.json'}
    require(set(text('ls-tree','-r','--name-only','HEAD','--',PROJECT).splitlines())==expected)
    require(set(text('diff-tree','--no-commit-id','--name-only','-r',source).splitlines())==expected)
    require(text('status','--porcelain','--untracked-files=all')=='')
    template=payloads['WORKFLOW_TEMPLATE.yml.in'].decode().replace('__SOURCE_COMMIT__',source).replace('__MANIFEST_SHA256__',manifest).replace('__BOOTSTRAP_SHA256__',sha256(payloads['bootstrap.py']).hexdigest())
    require(git('show','HEAD:'+WORKFLOW)==template.encode('utf-8'))
    binding=dict(protocol_sha256=PROTOCOL_SHA,source_manifest_sha256=manifest,source_commit=source,
        workflow_commit=after,run_id=env['GITHUB_RUN_ID'],run_attempt=1,request_sha256=REQUEST_SHA)
    validate_binding(binding);return binding


def owner_admission(argument):
    global _GRANT
    bootstrap_bound('owner',argument);require(argument=='unused' and _GRANT is None)
    env=os.environ;root=globals()['_SOURCE_ROOT'];manifest=globals()['_MANIFEST_SHA'];end=time.monotonic()+30
    require(root.resolve()==root and Path(env['GITHUB_WORKSPACE']).resolve()==Path(env['GITHUB_WORKSPACE']))
    def git(*args):
        remaining=end-time.monotonic();require(remaining>0)
        result=subprocess.run(['/usr/bin/git',*args],cwd=env['GITHUB_WORKSPACE'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=min(5,remaining),
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
        require(len(result.stdout)<=131072);return result.stdout
    path=Path(env['GITHUB_EVENT_PATH']);require(path.is_absolute() and path.stat().st_size<=1048576)
    event=strict_json(path.read_bytes());binding=admit_owner(env,event,git,root,manifest,globals()['_PAYLOADS'],own_argv())
    require(time.monotonic()<end);_GRANT=dict(role='owner',pid=os.getpid());return binding


class Deadline:
    def __init__(self,end,clock=time.monotonic,checker=None):self.end,self.clock,self.checker=end,clock,checker
    def remaining(self):
        if self.checker:self.checker()
        remaining=self.end-self.clock()
        if remaining<=0:raise ProbeFailure('DEADLINE_EXPIRED')
        return remaining


def validate_worker_context(context,root,manifest,parent_pid,parent_argv,parent_exe,self_exe,now):
    require(type(context) is dict and set(context)=={'binding','parent_pid','owner_argv','workspace','work_end','outer_end'})
    validate_binding(context['binding']);require(context['binding']['source_manifest_sha256']==manifest)
    require(type(context['parent_pid']) is int and context['parent_pid']>1 and parent_pid==context['parent_pid'])
    require(parent_argv==context['owner_argv'] and argv_matches(parent_argv,root,Path(context['workspace']),manifest))
    require(parent_exe==self_exe and Path(context['workspace'])/PROJECT==root)
    require(all(type(context[key]) is float for key in ('work_end','outer_end')) and context['outer_end']-context['work_end']==10.)
    if not 0<context['work_end']-now<=20:raise ProbeFailure('DEADLINE_EXPIRED')


def worker_admission(argument):
    global _GRANT
    bootstrap_bound('worker',argument);require(_GRANT is None and type(argument) is str and len(argument)<=8192)
    raw=base64.b64decode(argument,validate=True);require(len(raw)<=6144);context=strict_json(raw);require(canonical(context)==raw)
    parent=os.getppid();proc=Path('/proc')/str(parent);cmd=(proc/'cmdline').read_bytes();require(len(cmd)<=8192 and cmd.endswith(b'\0'))
    argv=[part.decode('utf-8','strict') for part in cmd[:-1].split(b'\0')]
    validate_worker_context(context,globals()['_SOURCE_ROOT'],globals()['_MANIFEST_SHA'],parent,argv,
        os.readlink(proc/'exe'),os.readlink('/proc/self/exe'),time.monotonic())
    _GRANT=dict(role='worker',pid=os.getpid(),parent_pid=parent);return context


def address_space_limit():
    require_role('owner')
    # Inherited by the one worker across exec; bounds each address space more
    # conservatively than the128MiB RSS limit, aggregate at most256MiB.
    resource.setrlimit(resource.RLIMIT_AS,(WORKER_RSS,WORKER_RSS))


def public_address(addresses):
    if not addresses:raise ProbeFailure('DNS_FAILURE')
    for row in addresses:
        if type(row) not in (tuple,list) or len(row)!=5:raise ProbeFailure('DNS_FAILURE')
        family,kind,proto,_,address=row
        if family not in (socket.AF_INET,socket.AF_INET6) or kind!=socket.SOCK_STREAM or proto!=socket.IPPROTO_TCP:
            raise ProbeFailure('DNS_FAILURE')
        try:
            valid=type(address) is tuple and len(address)==(2 if family==socket.AF_INET else 4)
            parsed=ipaddress.ip_address(address[0])
            valid=valid and parsed.version==(4 if family==socket.AF_INET else 6) and parsed.is_global and type(address[1]) is int and address[1]==443
            if family==socket.AF_INET6:
                valid=valid and all(type(address[n]) is int for n in (2,3)) and 0<=address[2]<=1048575 and address[3]==0
        except (ValueError,IndexError,TypeError):valid=False
        if not valid:raise ProbeFailure('DNS_FAILURE')
    return addresses[0]


class NativeReader:
    def __init__(self,connection,deadline):self.connection,self.deadline=connection,deadline
    def read(self,n,remaining):
        require_role('worker');require(n==1)
        self.connection.settimeout(min(remaining,self.deadline.remaining()));self.deadline.remaining()
        data=self.connection.recv(1);self.deadline.remaining();return data


def observe_one(context,classes,*,clock=time.monotonic,dns=None,socket_factory=None,tls_factory=None):
    require_role('worker');frame=new_frame(context['binding']);deadline=Deadline(context['work_end'],clock,lambda:require_role('worker'))
    dns=dns or socket.getaddrinfo;socket_factory=socket_factory or socket.socket;tls_factory=tls_factory or ssl.create_default_context
    connection=None;stage='DNS_FAILURE'
    try:
        deadline.remaining();frame['initial_exchange_intents']=1
        addresses=dns(INITIAL_HOST,443,type=socket.SOCK_STREAM);deadline.remaining()
        family,kind,proto,_,address=public_address(addresses)
        stage='CONNECT_FAILURE';deadline.remaining();connection=socket_factory(family,kind,proto)
        deadline.remaining();connection.settimeout(deadline.remaining());deadline.remaining();connection.connect(address);deadline.remaining()
        stage='TLS_FAILURE';tls=tls_factory();deadline.remaining()
        if tls.check_hostname is not True or tls.verify_mode!=ssl.CERT_REQUIRED:raise ProbeFailure('TLS_FAILURE')
        deadline.remaining();connection=tls.wrap_socket(connection,server_hostname=INITIAL_HOST);deadline.remaining()
        stage='SEND_FAILURE';view=memoryview(REQUEST);require(len(view)<=8192)
        while view:
            deadline.remaining();connection.settimeout(deadline.remaining());deadline.remaining();count=connection.send(view);deadline.remaining()
            if type(count) is not int or not 0<count<=len(view):raise ProbeFailure('SEND_FAILURE')
            view=view[count:]
        frame['request_send_complete']=True;stage='UNKNOWN_FAILURE'
        status,headers=read_headers(NativeReader(connection,deadline),deadline);deadline.remaining()
        frame.update(classify_response(status,headers,classes));frame['header_block_complete']=True;deadline.remaining()
    except ProbeFailure as exc:fail(frame,exc.code)
    except MemoryError:fail(frame,'RESOURCE_CAP')
    except BaseException:fail(frame,stage)
    finally:
        if clock()>=context['outer_end']:
            frame['cleanup']='UNCONFIRMED';fail(frame,'DEADLINE_EXPIRED')
        else:
            try:
                if connection is not None:connection.close()
                frame['cleanup']='CONFIRMED' if clock()<context['outer_end'] else 'UNCONFIRMED'
                if frame['cleanup']=='UNCONFIRMED':fail(frame,'DEADLINE_EXPIRED')
            except BaseException:frame['cleanup']='UNCONFIRMED';fail(frame,'CLEANUP_UNCONFIRMED')
    return validate_frame(frame,context['binding'],classes)


class NativeOwnerServices:
    def __init__(self,root,manifest,context):
        self.root,self.manifest,self.context=root,manifest,context
        self.box={};self.thread=None;self.ready=False
    def launch(self):
        require_role('owner')
        encoded=base64.b64encode(canonical(self.context)).decode('ascii')
        argv=['/usr/bin/python3','-I','-B',str(self.root/'bootstrap.py'),'worker',self.manifest,encoded]
        def target():
            try:
                if time.monotonic()>=self.context['work_end']:self.box['error']=True;return
                self.box['process']=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,cwd=str(self.root),env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'},close_fds=True)
            except BaseException:self.box['error']=True
        self.thread=threading.Thread(target=target,name='owned-header-launch',daemon=True);self.thread.start()
    def process(self):return self.box.get('process')
    def launch_error(self):return self.box.get('error',False)
    def launcher_done(self):return self.thread is not None and not self.thread.is_alive()
    def read(self,cap):
        require_role('owner');proc=self.process()
        if not self.ready:os.set_blocking(proc.stdout.fileno(),False);self.ready=True
        try:return os.read(proc.stdout.fileno(),cap)
        except BlockingIOError:return None
    def poll(self):
        require_role('owner');return self.process().poll()
    def terminate(self):require_role('owner');self.process().terminate()
    def kill(self):require_role('owner');self.process().kill()
    def close(self):require_role('owner');self.process().stdout.close()
    def memory_ok(self):
        require_role('owner')
        def rss(pid):
            raw=Path('/proc')/str(pid)/'status';data=raw.read_bytes()
            require(len(data)<=16384);match=re.search(rb'^VmRSS:\s+([0-9]+) kB$',data,re.M)
            require(match is not None);return int(match[1])*1024
        own=rss(os.getpid());proc=self.process();child=0
        if proc is not None and proc.poll() is None:
            try:child=rss(proc.pid)
            except (FileNotFoundError,ProcessLookupError):
                if proc.poll() is None:raise
        return child<=WORKER_RSS and own+child<=AGGREGATE_RSS
    def pause(self):time.sleep(.01)


def supervise(binding,classes,services,start,*,clock=time.monotonic):
    require_role('owner');frame=new_frame(binding);work_end=start+20;outer_end=start+30
    raw=bytearray();accepted=False;terminated=False;killed=False;term_at=None;eof=False;close_ok=False;close_attempted=False
    def check_outer():
        if clock()>=outer_end:raise ProbeFailure('DEADLINE_EXPIRED')
    if clock()>=work_end:fail(frame,'DEADLINE_EXPIRED');frame['cleanup']='CONFIRMED';return frame
    try:
        # Once launch may have begun, progress is unknown until a valid timely
        # bound worker frame arrives; never fabricate an unattempted request.
        frame.update(initial_exchange_intents=None,request_send_complete=None,header_block_complete=None)
        check_outer();services.launch();check_outer()
        while clock()<outer_end:
            check_outer();proc=services.process();check_outer()
            if services.launch_error():fail(frame,'UNKNOWN_FAILURE')
            try:
                check_outer();memory_ok=services.memory_ok();check_outer()
                if not memory_ok:fail(frame,'RESOURCE_CAP')
            except ProbeFailure:raise
            except BaseException:fail(frame,'RESOURCE_CAP')
            if clock()>=work_end and not accepted:fail(frame,'DEADLINE_EXPIRED')
            if proc is not None:
                try:
                    check_outer();chunk=services.read(2049-len(raw)) if not eof and len(raw)<2049 else None;check_outer()
                    if chunk is not None:
                        if not chunk:eof=True
                        else:raw.extend(chunk)
                    if len(raw)>2048:fail(frame,'RESOURCE_CAP')
                except ProbeFailure:raise
                except BaseException:fail(frame,'UNKNOWN_FAILURE')
                check_outer();code=services.poll();check_outer()
                if code is not None:
                    if not accepted and clock()<work_end and eof and frame['failure']=='NONE':
                        try:
                            require(raw.endswith(b'\n') and raw.count(b'\n')==1)
                            value=strict_json(bytes(raw[:-1]));validate_frame(value,binding,classes)
                            require(canonical(value)+b'\n'==bytes(raw) and code==(0 if value['failure']=='NONE' else 1))
                            if clock()>=work_end:raise ProbeFailure('DEADLINE_EXPIRED')
                            frame=value;accepted=True
                        except ProbeFailure as exc:fail(frame,exc.code)
                        except BaseException:fail(frame,'UNKNOWN_FAILURE')
                    if eof or clock()>=work_end or frame['failure']!='NONE':
                        if not close_attempted:
                            close_attempted=True
                            try:check_outer();services.close();check_outer();close_ok=True
                            except ProbeFailure:raise
                            except BaseException:fail(frame,'CLEANUP_UNCONFIRMED')
                        check_outer();launcher_done=services.launcher_done();check_outer()
                        if launcher_done:
                            if not accepted:frame['cleanup']='CONFIRMED' if close_ok else 'UNCONFIRMED'
                            elif not close_ok:frame['cleanup']='UNCONFIRMED'
                            break
                elif frame['failure']!='NONE' or clock()>=work_end:
                    if not terminated:
                        terminated=True;term_at=clock()
                        try:check_outer();services.terminate();check_outer()
                        except ProbeFailure:raise
                        except BaseException:fail(frame,'CLEANUP_UNCONFIRMED')
                    elif not killed and clock()-term_at>=2:
                        killed=True
                        try:check_outer();services.kill();check_outer()
                        except ProbeFailure:raise
                        except BaseException:fail(frame,'CLEANUP_UNCONFIRMED')
            elif services.launcher_done() and services.launch_error():
                # A Popen exception does not prove the OS never created a child.
                frame['cleanup']='UNCONFIRMED';break
            check_outer();services.pause();check_outer()
        else:frame['cleanup']='UNCONFIRMED';fail(frame,'DEADLINE_EXPIRED')
    except ProbeFailure as exc:frame['cleanup']='UNCONFIRMED';fail(frame,exc.code)
    except BaseException:frame['cleanup']='UNCONFIRMED';fail(frame,'UNKNOWN_FAILURE')
    if clock()>=outer_end:frame['cleanup']='UNCONFIRMED';fail(frame,'DEADLINE_EXPIRED')
    validate_frame(frame,binding,classes)
    if clock()>=outer_end:frame['cleanup']='UNCONFIRMED';fail(frame,'DEADLINE_EXPIRED')
    return frame


def main(mode,argument):
    classes=host_classes()
    if mode=='worker':
        context=worker_admission(argument);result=observe_one(context,classes)
    else:
        binding=owner_admission(argument);root=globals()['_SOURCE_ROOT'];manifest=globals()['_MANIFEST_SHA']
        start=time.monotonic();context=dict(binding=binding,parent_pid=os.getpid(),owner_argv=own_argv(),
            workspace=os.environ['GITHUB_WORKSPACE'],work_end=start+20.,outer_end=start+30.)
        try:address_space_limit()
        except BaseException:
            result=new_frame(binding);fail(result,'RESOURCE_CAP');result['cleanup']='CONFIRMED'
        else:result=supervise(binding,classes,NativeOwnerServices(root,manifest,context),start)
    validate_frame(result,{key:result[key] for key in BINDING_KEYS},classes)
    sys.stdout.buffer.write(canonical(result)+b'\n');sys.stdout.buffer.flush()
    return 0 if result['failure']=='NONE' and result['header_block_complete'] is True and result['cleanup']=='CONFIRMED' else 1
