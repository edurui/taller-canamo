"""Read-only Access object forensics; raw evidence stays outside the repository.

The stdout/summary.json contract contains only counts, hashes, aliases and an exact
allowlist of known technical expressions. Object names, SQL, literals, connection
strings and VBA source are private. This is a developer tool, not a report renderer
or a historical tax decision engine. Requires the prepared runtime and JDK 17+.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'backend/taller/access_runtime'
MAX_STREAM = 16 * 1024 * 1024
MAX_DECOMPRESSED = 16 * 1024 * 1024
# Exact literals only; arbitrary object names or formula arguments may contain PII.
SAFE_FORMULAS = {'=Sum([TOTAL])', '=DATE()', '=Now()', '=Format(Date(),"Short Date")'}
for _base in ('[BRUTO]', '[Suma De TOTAL]', 'Sum([TOTAL])'):
    for _factor in ('0.16', '1.16', '0.18', '1.18', '0.21', '1.21'):
        SAFE_FORMULAS.add(f'={_base}*{_factor}')
SAFE_STATEMENTS = {
    'TOTAL = CANTIDAD * PRECIO', 'BRUTO = BRUTO + TOTAL', 'BRUTO = 0',
    'FACTURA = temporal + 1', 'stDocName = "Facturacion"',
}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def decompress_vba(data: bytes, max_output: int = MAX_DECOMPRESSED, *, allow_empty_tail: bool = False) -> bytes:
    """Strict bounded decoder for MS-OVBA 2.4.1 (never executes VBA)."""
    if not data or data[0] != 1:
        raise ValueError('Invalid VBA signature')
    output = bytearray()
    pos = 1
    while pos < len(data):
        start = pos
        if pos + 2 > len(data):
            raise ValueError('Truncated VBA header')
        header = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        end = start + (header & 0xFFF) + 3
        if (header >> 12) & 7 != 3 or end > len(data):
            raise ValueError('Invalid VBA chunk')
        base = len(output)
        if not header & 0x8000:
            if end - pos != 4096 or len(output) + 4096 > max_output:
                raise ValueError('Invalid or oversized raw VBA chunk')
            output.extend(data[pos:end])
            pos = end
            continue
        while pos < end:
            flags = data[pos]
            pos += 1
            if pos == end and not allow_empty_tail:
                raise ValueError('Empty VBA token sequence')
            for bit in range(8):
                if pos == end:
                    break
                if flags & (1 << bit):
                    if pos + 2 > end:
                        raise ValueError('Truncated VBA copy token')
                    token = struct.unpack_from('<H', data, pos)[0]
                    pos += 2
                    width = max(4, (len(output) - base - 1).bit_length())
                    length = (token & (0xFFFF >> width)) + 3
                    offset = (token >> (16 - width)) + 1
                    if (offset > len(output) - base or len(output) - base + length > 4096
                            or len(output) + length > max_output):
                        raise ValueError('Invalid or oversized VBA copy')
                    for _ in range(length):
                        output.append(output[-offset])
                else:
                    if len(output) - base >= 4096 or len(output) >= max_output:
                        raise ValueError('Oversized VBA output')
                    output.append(data[pos])
                    pos += 1
    return bytes(output)


def utf16_strings(data: bytes):
    """Find printable UTF-16LE runs at either byte alignment, with byte offsets."""
    for match in re.finditer(rb'(?:[\x20-\x7e]\x00){3,}', data):
        yield match.start(), match.group().decode('utf-16le')


def parse_access_directory(data: bytes) -> dict[str, str]:
    """Observed Access 2003 DirData records; reject unknown layouts, never guess."""
    if data[:4] != bytes(4):
        raise ValueError('Unknown Access directory header')
    result = {}
    pos = 4
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError('Truncated Access directory')
        tag, size = data[pos:pos + 2]
        pos += 2
        if tag != 4 or size < 4 or size % 2 or pos + size > len(data):
            raise ValueError('Unknown Access directory record')
        record = data[pos:pos + size]
        key = str(int.from_bytes(record[-4:], 'little'))
        if key in result:
            raise ValueError('Duplicate Access directory key')
        result[key] = record[:-4].decode('utf-16le')
        pos += size
    return result


def private_binary(folder: Path, value: dict) -> bytes:
    name = value['file']
    if not re.fullmatch(r'binary-\d+-\d+-\d+\.dat', name):
        raise ValueError('Unsafe evidence filename')
    path = folder / name
    if path.is_symlink() or path.stat().st_size > MAX_STREAM:
        raise ValueError('Unsupported evidence stream')
    return path.read_bytes()


def read_rows(folder: Path, table: dict):
    name = table['file']
    if not re.fullmatch(r'system-\d+\.jsonl', name):
        raise ValueError('Unsafe evidence table')
    with (folder / name).open(encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def summarize(folder: Path) -> dict:
    catalog = json.loads((folder / 'catalog.json').read_text(encoding='utf-8'))
    tables = {table['name']: table for table in catalog['tables']}
    rows = list(read_rows(folder, tables['MSysAccessStorage'])) if 'MSysAccessStorage' in tables else []
    by_id = {row['Id']: row for row in rows}
    blobs, modules = [], []
    for row in rows:
        if not row.get('Lv'):
            continue
        data = private_binary(folder, row['Lv'])
        if row['Name'] == 'Blob':
            parent = by_id.get(row['ParentId'], {})
            category = by_id.get(parent.get('ParentId'), {}).get('Name')
            if category in ('Forms', 'Reports', 'Scripts'):
                strings = list(utf16_strings(data))
                blobs.append({
                    'alias': f'object-{len(blobs)}', 'category': category,
                    'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                    'formulas': [{'offset': offset, 'expression': text}
                                 for offset, text in strings if text in SAFE_FORMULAS],
                    'two_decimal_format_present': any('#,##0.00' in text for _, text in strings),
                })
        parent = by_id.get(row['ParentId'], {})
        if (parent.get('Name') != 'VBA' or by_id.get(parent.get('ParentId'), {}).get('Name') != 'VBAProject'
                or row['Name'] in ('dir', '_VBA_PROJECT')):
            continue
        # Source offsets normally come from the dir stream. Bounded recovery scans
        # the small module stream and requires a complete valid container plus the
        # VBA source signature. This is source recovery, not a p-code audit.
        found = None
        for offset in range(min(len(data), 65536)):
            if data[offset] != 1:
                continue
            compatibility_tail = False
            try:
                source = decompress_vba(data[offset:])
            except ValueError as failure:
                if str(failure) != 'Empty VBA token sequence':
                    continue
                # Some Access streams end with a flag byte and no token. The
                # Microsoft decoder pseudocode ignores it; retain that exception
                # explicitly in evidence instead of claiming strict conformance.
                try:
                    source = decompress_vba(data[offset:], allow_empty_tail=True)
                    compatibility_tail = True
                except ValueError:
                    continue
            if source.startswith(b'Attribute VB_Name = "'):
                found = (offset, source, compatibility_tail)
                break
        entry = {'alias': f'module-{len(modules)}', 'recovered': found is not None}
        if found:
            offset, source, compatibility_tail = found
            # Raw source is private and filenames cannot be controlled by its name.
            target = folder / f'{entry["alias"]}.vba'
            with target.open('xb') as output:
                output.write(source)
            text = source.decode('cp1252', errors='replace')
            lines = {line.strip() for line in text.splitlines()}
            entry.update({'source_offset': offset, 'source_bytes': len(source),
                          'empty_tail_compatibility': compatibility_tail,
                          'sha256': hashlib.sha256(source).hexdigest(),
                          'known_statements': sorted(lines & SAFE_STATEMENTS),
                          'round_call_present': bool(re.search(r'\bRound\s*\(', text, re.I)),
                          'formatcount_guard_present': bool(re.search(r'\bIf\s+FormatCount\b', text, re.I))})
        modules.append(entry)
    objects = list(read_rows(folder, tables['MSysObjects'])) if 'MSysObjects' in tables else []
    return {
        'format': catalog['format'] if catalog['format'] in ('V2000', 'V2003', 'V2007', 'V2010', 'V2016', 'V2019') else 'other',
        'read_only': True, 'links_followed': 0, 'executed_code': False,
        'system_table_count': len(tables),
        'object_type_counts': dict(sorted(Counter(str(row['Type']) for row in objects).items())),
        'query_type_counts': dict(sorted(Counter(query['type'] for query in catalog['queries']).items())),
        'storage_rows': len(rows), 'blobs': blobs, 'vba_modules': modules,
        'limits': ['No report rendering', 'No p-code validation', 'No historical tax-period inference'],
    }


def extract(source: Path, destination: Path) -> dict:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination == ROOT or destination.is_relative_to(ROOT):
        raise ValueError('Private evidence must stay outside the repository')
    if destination.exists():
        raise ValueError('Evidence destination already exists')
    if not source.is_file():
        raise ValueError('Source must be a file')
    before = sha256(source)
    destination.mkdir(mode=0o700, parents=True)
    os.chmod(destination, 0o700)
    old_umask = os.umask(0o077)
    try:
        library = RUNTIME / 'lib/jackcess-5.0.1.jar'
        reader = RUNTIME / 'canamo-access.jar'
        javac = shutil.which('javac')
        java = RUNTIME / 'jre/bin' / ('java.exe' if os.name == 'nt' else 'java')
        if not javac or not java.exists() or not library.exists() or not reader.exists():
            raise ValueError('Prepared Access runtime and JDK required')
        classes = destination / 'classes'
        classes.mkdir()
        classpath = os.pathsep.join(map(str, (reader, library)))
        with (destination / 'private-process.log').open('xb') as log:
            subprocess.run([javac, '--release', '17', '-encoding', 'UTF-8', '-cp', classpath,
                            '-d', str(classes), str(ROOT / 'tools/access/AccessForensics.java')],
                           check=True, stdout=log, stderr=log, timeout=60)
            subprocess.run([str(java), '-Xmx512m', '-cp', os.pathsep.join((str(classes), classpath)),
                            'AccessForensics', str(source), str(destination / 'raw')],
                           check=True, stdout=log, stderr=log, timeout=120)
        result = summarize(destination / 'raw')
        after = sha256(source)
        if before != after:
            raise ValueError('Source changed during examination')
        result.update({'source_sha256': before, 'source_unchanged': True})
        (destination / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result
    finally:
        os.umask(old_umask)
        if sha256(source) != before:
            raise ValueError('Source changed during examination')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--private-output', type=Path,
                        help='New evidence directory outside the repository; defaults to a private temporary directory')
    args = parser.parse_args()
    destination = args.private_output
    if destination is None:
        parent = Path(tempfile.mkdtemp(prefix='canamo-forensics-'))
        destination = parent / 'evidence'
    try:
        result = extract(args.source, destination)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError):
        raise SystemExit('Forensic extraction failed; inspect the private local evidence log. No database text is printed.')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
