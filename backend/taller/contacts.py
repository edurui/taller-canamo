import re
from .db import uid, dumps
from .errors import AppError, require
from .validation import normalized, plate, clean_text, now, iso_date, valid_tax_id

CUSTOMER_FIELDS = ['legacy_code','name','tax_id','address','postal_code','city','province','country','phone','phone2','email','notes']


def sql_like(text):
    return text.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')


class Contacts:
    def __init__(self, db):
        self.db = db

    def save_customer(self, data):
        identifier = data.get('id') or uid()
        values = {key: clean_text(data,key,4000 if key=='notes' else 250, key=='name') for key in CUSTOMER_FIELDS}
        values['tax_id'] = plate(values['tax_id'])
        values['legacy_code'] = values['legacy_code'] or None
        values['country'] = (values['country'] or 'ES').upper()
        require(re.fullmatch(r'[A-Z]{2}', values['country']), 'Indica el país con dos letras, por ejemplo ES, PT o FR.')
        require(not values['email'] or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['email']), 'El correo electr\u00f3nico no es v\u00e1lido.')
        if values['country'] == 'ES':
            require(not values['postal_code'] or re.fullmatch(r'\d{5}',values['postal_code']), 'El c\u00f3digo postal debe tener 5 cifras.')
        else:
            require(len(values['postal_code']) <= 20 and not re.search(r'[\r\n\t]', values['postal_code']),
                    'El código postal admite hasta 20 caracteres en una sola línea.')
        search = normalized(' '.join(str(v or '') for k,v in values.items() if k!='notes')) + ' ' + plate(values['phone']) + ' ' + plate(values['phone2'])
        with self.db.transaction() as conn:
            existing = conn.execute('SELECT * FROM customers WHERE id=?',(identifier,)).fetchone()
            if existing:
                require(data.get('version') == existing['version'], 'El cliente ha cambiado. Recarga su ficha antes de guardar.', 'conflict')
                conn.execute('UPDATE customers SET '+','.join(k+'=?' for k in CUSTOMER_FIELDS)+',search_text=?,updated_at=?,version=version+1 WHERE id=?',(*values.values(),search,now(),identifier))
            else:
                conn.execute('INSERT INTO customers(id,'+','.join(CUSTOMER_FIELDS)+',search_text,created_at,updated_at) VALUES('+','.join('?' for _ in range(len(CUSTOMER_FIELDS)+4))+')',(identifier,*values.values(),search,now(),now()))
            self.db.audit(conn,'customer.save',identifier,{'name':values['name'],'version':existing['version']+1 if existing else 1})
        return self.customer(identifier)

    def customer(self, identifier):
        with self.db.read() as conn:
            row = conn.execute('SELECT * FROM customers WHERE id=?',(identifier,)).fetchone()
            require(row is not None, 'No se encuentra el cliente.', 'not_found')
            result = dict(row)
            result['vehicles'] = [dict(v) for v in conn.execute('SELECT * FROM vehicles WHERE customer_id=? ORDER BY archived,plate',(identifier,))]
            result['tax_id_valid'] = valid_tax_id(result['tax_id']) if result['tax_id'] else False
            return result

    def archive_customer(self, identifier, archived=True):
        with self.db.transaction() as conn:
            require(conn.execute('SELECT 1 FROM customers WHERE id=?',(identifier,)).fetchone(), 'Cliente no encontrado.')
            conn.execute('UPDATE customers SET archived=?,version=version+1,updated_at=? WHERE id=?',(int(bool(archived)),now(),identifier))
            self.db.audit(conn,'customer.archive',identifier,{'archived':bool(archived)})
        return {'id':identifier}

    def search(self, query='', limit=12):
        query = normalized(query)[:100]
        if not query or not plate(query):
            return []
        tokens = query.split()[:8]
        compact = plate(query)
        conditions, params = [], []
        for token in tokens:
            variants = [token]
            compact_token = normalized(plate(token))
            if compact_token and compact_token != token:
                variants.append(compact_token)
            text_matches = ["c.search_text LIKE ? ESCAPE '\\'" for _ in variants]
            params.extend('%'+sql_like(value)+'%' for value in variants)
            conditions.append('('+' OR '.join(text_matches)+" OR normalized(v.plate) LIKE ? ESCAPE '\\' OR v.plate_normalized LIKE ? ESCAPE '\\')")
            params.extend(['%'+sql_like(token)+'%','%'+sql_like(plate(token))+'%'])
        params.append(max(1,min(int(limit),100)))
        # A customer's normalization is shared by their vehicle rows. Ranking
        # precedes LIMIT, so an exact old code/phone/NIF cannot be truncated by
        # many partial matches or outranked by a plate prefix.
        customer_ranks = {}
        def match_rank(identifier, name, legacy_code, tax_id, phone, phone2, vehicle_plate):
            if identifier not in customer_ranks:
                words = (normalized(name), normalized(legacy_code))
                identifiers = (plate(tax_id), plate(phone), plate(phone2))
                customer_ranks[identifier] = (
                    0 if query in words or compact in identifiers else
                    1 if any(value.startswith(query) for value in words)
                         or any(value.startswith(compact) for value in identifiers) else 2)
            vehicle_plate = vehicle_plate or ''
            vehicle_rank = 0 if vehicle_plate == compact else 1 if vehicle_plate.startswith(compact) else 2
            return min(customer_ranks[identifier], vehicle_rank)
        with self.db.read() as conn:
            conn.create_function('contact_match_rank', 7, match_rank, deterministic=True)
            rows = conn.execute('''SELECT c.id AS customer_id,c.name,c.phone,c.tax_id,c.legacy_code,
                v.id AS vehicle_id,v.plate,v.make,v.model FROM customers c
                LEFT JOIN vehicles v ON v.customer_id=c.id AND v.archived=0
                WHERE c.archived=0 AND '''+' AND '.join(conditions)+'''
                ORDER BY contact_match_rank(c.id,c.name,c.legacy_code,c.tax_id,c.phone,c.phone2,v.plate_normalized),
                c.name,v.plate,c.id,v.id LIMIT ?''',params)
            return [dict(r) for r in rows]

    def list_customers(self, query='', page=0, archived=False):
        query = normalized(query)[:100]
        params = [int(bool(archived))]
        condition = 'c.archived=?'
        if query:
            condition += " AND (c.search_text LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM vehicles vv WHERE vv.customer_id=c.id AND vv.plate_normalized LIKE ? ESCAPE '\\'))"
            params.extend(['%'+sql_like(query)+'%','%'+sql_like(plate(query))+'%'])
        with self.db.read() as conn:
            count = conn.execute('SELECT count(*) FROM customers c WHERE '+condition,params).fetchone()[0]
            rows = conn.execute('''SELECT c.*,(SELECT group_concat(v.plate, ', ') FROM vehicles v WHERE v.customer_id=c.id AND v.archived=0) AS plates,
                (SELECT max(d.issue_date) FROM documents d WHERE d.customer_id=c.id AND d.kind='invoice') AS last_visit
                FROM customers c WHERE '''+condition+' ORDER BY normalized(c.name) LIMIT 50 OFFSET ?',(*params,max(0,int(page))*50))
            return {'items':[dict(r) for r in rows],'total':count,'page':page}

    def save_vehicle(self, data):
        identifier = data.get('id') or uid()
        normalized_plate = plate(data.get('plate'))
        require(3 <= len(normalized_plate) <= 15, 'Introduce una matr\u00edcula o identificador v\u00e1lido.')
        owner = data.get('customer_id')
        km = data.get('km',0)
        require(isinstance(km,int) and not isinstance(km,bool) and 0<=km<=10000000, 'Kilometraje no v\u00e1lido.')
        fields = {key:clean_text(data,key,4000 if key=='notes' else 150) for key in ['plate','make','model','vin','kind','itv_date','next_service','notes']}
        for key in ('itv_date','next_service'):
            if fields[key]: fields[key] = iso_date(fields[key])
        fields['plate'] = fields['plate'].upper()
        with self.db.transaction() as conn:
            require(conn.execute('SELECT 1 FROM customers WHERE id=?',(owner,)).fetchone(), 'Selecciona un cliente existente.')
            existing = conn.execute('SELECT * FROM vehicles WHERE id=?',(identifier,)).fetchone()
            if existing:
                require(existing['version']==data.get('version'), 'El veh\u00edculo ha cambiado. Recarga la ficha.', 'conflict')
                require(existing['customer_id']==owner, 'Utiliza Cambiar propietario para conservar el historial de titularidad.')
                require(km>=existing['km'] or bool(data.get('confirm_km_correction')), 'El kilometraje es menor que el anterior. Confirma que es una correcci\u00f3n.')
                conn.execute('UPDATE vehicles SET '+','.join(k+'=?' for k in fields)+',plate_normalized=?,km=?,updated_at=?,version=version+1 WHERE id=?',(*fields.values(),normalized_plate,km,now(),identifier))
            else:
                conn.execute('INSERT INTO vehicles(id,customer_id,'+','.join(fields)+',plate_normalized,km,created_at,updated_at) VALUES('+','.join('?' for _ in range(len(fields)+6))+')',(identifier,owner,*fields.values(),normalized_plate,km,now(),now()))
                conn.execute('INSERT INTO vehicle_owners(id,vehicle_id,customer_id,from_date) VALUES(?,?,?,?)',(uid(),identifier,owner,now()))
            self.db.audit(conn,'vehicle.save',identifier,{'plate':normalized_plate,'km':km})
        return {'id':identifier}

    def list_vehicles(self,query=''):
        with self.db.read() as conn:
            q = '%'+sql_like(normalized(query))+'%'
            cp = '%'+sql_like(plate(query))+'%'
            rows = conn.execute("SELECT v.*,c.name AS customer_name,c.phone FROM vehicles v JOIN customers c ON c.id=v.customer_id WHERE v.archived=0 AND (v.plate_normalized LIKE ? ESCAPE '\\' OR normalized(v.make||' '||v.model||' '||c.name) LIKE ? ESCAPE '\\') ORDER BY v.updated_at DESC LIMIT 300",(cp,q))
            return [dict(r) for r in rows]

    def vehicle(self, identifier):
        with self.db.read() as conn:
            row = conn.execute('SELECT v.*,c.name AS customer_name,c.phone FROM vehicles v JOIN customers c ON c.id=v.customer_id WHERE v.id=?',(identifier,)).fetchone()
            require(row, 'Vehículo no encontrado.', 'not_found')
            return {**dict(row), 'owners':[dict(owner) for owner in conn.execute(
                'SELECT o.*,c.name AS customer_name FROM vehicle_owners o JOIN customers c ON c.id=o.customer_id WHERE o.vehicle_id=? ORDER BY o.from_date,o.rowid',(identifier,))]}

    def vehicles_page(self, query='', page=0):
        require(isinstance(page,int) and not isinstance(page,bool) and page>=0, 'Página no válida.')
        if query and not plate(query):
            return {'items':[], 'total':0, 'page':page}
        with self.db.read() as conn:
            params = ('%'+sql_like(plate(query))+'%', '%'+sql_like(normalized(query))+'%')
            source = " FROM vehicles v JOIN customers c ON c.id=v.customer_id WHERE v.archived=0 AND (v.plate_normalized LIKE ? ESCAPE '\\' OR normalized(v.make||' '||v.model||' '||c.name) LIKE ? ESCAPE '\\')"
            count = conn.execute('SELECT count(*)'+source, params).fetchone()[0]
            rows = conn.execute('SELECT v.*,c.name AS customer_name,c.phone'+source+' ORDER BY v.plate,v.id LIMIT 50 OFFSET ?',(*params,page*50))
            return {'items':[dict(row) for row in rows], 'total':count, 'page':page}

    def transfer_vehicle(self, identifier, customer_id, reason, expected_version=None):
        require(str(reason).strip(), 'Indica el motivo del cambio de propietario.')
        with self.db.transaction() as conn:
            old = conn.execute('SELECT * FROM vehicles WHERE id=?',(identifier,)).fetchone()
            require(old, 'Veh\u00edculo no encontrado.')
            require(expected_version is None or expected_version==old['version'], 'El vehículo ha cambiado. Revisa el titular actual antes de transferirlo.', 'conflict')
            require(old['customer_id']!=customer_id, 'Ese cliente ya es el propietario.')
            require(conn.execute('SELECT 1 FROM customers WHERE id=? AND archived=0',(customer_id,)).fetchone(), 'Cliente no encontrado.')
            conn.execute('UPDATE vehicle_owners SET until_date=? WHERE vehicle_id=? AND until_date IS NULL',(now(),identifier))
            conn.execute('INSERT INTO vehicle_owners VALUES(?,?,?,?,NULL,?)',(uid(),identifier,customer_id,now(),str(reason)[:500]))
            conn.execute('UPDATE vehicles SET customer_id=?,updated_at=?,version=version+1 WHERE id=?',(customer_id,now(),identifier))
            self.db.audit(conn,'vehicle.transfer',identifier,{'from':old['customer_id'],'to':customer_id,'reason':reason})
        return {'id':identifier}
