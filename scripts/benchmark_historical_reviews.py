#!/usr/bin/env python3
"""Benchmark historical review lists in a disposable, exclusively synthetic database."""
import argparse
from contextlib import contextmanager
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from taller.app import App
from taller.db import dumps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', type=int, default=5000)
    parser.add_argument('--iterations', type=int, default=60)
    args = parser.parse_args()
    if not 100 <= args.documents <= 50000 or not 10 <= args.iterations <= 1000:
        parser.error('Use 100–50000 documents and 10–1000 iterations.')
    with tempfile.TemporaryDirectory(prefix='canamo-synthetic-history-') as directory:
        app = App(Path(directory) / 'data')
        customer = app.contacts.save_customer({'name': 'Cliente sintético de rendimiento'})
        line = {'description': 'Trabajo sintético', 'quantity': '1', 'unit_price': '100.004',
                'amount_raw': '100.004', 'base_cents': None, 'tax_cents': None,
                'total_cents': None, 'tax_rate': None, 'tax_kind': 'historical'}
        payload = {'historical': True, 'preservation': 'partial', 'date_state': 'known',
                   'payment_state': 'unknown', 'base_cents': None, 'tax_cents': None,
                   'total_cents': None, 'lines': [line] * 6, 'taxes': [],
                   'amounts_provenance': {'policy': 'source_only_no_rounding', 'line_amount': 'unclassified'},
                   'customer': {}, 'issuer': {}, 'branding': {}}
        with app.db.transaction() as conn:
            for index in range(args.documents):
                value = payload if index % 17 else {**payload, 'lines': []}
                conn.execute('''INSERT INTO documents
                    (id,kind,status,customer_id,issue_date,full_number,payload,base_cents,tax_cents,total_cents,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,?,?)''',
                    (f'synthetic-{index}', 'invoice', 'historical', customer['id'],
                     '2012-09-01', f'BENCH-{index:06}', dumps(value), '2026-01-01', '2026-01-01'))
        # Includes lazy population, if the implementation uses it; measured reads
        # have the same state as a normal application after its initial migration.
        start = time.perf_counter_ns()
        app.documents.list()
        initialization_ms = (time.perf_counter_ns() - start) / 1e6
        cases = {
            'first_page': lambda: app.documents.list(),
            'page_10': lambda: app.documents.list(page=10),
            'pending_review': lambda: app.documents.list(review_state='pending_review'),
            'estimated': lambda: app.documents.list(review_state='estimated'),
            'number_filter': lambda: app.documents.list(query='BENCH-000'),
            'detail': lambda: app.documents.get('synthetic-1'),
        }
        results = {}
        for name, operation in cases.items():
            for _ in range(5):
                operation()
            samples = []
            for _ in range(args.iterations):
                start = time.perf_counter_ns()
                answer = operation()
                samples.append((time.perf_counter_ns() - start) / 1e6)
            ordered = sorted(samples)
            results[name] = {
                'median_ms': round(statistics.median(samples), 3),
                'p95_ms': round(ordered[(len(ordered) * 95 + 99) // 100 - 1], 3),
                'max_ms': round(max(samples), 3),
                'count': answer.get('total', 1),
            }
        statements = []
        original_read = app.db.read

        @contextmanager
        def traced_read():
            with original_read() as conn:
                conn.set_trace_callback(statements.append)
                try:
                    yield conn
                finally:
                    conn.set_trace_callback(None)

        app.db.read = traced_read
        try:
            app.documents.list(review_state='pending_review')
        finally:
            app.db.read = original_read
        with app.db.read() as conn:
            plans = [[row[3] for row in conn.execute('EXPLAIN QUERY PLAN '+sql)]
                     for sql in statements if sql.startswith(('SELECT count(*)', 'SELECT d.id,'))]
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
            assert conn.execute('SELECT count(*) FROM documents WHERE total_cents IS NOT NULL').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM fiscal_records').fetchone()[0] == 0
            assert conn.execute('SELECT count(*) FROM payments').fetchone()[0] == 0
            state_counts = dict(conn.execute('SELECT state,count(*) FROM historical_review_current GROUP BY state'))
            line_count = sum(len(json.loads(row[0])['lines']) for row in conn.execute('SELECT payload FROM documents'))
        print(json.dumps({'synthetic_documents': args.documents, 'synthetic_lines': line_count,
                          'initialization_ms': round(initialization_ms, 3), 'states': state_counts,
                          'pending_filter_query_plans': plans, 'warmup': 5,
                          'iterations': args.iterations, 'results': results}, indent=2))


if __name__ == '__main__':
    main()
