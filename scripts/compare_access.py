"""Compare two LOCAL Jackcess extractions; stdout contains aggregate counts only.

Run access_tool.py extract first if needed, and unpack into private directories.
This tool never runs queries, modifies either extraction, or writes record values,
identifiers, fingerprints, arbitrary table names or filesystem paths to its report.
The backup is evidence, never a second import source. Counts preserve multiplicity.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from taller.access import jsonl_rows
from taller.errors import AppError
from taller.validation import normalized, plate

TABLES = ('Clientes', 'Clientes 2004', 'Codigos_Postal', 'DETALLE', 'Detalle 2004', 'Facturas', 'Errores de pegado')
CUSTOMER_FIELDS = ('Cod_cli', 'Cliente', 'Cif o Nif', 'Direccion', 'Codigo_postal', 'Telefono1', 'Telefono2', 'Fax', 'Email', 'Matricula', 'Tipo de Vehiculo')
LINE_FIELDS = ('COD_CLI', 'FACTURA', 'CANTIDAD', 'CONCEPTO', 'PRECIO', 'TOTAL', 'FECHAFACTURA')


def canonical(row):
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def blank(value):
    return value is None or isinstance(value, str) and not value.strip()


def key(row, columns=('COD_CLI', 'FACTURA')):
    values = tuple(row.get(column) for column in columns)
    # Zero is a valid scalar identifier. It is never conflated with NULL.
    if any(blank(value) or isinstance(value, (dict, list, bool)) for value in values):
        return None
    return tuple(str(value) for value in values)


def groups(rows, columns=('COD_CLI', 'FACTURA')):
    result = defaultdict(list)
    for row in rows:
        identity = key(row, columns)
        if identity is not None:
            result[identity].append(row)
    return result


def load(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 'canamo-access-raw-v1' or manifest.get('read_only') is not True:
        raise ValueError('Requires a read-only native extraction.')
    tables = {}
    metadata = {}
    for table in manifest['tables']:
        name = table['name']
        if name not in TABLES or table.get('linked'):
            continue
        if name in tables or not re.fullmatch(r'table-\d+\.jsonl', table.get('file', '')):
            raise ValueError('Invalid extraction metadata.')
        source = (directory / table['file']).resolve()
        if source.parent != directory:
            raise ValueError('Extraction escapes its directory.')
        with source.open('rb') as stream:
            tables[name] = [row for _, row in jsonl_rows(stream)]
        if len(tables[name]) != table['rows']:
            raise ValueError('Extraction row count does not reconcile.')
        metadata[name] = table
    return tables, metadata


def structural(tables):
    customers = tables.get('Clientes', [])
    headers = tables.get('Facturas', [])
    lines = tables.get('DETALLE', [])
    customer_groups = groups(customers, ('Cod_cli',))
    hg, lg = groups(headers), groups(lines)
    date_sets = {identity: {row.get('FECHAFACTURA') for row in rows if not blank(row.get('FECHAFACTURA'))}
                 for identity, rows in lg.items()}
    bad_customers = [row for row in customers if key(row, ('Cod_cli',)) is None or blank(row.get('Cliente'))]
    numbers = defaultdict(set)
    for customer, number in lg:
        numbers[number].add(customer)
    orphan_keys = lg.keys() - hg.keys()
    missing = hg.keys() - lg.keys()
    return {
        'customers': {'rows': len(customers), 'incomplete_rows': len(bad_customers),
                      'duplicate_key_groups': sum(len(rows) > 1 for rows in customer_groups.values()),
                      'incomplete_with_headers': sum(any(k[0] == str(row.get('Cod_cli')) for k in hg) for row in bad_customers),
                      'incomplete_with_lines': sum(any(k[0] == str(row.get('Cod_cli')) for k in lg) for row in bad_customers),
                      'empty_except_key': sum(all(blank(value) for name, value in row.items() if name != 'Cod_cli') for row in bad_customers)},
        'headers': {'rows': len(headers), 'complete_keys': len(hg),
                    'incomplete_rows': sum(key(row) is None for row in headers),
                    'null_customer_rows': sum(row.get('COD_CLI') is None for row in headers),
                    'all_null_rows': sum(all(blank(value) for value in row.values()) for row in headers),
                    'duplicate_groups': sum(len(rows) > 1 for rows in hg.values()),
                    'duplicate_extra_rows': sum(len(rows) - 1 for rows in hg.values()),
                    'duplicate_groups_exact': sum(len(rows) > 1 and len({canonical(row) for row in rows}) == 1 for rows in hg.values()),
                    'without_lines_keys': len(missing), 'without_lines_rows': sum(len(hg[k]) for k in missing),
                    'without_customer_keys': sum((identity[0],) not in customer_groups for identity in hg)},
        'lines': {'rows': len(lines), 'incomplete_key_rows': sum(key(row) is None for row in lines),
                  'falsy_key_rows': sum(not row.get('COD_CLI') or not row.get('FACTURA') for row in lines),
                  'zero_key_rows': sum(any(row.get(name) == 0 for name in ('COD_CLI', 'FACTURA')) for row in lines),
                  'orphan_complete_keys': len(orphan_keys), 'orphan_rows': sum(len(lg[k]) for k in orphan_keys),
                  'orphan_zero_keys': sum('0' in identity for identity in orphan_keys),
                  'orphan_with_customer_keys': sum((identity[0],) in customer_groups for identity in orphan_keys),
                  'without_customer_keys': sum((identity[0],) not in customer_groups for identity in lg),
                  'date_conflict_keys': sum(len(dates) > 1 for dates in date_sets.values()),
                  'date_conflict_header_rows': sum(len(hg.get(identity, [])) for identity, dates in date_sets.items() if len(dates) > 1),
                  'date_conflict_max_distinct': max(map(len, date_sets.values()), default=0),
                  'same_number_multiple_customers': sum(len(clients) > 1 for clients in numbers.values())},
    }


def snapshot_summary(main, backup):
    current = groups(main.get('Clientes', []), ('Cod_cli',))
    snapshot = main.get('Clientes 2004', [])
    fields = Counter()
    same = missing = ambiguous = 0
    for row in snapshot:
        matches = current.get(key(row, ('Cod_cli',)), [])
        if not matches:
            missing += 1
        elif len(matches) != 1:
            ambiguous += 1
        elif canonical(row) == canonical(matches[0]):
            same += 1
        else:
            fields.update(name for name in CUSTOMER_FIELDS if row.get(name) != matches[0].get(name))
    now_counts = Counter(map(canonical, main.get('DETALLE', [])))
    old_counts = Counter(map(canonical, backup.get('DETALLE', [])))
    snapshot_counts = Counter(map(canonical, main.get('Detalle 2004', [])))
    current_lines = groups(main.get('DETALLE', []))
    extra = snapshot_counts - now_counts
    return {'customers': {'rows': len(snapshot), 'exact_rows': same, 'missing_keys': missing,
                          'ambiguous_keys': ambiguous, 'changed_rows': len(snapshot) - same - missing - ambiguous,
                          'changed_field_counts': dict(sorted(fields.items()))},
            'lines': {'rows': sum(snapshot_counts.values()), 'exact_multiset_rows': sum((snapshot_counts & now_counts).values()),
                      'different_rows': sum(extra.values()),
                      'different_with_current_key': sum(count for serialized, count in extra.items() if key(json.loads(serialized)) in current_lines),
                      'different_exact_in_backup': sum((extra & old_counts).values())}}


def incomplete_customer_recovery(main, backup):
    rows = [row for row in main.get('Clientes', []) if key(row, ('Cod_cli',)) is None or blank(row.get('Cliente'))]
    result = {'incomplete_rows': len(rows)}
    for label, source in [('backup', backup.get('Clientes', [])), ('snapshot', main.get('Clientes 2004', []))]:
        index = groups(source, ('Cod_cli',))
        matches = [index.get(key(row, ('Cod_cli',)), []) for row in rows]
        result[label + '_present'] = sum(bool(group) for group in matches)
        result[label + '_unique_named'] = sum(len(group) == 1 and not blank(group[0].get('Cliente')) for group in matches)
    return result


def line_recovery_candidates(main, backup):
    """Candidates are evidence only, never an instruction to add/remove lines."""
    index = defaultdict(list)
    current = Counter(map(canonical, main.get('DETALLE', [])))
    for row in backup.get('DETALLE', []):
        if key(row) is not None:
            index[canonical({name: value for name, value in row.items() if name != 'FACTURA'})].append(row)
    result = Counter()
    for row in main.get('DETALLE', []):
        if key(row) is not None:
            continue
        matches = index[canonical({name: value for name, value in row.items() if name != 'FACTURA'})]
        keys = {key(match) for match in matches}
        result['none' if not keys else 'unique' if len(keys) == 1 else 'ambiguous'] += 1
        if len(keys) == 1:
            result['unique_already_present_complete'] += all(current[canonical(match)] for match in matches)
    return dict(sorted(result.items()))


def date_summary(rows):
    dates = sorted(row['FECHAFACTURA'][:10] for row in rows
                   if isinstance(row.get('FECHAFACTURA'), str)
                   and re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+', row['FECHAFACTURA']))
    return {'first': dates[0] if dates else None, 'last': dates[-1] if dates else None,
            'dated_rows': len(dates), 'years': dict(sorted(Counter(value[:4] for value in dates).items()))}


def plate_summary(main, backup):
    def plate_groups(rows):
        result = defaultdict(list)
        for row in rows:
            normalized_plate = plate(row.get('Matricula'))
            if normalized_plate:
                result[normalized_plate].append(row)
        return result
    pg = plate_groups(main.get('Clientes', []))
    bg = plate_groups(backup.get('Clientes', []))
    shared = {identifier: rows for identifier, rows in pg.items() if len(rows) > 1}
    dates = defaultdict(list)
    for row in main.get('DETALLE', []):
        date = row.get('FECHAFACTURA')
        if isinstance(date, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T[0-9:.]+', date):
            dates[str(row.get('COD_CLI'))].append(date[:10])
    metrics = Counter()
    for identifier, rows in shared.items():
        customers = {str(row.get('Cod_cli')) for row in rows}
        metrics['multiple_customer_keys'] += len(customers) > 1
        old_customers = {str(row.get('Cod_cli')) for row in bg.get(identifier, [])}
        metrics['already_shared_backup'] += len(old_customers) > 1
        metrics['backup_single_customer'] += len(old_customers) == 1
        metrics['absent_backup'] += not old_customers
        for label, field in [('same_nonempty_name', 'Cliente'), ('same_nonempty_tax_id', 'Cif o Nif')]:
            values = {normalized(row.get(field)) for row in rows}
            metrics[label] += len(values) == 1 and '' not in values
        intervals = sorted((min(dates[c]), max(dates[c])) for c in customers if dates[c])
        if len(intervals) != len(customers):
            metrics['billing_intervals_incomplete'] += 1
        elif all(intervals[i][1] < intervals[i+1][0] for i in range(len(intervals)-1)):
            metrics['billing_intervals_disjoint'] += 1
        else:
            metrics['billing_intervals_overlap'] += 1
    return {'shared_plates': len(shared), 'shared_rows': sum(map(len, shared.values())),
            'max_rows_per_plate': max(map(len, shared.values()), default=0), **dict(sorted(metrics.items()))}


def compare(main, backup, main_metadata=None, backup_metadata=None):
    table_counts = {}
    for table in TABLES:
        current = Counter(map(canonical, main.get(table, [])))
        previous = Counter(map(canonical, backup.get(table, [])))
        row = {'main_rows': sum(current.values()), 'backup_rows': sum(previous.values()),
               'equal_multiset_rows': sum((current & previous).values()),
               'main_only_rows': sum((current - previous).values()), 'backup_only_rows': sum((previous - current).values())}
        if main_metadata is not None and backup_metadata is not None:
            ma, mb = main_metadata.get(table, {}), backup_metadata.get(table, {})
            def count(metadata):
                value = metadata.get('reported_rows')
                return value if type(value) is int and value >= 0 else None
            row.update({'same_schema': ma.get('columns') == mb.get('columns'),
                        'main_reported_rows': count(ma), 'backup_reported_rows': count(mb)})
        table_counts[table] = row
    mg, bg = groups(main.get('DETALLE', [])), groups(backup.get('DETALLE', []))
    conflicts = {identity: rows for identity, rows in mg.items()
                 if len({row.get('FECHAFACTURA') for row in rows if not blank(row.get('FECHAFACTURA'))}) > 1}
    date_comparison = Counter()
    for identity, rows in conflicts.items():
        previous = bg.get(identity, [])
        dates = {row.get('FECHAFACTURA') for row in previous if not blank(row.get('FECHAFACTURA'))}
        date_comparison['absent_backup' if not previous else 'already_ambiguous_backup' if len(dates) > 1 else 'single_date_backup'] += 1
        date_comparison['exact_same_line_multiset'] += bool(previous) and Counter(map(canonical, rows)) == Counter(map(canonical, previous))
    return {'format': 'canamo-access-comparison-sanitized-v1', 'tables': table_counts,
            'main': structural(main), 'backup': structural(backup), 'snapshot_2004': snapshot_summary(main, backup),
            'incomplete_customer_recovery': incomplete_customer_recovery(main, backup),
            'incomplete_line_candidates': line_recovery_candidates(main, backup),
            'date_ranges': {'main': date_summary(main.get('DETALLE', [])), 'backup': date_summary(backup.get('DETALLE', [])),
                            'snapshot_2004': date_summary(main.get('Detalle 2004', []))},
            'backup_customer_keys_absent_main': len(groups(backup.get('Clientes', []), ('Cod_cli',)).keys() - groups(main.get('Clientes', []), ('Cod_cli',)).keys()),
            'shared_plates': plate_summary(main, backup), 'ambiguous_dates': dict(sorted(date_comparison.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main_directory', type=Path)
    parser.add_argument('backup_directory', type=Path)
    args = parser.parse_args()
    try:
        current, current_meta = load(args.main_directory)
        previous, previous_meta = load(args.backup_directory)
        result = compare(current, previous, current_meta, previous_meta)
    except (AppError, OSError, ValueError, TypeError, KeyError, RecursionError):
        # Never echo an exception: source values and paths are private.
        raise SystemExit('No se pudo comparar la extracción local; comprueba manifiesto, archivos y esquema.')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
