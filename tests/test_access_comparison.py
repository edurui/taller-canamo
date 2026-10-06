"""Synthetic regression tests for the offline aggregate-only comparator."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('access_comparison', Path(__file__).resolve().parents[1] / 'scripts/compare_access.py')
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def line(customer, number, description='PRIVATE_SENTINEL', date='2004-01-01T00:00'):
    return {'COD_CLI': customer, 'FACTURA': number, 'CONCEPTO': description, 'FECHAFACTURA': date}


def test_zero_and_null_are_distinct_and_table_counts_preserve_multiplicity():
    data = {'Clientes': [{'Cod_cli': 0, 'Cliente': 'PRIVATE_SENTINEL'}],
            'Facturas': [{'COD_CLI': 0, 'FACTURA': 0}] * 2,
            'DETALLE': [line(0, 0), line(0, None), line(0, 2)]}
    report = comparison.compare(data, data)
    assert report['main']['lines']['incomplete_key_rows'] == 1
    assert report['main']['lines']['falsy_key_rows'] == 3
    assert report['main']['headers']['duplicate_extra_rows'] == 1
    assert report['main']['lines']['orphan_complete_keys'] == 1
    assert report['main']['lines']['orphan_with_customer_keys'] == 1
    assert report['tables']['Facturas']['equal_multiset_rows'] == 2
    assert comparison.key({'COD_CLI': ' ', 'FACTURA': 1}) is None
    assert comparison.key({'COD_CLI': False, 'FACTURA': 1}) is None


def test_summary_does_not_disclose_source_values_unknown_names_or_paths():
    secret = 'DO_NOT_DISCLOSE_7XQ_SECRET'
    data = {'Clientes': [{'Cod_cli': secret, 'Cliente': secret, 'Matricula': secret, 'Cif o Nif': secret}],
            'DETALLE': [line(secret, secret, secret)], secret: [{secret: secret}]}
    metadata = {'Clientes': {'columns': [{'name': secret}], 'reported_rows': secret}}
    serialized = json.dumps(comparison.compare(data, data, metadata, metadata), sort_keys=True)
    assert secret not in serialized
    assert 'PRIVATE_SENTINEL' not in serialized
    assert comparison.compare(data, data, metadata, metadata) == comparison.compare(data, data, metadata, metadata)


def test_snapshot_and_backup_candidates_never_recover_duplicate_complete_lines():
    complete = line(1, 7)
    incomplete = line(1, None)
    main = {'DETALLE': [complete, incomplete], 'Detalle 2004': [complete, complete]}
    backup = {'DETALLE': [complete]}
    report = comparison.compare(main, backup)
    assert report['incomplete_line_candidates'] == {'unique': 1, 'unique_already_present_complete': 1}
    assert report['snapshot_2004']['lines']['exact_multiset_rows'] == 1
    assert report['snapshot_2004']['lines']['different_rows'] == 1
    assert main['DETALLE'] == [complete, incomplete]


def test_old_ambiguity_and_ownership_intervals_are_only_counts():
    customers = [{'Cod_cli': 1, 'Cliente': 'A', 'Matricula': 'TEST-123'},
                 {'Cod_cli': 2, 'Cliente': 'B', 'Matricula': 'test123'}]
    lines = [line(1, 7), line(1, 7, date='2004-01-02T00:00'), line(2, 8, date='2005-01-01T00:00')]
    data = {'Clientes': customers, 'DETALLE': lines}
    report = comparison.compare(data, data)
    assert report['ambiguous_dates']['already_ambiguous_backup'] == 1
    assert report['ambiguous_dates']['exact_same_line_multiset'] == 1
    assert report['shared_plates']['billing_intervals_disjoint'] == 1
    assert report['shared_plates']['already_shared_backup'] == 1
    assert 'TEST-123' not in json.dumps(report)


def test_loader_refuses_path_escape_and_reports_invalid_data_without_echo(tmp_path, monkeypatch, capsys):
    (tmp_path / 'manifest.json').write_text(json.dumps({'format': 'canamo-access-raw-v1', 'read_only': True,
        'tables': [{'name': 'Clientes', 'file': '../PRIVATE_SENTINEL.jsonl', 'rows': 1}]}))
    with pytest.raises(ValueError):
        comparison.load(tmp_path)
    monkeypatch.setattr('sys.argv', ['compare_access.py', str(tmp_path), str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        comparison.main()
    assert 'PRIVATE_SENTINEL' not in str(error.value)
    assert str(tmp_path) not in str(error.value)
    assert capsys.readouterr().out == ''
