"""Pure source closure verification; never imports or executes kit modules."""
from hashlib import sha256
import ast
import json
from pathlib import Path
import re
import sys

def require(value, message):
    if not value:
        raise ValueError(message)

def main():
    require(len(sys.argv) == 2 and re.fullmatch('[0-9a-f]{64}', sys.argv[1]), 'expected exact kit hash')
    root = Path(__file__).resolve().parent
    raw = (root / 'KIT_MANIFEST.json').read_bytes()
    require(sha256(raw).hexdigest() == sys.argv[1], 'kit manifest identity')
    manifest = json.loads(raw)
    entries = manifest['files']
    require(len(entries) <= 128 and len({e['path'] for e in entries}) == len(entries), 'unique closure')
    expected = {'KIT_MANIFEST.json'}
    for item in entries:
        name = item['path']
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts, 'relative source path')
        path = root / name
        require(not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(root), 'regular source file')
        data = path.read_bytes()
        require(len(data) == item['bytes'] and sha256(data).hexdigest() == item['sha256'], 'source byte identity')
        if name.endswith('.py'):
            ast.parse(data, filename=name)
        expected.add(name)
    observed = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    require(observed == expected, 'exact source inventory')
    metadata = json.loads((root / 'INPUT_COMMITMENTS.json').read_bytes())
    plan = json.loads((root / 'SOURCE_PLAN.json').read_bytes())
    require(metadata['source_parent'] == plan['source_parent'] == manifest['source_parent'], 'parent binding')
    require(metadata['attempt_id'] == plan['attempt_id'] == manifest['attempt_id'], 'attempt metadata binding')
    require(plan['source_commit'] is None and plan['trigger_commit'] is None, 'prospective source and trigger')
    require(metadata['commitments']['source_plan'] == sha256((root / 'SOURCE_PLAN.json').read_bytes()).hexdigest(), 'plan commitment')
    require(not any(p.name == 'ONE_SHOT_CPU_ATTEMPT.json' for p in root.rglob('*')), 'no runtime claim')
    template = (root / 'WORKFLOW_TEMPLATE.yml.in').read_text()
    require(set(re.findall(r'__[A-Z0-9_]+__', template)) == {'__REVIEWED_SOURCE_COMMIT_A__', '__KIT_MANIFEST_SHA256__', '__BOOTSTRAP_SHA256__'}, 'prospective workflow placeholders')
    print(json.dumps(dict(status='PASS', payload_files=len(entries), source_files=len(expected), native_operations=0)))

if __name__ == '__main__':
    main()
