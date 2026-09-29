"""Whitelisted application API, identical in desktop and end-to-end tests."""
import base64
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from .db import Database
from .settings import Settings
from .contacts import Contacts
from .catalogue import Catalogue
from .documents import Documents, PAYMENT_KNOWN_SQL, PAID_SQL
from .agenda import Agenda
from .assistance import Assistance
from .reporting import Reporting
from .b2b import B2B
from .backups import Backups, recover_pending_restore
from .imports import Imports
from .certificates import Certificates
from .fiscal import Fiscal
from .errors import require, AppError
from .money import calculate
from .files import atomic_write
from .validation import now, today, TZ
from . import __version__
from . import licensing


class App:
    def __init__(self,root):
        recover_pending_restore(root)
        self.db=Database(root)
        self.settings=Settings(self.db)
        self.contacts=Contacts(self.db)
        self.catalogue=Catalogue(self.db,self.settings)
        self.certificates=Certificates(self.db,self.settings)
        self.fiscal=Fiscal(self.db,self.settings,self.certificates)
        self.documents=Documents(self.db,self.settings,self.fiscal,self.catalogue)
        self.agenda=Agenda(self.db,self.settings)
        self.assistance=Assistance(self.db,self.settings,self.documents,self.contacts)
        self.b2b=B2B(self.db,self.settings,self.documents)
        self.backups=Backups(self.db,self.settings)
        self.reporting=Reporting(self.db,self.settings,self.backups)
        self.imports=Imports(self.db,self.contacts,self.backups)
        self.fiscal.recover_interrupted()
        self.actions={
          'bootstrap':self.bootstrap,'dashboard':self.dashboard,
          'settings.get':self.settings.get,'settings.save':self.settings.save,
          'settings.logo':self.settings.logo,'asset.read':self.asset,
          'series.list':self.settings.list_series,'series.save':self.settings.save_series,
          'customers.search':self.contacts.search,'customers.list':self.contacts.list_customers,
          'customers.get':self.contacts.customer,'customers.save':self.contacts.save_customer,'customers.archive':self.contacts.archive_customer,
          'vehicles.list':self.contacts.list_vehicles,'vehicles.save':self.contacts.save_vehicle,'vehicles.transfer':self.contacts.transfer_vehicle,
          'vehicles.get':self.contacts.vehicle,'vehicles.page':self.contacts.vehicles_page,
          'documents.list':self.documents.list,'documents.get':self.documents.get,'documents.save':self.documents.save,
          'documents.publish':self.documents.publish,'documents.delete':self.documents.delete_draft,
          'documents.status':self.documents.change_status,'documents.convert':self.documents.convert,
          'documents.rectify':self.documents.rectify,'documents.void':self.documents.void,'documents.pdf':self.pdf,
          'documents.calculate':calculate,'documents.concepts':self.documents.concepts,'payments.add':self.documents.pay,'payments.reverse':self.documents.reverse_payment,
          'documents.record_payment_state':self.documents.record_payment_state,'documents.adjust_payment_state':self.documents.adjust_payment_state,
          'products.list':self.catalogue.products,'products.save':self.catalogue.save_product,'products.move':self.catalogue.move,
          'products.archive':self.catalogue.archive_product,'products.adjust':self.catalogue.adjust_stock,
          'suppliers.archive':self.catalogue.archive_supplier,
          'products.movements':self.catalogue.movements,'suppliers.list':self.catalogue.suppliers,'suppliers.save':self.catalogue.save_supplier,
          'agenda.list':self.agenda.list,'agenda.save':self.agenda.save,'agenda.delete':self.agenda.remove,
          'agenda.get':self.agenda.get,'agenda.restore_occurrence':self.agenda.restore_occurrence,
          'notifications.list':self.agenda.notifications,'notifications.mark':self.agenda.mark,
          'backup.create':self.backups.create,'backup.list':self.backups.list,'backup.preview':self.backups.preview,'backup.restore':self.backups.restore,
          'backup.password':self.backups.password,'import.preview':self.imports.preview,'import.execute':self.imports.execute,
          'import.sources':self.imports.sources,'import.source_save':self.imports.source_save,
          'import.profiles':self.imports.profiles,'import.profile_save':self.imports.profile_save,
          'import.upload_start':self.imports.upload_start,'import.upload_status':self.imports.upload_status,'import.upload_chunk':self.imports.upload_chunk,
          'import.diagnose':self.imports.diagnose,'import.batches':self.imports.batches,'import.review':self.imports.review,
          'import.map':self.imports.map,'import.simulate':self.imports.simulate,'import.run':self.imports.run,
          'import.pause':self.imports.pause,'import.reconcile':self.imports.reconcile,'import.rollback':self.imports.rollback,
          'import.export_report_chunk':self.imports.export_report_chunk,
          'import.records':self.imports.records,'import.raw_table':self.imports.raw_table,
          'import.capacity':self.imports.capacity,'import.discard':self.imports.discard,
          'backup.recovery_status':self.backups.recovery_status,
          'backup.prepare_transfer':self.backups.prepare_transfer,'backup.activate_transfer':self.backups.activate_transfer,
          'backup.retention':self.backups.configure_retention,
          'backup.download_chunk':self.backups.download_chunk,'backup.release_download':self.backups.release_download,
          'backup.upload_start':self.backups.upload_start,'backup.upload_chunk':self.backups.upload_chunk,
          'backup.upload_status':self.backups.upload_status,'backup.upload_finish':self.backups.upload_finish,
          'backup.upload_cancel':self.backups.upload_cancel,'backup.upload_list':self.backups.upload_list,
          'fiscal.list':self.fiscal.records,'fiscal.send':self.fiscal.send_next,'fiscal.specs':self.fiscal.download_specs,
          'fiscal.correct':self.fiscal.correct,'fiscal.details':self.fiscal.details,
          'fiscal.reconcile':self.fiscal.reconcile,'fiscal.readiness':self.fiscal.readiness,
          'fiscal.export':self.fiscal_export,'fiscal.check':self.fiscal.verify_chain,
          'certificate.save':self.certificates.save,'certificate.delete':self.certificates.delete,
          'audit.check':self.db.check_audit,'data.export':self.export,'agenda.export':self.calendar_export,
          'assistant.rewrite':self.assistance.rewrite,'assistant.status':self.assistance.status,
          'assistant.transcribe':self.assistance.transcribe,'assistant.extract':self.assistance.extract,
          'assistant.history':self.assistance.history,'messages.prepare':self.assistance.message,
          'assistant.start':self.assistance.start,'assistant.job_status':self.assistance.job_status,
          'assistant.cancel':self.assistance.cancel,
          'licenses.status':licensing.status,'licenses.export':licensing.export,
          'b2b.capabilities':self.b2b.capabilities,'b2b.list':self.b2b.list,'b2b.get':self.b2b.get,
          'b2b.prepare':self.b2b.prepare,'b2b.receive':self.b2b.receive,'b2b.validate':self.b2b.validate,
          'b2b.state':self.b2b.record_state,'b2b.export':self.b2b.export,'b2b.check':self.b2b.check,
          'demo.load':self.seed_demo,'app.shutdown':self.shutdown,
          'background.tick':self.tick,'reports':self.reports
        }

    def dispatch(self,action,params=None):
        require(isinstance(action,str) and action in self.actions,'Acci\u00f3n no disponible.','not_found')
        require(params is None or isinstance(params,dict),'Par\u00e1metros no v\u00e1lidos.')
        # Internal connections/transports must never be accepted from the IPC layer.
        require(not (set(params or {}) & {'conn','transport'}),'Par\u00e1metro interno no permitido.')
        try:
            with self.db.lock:
                require(action in ('backup.recovery_status','app.shutdown') or not (self.db.root/'.restore-journal.json').exists(),
                        'La restauración necesita recuperar sus archivos. Cierra y vuelve a abrir la aplicación antes de continuar.',
                        'restore_recovery_pending')
                return self.actions[action](**(params or {}))
        except sqlite3.IntegrityError as exc:
            message=str(exc)
            if 'plate_normalized' in message: raise AppError('Esa matr\u00edcula ya est\u00e1 registrada. Busca su ficha antes de duplicarla.') from exc
            if 'legacy_code' in message: raise AppError('Ese c\u00f3digo de cliente ya existe.') from exc
            if 'series' in message: raise AppError('Ya existe una serie con ese prefijo y a\u00f1o.') from exc
            if 'sku' in message: raise AppError('Esa referencia de art\u00edculo ya existe.') from exc
            raise AppError('No se ha guardado: una restricci\u00f3n protege los datos relacionados. Revisa el documento.') from exc
        except (TypeError,ValueError,KeyError) as exc:
            raise AppError('Faltan datos o hay un formato incorrecto. Revisa los campos antes de guardar.') from exc

    def bootstrap(self):
        config=self.settings.get()
        released=config['fiscal']['mode']=='production' and self.fiscal.readiness()['production_ready'] is True
        return {'version':__version__,'settings':config,'series':self.settings.list_series(),
                'dashboard':self.dashboard(),'data_directory':str(self.db.root),'production_released':released,
                'recovery':self.backups.recovery_status()}

    def dashboard(self):
        with self.db.read() as conn:
            customers=conn.execute('SELECT count(*) FROM customers WHERE archived=0').fetchone()[0]
            drafts=conn.execute("SELECT count(*) FROM documents WHERE kind='invoice' AND status='draft'").fetchone()[0]
            active_orders=conn.execute("SELECT count(*) FROM documents WHERE kind='order' AND status NOT IN ('draft','delivered')").fetchone()[0]
            balances=conn.execute("SELECT coalesce(sum(CASE WHEN balance>0 THEN balance ELSE 0 END),0),coalesce(sum(CASE WHEN balance<0 THEN -balance ELSE 0 END),0) FROM (SELECT d.total_cents-"+PAID_SQL+" AS balance FROM documents d WHERE kind='invoice' AND status IN ('issued','historical') AND "+PAYMENT_KNOWN_SQL+")").fetchone()
            pending,refund=balances
            unknown=conn.execute("SELECT count(*) FROM documents d WHERE kind='invoice' AND status='historical' AND NOT "+PAYMENT_KNOWN_SQL).fetchone()[0]
        start=datetime.now(TZ).replace(hour=0,minute=0,second=0,microsecond=0)
        return {'customers':customers,'drafts':drafts,'active_orders':active_orders,'pending_cents':pending,'refund_due_cents':refund,'unknown_payment_documents':unknown,
                'recent_invoices':self.documents.list()['items'][:5],
                'today_events':self.agenda.list(start.isoformat(),(start+timedelta(days=1)).isoformat())[:6],
                'low_stock':sum(p['low_stock'] for p in self.catalogue.products())}

    def reports(self,start='',end=''):
        return self.reporting.summary(start,end)

    def asset(self,identifier):
        require(re.fullmatch(r'[a-f0-9]{64}\.png',str(identifier or '')),'Identificador de imagen no v\u00e1lido.')
        path=self.db.root/'assets'/identifier
        require(path.is_file(),'No se encuentra el logo.','not_found')
        return {'content':base64.b64encode(path.read_bytes()).decode(),'mime':'image/png'}

    def pdf(self,identifier):
        from .pdf import render_document
        # Serialize resource reads/writes with backup/restore and logo changes.
        with self.db.lock:
            doc=self.documents.get(identifier)
            payload=doc['payload']
            cache=self.db.root/'pdfs'/(identifier+'.pdf')
            immutable=doc['kind']=='invoice' and doc['status'] in ('issued','historical','void')
            if immutable and cache.is_file():
                content=cache.read_bytes()
                require(content.startswith(b'%PDF-'),'El PDF conservado está dañado. Restaura una copia verificada; no se sobrescribirá el original.')
            else:
                if doc.get('reference_id') and 'reference' not in payload:
                    original=self.documents.get(doc['reference_id'])
                    payload['reference']={key:original[key] for key in ('id','full_number','issue_date')}
                if doc['status']=='draft':
                    if 'customer' not in payload:
                        payload['customer']=self.contacts.customer(doc['customer_id'])
                    if 'vehicle' not in payload and doc['vehicle_id']:
                        with self.db.read() as conn:
                            row=conn.execute('SELECT * FROM vehicles WHERE id=?',(doc['vehicle_id'],)).fetchone()
                            payload['vehicle']=dict(row) if row else None
                content=render_document(doc,self.settings.get(),self.db.root)
                if doc['status']!='draft':
                    atomic_write(cache,content)
            name=re.sub(r'[^A-Za-z0-9_.-]','_',doc['full_number'] or 'borrador-'+identifier[:8])+'.pdf'
            return {'content':base64.b64encode(content).decode(),'name':name,'mime':'application/pdf'}

    def fiscal_export(self,record_id):
        with self.db.read() as conn:
            row=conn.execute('SELECT xml FROM fiscal_records WHERE id=?',(record_id,)).fetchone()
        require(row,'Registro no encontrado.')
        return {'content':base64.b64encode(row['xml'].encode()).decode(),'name':'verifactu-'+record_id+'.xml','mime':'application/xml'}

    def export(self,kind='customers',start='',end=''):
        return self.reporting.export(kind,start,end)

    def calendar_export(self):
        return {'content':base64.b64encode(self.agenda.export_ics()).decode(),'name':'agenda-'+today()+'.ics','mime':'text/calendar'}

    def tick(self):
        result={'notifications':self.agenda.notifications(True)}
        try: result['backup']=self.backups.automatic()
        except (AppError,OSError): result['backup']={'status':'error','message':'No se ha podido completar la copia autom\u00e1tica.'}
        # The sender enforces the release/certificate gates before claiming any
        # production work; both remote modes retain automatic retries after restart.
        if self.settings.get()['fiscal']['mode'] in ('aeat_test','production'):
            try:
                result['fiscal']=self.fiscal.send_next()
            except AppError as exc:
                result['fiscal']={'status':'blocked','code':exc.code,'message':str(exc)}
        return result

    def shutdown(self):
        if self.settings.get()['backup']['on_close']:
            self.backups.automatic(force=True)
        return {'ok':True}

    def seed_demo(self):
        with self.db.read() as conn:
            require(conn.execute('SELECT count(*) FROM customers').fetchone()[0]==0,'La demostraci\u00f3n solo se carga en una base vac\u00eda para no mezclar datos.')
        self.settings.save('company',{'legal_name':'TALLER DE DEMOSTRACION - NO REAL','tax_id':'89890001K'})
        people=[('Lucia Medina','12345678Z','612 000 001','0826 LFG','Seat','Leon'),
                ('Antonio Romero','00000000T','612 000 002','4218 KLM','Renault','Clio'),
                ('Transportes Sur (demo)','11111111H','612 000 003','5632 JPN','Ford','Transit'),
                ('Carmen Vega','22222222J','612 000 004','7403 MBC','Peugeot','308'),
                ('Manuel Santos','33333333P','612 000 005','9125 HGT','Citroen','C3')]
        records=[]
        for i,(name,nif,phone,p,make,model) in enumerate(people):
            customer=self.contacts.save_customer({'name':name,'tax_id':nif,'phone':phone,'address':'Calle de ejemplo, '+str(i+1),'postal_code':'41300','city':'San Jose de la Rinconada','province':'Sevilla','legacy_code':'DEMO-'+str(i+1),'email':'cliente'+str(i+1)+'@example.invalid'})
            vehicle=self.contacts.save_vehicle({'customer_id':customer['id'],'plate':p,'make':make,'model':model,'km':126000+i*10000,'kind':'Turismo'})
            records.append((customer['id'],vehicle['id']))
        supplier=self.catalogue.save_supplier({'name':'Recambios de ejemplo','phone':'900 000 000','notes':'Proveedor ficticio de demostracion'})
        for sku,name,price,stock in [('ACE-5W30','Aceite de motor 5W30','12.50','24'),('FIL-001','Filtro de aceite','18.00','8'),('PAS-001','Juego de pastillas delanteras','62.00','2'),('MO-001','Mano de obra','34.00','0')]:
            product=self.catalogue.save_product({'sku':sku,'name':name,'unit_price':price,'cost_price':'0','min_stock':'3','supplier_id':supplier['id'],'track_stock':sku!='MO-001'})
            if stock!='0':self.catalogue.move(product['id'],stock,'Existencias iniciales de demostracion','demo:'+sku)
        for i,(customer_id,vehicle_id) in enumerate(records[:3]):
            document=self.documents.save({'kind':'invoice','customer_id':customer_id,'vehicle_id':vehicle_id,'issue_date':today(),
                  'lines':[{'description':'Cambio de aceite y filtro','quantity':'1','unit_price':'68.00','tax_rate':'21'},
                           {'description':'Mano de obra','quantity':'1.5','unit_price':'34.00','tax_rate':'21'}], 'kilometres':126000+i*10000})
            document=self.documents.publish(document['id'])
            if i==0:self.documents.pay(document['id'],str(DecimalProxy(document['total_cents'])),'card',today(),'demo-payment')
        for i,kind in enumerate(('order','quote')):
            c,v=records[i]
            document=self.documents.save({'kind':kind,'customer_id':c,'vehicle_id':v,'lines':[{'description':'Revision de frenos delanteros','quantity':'1','unit_price':'95','tax_rate':'21'}],'notes':'Revisar ruido al frenar. Confirmar antes de sustituir piezas.'})
            self.documents.publish(document['id'])
        start=datetime.now(TZ).replace(hour=9,minute=0,second=0,microsecond=0)
        for i,title in enumerate(('Revision y cambio de aceite','Entrega del Renault Clio','Revision de frenos','Llamar al proveedor')):
            t=start+timedelta(hours=i*2)
            self.agenda.save({'title':title,'kind':'pickup' if i==1 else 'appointment','start':t.isoformat(),'end':(t+timedelta(minutes=60)).isoformat(),'customer_id':records[i][0],'vehicle_id':records[i][1],'reminders':[15]})
        return self.bootstrap()


def DecimalProxy(cents):
    from decimal import Decimal
    return Decimal(cents)/100
