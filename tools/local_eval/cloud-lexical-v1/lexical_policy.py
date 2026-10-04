"""Pure, source-only entry filter. No parser import, inference or expected labels."""
import re

def validate_tokens(source, tokens):
    if not isinstance(source,str) or not isinstance(tokens,list):
        raise ValueError('invalid source/tokens')
    end=0
    for t in tokens:
        if set(t)!={'start','end','raw_surface','pos','is_oov','dictionary_id'}:
            raise ValueError('token schema')
        a,b=t['start'],t['end']
        if type(a) is not int or type(b) is not int or not end<=a<b<=len(source):
            raise ValueError('span bounds/order')
        if source[end:a] and not source[end:a].isspace():
            raise ValueError('uncovered source')
        if t['raw_surface']!=source[a:b]:
            raise ValueError('surface mismatch')
        if not isinstance(t['pos'],list) or len(t['pos'])!=6 or not all(isinstance(p,str) for p in t['pos']):
            raise ValueError('POS schema')
        if type(t['is_oov']) is not bool or type(t['dictionary_id']) is not int:
            raise ValueError('dictionary schema')
        if (t['is_oov'],t['dictionary_id']) not in ((True,-1),(False,0)):
            raise ValueError('OOV/dictionary inconsistency or user dictionary')
        end=b
    if source[end:] and not source[end:].isspace():
        raise ValueError('uncovered source tail')

def admitted_entries(source,tokens,keys):
    validate_tokens(source,tokens)
    if len(set(keys))!=len(keys) or not all(isinstance(k,str) and k and not any(c.isspace() for c in k) for k in keys):
        raise ValueError('invalid fixed canon')
    spans={(t['start'],t['end']):t for t in tokens}
    result=[]
    for key in keys:
        occurrences=[(m.start(),m.end()) for m in re.finditer(re.escape(key),source)]
        if occurrences and all((span in spans and not spans[span]['is_oov'] and spans[span]['dictionary_id']==0 and spans[span]['pos'][:3]==['名詞','固有名詞','人名']) for span in occurrences):
            result.append(key)
    return result
