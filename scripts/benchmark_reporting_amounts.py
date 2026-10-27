#!/usr/bin/env python3
"""Measure consultation reports using disposable synthetic invoice databases only."""
import argparse
import json
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from taller.app import App
from taller.db import dumps


def measure(operation, iterations):
    for _ in range(5):
        operation()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - start) / 1e6)
    return {'median_ms': round(statistics.median(samples), 3),
            'p95_ms': round(sorted(samples)[(iterations * 95 + 99) // 100 - 1], 3),
            'max_ms': round(max(samples), 3)}


def benchmark(count, iterations):
    with tempfile.TemporaryDirectory(prefix='canamo-synthetic-reporting-') as directory:
        app = App(Path(directory) / 'data')
        customer = app.contacts.save_customer({'name': 'Cliente sintético de rendimiento'})
        line = {'description': 'Trabajo sintético', 'quantity': '1', 'unit_price': '100.004',
                'amount_raw': '100.004', 'base_cents': None, 'tax_cents': None, 'total_cents': None}
        payload = {'historical': True, 'preservation': 'partial', 'date_state': 'known',
                   'payment_state': 'unknown', 'lines': [line] * 6, 'taxes': [],
                   'base_cents': None, 'tax_cents': None, 'total_cents': None}
        with app.db.transaction() as conn:
            for index in range(count):
                month = index % 36
                value = payload if index % 17 else {**payload, 'lines': []}
                conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,
                    full_number,payload,base_cents,tax_cents,total_cents,created_at,updated_at)
                    VALUES(?,'invoice','historical',?,?,?,?,NULL,NULL,NULL,'2026-01-01','2026-01-01')''',
                             (f'synthetic-{index}', customer['id'],
                              f'{2020 + month // 12}-{month % 12 + 1:02}-15', f'SYN-{index}', dumps(value)))
        # The migration/import consumes this queue before normal report reads.
        start = time.perf_counter_ns()
        initial = app.reports()
        initialization_ms = (time.perf_counter_ns() - start) / 1e6
        statements = []
        connect = app.db.connect

        def traced_connect():
            conn = connect()
            conn.set_trace_callback(statements.append)
            return conn

        app.db.connect = traced_connect
        try:
            app.reports()
        finally:
            app.db.connect = connect
        query = next(command for command in statements if command.startswith('WITH amounts AS'))
        full_report = measure(app.reports, iterations)
        with app.db.read() as conn:
            aggregate = measure(lambda: conn.execute(query).fetchall(), iterations)
            # Reproducible comparison of SQLite's repeated expression expansion.
            inline_query = query.replace('WITH amounts AS MATERIALIZED', 'WITH amounts AS', 1)
            inline = measure(lambda: conn.execute(inline_query).fetchall(), iterations)
            assert [tuple(row) for row in conn.execute(query)] == [tuple(row) for row in conn.execute(inline_query)]
            plans = {name: [row[3] for row in conn.execute('EXPLAIN QUERY PLAN ' + sql)]
                     for name, sql in [('before_materialization', inline_query), ('selected', query)]}
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
            assert conn.execute('SELECT count(*) FROM documents WHERE total_cents IS NOT NULL').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM payments').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM historical_review_pending').fetchone()[0] == 0
        return {'synthetic_invoices': count, 'synthetic_lines': (count - (count + 16) // 17) * 6,
                'months': len(initial['overview_months']), 'initialization_ms': round(initialization_ms, 3),
                'totals': initial['billing_overview'], 'full_report': full_report,
                'overview_aggregate': aggregate, 'aggregate_before_materialization': inline,
                'overview_query_count': sum(command.startswith('WITH amounts AS') for command in statements),
                'query_plans': plans}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', nargs='+', type=int, default=[5000, 30000])
    parser.add_argument('--iterations', type=int, default=30)
    args = parser.parse_args()
    if not all(100 <= count <= 50000 for count in args.documents) or not 10 <= args.iterations <= 1000:
        parser.error('Use 100–50000 invoices per scenario and 10–1000 iterations.')
    print(json.dumps({'sqlite': sqlite3.sqlite_version, 'warmup': 5, 'iterations': args.iterations,
                      'scenarios': [benchmark(count, args.iterations) for count in args.documents]}, indent=2))


if __name__ == '__main__':
    main()
