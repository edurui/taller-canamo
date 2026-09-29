"""Document aggregates. Issuing, numbering, stock and fiscal outbox are atomic."""
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from .db import uid, dumps
from .errors import require, AppError
from .money import calculate, decimal, cents, canonical_tax_rate, normalize_tax_adjustments
from .validation import today, now, iso_date, valid_tax_id, normalized, plate
from .settings import Settings

METHODS = ('cash','card','transfer','bizum','other')
IMMUTABLE = ('issued','historical','void')
_CUSTOMER_SNAPSHOT_FIELDS = ('id','legacy_code','name','tax_id','address','postal_code','city','province','country','phone','email')

PAYMENT_KNOWN_SQL = "(d.status NOT IN ('historical','import_reverted') OR coalesce(json_extract(d.payload,'$.payment_state'),'unknown') != 'unknown' OR EXISTS(SELECT 1 FROM document_payment_baselines b WHERE b.document_id=d.id))"
PAID_SQL = "(coalesce((SELECT b.paid_cents FROM document_payment_baselines b WHERE b.document_id=d.id),0)+coalesce((SELECT sum(p.amount_cents) FROM payments p WHERE p.document_id=d.id),0))"


def _is_test_document(environment):
    """Metadata only; callers must pass the release gates before persisting it."""
    require(environment in ('local_test','aeat_test','production'),'Entorno fiscal no admitido.')
    return environment!='production'

# The same identity must be used for detail, count, filtering and pagination.
# An absent vehicle snapshot intentionally stays absent after publication.
_SNAPSHOT_IDENTITY = "(d.status IN ('issued','historical','void') OR (d.status!='draft' AND json_type(d.payload,'$.customer')='object'))"
_DOCUMENT_ROWS = f'''(SELECT d.*,
    CASE WHEN {_SNAPSHOT_IDENTITY} THEN json_extract(d.payload,'$.customer.name') ELSE c.name END AS customer_name,
    CASE WHEN {_SNAPSHOT_IDENTITY} OR (d.reference_id IS NOT NULL AND json_type(d.payload,'$.vehicle') IS NOT NULL)
        THEN json_extract(d.payload,'$.vehicle.plate') ELSE v.plate END AS plate
    FROM documents d JOIN customers c ON c.id=d.customer_id
    LEFT JOIN vehicles v ON v.id=d.vehicle_id) d'''


class Documents:
    def __init__(self,db,settings,fiscal,catalogue):
        self.db,self.settings,self.fiscal,self.catalogue = db,settings,fiscal,catalogue

    def get(self, identifier, conn=None):
        if conn is None:
            with self.db.read() as current:
                return self.get(identifier,current)
        row = conn.execute('SELECT d.* FROM '+_DOCUMENT_ROWS+' WHERE d.id=?',(identifier,)).fetchone()
        require(row, 'No se encuentra el documento.', 'not_found')
        result = dict(row)
        result['payload'] = json.loads(row['payload'])
        result['payments'] = [dict(p) for p in conn.execute('SELECT * FROM payments WHERE document_id=? ORDER BY created_at',(identifier,))]
        baseline = conn.execute('SELECT * FROM document_payment_baselines WHERE document_id=?',(identifier,)).fetchone()
        result['payment_baseline'] = dict(baseline) if baseline else None
        result['payment_known'] = bool(baseline or result['status'] not in ('historical','import_reverted') or result['payload'].get('payment_state','unknown')!='unknown')
        result['paid_cents'] = (sum(p['amount_cents'] for p in result['payments']) + (baseline['paid_cents'] if baseline else 0)) if result['payment_known'] else None
        result['pending_cents'] = result['total_cents'] - result['paid_cents'] if result['payment_known'] else None
        result['conversion_identity_locked'] = bool(row['origin_id'] or conn.execute(
            'SELECT 1 FROM documents WHERE origin_id=? LIMIT 1',(identifier,)).fetchone())
        result['active_rectifications'] = [dict(item) for item in conn.execute('''WITH RECURSIVE corrections(id) AS (
            SELECT ? UNION SELECT d.id FROM documents d JOIN corrections c ON d.reference_id=c.id)
            SELECT d.id,d.status,d.full_number FROM documents d JOIN corrections c ON d.id=c.id
            WHERE d.id!=? AND d.status NOT IN ('void','import_reverted') ORDER BY d.created_at,d.id''',(identifier,identifier))]
        status = conn.execute('SELECT o.status,o.last_error,o.csv FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id WHERE r.document_id=? ORDER BY r.seq DESC LIMIT 1',(identifier,)).fetchone()
        result['fiscal_status'] = dict(status) if status else None
        return result

    def list(self,kind='invoice',query='',customer_id=None,vehicle_id=None,status='',page=0):
        require(kind in ('invoice','quote','order'), 'Tipo no admitido.')
        condition,params = ["d.kind=?", "d.status!='import_reverted'"],[kind]
        if customer_id:
            condition.append('d.customer_id=?');params.append(customer_id)
        if vehicle_id:
            condition.append('d.vehicle_id=?');params.append(vehicle_id)
        if status:
            condition.append('d.status=?');params.append(status)
        if query:
            text_match = "normalized(coalesce(d.full_number,'')||' '||coalesce(d.customer_name,'')||' '||coalesce(d.plate,'')) LIKE ? ESCAPE '\\'"
            q = normalized(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            params.append('%'+q+'%')
            compact = plate(query)
            if compact:
                condition.append('('+text_match+' OR normalized_plate(d.plate) LIKE ?)')
                params.append('%'+compact+'%')
            else:
                condition.append(text_match)
        joins = ' FROM '+_DOCUMENT_ROWS+' WHERE '+' AND '.join(condition)
        with self.db.read() as conn:
            conn.create_function('normalized_plate',1,plate,deterministic=True)
            total = conn.execute('SELECT count(*)'+joins,params).fetchone()[0]
            rows = conn.execute("SELECT d.id,d.kind,d.status,d.issue_date,d.due_date,d.full_number,d.customer_id,d.vehicle_id,d.total_cents,d.base_cents,d.version,d.customer_name,d.plate,"+PAYMENT_KNOWN_SQL+" AS payment_known, CASE WHEN "+PAYMENT_KNOWN_SQL+" THEN "+PAID_SQL+" ELSE NULL END AS paid_cents,(SELECT o.status FROM fiscal_records r JOIN fiscal_outbox o ON o.record_id=r.id WHERE r.document_id=d.id ORDER BY r.seq DESC LIMIT 1) AS fiscal_state"+joins+' ORDER BY d.issue_date DESC,d.created_at DESC,d.id DESC LIMIT 50 OFFSET ?',(*params,max(0,int(page))*50))
            return {'items':[dict(r) for r in rows],'total':total,'page':page}

    def save(self,data):
        with self.db.transaction() as conn:
            return self._save(data,conn)

    def _save(self,data,conn):
        identifier = data.get('id') or uid()
        require(re.fullmatch(r'[0-9a-f-]{36}',identifier), 'Identificador no v\u00e1lido.')
        kind = data.get('kind','invoice')
        require(kind in ('invoice','quote','order'), 'Tipo de documento no admitido.')
        invoice_type = data.get('invoice_type','F1')
        require(invoice_type in ('F1','R1','R2','R3','R4'), 'Tipo fiscal no admitido.')
        billing = self.settings.get(conn)['billing']
        raw_lines = data.get('lines', [])
        require(isinstance(raw_lines, list), 'Las líneas deben ser una lista.')
        tax_adjustments=data.get('tax_adjustments')
        require(invoice_type not in ('R2','R3') or tax_adjustments is not None,
                'En R2/R3 indica expresamente las cuotas de IVA que se rectifican, sin invertir las bases de la factura.','tax_adjustment')
        totals = calculate([{**{'tax_rate': billing['vat']}, **line} if isinstance(line, dict) else line for line in raw_lines],
                           corrective=invoice_type.startswith('R'),invoice_type=invoice_type,tax_adjustments=tax_adjustments)
        issue_date = iso_date(data.get('issue_date') or today())
        default_due = (date.fromisoformat(issue_date) + timedelta(days=billing['quote_days'] if kind == 'quote' else billing['due_days'])).isoformat() if kind != 'order' else ''
        due_value = data.get('due_date', default_due)
        due_date = iso_date(due_value) if due_value else ''
        if due_date: require(due_date>=issue_date, 'El vencimiento no puede ser anterior a la fecha del documento.')
        method = data.get('payment_method',billing['payment_method'])
        require(method in METHODS, 'Forma de pago no v\u00e1lida.')
        km = data.get('kilometres',0)
        require(isinstance(km,int) and not isinstance(km,bool) and 0<=km<=10000000, 'Kilometraje no v\u00e1lido.')
        customer_id,vehicle_id = data.get('customer_id'),data.get('vehicle_id') or None
        notes = str(data.get('notes','')).strip()
        require(len(notes)<=4000, 'Las observaciones son demasiado largas.')
        customer = conn.execute('SELECT * FROM customers WHERE id=? AND archived=0',(customer_id,)).fetchone()
        require(customer, 'Selecciona el cliente de este documento.')
        reference_id = data.get('reference_id') or None
        original = None
        if invoice_type.startswith('R'):
            require(kind=='invoice' and reference_id, 'La rectificativa debe indicar la factura original.')
            original = conn.execute('SELECT * FROM documents WHERE id=?',(reference_id,)).fetchone()
            require(original and original['kind']=='invoice' and original['status'] in ('issued','historical'), 'Factura original no v\u00e1lida.')
            require(original['customer_id']==customer_id, 'La rectificativa debe corresponder al mismo cliente.')
            require(notes, 'Indica el motivo de rectificaci\u00f3n.')
        else:
            require(not reference_id, 'Solo una rectificativa puede referenciar una factura.')
        operation_date=self._operation_date(data.get('operation_date'),issue_date,original)
        if tax_adjustments is not None:
            require(not data.get('stock_affect',False),'La rectificación exclusiva de cuota no mueve existencias.','tax_adjustment')
            self._validate_tax_adjustments(conn,original,totals['tax_adjustments'],identifier)
        elif original is not None:
            self._validate_tax_adjustments(conn,original,[],identifier,commercial_change=totals['taxes'])
        vehicle = None
        if vehicle_id:
            vehicle = conn.execute('SELECT * FROM vehicles WHERE id=?',(vehicle_id,)).fetchone()
            from_original = original is not None and original['vehicle_id']==vehicle_id
            require(vehicle and (from_original or (not vehicle['archived'] and vehicle['customer_id']==customer_id)),
                    'El veh\u00edculo no pertenece al cliente seleccionado.')
        payload = {**totals,'invoice_type':invoice_type,'operation_date':operation_date,'payment_method':method,'kilometres':km,'notes':notes,
                   'stock_affect':bool(data.get('stock_affect',False)),'footer':str(data.get('footer',self.settings.get(conn)['billing']['footer']))[:800]}
        if original is not None:
            payload['reference'] = {key:original[key] for key in ('id','full_number','issue_date')}
        if original is not None and original['vehicle_id']==vehicle_id:
            # A correction belongs to the original work, even after a transfer or
            # plate change. Do not invent a missing historical vehicle snapshot.
            payload['vehicle'] = json.loads(original['payload']).get('vehicle')
        existing = conn.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone()
        origin_id = data.get('origin_id') or None
        if existing:
            require('origin_id' not in data or origin_id==existing['origin_id'],
                    'El documento conserva su origen de conversión. Crea un documento independiente para otro trabajo.','conversion_origin')
            origin_id = existing['origin_id']
        self._validate_conversion(conn,identifier,kind,customer_id,vehicle_id,origin_id,invoice_type,existing)
        if existing:
            require(existing['kind']==kind, 'No puedes cambiar el tipo del documento.')
            require(existing['status']=='draft' or (kind=='order' and existing['status']!='delivered'), 'El documento est\u00e1 cerrado. Crea otro o una rectificativa.')
            require(existing['version']==data.get('version'), 'El documento ha cambiado. Recarga antes de guardar.', 'conflict')
            if existing['status']!='draft':
                previous_payload = json.loads(existing['payload'])
                for key in ('customer','vehicle','issuer','branding','test_document','issued_at'):
                    if key in previous_payload:
                        payload[key] = previous_payload[key]
                # Editing the work preserves its published identity. Explicitly
                # selecting another customer/vehicle captures that selection.
                if existing['customer_id']!=customer_id:
                    payload['customer'] = {key:customer[key] for key in _CUSTOMER_SNAPSHOT_FIELDS}
                if existing['vehicle_id']!=vehicle_id:
                    payload['vehicle'] = dict(vehicle) if vehicle else None
            conn.execute('UPDATE documents SET customer_id=?,vehicle_id=?,issue_date=?,due_date=?,series_id=?,payload=?,base_cents=?,tax_cents=?,total_cents=?,reference_id=?,updated_at=?,version=version+1 WHERE id=?',
                         (customer_id,vehicle_id,issue_date,due_date,data.get('series_id') or None,dumps(payload),totals['base_cents'],totals['tax_cents'],totals['total_cents'],reference_id,now(),identifier))
        else:
            conn.execute('INSERT INTO documents(id,kind,status,customer_id,vehicle_id,issue_date,due_date,series_id,payload,base_cents,tax_cents,total_cents,reference_id,origin_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (identifier,kind,'draft',customer_id,vehicle_id,issue_date,due_date,data.get('series_id') or None,dumps(payload),totals['base_cents'],totals['tax_cents'],totals['total_cents'],reference_id,origin_id,now(),now()))
        self.db.audit(conn,'document.save',identifier,{'kind':kind,'total_cents':totals['total_cents']})
        return self.get(identifier,conn)

    def publish(self,identifier,expected_version=None):
        with self.db.transaction() as conn:
            document = self.get(identifier,conn)
            if document['status']!='draft':
                return document  # Double-click/retry never takes another number.
            from .backups import assert_restore_allows_emission
            assert_restore_allows_emission(self.db)
            if expected_version is not None:
                require(document['version']==expected_version, 'El borrador ha cambiado. Rev\u00edsalo antes de emitir.', 'conflict')
            config = self.settings.get(conn)
            payload = document['payload']
            self._validate_conversion(conn,document['id'],document['kind'],document['customer_id'],document['vehicle_id'],
                                      document['origin_id'],payload['invoice_type'],document)
            totals = calculate(payload['lines'],corrective=payload['invoice_type'].startswith('R'),
                               invoice_type=payload['invoice_type'],tax_adjustments=payload.get('tax_adjustments'))
            require(all(totals[key]==document[key] for key in ('base_cents','tax_cents','total_cents')),
                    'Los importes del borrador necesitan recalcularse. Guarda y revisa el documento antes de emitir.', 'conflict')
            payload.update(totals)
            customer = dict(conn.execute('SELECT * FROM customers WHERE id=?',(document['customer_id'],)).fetchone())
            vehicle = conn.execute('SELECT * FROM vehicles WHERE id=?',(document['vehicle_id'],)).fetchone() if document['vehicle_id'] else None
            original = self.get(document['reference_id'],conn) if payload['invoice_type'].startswith('R') else None
            if original:
                require(original['kind']=='invoice' and original['status'] in ('issued','historical')
                        and original['customer_id']==document['customer_id'], 'La factura original ya no permite esta rectificativa.')
            payload['operation_date']=self._operation_date(payload.get('operation_date'),document['issue_date'],original)
            require(payload['invoice_type'] not in ('R2','R3') or payload.get('tax_adjustments') is not None,
                    'En R2/R3 indica las cuotas de IVA que se rectifican.','tax_adjustment')
            if payload.get('tax_adjustments') is not None:
                require(not payload.get('stock_affect'),'La rectificación exclusiva de cuota no mueve existencias.','tax_adjustment')
                self._validate_tax_adjustments(conn,original,payload['tax_adjustments'],document['id'])
            elif original is not None:
                self._validate_tax_adjustments(conn,original,[],document['id'],commercial_change=payload['taxes'])
            from_original = original is not None and original['vehicle_id']==document['vehicle_id']
            if vehicle:
                require(from_original or vehicle['customer_id']==customer['id'], 'El veh\u00edculo ha cambiado de propietario. Revisa el borrador.')
            if document['kind']=='invoice':
                require(config['company']['legal_name'] and valid_tax_id(config['company']['tax_id']), 'Completa el nombre fiscal y NIF del taller en Configuraci\u00f3n.')
                require(customer['country']=='ES' and valid_tax_id(customer['tax_id']), 'Completa un NIF espa\u00f1ol v\u00e1lido en la ficha del cliente. Esta edici\u00f3n no admite operaciones internacionales.')
                require(customer['address'] and customer['postal_code'] and customer['city'], 'Completa la direcci\u00f3n fiscal del cliente.')
                require(document['issue_date']<=today(), 'No se pueden emitir facturas con fecha futura.')
            expected_kind = 'rectification' if payload['invoice_type'].startswith('R') else document['kind']
            series_id = document['series_id']
            if not series_id:
                candidates = conn.execute('SELECT id,year FROM series WHERE kind=? AND year IN (0,?) AND archived=0 ORDER BY year DESC,label',(expected_kind,int(document['issue_date'][:4]))).fetchall()
                found = candidates[0] if candidates else None
                require(found, 'Crea primero una serie para ese tipo de documento y a\u00f1o en Configuraci\u00f3n.')
                require(sum(row['year']==found['year'] for row in candidates)==1, 'Hay varias series disponibles. Selecciona la serie del documento antes de emitir.')
                series_id = found['id']
            series = conn.execute('SELECT * FROM series WHERE id=? AND archived=0',(series_id,)).fetchone()
            require(series and series['kind']==expected_kind and series['year'] in (0,int(document['issue_date'][:4])), 'La serie no corresponde al tipo de documento o a\u00f1o.')
            previous = conn.execute('SELECT max(issue_date) FROM documents WHERE series_id=? AND full_number IS NOT NULL',(series_id,)).fetchone()[0]
            require(not previous or document['issue_date']>=previous, 'La fecha no puede ser anterior a la \u00faltima factura de la serie.')
            require(series['next_number']<999999999, 'La numeraci\u00f3n de la serie est\u00e1 agotada.')
            full_number = Settings.format_number(series)
            require(not conn.execute('SELECT 1 FROM documents WHERE kind=? AND full_number=?',(document['kind'],full_number)).fetchone(), 'Ese n\u00famero ya existe. Revisa la serie antes de emitir.')
            payload['issuer'] = config['company']
            payload['customer'] = {k:customer[k] for k in _CUSTOMER_SNAPSHOT_FIELDS}
            payload['vehicle'] = original['payload'].get('vehicle') if from_original else (dict(vehicle) if vehicle else None)
            payload['branding'] = {k:config['billing'][k] for k in ('logo_id','watermark_opacity','show_bank')}
            payload['issued_at'] = now()
            document.update(full_number=full_number,sequence=series['next_number'],series_id=series_id)
            from .pdf import validate_printable_text
            validate_printable_text(document)
            # A relation can be inserted while the document is still a draft; commit is all-or-nothing.
            if document['kind']=='invoice':
                payload['fiscal'] = self.fiscal.append(conn,document,payload)
                if payload['stock_affect']:
                    for line in payload['lines']:
                        if line.get('product_id'):
                            product = conn.execute('SELECT * FROM products WHERE id=?',(line['product_id'],)).fetchone()
                            require(product, 'El art\u00edculo enlazado ya no existe.')
                            if product['track_stock']:
                                self.catalogue.move(product['id'],str(-Decimal(line['quantity'])),'Factura '+full_number,
                                                    identifier+':'+str(line['position']),identifier,conn)
                state = 'issued'
            else:
                if config['fiscal']['mode']=='production':
                    # Quotes/orders do not append a fiscal record, but removing
                    # their test mark still requires the same approved runtime.
                    self.fiscal._endpoint('production')
                state = 'sent' if document['kind']=='quote' else 'received'
            payload['test_document'] = _is_test_document(config['fiscal']['mode'])
            conn.execute('UPDATE documents SET status=?,series_id=?,sequence=?,full_number=?,payload=?,updated_at=?,version=version+1 WHERE id=?',
                         (state,series_id,series['next_number'],full_number,dumps(payload),now(),identifier))
            conn.execute('UPDATE series SET next_number=next_number+1,used=used+1 WHERE id=?',(series_id,))
            if vehicle and not from_original and payload['kilometres']>vehicle['km']:
                conn.execute('UPDATE vehicles SET km=?,updated_at=?,version=version+1 WHERE id=?',(payload['kilometres'],now(),vehicle['id']))
            self.db.audit(conn,'document.publish',identifier,{'number':full_number,'total_cents':document['total_cents'],'test_document':payload['test_document']})
            return self.get(identifier,conn)

    def delete_draft(self,identifier):
        with self.db.transaction() as conn:
            row = conn.execute('SELECT status FROM documents WHERE id=?',(identifier,)).fetchone()
            require(row and row['status']=='draft', 'Solo se pueden eliminar borradores.')
            conn.execute('DELETE FROM documents WHERE id=?',(identifier,))
            self.db.audit(conn,'document.delete_draft',identifier,{})
        return {'deleted':True}

    def change_status(self,identifier,status):
        with self.db.transaction() as conn:
            row = conn.execute('SELECT * FROM documents WHERE id=?',(identifier,)).fetchone()
            require(row, 'Documento no encontrado.')
            allowed = {'quote':{'sent','accepted','rejected','expired'}, 'order':{'received','repairing','waiting_parts','ready','delivered'}}
            require(row['kind'] in allowed and status in allowed[row['kind']] and row['status']!='draft', 'Transici\u00f3n de estado no permitida.')
            conn.execute('UPDATE documents SET status=?,updated_at=?,version=version+1 WHERE id=?',(status,now(),identifier))
            self.db.audit(conn,'document.status',identifier,{'from':row['status'],'to':status})
            return self.get(identifier,conn)

    def convert(self,identifier,target='invoice'):
        require(target in ('invoice','quote','order'), 'Destino no admitido.')
        with self.db.transaction() as conn:
            origin = self.get(identifier,conn)
            require(target in {'quote':('order','invoice'),'order':('invoice',)}.get(origin['kind'],()),
                    'Solo se convierte un presupuesto en orden o factura, o una orden en factura.')
            require(origin['status'] not in ('draft','void'), 'Publica el documento antes de convertirlo.')
            family = self._validate_conversion(conn,identifier,origin['kind'],origin['customer_id'],origin['vehicle_id'],
                                               origin['origin_id'],origin['payload']['invoice_type'],origin)
            existing = [item for item in family if item['kind']==target]
            if existing:
                return self.get(existing[0]['id'],conn)
            payload = origin['payload']
            return self._save({'kind':target,'customer_id':origin['customer_id'],'vehicle_id':origin['vehicle_id'],
                               'issue_date':today(),'lines':payload['lines'],'payment_method':payload['payment_method'],
                               'kilometres':payload['kilometres'],'notes':payload['notes'],'origin_id':identifier,
                               'stock_affect':payload.get('stock_affect',False),'footer':payload.get('footer','')},conn)

    @staticmethod
    def _validate_conversion(conn,identifier,kind,customer_id,vehicle_id,origin_id,invoice_type,existing=None):
        """A converted family represents one customer and vehicle throughout."""
        allowed = {'quote':('order','invoice'),'order':('invoice',)}
        if origin_id:
            origin = conn.execute('SELECT * FROM documents WHERE id=?',(origin_id,)).fetchone()
            require(origin and origin['status'] not in ('draft','void','import_reverted')
                    and kind in allowed.get(origin['kind'],()),
                    'El origen debe ser un presupuesto publicado para una orden o factura, o una orden publicada para una factura.',
                    'conversion_origin')
        if not origin_id and existing is None:
            return []
        # Both paths quote -> invoice and quote -> order -> invoice share one
        # family. The transaction also prevents parallel callers from forking it.
        family = conn.execute('''WITH RECURSIVE family(id) AS (
            SELECT ?
            UNION SELECT d.id FROM documents d JOIN family f ON d.origin_id=f.id
            UNION SELECT d.origin_id FROM documents d JOIN family f ON d.id=f.id WHERE d.origin_id IS NOT NULL
        ) SELECT d.* FROM documents d JOIN family f ON f.id=d.id''',(identifier if existing is not None else origin_id,)).fetchall()
        require(len({item['kind'] for item in family})==len(family)
                and not any(item['kind']==kind and item['id']!=identifier for item in family),
                'El origen ya tiene un documento de ese tipo. Ábrelo desde Convertir; no se creará otro.', 'conversion_conflict')
        if origin_id or len(family)>1:
            require(invoice_type=='F1','Una rectificativa referencia su factura original y no procede de una conversión.','conversion_origin')
            require(all(item['customer_id']==customer_id and item['vehicle_id']==vehicle_id
                        for item in family if item['id']!=identifier),
                    'Los documentos convertidos deben conservar el mismo cliente y vehículo. Crea un documento independiente para otro trabajo.',
                    'conversion_identity')
        members = {item['id']:item for item in family}
        for item in family:
            if item['origin_id']:
                parent = members.get(item['origin_id'])
                require(parent is not None and item['kind'] in allowed.get(parent['kind'],())
                        and parent['status'] not in ('draft','void','import_reverted'),
                        'El historial de conversión contiene un origen no válido. Revisa sus documentos.','conversion_origin')
        return family

    @staticmethod
    def _operation_date(value,issue_date,original=None):
        if original is not None:
            source=original['payload']
            source=json.loads(source) if isinstance(source,str) else source
            known=source.get('operation_date')
            if not value:
                require(known or original['status']!='historical',
                        'El histórico no conserva la fecha de operación. Indícala expresamente según el documento original.','operation_date_required')
                value=known or original['issue_date']
        value=iso_date(value or issue_date)
        require(value<=issue_date,'La fecha de operación no puede ser posterior a la fecha de expedición.','operation_date')
        return value

    def _validate_tax_adjustments(self,conn,original,adjustments,exclude_id=None,commercial_change=None):
        require(original is not None,'La cuota rectificativa requiere una factura original.','tax_adjustment')
        root=original
        visited=set()
        while root['reference_id']:
            require(root['id'] not in visited,'La cadena de facturas rectificadas es circular.','integrity')
            visited.add(root['id'])
            root=conn.execute('SELECT * FROM documents WHERE id=?',(root['reference_id'],)).fetchone()
            require(root is not None,'Falta la factura original de la rectificación.','integrity')
        rows=conn.execute('''WITH RECURSIVE family(id) AS (
            SELECT ? UNION SELECT d.id FROM documents d JOIN family f ON d.reference_id=f.id)
            SELECT d.* FROM documents d JOIN family f ON d.id=f.id
            WHERE d.status IN ('issued','historical') AND d.id!=?''',(root['id'],exclude_id or '')).fetchall()
        stored_rows=[json.loads(row['payload']) for row in rows]
        if not adjustments and not any(stored.get('tax_adjustments') is not None for stored in stored_rows):
            return
        available,adjusted={},{}
        for stored in stored_rows:
            require(isinstance(stored.get('taxes'),list) and bool(stored['taxes']),
                    'El original no conserva cuotas por tipo. Documenta su desglose antes de rectificar solo el IVA.','tax_adjustment')
            for tax in stored['taxes']:
                require(tax.get('kind')!='historical' and isinstance(tax.get('tax_cents'),int),
                        'El histórico no conserva cuotas por tipo de IVA. La cuota no puede deducirse del total.','tax_adjustment')
                if tax.get('kind')!='S1':
                    continue
                rate=canonical_tax_rate(tax.get('rate'))
                target=adjusted if stored.get('tax_adjustments') is not None else available
                target[rate]=target.get(rate,0)+tax['tax_cents']
        for tax in commercial_change or []:
            if tax['kind']=='S1':
                rate=tax['rate'];available[rate]=available.get(rate,0)+tax['tax_cents']
        for item in adjustments:
            rate=item['tax_rate']
            require(available.get(rate,0)>0,'El original no contiene cuota positiva documentada de ese tipo.','tax_adjustment_limit')
            adjusted[rate]=adjusted.get(rate,0)+item['tax_cents']
        for rate,balance in adjusted.items():
            base_quota=available.get(rate,0)
            require(base_quota>=0 and -base_quota<=balance<=0,
                    f'La cuota del {rate} % excede el IVA documentado o ya rectificado. Revisa el original y sus correcciones previas.','tax_adjustment_limit')

    def rectify(self,identifier,reason,invoice_type='R4',lines=None,operation_date=None,tax_adjustments=None):
        original = self.get(identifier)
        require(original['kind']=='invoice' and original['status'] in ('issued','historical'), 'Selecciona una factura emitida.')
        require(reason and invoice_type in ('R1','R2','R3','R4'), 'Indica el motivo y tipo de rectificaci\u00f3n.')
        operation_date=self._operation_date(operation_date,today(),original)
        if tax_adjustments is not None:
            tax_adjustments=normalize_tax_adjustments(tax_adjustments,invoice_type)
            if lines is None:
                lines=[{'description':f'Rectificación exclusiva de cuota IVA {item["tax_rate"]} % de {original["full_number"]}',
                        'quantity':'1','unit_price':'0','discount':'0','tax_rate':item['tax_rate'],'tax_kind':'S1'}
                       for item in tax_adjustments]
        if lines is None:
            require(all(line.get('quantity') not in (None,'') and line.get('unit_price') not in (None,'')
                        and line.get('tax_rate') not in (None,'') and line.get('tax_kind','S1') != 'historical'
                        for line in original['payload']['lines']),
                    'El histórico no conserva el desglose completo. Introduce explícitamente los conceptos, cantidades, precios e impuestos de la rectificativa.')
            lines = [{**line,'quantity':str(-Decimal(line['quantity']))} for line in original['payload']['lines']]
        return self.save({'kind':'invoice','customer_id':original['customer_id'],'vehicle_id':original['vehicle_id'],
                          'lines':lines,'reference_id':identifier,'invoice_type':invoice_type,'notes':reason,'issue_date':today(),
                          'operation_date':operation_date,'tax_adjustments':tax_adjustments,
                          'payment_method':original['payload'].get('payment_method') if original['payload'].get('payment_method') in METHODS else self.settings.get()['billing']['payment_method'],
                          'kilometres':original['payload'].get('kilometres') or 0})

    def void(self,identifier,reason,confirmation):
        require(confirmation=='ANULAR' and str(reason).strip(), 'Escribe ANULAR e indica el motivo del error material.')
        with self.db.transaction() as conn:
            document = self.get(identifier,conn)
            require(document['kind']=='invoice' and document['status']=='issued', 'Solo se puede anular una factura emitida aqu\u00ed.')
            require(not document['active_rectifications'],
                    'La factura tiene rectificativas emitidas o en borrador. Revisa las emitidas y elimina los borradores antes de anularla.',
                    'rectifications_exist',document['active_rectifications'])
            require(document['paid_cents']==0, 'Revierte los cobros antes de anular. Una devoluci\u00f3n comercial requiere una rectificativa.')
            self.fiscal.append(conn,document,document['payload'],'anulacion')
            movements = conn.execute('SELECT * FROM stock_movements WHERE document_id=?',(identifier,)).fetchall()
            for movement in movements:
                self.catalogue.move(movement['product_id'],str(-Decimal(movement['quantity'])),'Anulaci\u00f3n '+document['full_number'],'void:'+movement['id'],identifier,conn)
            conn.execute("UPDATE documents SET status='void',version=version+1,updated_at=? WHERE id=?",(now(),identifier))
            self.db.audit(conn,'invoice.void',identifier,{'reason':reason})
            return self.get(identifier,conn)

    def pay(self,identifier,value,method,paid_on,idempotency_key,notes=''):
        require(method in METHODS and idempotency_key, 'Indica la forma de pago y clave de operaci\u00f3n.')
        paid_on = iso_date(paid_on)
        amount_cents = cents(decimal(value,'Importe cobrado',2))
        with self.db.transaction() as conn:
            prior = conn.execute('SELECT * FROM payments WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            if prior:
                require(prior['document_id']==identifier and prior['amount_cents']==amount_cents and prior['method']==method and prior['paid_on']==paid_on, 'La clave de operacion ya corresponde a otro cobro.', 'conflict')
                return self.get(identifier,conn)
            doc = self.get(identifier,conn)
            require(doc['kind']=='invoice' and doc['status'] in ('issued','historical'), 'Solo se registran cobros de facturas emitidas.')
            require(doc['payment_known'], 'El cobro histórico no está documentado. Registra primero su saldo inicial con la evidencia disponible.')
            pending = doc['pending_cents']
            require(amount_cents != 0 and ((0 < amount_cents <= pending) or (pending <= amount_cents < 0)), 'El importe debe corresponder al saldo pendiente, sin excederlo.')
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,NULL,?,?)',(uid(),identifier,amount_cents,method,paid_on,str(notes)[:500],idempotency_key,now()))
            self.db.audit(conn,'payment.add',identifier,{'amount_cents':amount_cents,'method':method})
            return self.get(identifier,conn)

    def record_payment_state(self,identifier,paid_cents,evidence,idempotency_key):
        """Document an unknown imported opening balance without rewriting history."""
        require(isinstance(paid_cents,int) and not isinstance(paid_cents,bool), 'El saldo inicial se expresa en céntimos exactos.')
        require(isinstance(evidence,str) and 5<=len(evidence.strip())<=2000, 'Describe la fuente que acredita el saldo inicial (entre 5 y 2.000 caracteres).')
        require(isinstance(idempotency_key,str) and 1<=len(idempotency_key)<=150, 'Clave de operación no válida.')
        with self.db.transaction() as conn:
            previous = conn.execute('SELECT * FROM document_payment_baselines WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            if previous:
                require(previous['document_id']==identifier and previous['paid_cents']==paid_cents and previous['evidence']==evidence.strip(), 'La clave corresponde a otra conciliación de saldo.', 'conflict')
                return self.get(identifier,conn)
            document = self.get(identifier,conn)
            require(document['kind']=='invoice' and document['status']=='historical' and not document['payment_known'], 'Solo se documenta el saldo inicial de una histórica con cobro desconocido.')
            require(min(0,document['total_cents'])<=paid_cents<=max(0,document['total_cents']), 'El saldo cobrado debe estar comprendido entre cero y el importe de la factura.')
            require(not document['payments'], 'Esta histórica ya tiene movimientos. Revisa la conciliación antes de fijar su saldo inicial.')
            conn.execute('INSERT INTO document_payment_baselines VALUES(?,?,?,?,?)',(identifier,paid_cents,evidence.strip(),idempotency_key,now()))
            self.db.audit(conn,'historical.payment_baseline',identifier,{'paid_cents':paid_cents,'evidence':evidence.strip()})
            return self.get(identifier,conn)

    def adjust_payment_state(self,identifier,paid_cents,evidence,idempotency_key):
        """Append a documented opening-balance correction; it is not a cash receipt."""
        require(isinstance(paid_cents,int) and not isinstance(paid_cents,bool), 'El saldo se expresa en céntimos exactos.')
        require(isinstance(evidence,str) and 5<=len(evidence.strip())<=2000, 'Describe la evidencia de la corrección del saldo.')
        require(isinstance(idempotency_key,str) and 1<=len(idempotency_key)<=150, 'Clave de operación no válida.')
        key = 'opening-adjust:'+idempotency_key
        with self.db.transaction() as conn:
            document = self.get(identifier,conn)
            require(document['kind']=='invoice' and document['status']=='historical' and document['payment_baseline'], 'Primero documenta el saldo inicial desconocido de la histórica.')
            detail = dumps({'paid_cents':paid_cents,'evidence':evidence.strip()})
            prior = conn.execute('SELECT * FROM payments WHERE idempotency_key=?',(key,)).fetchone()
            if prior:
                require(prior['document_id']==identifier and prior['notes']==detail, 'La clave corresponde a otro ajuste.', 'conflict')
                return document
            require(min(0,document['total_cents'])<=paid_cents<=max(0,document['total_cents']), 'El saldo cobrado debe estar entre cero y el importe de la factura.')
            delta = paid_cents-document['paid_cents']
            require(delta!=0, 'La evidencia no cambia el saldo documentado.')
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,NULL,?,?)',(uid(),identifier,delta,'opening_adjustment',today(),detail,key,now()))
            self.db.audit(conn,'historical.payment_adjustment',identifier,{'difference_cents':delta,'evidence':evidence.strip()})
            return self.get(identifier,conn)

    def reverse_payment(self,payment_id,reason):
        require(str(reason).strip(), 'Indica por qu\u00e9 reviertes el cobro.')
        with self.db.transaction() as conn:
            p = conn.execute('SELECT * FROM payments WHERE id=?',(payment_id,)).fetchone()
            require(p and not p['reversal_of'], 'Cobro no v\u00e1lido.')
            require(p['method'] != 'opening_adjustment', 'Corrige el saldo documentado con su evidencia; este ajuste no es un cobro.')
            require(not conn.execute('SELECT 1 FROM payments WHERE reversal_of=?',(payment_id,)).fetchone(), 'Este cobro ya est\u00e1 revertido.')
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',(uid(),p['document_id'],-p['amount_cents'],p['method'],today(),str(reason)[:500],payment_id,'reverse:'+payment_id,now()))
            self.db.audit(conn,'payment.reverse',payment_id,{'reason':reason})
            return self.get(p['document_id'],conn)

    def concepts(self,query=''):
        q = normalized(query)
        with self.db.read() as conn:
            docs = conn.execute("SELECT payload FROM documents WHERE status NOT IN ('import_reverted','void') ORDER BY updated_at DESC LIMIT 200").fetchall()
        found = {}
        for document in docs:
            for line in json.loads(document['payload'])['lines']:
                if line.get('unit_price') in (None, '') or line.get('tax_rate') in (None, '') or line.get('tax_kind','S1') != 'S1':
                    continue
                key = normalized(line['description'])
                if q in key and key not in found:
                    found[key] = {k:line[k] for k in ('description','unit_price','tax_rate')}
        return list(found.values())[:30]
