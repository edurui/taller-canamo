"""Measure real SQLite customer search over a declared synthetic dataset."""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from taller.app import App
from taller.validation import normalized, now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--customers', type=int, default=15000)
    parser.add_argument('--report', default='reports/search-benchmark.json')
    args = parser.parse_args()
    if not 100<=args.customers<=100000:
        parser.error('Utiliza entre 100 y 100000 clientes sintéticos.')
    with tempfile.TemporaryDirectory(prefix='canamo-benchmark-') as folder:
        app = App(Path(folder))
        stamp = now()
        with app.db.transaction() as conn:
            for index in range(args.customers):
                identifier = str(UUID(int=index+1))
                name = f'Cliente Álvarez {index:06d}'
                code = f'{index:08d}'
                phone = str(600000000+index)
                conn.execute('INSERT INTO customers(id,legacy_code,name,phone,search_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                             (identifier,code,name,phone,normalized(' '.join([name,code,phone])),stamp,stamp))
                for car in range(2):
                    vehicle_index = index*2+car
                    plate = f'{vehicle_index%10000:04d}{chr(65+vehicle_index//10000)}BC'
                    conn.execute('INSERT INTO vehicles(id,customer_id,plate,plate_normalized,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                                 (str(UUID(int=200001+vehicle_index)),identifier,plate,plate,stamp,stamp))
        queries = ['0','cliente','alvarez','0000 abc','00000001','600000001','sin coincidencia','%','___']
        measurements = []
        for query in queries:
            app.contacts.search(query)
            values = []
            for _ in range(15):
                started = time.perf_counter()
                rows = app.contacts.search(query)
                values.append((time.perf_counter()-started)*1000)
            measurements.append({'query':query,'results':len(rows),'p50_ms':round(statistics.median(values),3),
                                 'p95_ms':round(sorted(values)[math.ceil(len(values)*.95)-1],3),'max_ms':round(max(values),3)})
        result = {'environment':{'os':platform.platform(),'python':sys.version,'cpu':platform.processor() or platform.machine(),'logical_cpus_visible':os.cpu_count()},
                  'dataset':{'customers':args.customers,'vehicles':args.customers*2,'synthetic':True},
                  'scope':'Servicio Python y SQLite real, una conexión por búsqueda. No incluye transporte ni pintado de interfaz; equipo compartido.',
                  'samples_per_query':15,'measurements':measurements}
    output = ROOT/args.report
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
