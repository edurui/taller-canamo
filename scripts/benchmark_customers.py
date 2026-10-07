"""Private, reproducible customers.list benchmark with aggregate-only evidence.

Never initialize Database/App on real data: real SQLite is opened mode=ro,
immutable=1, query_only=ON, with no WAL accepted. Candidate schema changes happen
only in mode-0700 temporary copies. Query values, IDs and result rows never leave
memory. Baseline source is frozen from a local Git commit before implementation.
"""
import argparse
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from uuid import UUID
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from taller.db import Database
from taller.migrations import LATEST_VERSION
from taller.validation import normalized, plate

FIELDS = 'c.id,c.name,c.city,c.phone,c.tax_id,c.legacy_code'
PLATES = "(SELECT group_concat(v.plate, ', ') FROM vehicles v WHERE v.customer_id=c.id AND v.archived=0) AS plates"
LAST_VISIT = "(SELECT max(d.issue_date) FROM documents d WHERE d.customer_id=c.id AND d.kind='invoice') AS last_visit"


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def connect(path, mutable=False):
    if not mutable and Path(str(path) + '-wal').exists() and Path(str(path) + '-wal').stat().st_size:
        raise RuntimeError('Non-empty WAL: close the application before benchmarking; no checkpoint is attempted.')
    conn = sqlite3.connect(str(path) if mutable else Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=not mutable)
    conn.row_factory = sqlite3.Row
    conn.create_function('normalized', 1, normalized, deterministic=True)
    if not mutable:
        conn.execute('PRAGMA query_only=ON')
    return conn


class ReadOnlyDatabase:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def read(self):
        conn = connect(self.path)
        try:
            yield conn
        finally:
            conn.close()


class MeteredCursor:
    def __init__(self, cursor, started, timings, label):
        self.cursor, self.started, self.timings, self.label = cursor, started, timings, label

    def finish(self):
        self.timings[self.label] += (time.perf_counter() - self.started) * 1000

    def fetchone(self):
        result = self.cursor.fetchone()
        self.finish()
        return result

    def __iter__(self):
        yield from self.cursor
        self.finish()

    def fetchall(self):
        return list(self)


class MeteredDatabase(ReadOnlyDatabase):
    def __init__(self, path):
        super().__init__(path)
        self.timings = Counter()

    @contextmanager
    def read(self):
        with super().read() as conn:
            timings = self.timings
            class Proxy:
                def execute(self, sql, params=()):
                    started = time.perf_counter()
                    cursor = conn.execute(sql, params)
                    label = 'count_ms' if sql.lstrip().lower().startswith('select count(') else 'rows_ms'
                    return MeteredCursor(cursor, started, timings, label)
            yield Proxy()


def execute_service(contacts, query, page):
    contacts.db.timings.clear()
    started = time.perf_counter()
    result = contacts.list_customers(query=query, page=page)
    elapsed = (time.perf_counter() - started) * 1000
    return {'rows': result['items'], 'total': result['total']}, {
        'count_ms': contacts.db.timings['count_ms'], 'rows_ms': contacts.db.timings['rows_ms'], 'total_ms': elapsed}


def table_counts(path):
    with closing(connect(path)) as conn:
        names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: conn.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in sorted(names)}


def validate_synthetic_fixture(path, customers, documents):
    """Accept an existing complete fixture, never silently resize or reseed it."""
    error = 'Synthetic fixture is incomplete or differs from the requested dimensions/metadata; use a new private --work directory.'
    metadata_path = path.with_name('benchmark-fixture.json')
    metadata = {'generator_version': 1, 'customers': customers, 'vehicles': customers * 2,
                'documents': documents, 'schema_version': LATEST_VERSION}
    try:
        with closing(connect(path)) as conn:
            counts = {table: conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                      for table in ('customers', 'vehicles', 'documents')}
            complete = (
                all(counts[table] == metadata[table] for table in counts)
                and conn.execute('PRAGMA user_version').fetchone()[0] == LATEST_VERSION
                and conn.execute('SELECT count(*) FROM customers WHERE archived=0').fetchone()[0] == customers
                and conn.execute('SELECT count(*) FROM vehicles WHERE archived=0').fetchone()[0] == customers * 2
                and conn.execute("SELECT count(*) FROM documents WHERE kind='invoice' AND status='historical'").fetchone()[0] == documents
                and conn.execute('SELECT 1 FROM customers c WHERE (SELECT count(*) FROM vehicles v WHERE v.customer_id=c.id)<>2 LIMIT 1').fetchone() is None
                and conn.execute('PRAGMA foreign_key_check').fetchone() is None)
        if not complete:
            raise RuntimeError(error)
        metadata['database_sha256'] = digest(path)
        if metadata_path.exists():
            if json.loads(metadata_path.read_text()) != metadata:
                raise RuntimeError(error)
        else:
            # Older complete fixtures predate this manifest. Validate them first,
            # then record provenance without modifying the SQLite file.
            pending = metadata_path.with_suffix('.json.tmp')
            pending.write_text(json.dumps(metadata, sort_keys=True, indent=2) + '\n')
            pending.replace(metadata_path)
    except (sqlite3.Error, OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, RuntimeError) and str(exc) == error:
            raise
        raise RuntimeError(error) from exc


def prepare(work, baseline_ref, customers, documents):
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    work.chmod(0o700)
    baseline = work / 'baseline_contacts.py'
    code = subprocess.run(['git', 'show', baseline_ref + ':backend/taller/contacts.py'], cwd=ROOT,
                          check=True, capture_output=True).stdout
    if baseline.exists():
        if baseline.read_bytes() != code:
            raise RuntimeError('Frozen baseline differs from the requested Git reference; use a new private work directory.')
    else:
        baseline.write_bytes(code)
    path = work / 'synthetic' / 'taller.sqlite3'
    if not path.exists():
        if path.with_name('benchmark-fixture.json').exists():
            raise RuntimeError('Synthetic fixture database is missing; use a new private --work directory.')
        db = Database(path.parent)
        stamp = '2026-10-06T12:00:00+00:00'
        with db.transaction() as conn:
            for index in range(customers):
                identifier = str(UUID(int=index + 1))
                # Deliberately not inserted in alphabetical order; include accents.
                name = f'Cliente Sintético Álvarez {(index * 7919) % customers:06d}'
                code = f'SYN{index:08d}'
                phone = str(600000000 + index)
                conn.execute('INSERT INTO customers(id,legacy_code,name,phone,search_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                             (identifier, code, name, phone, normalized(' '.join([name, code, phone])), stamp, stamp))
                for car in range(2):
                    number = index * 2 + car
                    registration = f'{number % 10000:04d}{chr(65 + number // 10000)}BC'
                    conn.execute('INSERT INTO vehicles(id,customer_id,plate,plate_normalized,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                                 (str(UUID(int=200001 + number)), identifier, registration, registration, stamp, stamp))
            conn.executemany('INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,base_cents,tax_cents,total_cents,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                             ((str(UUID(int=1000001 + i)), 'invoice', 'historical', str(UUID(int=i % customers + 1)),
                              f'{2004 + i % 23:04d}-{1 + i % 12:02d}-{1 + i % 28:02d}', f'SYN-{i}', '{}', None, None, None, stamp, stamp)
                              for i in range(documents)))
    validate_synthetic_fixture(path, customers, documents)
    return path, baseline


def where(query, membership=False):
    query = normalized(query)[:100]
    condition, params = 'c.archived=?', [0]
    if query:
        escape = lambda value: value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        if membership:
            condition += " AND (c.search_text LIKE ? ESCAPE '\\' OR c.id IN(SELECT vv.customer_id FROM vehicles vv WHERE vv.plate_normalized LIKE ? ESCAPE '\\'))"
        else:
            condition += " AND (c.search_text LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM vehicles vv WHERE vv.customer_id=c.id AND vv.plate_normalized LIKE ? ESCAPE '\\'))"
        params.extend(['%' + escape(query) + '%', '%' + escape(plate(query)) + '%'])
    return condition, params


def queries(path, pages=(0, 2), filters=('exact', 'partial')):
    with closing(connect(path)) as conn:
        name = conn.execute('SELECT name FROM customers WHERE archived=0 ORDER BY normalized(name) LIMIT 1 OFFSET 25').fetchone()[0]
        registration = conn.execute('SELECT plate FROM vehicles WHERE archived=0 ORDER BY id LIMIT 1').fetchone()[0]
    cases = [('first_page' if page == 0 else 'page_' + str(page), '', page) for page in pages]
    if 'exact' in filters:
        cases.extend([('name', name, 0), ('plate', registration, 0)])
    if 'partial' in filters:
        words = [word for word in re.findall(r'[^\W_]+', normalized(name)) if len(word) >= 4]
        if not words or len(plate(registration)) < 5:
            raise RuntimeError('Selected private fixture has no valid four-character partial query.')
        word = words[0]
        name_partial = word[1:5] if len(word) > 4 else word[:4]
        cases.extend([('name_partial', name_partial, 0), ('plate_partial', plate(registration)[1:5], 0)])
    cases.append(('no_result', 'ZZQBENCHMARKNOMATCH847291', 0))
    return cases


def statements(variant, query, page):
    condition, params = where(query, variant == 'page_then_plates_in')
    count = 'SELECT count(*) FROM customers c WHERE ' + condition
    sort = 'c.benchmark_sort_name' if variant == 'column_index' else 'normalized(c.name)'
    projection = 'c.*,' + PLATES + ',' + LAST_VISIT if variant == 'baseline' else FIELDS + ',' + PLATES
    if variant in ('page_then_plates', 'page_then_plates_in'):
        projection = FIELDS
    rows = 'SELECT ' + projection + ' FROM customers c WHERE ' + condition + ' ORDER BY ' + sort + ' LIMIT 50 OFFSET ?'
    if variant == 'paged_correlated':
        rows = 'SELECT ' + FIELDS + ',' + PLATES + ' FROM (SELECT ' + FIELDS + ',normalized(c.name) AS _sort,c.rowid AS _rowid FROM customers c WHERE ' + condition + ' ORDER BY normalized(c.name) LIMIT 50 OFFSET ?) c ORDER BY c._sort,c._rowid'
    return count, rows, params, [*params, max(0, page) * 50]


def execute(path, variant, query, page):
    start = time.perf_counter()
    count_sql, row_sql, count_params, row_params = statements(variant, query, page)
    with closing(connect(path)) as conn:
        at_count = time.perf_counter()
        total = conn.execute(count_sql, count_params).fetchone()[0]
        after_count = time.perf_counter()
        rows = [dict(row) for row in conn.execute(row_sql, row_params)]
        if variant in ('page_then_plates', 'page_then_plates_in') and rows:
            ids = [row['id'] for row in rows]
            plates = {row[0]: row[1] for row in conn.execute("SELECT customer_id,group_concat(plate, ', ') FROM vehicles WHERE archived=0 AND customer_id IN (" + ','.join('?' for _ in ids) + ') GROUP BY customer_id', ids)}
            for row in rows:
                row['plates'] = plates.get(row['id'])
        ended = time.perf_counter()
    closed = time.perf_counter()
    return {'rows': rows, 'total': total}, {'count_ms': (after_count - at_count) * 1000,
                                         'rows_ms': (ended - after_count) * 1000,
                                         'total_ms': (closed - start) * 1000}


def summary(samples):
    return {'median_ms': round(statistics.median(samples), 3),
            'p95_ms': round(sorted(samples)[math.ceil(len(samples) * .95) - 1], 3),
            'max_ms': round(max(samples), 3)}


def plans(path, variant, query, page):
    count, rows, cp, rp = statements(variant, query, page)
    with closing(connect(path)) as conn:
        result = {label: [row['detail'] for row in conn.execute('EXPLAIN QUERY PLAN ' + sql, params)]
                  for label, sql, params in [('count', count, cp), ('rows', rows, rp)]}
        if variant in ('page_then_plates', 'page_then_plates_in'):
            result['plates_for_page'] = [row['detail'] for row in conn.execute("EXPLAIN QUERY PLAN SELECT customer_id,group_concat(plate, ', ') FROM vehicles WHERE archived=0 AND customer_id IN (?) GROUP BY customer_id", ('synthetic-placeholder',))]
    return result


def operation_counts(path, variant, query, page):
    """Instrument only returned scalar values; never record their contents."""
    calls = Counter()
    def normalization(value):
        calls['normalized_name_calls'] += 1
        return normalized(value)
    def registration(value):
        calls['vehicle_plates_aggregated'] += 1
        return value
    _, sql, _, params = statements(variant, query, page)
    with closing(connect(path)) as conn:
        conn.create_function('normalized', 1, normalization, deterministic=True)
        conn.create_function('benchmark_plate', 1, registration)
        sql = sql.replace("group_concat(v.plate, ', ')", "group_concat(benchmark_plate(v.plate), ', ')")
        rows = list(conn.execute(sql, params))
        if variant in ('page_then_plates', 'page_then_plates_in') and rows:
            ids = [row['id'] for row in rows]
            list(conn.execute("SELECT customer_id,group_concat(benchmark_plate(plate), ', ') FROM vehicles WHERE archived=0 AND customer_id IN (" + ','.join('?' for _ in ids) + ') GROUP BY customer_id', ids))
    return dict(calls)


def fingerprint_results(result):
    # In-memory comparison only: even hashes of individual private rows are not reported.
    keys = ['id', 'name', 'city', 'phone', 'tax_id', 'legacy_code', 'plates']
    return {'total': result['total'], 'items': [{key: row.get(key) for key in keys} for row in result['rows']]}


def measure(path, variant, cases, repeats, warmup, expected, baseline_source):
    measurements = []
    baseline = source_class(baseline_source)(MeteredDatabase(path)) if variant == 'baseline' else None
    for label, query, page in cases:
        result = None
        for _ in range(warmup):
            result, _ = execute_service(baseline, query, page) if baseline else execute(path, variant, query, page)
        values = {key: [] for key in ['count_ms', 'rows_ms', 'total_ms']}
        for _ in range(repeats):
            result, times = execute_service(baseline, query, page) if baseline else execute(path, variant, query, page)
            for key in values:
                values[key].append(times[key])
        if label not in expected:
            expected[label] = fingerprint_results(result)
        if fingerprint_results(result) != expected[label]:
            raise RuntimeError('Candidate output differs from baseline; no private rows are printed.')
        measurements.append({'case': label, 'page': page, 'matching_customers': result['total'],
                             'returned_rows': len(result['rows']),
                             'payload_bytes': len(json.dumps(result['rows'], ensure_ascii=False).encode()),
                             **{key: summary(value) for key, value in values.items()}, 'plan': plans(path, variant, query, page),
                             'operation_counts': operation_counts(path, variant, query, page)})
        print(json.dumps({'phase': 'measured', 'variant': variant, 'case': label,
                          'median_ms': measurements[-1]['total_ms']['median_ms']}), flush=True)
    return measurements


def candidate_copy(source, destination, variant):
    if destination.exists():
        destination.unlink()  # Only tool-owned disposable candidate copies.
    shutil.copyfile(source, destination)
    with closing(connect(destination, mutable=True)) as conn, conn:
        conn.execute('PRAGMA journal_mode=DELETE')
        if variant == 'expression_index':
            conn.execute('CREATE INDEX benchmark_customer_order ON customers(archived,normalized(name))')
        elif variant == 'column_index':
            conn.execute('ALTER TABLE customers ADD COLUMN benchmark_sort_name TEXT')
            conn.execute('UPDATE customers SET benchmark_sort_name=normalized(name)')
            conn.execute('CREATE INDEX benchmark_customer_order ON customers(archived,benchmark_sort_name)')
    return destination


def source_class(path):
    spec = importlib.util.spec_from_file_location('taller._customers_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Contacts


def service_measure(path, source, cases, repeats, warmup, expected):
    contacts = source_class(source)(MeteredDatabase(path))
    measurements = []
    for label, query, page in cases:
        for _ in range(warmup):
            execute_service(contacts, query, page)
        times = {key: [] for key in ('count_ms', 'rows_ms', 'total_ms')}
        for _ in range(repeats):
            result, durations = execute_service(contacts, query, page)
            for key in times:
                times[key].append(durations[key])
        if fingerprint_results(result) != expected[label]:
            raise RuntimeError('Current service differs from measured reference; private results are not printed.')
        measurements.append({'case': label, 'page': page, 'matching_customers': result['total'], 'returned_rows': len(result['rows']),
                             'payload_bytes': len(json.dumps(result['rows'], ensure_ascii=False).encode()),
                             **{key: summary(value) for key, value in times.items()}})
    return measurements


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--real-data', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='388cb2a')
    parser.add_argument('--customers', type=int, default=15000)
    parser.add_argument('--documents', type=int, default=60000)
    parser.add_argument('--samples', type=int, default=15)
    parser.add_argument('--service-samples', type=int)
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--variants', default='baseline,no_last_visit,page_then_plates,paged_correlated,expression_index,column_index')
    parser.add_argument('--service-after', action='store_true')
    parser.add_argument('--pages', default='0,2')
    parser.add_argument('--filters', default='exact,partial', help='Comma-separated exact/partial filters; --pages "" measures only filters.')
    args = parser.parse_args()
    if args.samples < 3 or args.warmup < 1 or args.customers < 15000 or args.documents < 50000:
        parser.error('At least 3 samples, 1 warmup, 15,000 customers and 50,000 historical documents are required.')
    if args.service_samples is not None and args.service_samples < 3:
        parser.error('At least 3 service samples are required.')
    filters = tuple(args.filters.split(','))
    if any(kind not in ('exact', 'partial') for kind in filters):
        parser.error('Filters must be exact and/or partial.')
    if args.real_data:
        real_root = args.real_data.resolve()
        for writable in (args.work.resolve(), args.report.resolve()):
            if writable == real_root or real_root in writable.parents:
                parser.error('Work and report destinations must be outside real data.')
    os.umask(0o077)
    synthetic, baseline_source = prepare(args.work.resolve(), args.baseline_ref, args.customers, args.documents)
    if args.prepare_only:
        print(json.dumps({'prepared': True, 'synthetic_counts': table_counts(synthetic), 'baseline_source_sha256': digest(baseline_source)}))
        return
    datasets = [('synthetic', synthetic)]
    if args.real_data:
        real = args.real_data.resolve() / 'taller.sqlite3'
        if real == synthetic or args.work.resolve() == args.real_data.resolve() or args.real_data.resolve() in args.work.resolve().parents:
            raise RuntimeError('Work must be outside real data.')
        datasets.insert(0, ('real_private_readonly', real))
    output = {'started_at': datetime.now(ZoneInfo('Europe/Madrid')).isoformat(),
              'baseline_commit': args.baseline_ref, 'baseline_source_sha256': digest(baseline_source),
              'current_source_sha256': digest(ROOT / 'backend/taller/contacts.py'),
              'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                              'os': platform.platform(), 'cpu_count': os.cpu_count()},
              'samples': args.samples, 'warmup': args.warmup,
              'current_service_samples': args.service_samples or args.samples,
              'filter_kinds': filters,
              'payload_scope': 'JSON UTF-8 array of returned customer rows, without envelope, measured identically in baseline and current service.',
              'scope': 'Local Python/SQLite; fresh immutable read-only connection per request. No HTTP or UI. Query values and rows remain private.',
              'expression_index_warning': 'Experimental copy only: Python UDF expression index is incompatible with trusted_schema=OFF integrity validation without an innocuous UDF; not a deployable recommendation.',
              'datasets': {}}
    variants = args.variants.split(',')
    if any(variant not in ('baseline', 'no_last_visit', 'page_then_plates', 'page_then_plates_in', 'paged_correlated', 'expression_index', 'column_index') for variant in variants):
        raise RuntimeError('Unknown benchmark variant.')
    for label, path in datasets:
        before = digest(path)
        counts = table_counts(path)
        cases = queries(path, tuple(int(value) for value in args.pages.split(',') if value), filters)
        result = {'counts_before': counts, 'source_sha256_before': before, 'variants': {}}
        expected = {}
        for variant in variants:
            source = candidate_copy(path, args.work / (label + '-' + variant + '.sqlite3'), variant) if variant.endswith('_index') else path
            result['variants'][variant] = measure(source, variant, cases, args.samples, args.warmup, expected, baseline_source)
        if args.service_after:
            result['current_service'] = service_measure(path, ROOT / 'backend/taller/contacts.py', cases, args.service_samples or args.samples, args.warmup, expected)
        result['counts_after'] = table_counts(path)
        result['source_sha256_after'] = digest(path)
        result['original_unchanged'] = result['source_sha256_after'] == before and result['counts_after'] == counts
        if not result['original_unchanged']:
            raise RuntimeError('Original changed during benchmark; results rejected.')
        output['datasets'][label] = result
        output['finished_at'] = datetime.now(ZoneInfo('Europe/Madrid')).isoformat()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report_complete': True, 'originals_unchanged': True, 'datasets': len(datasets)}))


if __name__ == '__main__':
    main()
