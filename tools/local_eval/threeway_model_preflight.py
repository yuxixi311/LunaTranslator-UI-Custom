"""Read bounded GGUF metadata; never load tensors, download, or run a model."""
import hashlib
import struct

MAX_METADATA_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 100000
MAX_ARRAY_ITEMS = 2000000
MAX_STRING_BYTES = 4 * 1024 * 1024
SCALAR = {0: 'B', 1: 'b', 2: 'H', 3: 'h', 4: 'I', 5: 'i',
          6: 'f', 7: '?', 10: 'Q', 11: 'q', 12: 'd'}


def read_metadata(path):
    """GGUF v2/v3 little endian only; every read/count has a fixed bound.

    Arrays are traversed but discarded. Only architecture, quantization,
    block/NextN counts, and the chat template are retained. A duplicate key,
    nested array, unknown type, truncation or oversized header fails closed.
    """
    with open(path, 'rb') as stream:
        consumed = 0
        metadata_hash = hashlib.sha256()

        def take(size):
            nonlocal consumed
            if size < 0 or consumed + size > MAX_METADATA_BYTES:
                raise ValueError('GGUF metadata byte bound exceeded')
            raw = stream.read(size)
            if len(raw) != size:
                raise ValueError('Truncated GGUF metadata')
            consumed += size
            metadata_hash.update(raw)
            return raw

        def number(fmt):
            return struct.unpack('<' + fmt, take(struct.calcsize('<' + fmt)))[0]

        def string(keep=True):
            length = number('Q')
            if length > MAX_STRING_BYTES:
                raise ValueError('GGUF string byte bound exceeded')
            raw = take(length)
            # Validate every string, including skipped tokenizer strings.
            value = raw.decode('utf-8', errors='strict')
            return value if keep else None

        def value(kind, keep):
            if kind in SCALAR:
                item = number(SCALAR[kind])
                return item if keep else None
            if kind == 8:
                return string(keep)
            if kind == 9:
                subtype, count = number('I'), number('Q')
                if subtype == 9 or subtype not in set(SCALAR) | {8} or count > MAX_ARRAY_ITEMS:
                    raise ValueError('Invalid or excessive GGUF array')
                if keep:
                    raise ValueError('Required GGUF metadata must be scalar')
                if subtype in SCALAR:
                    take(struct.calcsize('<' + SCALAR[subtype]) * count)
                else:
                    for _ in range(count):
                        string(False)
                return None
            raise ValueError('Unknown GGUF metadata value type')

        if take(4) != b'GGUF':
            raise ValueError('Not a little-endian GGUF file')
        version, tensors, count = number('I'), number('Q'), number('Q')
        if version not in (2, 3) or not 0 < tensors <= 1000000 or not 0 < count <= MAX_ENTRIES:
            raise ValueError('Unsupported GGUF version/counts')
        selected, seen = {}, set()
        for _ in range(count):
            key = string()
            if len(key) > 512 or key in seen:
                raise ValueError('Duplicate or excessive GGUF key')
            seen.add(key)
            keep = key in ('general.architecture', 'general.file_type', 'tokenizer.chat_template') or key.endswith(('.block_count', '.nextn_predict_layers'))
            item = value(number('I'), keep)
            if keep:
                selected[key] = item
        return {'gguf_version': version, 'tensor_count': tensors, 'metadata_count': count,
                'metadata_bytes': consumed, 'metadata_sha256': metadata_hash.hexdigest(),
                'values': selected}


def validate_metadata(record, spec):
    values = record['values']
    architecture = values.get('general.architecture')
    if architecture != spec['architecture']:
        raise ValueError('Unexpected model architecture')
    # GGUF MOSTLY_Q4_K_M is 15. Full-file SHA also pins the exact quantization.
    if type(values.get('general.file_type')) is not int or values['general.file_type'] != 15:
        raise ValueError('Expected pinned Q4_K_M quantization')
    blocks = values.get(architecture + '.block_count')
    if type(blocks) is not int or not 1 <= blocks <= 98:
        raise ValueError('Invalid block count for fixed 99-layer offload request')
    nextn = values.get(architecture + '.nextn_predict_layers', 0)
    if type(nextn) is not int or not 0 <= nextn < blocks:
        raise ValueError('Invalid NextN count')
    template = values.get('tokenizer.chat_template')
    if not isinstance(template, str):
        raise ValueError('Missing embedded chat template')
    template_sha = hashlib.sha256(template.encode('utf-8')).hexdigest()
    if template_sha not in spec['embedded_template_sha256']:
        raise ValueError('Unrecognized embedded chat template')
    for field, minimum, maximum in (('gguf_version', 2, 3), ('tensor_count', 1, 1000000),
                                     ('metadata_count', 1, MAX_ENTRIES), ('metadata_bytes', 1, MAX_METADATA_BYTES)):
        if type(record.get(field)) is not int or not minimum <= record[field] <= maximum:
            raise ValueError('Invalid GGUF metadata evidence: ' + field)
    return {'architecture': architecture, 'block_count': blocks, 'nextn_predict_layers': nextn,
            'expected_offloaded_layers': blocks + 1, 'embedded_template_sha256': template_sha}
