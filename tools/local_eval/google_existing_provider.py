"""Execute a pinned, pre-existing Luna provider; never copy its client header.

This module has no network entry point. A reviewed collector must supply a
bounded session. It does not claim an installed application's configuration.
"""
import hashlib
from pathlib import Path
import sys
import types

PROVIDER_SHA256 = 'd53887fa426a9bc7fb1031b3e5fbd45f9770f045e9854a3f49ebdb5a566b7694'
ENDPOINT = 'https://translate-pa.googleapis.com/v1/translateHtml'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_existing_provider(path, bounded_session):
    """Run unchanged provider class definitions with inert UI/base dependencies.

    Must run in an isolated collector child. No app config or credentials are
    imported. Exact file hash rejects changed code before it is compiled.
    """
    path = Path(path)
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != PROVIDER_SHA256:
        raise ValueError('Existing Google provider source hash mismatch')
    language = types.ModuleType('language')
    language.Languages = types.SimpleNamespace(Chinese='zh-CN', TradChinese='zh-TW')
    base = types.ModuleType('translator.basetranslator')
    base.basetrans = type('InertBase', (), {})
    cdp = types.ModuleType('translator.cdp_helper')
    cdp.cdp_helper = type('UnusedBrowserHelper', (), {})
    shims = {'language': language, 'translator.basetranslator': base, 'translator.cdp_helper': cdp}
    previous = {name: sys.modules.get(name) for name in shims}
    try:
        sys.modules.update(shims)
        namespace = {'__name__': 'luna_existing_google_under_test', '__file__': str(path)}
        exec(compile(source, str(path), 'exec'), namespace)
        provider = namespace['TS']()
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    provider.srclang = 'ja'
    provider.tgtlang = 'zh-CN'
    provider.proxysession = bounded_session
    return provider
