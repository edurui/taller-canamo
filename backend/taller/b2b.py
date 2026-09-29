"""Separate B2B workflow. Local validation/export is never remote delivery."""
import base64
import hashlib
import json
import re
import sqlite3
from itertools import chain

from . import __version__
from .b2b_xml import generate, validate_xml, validation_session, identity, resources, decode_file, parse_xml
from lxml import etree
from .db import dumps, uid
from .errors import AppError, require
from .validation import iso_date, now, today

LAW = 'https://www.boe.es/eli/es/rd/2026/03/25/238/con'
DRAFT = 'https://www.hacienda.gob.es/sgt/normativadoctrina/proyectos/16042026-proyecto-pom-factura-electronica.pdf'
SERVICE_LIMIT = ('No se ha localizado una especificación final publicada del servicio público B2B '
                 'ni un endpoint oficial de remisión en las fuentes revisadas el 23/09/2026. '
                 'El documento de Hacienda consultado está rotulado como proyecto. '
                 'Se conservan las obligaciones de envío, sin transmitir ni marcar entrega.')
COMMERCIAL = ('accepted','rejected','partially_accepted','partially_rejected')
PAYMENT = ('partially_paid','paid')


def event_hash(previous, request, stamp):
    return hashlib.sha256((previous+'|'+dumps(request)+'|'+stamp).encode()).hexdigest()


def check_storage(conn, identifier=None):
    """Verify a database or staged backup, including pre-B2B schema versions.

    The caller owns the connection/transaction. No database writes, credentials,
    application initialization or network access are needed. Version 6 records
    may lack original encoded bytes, which version 7 cannot reconstruct.
    """
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = cursor.execute('PRAGMA user_version').fetchone()[0]
    if version < 6 and 'b2b_documents' not in tables:
        return {'ok':True,'documents_checked':0,'events_checked':0,'sources_checked':0,'sources_unavailable':0}
    require({'b2b_documents','b2b_events','b2b_obligations'} <= tables,
            'Faltan tablas de conservación B2B.','b2b_integrity')
    require(version < 7 or 'b2b_source_files' in tables,
            'Falta la conservación de archivos originales B2B.','b2b_integrity')
    query = 'SELECT * FROM b2b_documents'+(' WHERE id=?' if identifier else '')+' ORDER BY created_at,id'
    documents = conn.cursor()
    documents.row_factory = sqlite3.Row
    documents.execute(query,(identifier,) if identifier else ())
    first = documents.fetchone()
    require(identifier is None or first is not None,'Factura B2B no encontrada.','not_found')
    result = {'ok':True,'documents_checked':0,'events_checked':0,'sources_checked':0,'sources_unavailable':0}
    if first is None:
        return result
    with validation_session() as validator:
        return _check_documents(cursor,chain((first,),documents),result,validator,'b2b_source_files' in tables)


def _check_documents(cursor,documents,result,validator,has_sources):
    for row in documents:
        document = dict(row)
        require(hashlib.sha256(document['xml'].encode('utf-8')).hexdigest()==document['digest'],
                'El XML conservado ha sido alterado.','b2b_integrity')
        validation = validator.validate(document['xml'])
        require(validation['ok'],'El XML conservado no supera EN16931.','b2b_integrity')
        require(all(document[key]==value for key,value in identity(document['xml']).items()),
                'La identidad o importes B2B no coinciden con el XML conservado.','b2b_integrity')
        source = cursor.execute('SELECT content,sha256 FROM b2b_source_files WHERE b2b_id=?',(document['id'],)).fetchone() if has_sources else None
        if source:
            require(hashlib.sha256(source['content']).hexdigest()==source['sha256'],
                    'El archivo original B2B ha sido alterado.','b2b_integrity')
            original = parse_xml(decode_file(source['content']))
            normalized = parse_xml(document['xml'])
            require(etree.tostring(original,method='c14n')==etree.tostring(normalized,method='c14n'),
                    'El archivo original B2B no corresponde al XML conservado.','b2b_integrity')
            result['sources_checked'] += 1
        else:
            result['sources_unavailable'] += 1
        previous = ''
        events = {}
        for row in cursor.execute('SELECT * FROM b2b_events WHERE b2b_id=? ORDER BY seq',(document['id'],)).fetchall():
            event = dict(row)
            request = {key:event[key] for key in ('b2b_id','state','occurred_on','evidence','paid_cents','corrects_event_id')}
            require(event['previous_hash']==previous and event['hash']==event_hash(previous,request,event['created_at'])
                    and event['request_hash']==hashlib.sha256(dumps(request).encode()).hexdigest(),
                    'El historial B2B presenta una alteración.','b2b_integrity')
            require(not event['corrects_event_id'] or event['corrects_event_id'] in events,
                    'La corrección B2B no tiene un estado anterior de la misma factura.','b2b_integrity')
            events[event['id']] = event
            previous=event['hash']
            result['events_checked'] += 1
        require(bool(events),'Falta el historial de conservación B2B.','b2b_integrity')
        for obligation in cursor.execute('SELECT * FROM b2b_obligations WHERE b2b_id=?',(document['id'],)).fetchall():
            try:
                payload = json.loads(obligation['payload'])
            except (TypeError,ValueError) as exc:
                raise AppError('La obligación B2B conservada está dañada.','b2b_integrity') from exc
            expected = events.get(obligation['event_id']) if obligation['event_id'] else {
                'document_digest':document['digest'],'syntax':document['syntax'],'test_document':bool(document['test_document'])}
            require(expected is not None and payload==expected,
                    'La obligación B2B no coincide con el documento o estado conservado.','b2b_integrity')
        result['documents_checked'] += 1
    return result


class B2B:
    def __init__(self,db,settings,documents):
        self.db,self.settings,self.documents = db,settings,documents

    def capabilities(self):
        manifest = resources()
        return {'version':__version__,'syntax':'UBL 2.1','semantic_validator':'EN16931 '+manifest['en16931_version'],
                'local_generation':True,'local_reception':True,'commercial_states':True,
                'public_submission':False,'spanish_service_profile_validated':False,
                'signature_verification':False,
                'scope':'Facturas completas interiores España, EUR, régimen general y exenciones E1/E4/E6; rectificación por diferencias.',
                'limit':SERVICE_LIMIT,'sources':[LAW,DRAFT],'reviewed_on':'2026-09-23','network_called':False}

    @staticmethod
    def validate(xml):
        return validate_xml(xml)

    def _store(self,conn,xml,direction,validation,document_id=None,source=None):
        data = identity(xml)
        require(data['currency']=='EUR','La recepción local B2B solo admite importes en EUR.','b2b_scope')
        digest = validation['sha256']
        existing = conn.execute('SELECT id,digest FROM b2b_documents WHERE direction=? AND issuer_nif=? AND invoice_number=? AND issue_date=?',
                                (direction,data['issuer_nif'],data['invoice_number'],data['issue_date'])).fetchone()
        if existing:
            require(existing['digest'] == digest,'Ya existe una factura con esa identidad y distinto contenido. Conserva el original y solicita su rectificación.','b2b_conflict')
            return self._get(conn,existing['id'])
        identifier = uid()
        conn.execute('''INSERT INTO b2b_documents(id,document_id,direction,syntax,xml,digest,issuer_nif,recipient_nif,
            invoice_number,issue_date,currency,total_cents,test_document,validation,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (identifier,document_id,direction,'UBL 2.1',xml,digest,data['issuer_nif'],data['recipient_nif'],data['invoice_number'],
             data['issue_date'],data['currency'],data['total_cents'],int(data['test_document']),dumps(validation),now()))
        original = source if source is not None else xml.encode('utf-8')
        conn.execute('INSERT INTO b2b_source_files VALUES(?,?,?,?)',
                     (identifier,original,hashlib.sha256(original).hexdigest(),now()))
        self._event(conn,identifier,'prepared' if direction=='outbound' else 'received',data['issue_date'],
                    'Documento validado y conservado localmente. No acredita entrega remota.','store:'+digest)
        if direction == 'outbound':
            conn.execute('INSERT INTO b2b_obligations(id,b2b_id,kind,payload,created_at) VALUES(?,?,?,?,?)',
                         (uid(),identifier,'invoice',dumps({'document_digest':digest,'syntax':'UBL 2.1','test_document':data['test_document']}),now()))
        self.db.audit(conn,'b2b.'+direction,identifier,{'digest':digest,'document_id':document_id})
        return self._get(conn,identifier)

    def prepare(self,document_id,recipient_business):
        require(recipient_business is True,'Confirma que el destinatario actúa como empresa o profesional en esta operación.','b2b_scope')
        with self.db.transaction() as conn:
            existing = conn.execute('SELECT id FROM b2b_documents WHERE document_id=?',(document_id,)).fetchone()
            if existing:
                return self._get(conn,existing['id'])
            document = self.documents.get(document_id,conn)
            require(document['kind']=='invoice' and document['status']=='issued',
                    'Selecciona una factura emitida y vigente; el histórico y los borradores no se remiten como nuevos.','b2b_scope')
            xml = generate(document)
            validation = validate_xml(xml)
            require(validation['ok'],'La factura no supera EN16931: '+'; '.join(item['id']+' '+item['message'] for item in validation['errors'])[:1800],'b2b_semantic')
            return self._store(conn,xml,'outbound',validation,document_id)

    def receive(self,xml=None,content=None):
        require((xml is None) != (content is None),'Aporta un XML o un archivo, sin combinarlos.','b2b_xml')
        if content is not None:
            require(isinstance(content,str) and len(content)<=7_000_000,'El archivo B2B supera el tamaño permitido.','b2b_xml')
            try:
                original=base64.b64decode(content,validate=True)
            except ValueError as exc:
                raise AppError('El archivo B2B no tiene una codificación válida.','b2b_xml') from exc
        else:
            require(isinstance(xml,str),'El XML debe ser texto.','b2b_xml')
            original=etree.tostring(parse_xml(xml),encoding='UTF-8',xml_declaration=True)
        xml=decode_file(original)
        validation = validate_xml(xml)
        require(validation['ok'],'La factura recibida no supera EN16931: '+'; '.join(item['id']+' '+item['message'] for item in validation['errors'])[:1800],'b2b_semantic')
        data = identity(xml)
        with self.db.transaction() as conn:
            tax_id = self.settings.get(conn)['company']['tax_id']
            require(tax_id and data['recipient_nif'] in (tax_id,'ES'+tax_id),
                    'La factura recibida no identifica al taller como destinatario.','b2b_recipient')
            return self._store(conn,xml,'inbound',validation,source=original)

    def _event(self,conn,identifier,state,occurred_on,evidence,key,paid_cents=None,corrects_event_id=None):
        request = {'b2b_id':identifier,'state':state,'occurred_on':occurred_on,'evidence':evidence,
                   'paid_cents':paid_cents,'corrects_event_id':corrects_event_id}
        fingerprint = hashlib.sha256(dumps(request).encode()).hexdigest()
        old = conn.execute('SELECT * FROM b2b_events WHERE idempotency_key=?',(key,)).fetchone()
        if old:
            require(old['request_hash']==fingerprint,'La clave de operación ya identifica otro estado.','conflict')
            return dict(old)
        last = conn.execute('SELECT hash FROM b2b_events WHERE b2b_id=? ORDER BY seq DESC LIMIT 1',(identifier,)).fetchone()
        previous = last['hash'] if last else ''
        stamp,record_id = now(),uid()
        digest = event_hash(previous,request,stamp)
        conn.execute('''INSERT INTO b2b_events(id,b2b_id,state,occurred_on,paid_cents,evidence,idempotency_key,request_hash,
            corrects_event_id,previous_hash,hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (record_id,identifier,state,occurred_on,paid_cents,evidence,key,fingerprint,corrects_event_id,previous,digest,stamp))
        return dict(conn.execute('SELECT * FROM b2b_events WHERE id=?',(record_id,)).fetchone())

    def record_state(self,identifier,state,occurred_on,evidence,idempotency_key,paid_cents=None,corrects_event_id=None):
        require(state in COMMERCIAL+PAYMENT,'Estado comercial B2B no admitido.')
        occurred_on = iso_date(occurred_on)
        require(occurred_on<=today(),'No se puede registrar como ocurrido un estado futuro.')
        require(isinstance(evidence,str) and 3<=len(evidence.strip())<=1500,'Describe la evidencia y fecha efectiva del estado.')
        require(isinstance(idempotency_key,str) and 1<=len(idempotency_key)<=200,'Falta la clave de operación.')
        with self.db.transaction() as conn:
            document = self._get(conn,identifier)
            require(occurred_on>=document['issue_date'],'El estado no puede ser anterior a la factura.')
            prior_same_key = conn.execute('SELECT id FROM b2b_events WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            category = PAYMENT if state in PAYMENT else COMMERCIAL
            prior = next((item for item in reversed(document['events']) if item['state'] in category),None)
            if state in PAYMENT:
                require(isinstance(paid_cents,int) and not isinstance(paid_cents,bool) and 0<paid_cents<=abs(document['total_cents']),
                        'El importe pagado acumulado debe ser positivo y no superar el total de la factura.')
                require((state=='paid') == (paid_cents==abs(document['total_cents'])),
                        'El estado de pago completo/parcial no coincide con el importe acumulado.')
            else:
                require(paid_cents is None,'El estado comercial no lleva un importe de pago.')
            if not prior_same_key:
                if corrects_event_id:
                    require(prior and prior['id']==corrects_event_id,'Solo puedes corregir el último estado de esa categoría.','conflict')
                elif prior:
                    require(occurred_on>=prior['occurred_on'],'El nuevo estado no puede retroceder en fecha sin documentar una corrección.')
                    if state in PAYMENT:
                        require(paid_cents>prior['paid_cents'],'Un descenso o repetición del pago exige corregir expresamente el estado anterior.')
                    else:
                        require(prior['state'].startswith('partially_') and state in ('accepted','rejected'),
                                'La aceptación o rechazo ya registrada se cambia con una corrección explícita.')
            event = self._event(conn,identifier,state,occurred_on,evidence.strip(),idempotency_key,paid_cents,corrects_event_id)
            if not prior_same_key:
                kind = 'payment_state' if state in PAYMENT else 'commercial_state'
                conn.execute('INSERT INTO b2b_obligations(id,b2b_id,event_id,kind,payload,created_at) VALUES(?,?,?,?,?,?)',
                             (uid(),identifier,event['id'],kind,dumps(event),now()))
                self.db.audit(conn,'b2b.state',identifier,{'event_id':event['id'],'state':state,'remote_delivery':False})
            return self._get(conn,identifier)

    def _get(self,conn,identifier):
        row = conn.execute('SELECT * FROM b2b_documents WHERE id=?',(identifier,)).fetchone()
        require(row is not None,'Factura B2B no encontrada.','not_found')
        result = dict(row);result['test_document'] = bool(result['test_document'])
        result['validation'] = json.loads(result['validation'])
        result['events'] = [dict(item) for item in conn.execute('SELECT * FROM b2b_events WHERE b2b_id=? ORDER BY seq',(identifier,))]
        result['obligations'] = [dict(item) for item in conn.execute('SELECT * FROM b2b_obligations WHERE b2b_id=? ORDER BY created_at,id',(identifier,))]
        result['remote_delivered'] = False
        result['signature_verified'] = False
        result['commercial_state'] = next((item['state'] for item in reversed(result['events']) if item['state'] in COMMERCIAL),'unrecorded')
        result['payment_state'] = next((item['state'] for item in reversed(result['events']) if item['state'] in PAYMENT),'unrecorded')
        result['limit'] = SERVICE_LIMIT
        return result

    def get(self,identifier):
        with self.db.read() as conn:
            return self._get(conn,identifier)

    def list(self,direction='',query='',page=0):
        require(direction in ('','outbound','inbound'),'Dirección B2B no admitida.')
        require(isinstance(page,int) and page>=0,'Página no válida.')
        terms,params = ['1=1'],[]
        if direction:
            terms.append('direction=?');params.append(direction)
        if query:
            terms.append("(invoice_number LIKE ? ESCAPE '\\' OR issuer_nif LIKE ? ESCAPE '\\' OR recipient_nif LIKE ? ESCAPE '\\')")
            term='%'+str(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';params.extend([term]*3)
        where=' WHERE '+' AND '.join(terms)
        with self.db.read() as conn:
            total=conn.execute('SELECT count(*) FROM b2b_documents'+where,params).fetchone()[0]
            rows=conn.execute('SELECT id,document_id,direction,invoice_number,issuer_nif,recipient_nif,issue_date,total_cents,currency,test_document,created_at FROM b2b_documents'+where+' ORDER BY created_at DESC,id LIMIT 50 OFFSET ?',(*params,page*50))
            return {'items':[dict(row) for row in rows],'total':total,'page':page}

    def export(self,identifier):
        with self.db.transaction() as conn:
            document = self._get(conn,identifier)
            require(hashlib.sha256(document['xml'].encode()).hexdigest()==document['digest'],'El XML conservado ha sido alterado.','b2b_integrity')
            safe = re.sub(r'[^A-Za-z0-9._-]','_',document['invoice_number'])[:80]
            source = conn.execute('SELECT content,sha256 FROM b2b_source_files WHERE b2b_id=?',(identifier,)).fetchone()
            content = source['content'] if source else document['xml'].encode('utf-8')
            digest = hashlib.sha256(content).hexdigest()
            require(not source or source['sha256']==digest,'El archivo original B2B ha sido alterado.','b2b_integrity')
            self._event(conn,identifier,'exported',today(),'Archivo exportado localmente; no acredita envío ni recepción.',
                        'export:'+identifier+':'+document['digest']+':'+today())
            return {'name':('PRUEBA-' if document['test_document'] else '')+safe+'.ubl.xml',
                    'mime':'application/xml','content':base64.b64encode(content).decode(),
                    'sha256':digest,'remote_delivered':False}

    def check(self,identifier):
        with self.db.read() as conn:
            return check_storage(conn,identifier)
