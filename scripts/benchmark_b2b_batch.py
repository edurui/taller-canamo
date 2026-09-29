"""Synthetic local benchmark. Creates and deletes its own temporary database."""
import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from lxml import etree
from taller.app import App
from taller.b2b import check_storage
from taller.b2b_xml import CBC, generate, validate_xml, validation_session


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--count',type=int,default=1000)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not 1<=args.count<=3000:
        parser.error('count debe estar entre 1 y 3000')
    with TemporaryDirectory(prefix='canamo-b2b-benchmark-') as temporary:
        app=App(Path(temporary)/'data')
        app.settings.save('company',{'legal_name':'Taller sintético','tax_id':'89890001K',
            'address':'Calle ficticia 1','postal_code':'41300','city':'Localidad sintética'})
        customer=app.contacts.save_customer({'name':'Empresa sintética','tax_id':'12345678Z',
            'address':'Calle ficticia 2','postal_code':'41300','city':'Localidad sintética'})
        invoice=app.documents.save({'customer_id':customer['id'],'lines':[{'description':'Trabajo sintético','unit_price':'100'}]})
        template=generate(app.documents.publish(invoice['id']))
        individual=[]
        for _ in range(10):
            started=time.perf_counter()
            assert validate_xml(template)['ok']
            individual.append(time.perf_counter()-started)
        started=time.perf_counter()
        with validation_session() as validator:
            for _ in range(10):
                assert validator.validate(template)['ok']
        batch_ten=time.perf_counter()-started
        started=time.perf_counter()
        # Fixture construction uses the same validators and persistence helper;
        # no production invoice, public reception or remote delivery is claimed.
        with app.db.transaction() as conn,validation_session() as validator:
            for index in range(args.count):
                root=etree.fromstring(template.encode())
                root.find('{'+CBC+'}ID').text='BENCH-SINTETICA-'+str(index)
                xml=etree.tostring(root,encoding='UTF-8',xml_declaration=True).decode()
                validation=validator.validate(xml)
                assert validation['ok']
                app.b2b._store(conn,xml,'outbound',validation)
        construction=time.perf_counter()-started
        started=time.perf_counter()
        with app.db.read() as conn:
            verified=check_storage(conn)
        verification=time.perf_counter()-started
        started=time.perf_counter()
        backup=app.backups.create(automatic=True)
        backup_seconds=time.perf_counter()-started
        assert verified['documents_checked']==args.count and verified['sources_checked']==args.count
        result={'recorded_at':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
            'python':platform.python_version(),'count':args.count,'independent_validations_10_seconds':round(sum(individual),4),
            'independent_validation_median_seconds':round(statistics.median(individual),4),
            'batch_10_seconds':round(batch_ten,4),'synthetic_construction_seconds':round(construction,4),
            'check_storage_seconds':round(verification,4),'verified':verified,
            'actual_backup_seconds':round(backup_seconds,4),'actual_backup_bytes':backup['bytes'],
            'network_called':False,'data':'Synthetic temporary SQLite, deleted after run; no model or certificate',
            'limits':'Measures this Linux host and this invoice fixture; no Windows or universal latency claim.',
            'files':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
                'backend/taller/b2b_xml.py','backend/taller/b2b.py','backend/taller/backups.py','scripts/benchmark_b2b_batch.py')}}
        output=Path(args.output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
