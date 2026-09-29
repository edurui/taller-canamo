from decimal import Decimal
import hashlib
import re
from .db import dumps
from .db import uid
from .errors import require
from .money import decimal, canonical_tax_rate
from .validation import now, clean_text


class Catalogue:
    def __init__(self,db,settings):
        self.db,self.settings = db,settings

    @staticmethod
    def _revision(row):
        return hashlib.sha256(dumps(dict(row)).encode()).hexdigest()

    def products(self,include_archived=False):
        with self.db.read() as conn:
            result = [dict(r) for r in conn.execute('SELECT p.*,s.name AS supplier_name FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id '+('' if include_archived else 'WHERE p.archived=0 ')+'ORDER BY p.name')]
            for row in result:
                row['revision'] = self._revision({key:value for key,value in row.items() if key!='supplier_name'})
        for row in result:
            row['low_stock'] = bool(row['track_stock']) and Decimal(row['stock']) <= Decimal(row['min_stock'])
        return result

    def save_product(self,data):
        identifier = data.get('id') or uid()
        name = clean_text(data,'name',200,True)
        sku = clean_text(data,'sku',80) or None
        price = decimal(data.get('unit_price','0'),'Precio')
        cost = decimal(data.get('cost_price','0'),'Coste')
        minimum = decimal(data.get('min_stock','0'),'Stock m\u00ednimo',3)
        require(price>=0 and cost>=0 and minimum>=0, 'Precio, coste y m\u00ednimo no pueden ser negativos.')
        rate = canonical_tax_rate(data.get('tax_rate','21'))
        with self.db.transaction() as conn:
            exists = conn.execute('SELECT * FROM products WHERE id=?',(identifier,)).fetchone()
            if exists and data.get('revision'):
                require(data['revision']==self._revision(exists),'El artículo ha cambiado. Vuelve a abrirlo.','conflict')
            require(not exists or data.get('track_stock',True) or Decimal(exists['stock'])==0,
                    'Deja las existencias a cero mediante un movimiento con motivo antes de desactivar el control.')
            if data.get('supplier_id'):
                supplier = conn.execute('SELECT * FROM suppliers WHERE id=?',(data['supplier_id'],)).fetchone()
                require(supplier and (not supplier['archived'] or (exists and exists['supplier_id']==supplier['id'])), 'Selecciona un proveedor activo.')
            require(not sku or not conn.execute('SELECT 1 FROM products WHERE lower(sku)=lower(?) AND id!=?',(sku,identifier)).fetchone(),
                    'Esa referencia de artículo ya existe.')
            values = (sku,name,data.get('supplier_id') or None,str(price),str(cost),rate,int(bool(data.get('track_stock',True))),str(minimum),clean_text(data,'notes',4000))
            if exists:
                conn.execute('UPDATE products SET sku=?,name=?,supplier_id=?,unit_price=?,cost_price=?,tax_rate=?,track_stock=?,min_stock=?,notes=? WHERE id=?',(*values,identifier))
            else:
                conn.execute('INSERT INTO products(id,sku,name,supplier_id,unit_price,cost_price,tax_rate,track_stock,min_stock,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',(identifier,*values))
            self.db.audit(conn,'product.save',identifier,{'name':name})
            saved = dict(conn.execute('SELECT * FROM products WHERE id=?',(identifier,)).fetchone())
        return {**saved,'revision':self._revision(saved)}

    def move(self, product_id, quantity, reason, idempotency_key, document_id=None, conn=None):
        if conn is None:
            with self.db.transaction() as current:
                return self.move(product_id,quantity,reason,idempotency_key,document_id,current)
        require(isinstance(idempotency_key,str) and 0<len(idempotency_key)<=120, 'Falta la clave de idempotencia.')
        require(isinstance(reason,str) and reason.strip(), 'Indica el motivo del movimiento.')
        reason = reason[:500]
        change = decimal(quantity,'Cantidad',3)
        require(change != 0, 'El movimiento no puede ser cero.')
        prior = conn.execute('SELECT * FROM stock_movements WHERE idempotency_key=?',(idempotency_key,)).fetchone()
        if prior:
            require(prior['product_id']==product_id and Decimal(prior['quantity'])==change
                    and prior['document_id']==document_id and prior['reason']==reason,
                    'La clave de operaci\u00f3n ya corresponde a otro movimiento.', 'conflict')
            return {'id':prior['id'],'repeated':True}
        product = conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
        require(product, 'Artículo no encontrado.')
        restoring_document = document_id is not None and change>0
        require((product['track_stock'] and not product['archived']) or restoring_document,
                'El artículo está archivado o no controla existencias.')
        if restoring_document and (product['archived'] or not product['track_stock']):
            conn.execute('UPDATE products SET archived=0,track_stock=1 WHERE id=?',(product_id,))
            self.db.audit(conn,'product.reactivate_for_return',product_id,{'document_id':document_id})
        final = Decimal(product['stock']) + change
        require(final>=0 or self.settings.get(conn)['billing']['allow_negative_stock'], 'No hay stock suficiente de '+product['name']+'. Registra la entrada o revisa las unidades.')
        identifier = uid()
        conn.execute('UPDATE products SET stock=? WHERE id=?',(str(final),product_id))
        conn.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?)',(identifier,product_id,str(change),reason,document_id,idempotency_key,now()))
        self.db.audit(conn,'stock.move',identifier,{'product':product_id,'quantity':str(change),'stock':str(final)})
        return {'id':identifier,'stock':str(final)}

    def movements(self,product_id,page=0):
        require(type(page) is int and page>=0, 'Página no válida.')
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM stock_movements WHERE product_id=? ORDER BY created_at DESC,rowid DESC LIMIT 200 OFFSET ?',(product_id,page*200))]

    def suppliers(self,include_archived=False):
        with self.db.read() as conn:
            return [{**dict(r),'revision':self._revision(r)} for r in conn.execute('SELECT * FROM suppliers '+('' if include_archived else 'WHERE archived=0 ')+'ORDER BY name')]

    def save_supplier(self,data):
        identifier = data.get('id') or uid()
        values = [clean_text(data,k,4000 if k=='notes' else 200,k=='name') for k in ('name','tax_id','phone','email','notes')]
        require(not values[3] or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values[3]), 'El correo electrónico no es válido.')
        with self.db.transaction() as conn:
            previous = conn.execute('SELECT * FROM suppliers WHERE id=?',(identifier,)).fetchone()
            if previous and data.get('revision'):
                require(data['revision']==self._revision(previous),'El proveedor ha cambiado. Vuelve a abrirlo.','conflict')
            conn.execute('INSERT INTO suppliers(id,name,tax_id,phone,email,notes) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,tax_id=excluded.tax_id,phone=excluded.phone,email=excluded.email,notes=excluded.notes',(identifier,*values))
            self.db.audit(conn,'supplier.save',identifier,{'name':values[0]})
            saved = dict(conn.execute('SELECT * FROM suppliers WHERE id=?',(identifier,)).fetchone())
        return {**saved,'revision':self._revision(saved)}

    def archive_product(self,identifier,archived=True):
        require(type(archived) is bool, 'Estado de archivo no válido.')
        with self.db.transaction() as conn:
            product = conn.execute('SELECT * FROM products WHERE id=?',(identifier,)).fetchone()
            require(product, 'Artículo no encontrado.')
            require(not archived or Decimal(product['stock'])==0, 'Antes de archivar, deja las existencias a cero con un movimiento justificado.')
            conn.execute('UPDATE products SET archived=? WHERE id=?',(int(bool(archived)),identifier))
            self.db.audit(conn,'product.archive',identifier,{'archived':bool(archived)})
        return {'archived':bool(archived)}

    def archive_supplier(self,identifier,archived=True):
        require(type(archived) is bool, 'Estado de archivo no válido.')
        with self.db.transaction() as conn:
            require(conn.execute('SELECT 1 FROM suppliers WHERE id=?',(identifier,)).fetchone(), 'Proveedor no encontrado.')
            conn.execute('UPDATE suppliers SET archived=? WHERE id=?',(int(bool(archived)),identifier))
            self.db.audit(conn,'supplier.archive',identifier,{'archived':bool(archived)})
        return {'archived':bool(archived)}

    def adjust_stock(self,product_id,target,expected_stock,reason,idempotency_key):
        final = decimal(target,'Existencias contadas',3)
        expected = decimal(expected_stock,'Existencias anteriores',3)
        with self.db.transaction() as conn:
            prior = conn.execute('SELECT * FROM stock_movements WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            product = conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
            require(product and product['track_stock'] and not product['archived'], 'Artículo no disponible para recuento.')
            if not prior:
                require(Decimal(product['stock'])==expected, 'Las existencias han cambiado. Reabre el recuento.','conflict')
            detail = 'Recuento '+format(expected.normalize(),'f')+' → '+format(final.normalize(),'f')+' · '+clean_text({'reason':reason},'reason',400,True)
            require(final!=expected, 'El recuento coincide; no hace falta registrar un movimiento.')
            return self.move(product_id,str(final-expected),detail,idempotency_key,conn=conn)
