"""Execute only pinned production matcher/render/query-selection AST methods.

No original module imports, app configuration, Qt, network, or model execution.
Language fields below are the two Chinese prompt labels and Japanese identity
needed by these production methods, not a general replacement language module.
"""
import ast
import copy
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace

# Pinned to the source inspected during this experimental policy preparation.
SOURCE_HASHES = {
    'transoptimi/noundict.py': 'd3d968c1aa3a7e54af7db804b81ea05dd19447d826db847d99f458c27115d64f',
    'translator/sakura_base.py': '3d9883f7965693cbe17a80db9a8d95ab95213737a782fc69acbee34cfa0ae28f',
    'translator/local_hymt.py': '5ea7215c0330ba43adacbb386517ed56bb5e5ab236088644196b36f8efdd98dc',
    'myutils/commonbase.py': 'c562d635565477af7d399273aa3048879652a6e1420f861154b7c958d11c8172',
}

class Languages:
    Chinese = SimpleNamespace(engname='Simplified Chinese', zhsname='简体中文')
    TradChinese = SimpleNamespace(engname='Traditional Chinese', zhsname='繁体中文')
    Japanese = SimpleNamespace(engname='Japanese', zhsname='日语')

def _trees():
    root = Path(__file__).resolve().parent / 'pinned_source'
    result = {}
    for rel, expected in SOURCE_HASHES.items():
        raw = (root / rel).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('pinned production source changed: ' + rel)
        result[rel] = ast.parse(raw, filename=rel)
    return result

def _class(tree, original, methods, name, bases=()):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == original)
    selected = [copy.deepcopy(n) for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    if {n.name for n in selected} != set(methods):
        raise ValueError('production method missing')
    return ast.ClassDef(name=name, bases=[ast.Name(id=b, ctx=ast.Load()) for b in bases], keywords=[], body=selected, decorator_list=[])

def _selection_function(tree):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TS')
    fn = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'translate'))
    end = next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='messages' for t in n.targets))
    fn.body = fn.body[:end+1] + [ast.Return(ast.Name(id='messages',ctx=ast.Load()))]
    return fn

def production_pair(raw_source, entries):
    trees = _trees()
    namespace = {'re':re, 'Languages':Languages, 'GptDict':list, 'GptTextWithDict':object, 'APIType':lambda _:None}
    nodes = [
        _class(trees['transoptimi/noundict.py'],'Process',['__createfake','process_before','process_before1'],'Process'),
        _class(trees['myutils/commonbase.py'],'commonbase',['checklangzhconv'],'Common'),
        _class(trees['translator/sakura_base.py'],'TS',['make_gpt_dict_text','hymt2_make_messages'],'Base',['Common']),
        _class(trees['translator/local_hymt.py'],'TS',['hymt2_make_messages'],'Local',['Base']),
        _selection_function(trees['translator/sakura_base.py']),
    ]
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])), '<pinned-production-policy>', 'exec'), namespace)
    process = namespace['Process']()
    # Exact settings: false whole-word, false case-sensitive, fixed stored order.
    process.usewhich = lambda:[{'src':e.src,'dst':e.dst,'whole-word':False,'case-sensitive':False} for e in entries]
    parsed, context = process.process_before(raw_source)
    matched = context['gpt_dict']
    local = namespace['Local']()
    local.tgtlang_1 = Languages.Chinese
    local.srclang = Languages.Japanese
    local.contextReal = []
    fake = SimpleNamespace(checkempty=lambda _:None,config={'prompt_version_1':'Hy-MT2'},maybedetectprompttype=lambda x:x,make_messages=lambda version,query,**kwargs:query)
    selected = namespace['translate'](fake, SimpleNamespace(rawtext=raw_source,parsedtext=parsed,dictionary=matched))
    if selected != raw_source or context['gpt_dict_origin'] != raw_source:
        raise ValueError('production raw-source selection mismatch')
    wrapped = [SimpleNamespace(src=e['src'],dst=e['dst'],info='') for e in matched]
    a = local.hymt2_make_messages(0, selected, None)
    b = local.hymt2_make_messages(0, selected, wrapped)
    return matched, a, b
