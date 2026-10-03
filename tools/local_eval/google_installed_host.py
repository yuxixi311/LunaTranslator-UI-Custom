"""Isolated loader for existing installed Luna source and libcurl DLL.

No app launcher, config/history import, private key extraction or new HTTP client.
Invoke only in an owned short-lived worker process. Do not import in the app.
"""
import ast
import hashlib
import os
from pathlib import Path
import struct
import sys
import types

SOURCE_HASHES = {
    'translator/google.py':'d53887fa426a9bc7fb1031b3e5fbd45f9770f045e9854a3f49ebdb5a566b7694',
    'requests.py':'968bbe3c3b68a9e2591d2a2acf08019593d17d45c02a1ef9ea4cc96f8dbfdf0a',
    'network/client/libcurl/requester.py':'7fc80265f98a77879874143ff32fbdf3c2e93e716f43976a5f729ea071dd6b93',
    'network/client/libcurl/libcurl.py':'5dde51d8b387b55166bc17c2dc0474ab4890a71ae9730a31056997db68a79504',
    'myutils/proxy.py':'d6213963569443a06535e6a030571dc453fe8b02250c68dec0d312c2886cfa33',
    'myutils/commonbase.py':'887e7ec67f069da4d132a03becf8892fd76ba8e2d41fb4c72610fa515fa3229e',
}
# This pure-stdlib dependency permits newline normalization only. Record raw hash.
STRUCTURES_LF_SHA = 'be08de95511309de5c3be42807a41031430de3b444e0ed9a91070adaf85b4b0b'
DLL_SHA256 = '9d785e07566b4324b2d143ab598ba9082695648d478d131be0805d401ad6cdc7'
DLL_BYTES = 3155048


def read_sources(root):
    root=Path(root);sources={};hashes={}
    for name,expected in SOURCE_HASHES.items():
        data=(root/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual != expected:raise ValueError('Installed source pin mismatch')
        sources[name]=data;hashes[name]=actual
    data=(root/'network/structures.py').read_bytes()
    if hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()!=STRUCTURES_LF_SHA:
        raise ValueError('Installed structures source mismatch')
    sources['network/structures.py']=data
    hashes['network/structures.py']=hashlib.sha256(data).hexdigest()
    hashes['network/structures.py.normalized-lf']=STRUCTURES_LF_SHA
    return sources,hashes


def compile_proxy_session(source, requests_module, getproxy):
    # Compile the ORIGINAL class only; never execute commonbase app imports.
    tree=ast.parse(source)
    found=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='proxysession']
    if len(found)!=1:raise ValueError('Expected original proxy session class')
    namespace={'requests':requests_module,'getproxy':getproxy}
    module=ast.Module(body=found,type_ignores=[])
    exec(compile(module,'installed-commonbase-proxysession','exec'),namespace)
    return namespace['proxysession']


def load_host(root,dll):
    if os.name!='nt' or struct.calcsize('P')!=8 or sys.getwindowsversion().major<10 or sys.version_info[:2]!=(3,12):
        raise ValueError('Requires existing Python 3.12 on modern Windows x64')
    sources,hashes=read_sources(root)
    dll=Path(dll)
    if dll.stat().st_size!=DLL_BYTES or hashlib.sha256(dll.read_bytes()).hexdigest()!=DLL_SHA256:
        raise ValueError('Installed libcurl pin mismatch')
    # All package shells are inert; no application package initializers run.
    for name in ('myutils','network','network.client','network.client.libcurl'):
        package=types.ModuleType(name);package.__path__=[];sys.modules[name]=package
    config=types.ModuleType('myutils.config')
    config.globalconfig={'network':1,'useproxy':True,'usesysproxy':True,
                         'fanyi':{'google':{'useproxy':True}}}
    sys.modules['myutils.config']=config
    gobject=types.ModuleType('gobject');gobject.sys_le_xp=False
    def original_dll_lookup(names):
        if names != ('libcurl.dll','libcurl-x64.dll'):raise ValueError('Unexpected DLL dependency')
        return str(dll)
    gobject.GetDllpath=original_dll_lookup;sys.modules['gobject']=gobject
    dll_search=os.add_dll_directory(str(dll.parent))
    def load(name,relative):
        module=types.ModuleType(name);module.__file__=str(Path(root)/relative)
        module.__package__=name.rpartition('.')[0];sys.modules[name]=module
        exec(compile(sources[relative],module.__file__,'exec'),module.__dict__)
        return module
    load('network.structures','network/structures.py')
    requests_module=load('requests','requests.py')
    load('network.client.libcurl.libcurl','network/client/libcurl/libcurl.py')
    requester=load('network.client.libcurl.requester','network/client/libcurl/requester.py')
    from google_curl_observer import install_observer
    completion=install_observer(requester)
    proxy=load('myutils.proxy','myutils/proxy.py')
    session_class=compile_proxy_session(sources['myutils/commonbase.py'],requests_module,proxy.getproxy)
    session=session_class('fanyi','google')
    # Retain DLL search ownership for this short-lived process only.
    session._test_dll_search=dll_search
    return session,requests_module.Response,hashes,completion
