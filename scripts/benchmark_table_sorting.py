#!/usr/bin/env python3
"""Synthetic, disposable benchmarks for global table ordering; no workshop files."""
import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from taller.app import App
from taller.db import dumps


def paid_balances(iterations):
    """Worst-case balance ordering includes a recorded receipt on each invoice."""
    with tempfile.TemporaryDirectory(prefix='canamo-synthetic-balances-') as directory:
        app = App(Path(directory))
        customer = app.contacts.save_customer({'name': 'Cliente sintético'})
        with app.db.transaction() as conn:
            for index in range(1500):
                conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
                    base_cents,tax_cents,total_cents,created_at,updated_at)
                    VALUES(?,'invoice','issued',?,'2020-01-01',?,'{}',10000,2100,12100,'2020-01-01','2020-01-01')''',
                    (f'd{index}', customer['id'], f'SYN{index}'))
                conn.execute("INSERT INTO payments VALUES(?,?,?,'cash','2020-01-01','',NULL,?,'2020-01-01')",
                             (f'p{index}', f'd{index}', index, f'key{index}'))
        for _ in range(5):
            app.documents.list(sort_by='pending_cents')
        samples = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            result = app.documents.list(sort_by='pending_cents')
            samples.append((time.perf_counter_ns()-start)/1e6)
        assert result['items'][0]['id'] == 'd1499'
        statements = []
        connect = app.db.connect
        def traced_connect():
            conn = connect(); conn.set_trace_callback(statements.append); return conn
        app.db.connect = traced_connect
        try:
            app.documents.list(sort_by='pending_cents')
        finally:
            app.db.connect = connect
        with app.db.read() as conn:
            plan = [[row[3] for row in conn.execute('EXPLAIN QUERY PLAN '+sql)]
                    for sql in statements if ' LIMIT 50 OFFSET ' in sql]
        return {'documents': 1500, 'payments': 1500, 'median_ms': round(statistics.median(samples), 3),
                'p95_ms': round(sorted(samples)[(iterations*95+99)//100-1], 3),
                'max_ms': round(max(samples), 3), 'plans': plan}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--customers', type=int, default=1600)
    parser.add_argument('--documents', type=int, default=5000)
    parser.add_argument('--iterations', type=int, default=30)
    parser.add_argument('--before', action='store_true')
    args = parser.parse_args()
    if not 100 <= args.customers <= 30000 or not 100 <= args.documents <= 60000 or not 10 <= args.iterations <= 1000:
        parser.error('Use 100–30000 customers, 100–60000 documents and 10–1000 iterations.')
    with tempfile.TemporaryDirectory(prefix='canamo-synthetic-sorting-') as directory:
        app = App(Path(directory) / 'data')
        with app.db.transaction() as conn:
            for index in range(args.customers):
                conn.execute('INSERT INTO customers(id,name,city,phone,tax_id,search_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                             (f'c{index:06}', f'Cliente sintético {args.customers-index:06}', 'Ciudad sintética',
                              f'{index:09}', f'SYN{index:09}', f'sintetico {index}', '2026-01-01', '2026-01-01'))
                for vehicle in range(2):
                    plate = f'SYN{index:06}{vehicle}'
                    conn.execute('INSERT INTO vehicles(id,customer_id,plate,plate_normalized,make,model,km,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                                 (f'v{index:06}-{vehicle}', f'c{index:06}', plate, plate, 'Marca sintética',
                                  f'Modelo {index%10}', index*10, '2026-01-01', '2026-01-01'))
            for index in range(args.documents):
                payload = dumps({'historical': True, 'preservation': 'partial', 'date_state': 'known',
                                 'payment_state': 'unknown', 'lines': [{'amount_raw': str(index%1000)}] if index%17 else [],
                                 'customer': {}, 'vehicle': None, 'taxes': []})
                conn.execute('''INSERT INTO documents(id,kind,status,customer_id,issue_date,full_number,payload,
                    base_cents,tax_cents,total_cents,created_at,updated_at)
                    VALUES(?,'invoice','historical',?,?,?,?,NULL,NULL,NULL,?,?)''',
                             (f'd{index:06}', f'c{index%args.customers:06}', f'2020-{index%12+1:02}-15',
                              f'SYN-{args.documents-index:06}', payload, '2026-01-01', '2026-01-01'))
        app.documents.list()  # Imported/migrated review projection is ready before measuring reads.
        cases = {'customers_default': lambda: app.contacts.list_customers(),
                 'vehicles_default': lambda: app.contacts.vehicles_page(),
                 'documents_default': lambda: app.documents.list()}
        if not args.before:
            cases.update(customers_name=lambda: app.contacts.list_customers(sort_by='name'),
                         customers_plates=lambda: app.contacts.list_customers(sort_by='plates'),
                         vehicles_description=lambda: app.contacts.vehicles_page(sort_by='description'),
                         documents_total=lambda: app.documents.list(sort_by='total_cents'),
                         documents_customer=lambda: app.documents.list(sort_by='customer_name'),
                         documents_pending=lambda: app.documents.list(sort_by='pending_cents'))
        results = {}
        for name, operation in cases.items():
            for _ in range(5):
                operation()
            samples = []
            for _ in range(args.iterations):
                start = time.perf_counter_ns()
                answer = operation()
                samples.append((time.perf_counter_ns()-start)/1e6)
            statements = []
            connect = app.db.connect
            def traced_connect():
                conn = connect(); conn.set_trace_callback(statements.append); return conn
            app.db.connect = traced_connect
            try:
                operation()
            finally:
                app.db.connect = connect
            with app.db.read() as conn:
                conn.create_function('normalized_plate', 1, lambda value: ''.join(c for c in (value or '').upper() if c.isalnum()))
                plans = [[row[3] for row in conn.execute('EXPLAIN QUERY PLAN '+sql)]
                         for sql in statements if ' LIMIT 50 OFFSET ' in sql]
            results[name] = {'median_ms': round(statistics.median(samples), 3),
                'p95_ms': round(sorted(samples)[(args.iterations*95+99)//100-1], 3),
                'max_ms': round(max(samples), 3), 'total': answer['total'], 'plans': plans}
        with app.db.read() as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
            assert conn.execute('SELECT count(*) FROM documents WHERE total_cents IS NOT NULL').fetchone()[0] == 0
        print(json.dumps({'customers': args.customers, 'vehicles': args.customers*2,
                          'documents': args.documents, 'warmup': 5, 'iterations': args.iterations,
                          'results': results,
                          'paid_balance_sort': None if args.before else paid_balances(args.iterations)}, indent=2))


if __name__ == '__main__':
    main()
