"""Synthetic forensic vectors: decompression, privacy boundary and read-only extraction."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('access_forensics', ROOT / 'scripts/access_forensics.py')
forensics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forensics)


def literals(value):
    body = b''.join(b'\x00' + value[pos:pos + 8] for pos in range(0, len(value), 8))
    return b'\x01' + struct.pack('<H', 0xB000 | (len(body) - 1)) + body


def test_vba_decodes_literals_and_overlapping_copy_and_resets_chunk():
    # Three literals ABC then an overlapping copy (offset 3, length 6).
    chunk = b'\x08ABC' + struct.pack('<H', (2 << 12) | 3)
    compressed = b'\x01' + struct.pack('<H', 0xB000 | (len(chunk) - 1)) + chunk
    assert forensics.decompress_vba(compressed) == b'ABCABCABC'
    assert forensics.decompress_vba(literals(b'Attribute VB_Name = "Synthetic"')) == b'Attribute VB_Name = "Synthetic"'
    assert forensics.decompress_vba(b'\x01\xff\x3f' + bytes(4096) + literals(b'END')[1:]) == bytes(4096) + b'END'


@pytest.mark.parametrize('value', [b'', b'\x02', b'\x01\x00', b'\x01\x00\x00',
                                     b'\x01\x02\xb0\x01\x00\x00', b'\x01\x00\xb0\x00'])
def test_vba_rejects_malformed_containers(value):
    with pytest.raises(ValueError):
        forensics.decompress_vba(value)


def test_vba_bounds_expansion():
    with pytest.raises(ValueError):
        forensics.decompress_vba(literals(b'12345678'), max_output=7)


def test_utf16_odd_alignment_and_exact_allowlist_excludes_private_literals():
    data = b'X' + '=[BRUTO]*0.21'.encode('utf-16le') + b'\x00\x00' + '=Client("Synthetic private identity")'.encode('utf-16le')
    found = list(forensics.utf16_strings(data))
    assert found[0] == (1, '=[BRUTO]*0.21')
    approved = [value for _, value in found if value in forensics.SAFE_FORMULAS]
    assert approved == ['=[BRUTO]*0.21']


def test_observed_access_directory_and_malformed_lengths():
    name = 'Synthetic report'.encode('utf-16le')
    value = bytes(4) + bytes([4, len(name) + 4]) + name + struct.pack('<I', 7)
    assert forensics.parse_access_directory(value) == {'7': 'Synthetic report'}
    with pytest.raises(ValueError):
        forensics.parse_access_directory(value[:-1])


def test_rejects_evidence_inside_repository_before_creation(tmp_path):
    source = tmp_path / 'input.mdb'
    source.write_bytes(b'synthetic')
    with pytest.raises(ValueError, match='outside the repository'):
        forensics.extract(source, ROOT / 'work/forensics-must-not-be-created')


def test_real_jackcess_fixture_is_unchanged_and_public_summary_has_no_rows(tmp_path):
    runtime = forensics.RUNTIME
    java = runtime / 'jre/bin' / ('java.exe' if os.name == 'nt' else 'java')
    source = tmp_path / 'synthetic.mdb'
    classpath = os.pathsep.join(map(str, (runtime / 'canamo-access.jar', runtime / 'lib/jackcess-5.0.1.jar')))
    subprocess.run([str(java), '-cp', classpath, 'CanamoAccess', 'fixture', str(source), 'mdb'],
                   check=True, capture_output=True)
    original = source.read_bytes()
    destination = tmp_path / 'evidence'
    summary = forensics.extract(source, destination)
    assert source.read_bytes() == original
    assert summary['source_unchanged'] and summary['read_only']
    assert summary['links_followed'] == 0 and not summary['executed_code']
    serialized = json.dumps(summary)
    for private in ['Cliente', '600000001', '1234-XYZ', 'forbidden.mdb', str(source)]:
        assert private not in serialized
    assert destination.stat().st_mode & 0o077 == 0
    assert (destination / 'summary.json').stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match='already exists'):
        forensics.extract(source, destination)


def test_access_empty_final_flag_requires_explicit_compatibility():
    # Microsoft's decoder pseudocode tolerates an empty last token sequence,
    # although the normative token-array constraint requires at least one token.
    body = b'\x00ABCDEFGH\x00'
    value = b'\x01' + struct.pack('<H', 0xB000 | (len(body) - 1)) + body
    with pytest.raises(ValueError, match='Empty VBA token sequence'):
        forensics.decompress_vba(value)
    assert forensics.decompress_vba(value, allow_empty_tail=True) == b'ABCDEFGH'


def test_summary_never_exports_unknown_object_names_or_vba_literals(tmp_path):
    def binary(index, data):
        name = f'binary-0-{index}-3.dat'
        (tmp_path / name).write_bytes(data)
        return {'file': name, 'bytes': len(data)}
    source = b'Attribute VB_Name = "Private Person"\r\nMsgBox "PRIVATE ACCOUNT"\r\nBRUTO = 0\r\n'
    rows = [
        {'Id': 1, 'ParentId': 1, 'Name': 'Forms', 'Lv': None},
        {'Id': 2, 'ParentId': 1, 'Name': 'Private Person', 'Lv': None},
        {'Id': 3, 'ParentId': 2, 'Name': 'Blob', 'Lv': binary(3, '=[BRUTO]*0.21\x00PRIVATE ACCOUNT'.encode('utf-16le'))},
        {'Id': 4, 'ParentId': 1, 'Name': 'VBAProject', 'Lv': None},
        {'Id': 5, 'ParentId': 4, 'Name': 'VBA', 'Lv': None},
        {'Id': 6, 'ParentId': 5, 'Name': 'PRIVATE ACCOUNT', 'Lv': binary(6, literals(source))},
    ]
    (tmp_path / 'system-0.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    (tmp_path / 'catalog.json').write_text(json.dumps({'format': 'V2003', 'tables': [
        {'name': 'MSysAccessStorage', 'file': 'system-0.jsonl'}], 'queries': []}))
    summary = forensics.summarize(tmp_path)
    assert summary['blobs'][0]['formulas'][0]['expression'] == '=[BRUTO]*0.21'
    assert summary['vba_modules'][0]['known_statements'] == ['BRUTO = 0']
    serialized = json.dumps(summary)
    assert 'Private Person' not in serialized and 'PRIVATE ACCOUNT' not in serialized
