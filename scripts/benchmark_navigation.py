"""Measure customer vehicle-reference payloads without exposing private values.

Reuses the read-only adapters and complete synthetic fixture from the customer
benchmark. Reports timings, sizes, counts and query-plan details only.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import sqlite3
import time

from benchmark_customers import (
    ROOT, MeteredDatabase, ReadOnlyDatabase, digest, fingerprint_results,
    prepare, queries, source_class, summary, table_counts,
)


class PlannedDatabase(ReadOnlyDatabase):
    def __init__(self, path):
        super().__init__(path)
        self.plans = []

    @contextmanager
    def read(self):
        with super().read() as conn:
            class Proxy:
                def execute(inner, sql, params=()):
                    self.plans.append([row['detail'] for row in conn.execute('EXPLAIN QUERY PLAN ' + sql, params)])
                    return conn.execute(sql, params)
            yield Proxy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--real-data', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='6be3445')
    parser.add_argument('--samples', type=int, default=31)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.samples < 3:
        parser.error('At least three samples are required.')
    root = args.real_data.resolve()
    for destination in (args.work.resolve(), args.report.resolve()):
        if destination == root or root in destination.parents:
            parser.error('Work and report must be outside real data.')
    os.umask(0o077)
    synthetic, baseline = prepare(args.work.resolve(), args.baseline_ref, 15000, 60000)
    if args.prepare_only:
        print(json.dumps({'prepared': True, 'counts': table_counts(synthetic)}))
        return
    report = {
        'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
        'samples': args.samples, 'warmup': 3,
        'baseline_ref': args.baseline_ref, 'baseline_sha256': digest(baseline),
        'current_sha256': digest(ROOT / 'backend/taller/contacts.py'),
        'scope': 'Fresh immutable read-only connection per request; includes SQL, dictionaries and close; excludes HTTP/UI and connection PRAGMAs.',
        'datasets': {},
    }
    for label, path in [('private_readonly', root / 'taller.sqlite3'), ('synthetic', synthetic)]:
        before = digest(path)
        counts = table_counts(path)
        results = []
        for case, query, page in queries(path, (0, 10), ('partial',)):
            entry = {'case': case, 'page': page}
            expected = None
            for version, source in [('before', baseline), ('after', ROOT / 'backend/taller/contacts.py')]:
                contacts = source_class(source)(MeteredDatabase(path))
                for _ in range(3):
                    contacts.list_customers(query=query, page=page)
                durations, count_durations = [], []
                for _ in range(args.samples):
                    contacts.db.timings.clear()
                    started = time.perf_counter()
                    response = contacts.list_customers(query=query, page=page)
                    durations.append((time.perf_counter() - started) * 1000)
                    count_durations.append(contacts.db.timings['count_ms'])
                comparable = fingerprint_results({'total': response['total'], 'rows': response['items']})
                if expected is None:
                    expected = comparable
                elif comparable != expected:
                    raise RuntimeError('Customer rows/order/count changed; private rows are not printed.')
                if version == 'after':
                    assert all((', '.join(v['plate'] for v in row['vehicles']) or None) == row['plates'] for row in response['items'])
                planned = PlannedDatabase(path)
                source_class(source)(planned).list_customers(query=query, page=page)
                entry[version] = {
                    'duration': summary(durations), 'count': summary(count_durations),
                    'matches': response['total'], 'rows': len(response['items']),
                    'payload_bytes': len(json.dumps(response, ensure_ascii=False).encode()),
                    'plans': planned.plans,
                }
            results.append(entry)
        if digest(path) != before or table_counts(path) != counts:
            raise RuntimeError('Original changed during measurement; report rejected.')
        report['datasets'][label] = {'counts': counts, 'original_unchanged': True, 'cases': results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report_complete': True, 'datasets': len(report['datasets']), 'originals_unchanged': True}))


if __name__ == '__main__':
    main()
