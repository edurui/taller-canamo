import base64
import hashlib
import io
import json
import re
from datetime import datetime
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import uid, dumps
from .errors import require, AppError
from .validation import valid_iban, valid_tax_id, plate, TZ
from .files import atomic_write
from .money import decimal

DEFAULTS = {
 'company': {'trading_name': 'Talleres El C\u00e1\u00f1amo', 'legal_name': '', 'tax_id': '',
             'address': 'Calle Torres Quevedo, 22', 'postal_code': '41300',
             'city': 'San Jos\u00e9 de la Rinconada', 'province': 'Sevilla', 'country': 'ES',
             'phone': '615 83 39 61', 'email': '', 'iban': ''},
 'billing': {'vat': '21', 'payment_method': 'cash', 'due_days': 0, 'quote_days': 30, 'labor_rate': '0.00',
             'footer': 'Gracias por confiar en nosotros.', 'watermark_opacity': 0.06,
             'logo_id': '', 'show_bank': False, 'allow_negative_stock': False},
 'appearance': {'theme': 'light', 'font_size': 'normal', 'high_contrast': False,
                'extras': True, 'calendar_start': 'month'},
 'agenda': {'reminder_minutes': 15, 'sound': True, 'desktop_notifications': False,
            'work_start': '08:30', 'work_end': '20:00', 'work_days': [1,2,3,4,5]},
 'backup': {'daily': True, 'on_close': True, 'external_directory': '', 'last_success': ''},
 'fiscal': {'mode': 'local_test', 'producer_name': '', 'producer_tax_id': '',
            'system_id': 'EC', 'installation_id': '', 'declaration_text': '',
            'certificate_info': None},
 'assistant': {'enabled': False, 'model': '', 'send_customer_data': False},
 'onboarding_done': False
}


class Settings:
    def __init__(self, db):
        self.db = db
        with db.transaction() as conn:
            if not conn.execute('SELECT 1 FROM settings').fetchone():
                defaults = json.loads(dumps(DEFAULTS))
                defaults['fiscal']['installation_id'] = uid()
                conn.execute('INSERT INTO settings(id,data) VALUES(1,?)', (dumps(defaults),))
                year = datetime.now(TZ).year
                for kind, label, prefix in [('invoice','Facturas','FAC-{YYYY}-'), ('rectification','Rectificativas','REC-{YYYY}-'), ('quote','Presupuestos','PRE-{YYYY}-'), ('order','\u00d3rdenes','OT-{YYYY}-')]:
                    conn.execute('INSERT INTO series(id,kind,label,prefix,year,padding,next_number) VALUES(?,?,?,?,?,5,1)', (uid(),kind,label,prefix,year))

    def get(self, conn=None):
        if conn is None:
            with self.db.read() as current:
                return self.get(current)
        stored = json.loads(conn.execute('SELECT data FROM settings WHERE id=1').fetchone()['data'])
        # Backfill new optional settings for existing installations without losing
        # internal keys or rewriting an immutable document's saved configuration.
        return {**DEFAULTS, **stored, **{
            key: {**value, **stored.get(key, {})} for key, value in DEFAULTS.items() if isinstance(value, dict)}}

    def save(self, section, values):
        allowed = set(DEFAULTS) - {'onboarding_done'}
        require(section in allowed, 'Secci\u00f3n de configuraci\u00f3n no admitida.')
        require(isinstance(values, dict), 'Configuraci\u00f3n no v\u00e1lida.')
        require(set(values) <= set(DEFAULTS[section]), 'Hay opciones de configuraci\u00f3n desconocidas.')
        protected = {'certificate_info', 'installation_id', 'last_success', 'logo_id'}
        require(not (set(values) & protected), 'Este dato se configura mediante su acci\u00f3n espec\u00edfica.')
        with self.db.transaction() as conn:
            config = self.get(conn)
            updated = {**config[section], **values}
            if section == 'company':
                require(len(str(updated['trading_name']).strip()) > 0, 'Introduce el nombre del taller.')
                require(all(isinstance(v, str) and len(v) <= 300 for v in updated.values()), 'Datos del taller demasiado largos.')
                if updated['tax_id']:
                    require(valid_tax_id(updated['tax_id']), 'El NIF del emisor no es v\u00e1lido.')
                    updated['tax_id'] = plate(updated['tax_id'])
                if updated['iban']:
                    require(valid_iban(updated['iban']), 'El IBAN no es v\u00e1lido.')
                    updated['iban'] = re.sub(r'\s+', '', updated['iban']).upper()
                previous_nif = config['company']['tax_id']
                if previous_nif and previous_nif != updated['tax_id']:
                    count = conn.execute("SELECT count(*) FROM fiscal_records WHERE environment!='local_test'").fetchone()[0]
                    require(count == 0, 'No cambies de obligado tributario en una instalaci\u00f3n con registros fiscales.')
                require(updated['country'] == 'ES', 'Esta edici\u00f3n est\u00e1 limitada a un emisor establecido en Espa\u00f1a.')
            if section == 'appearance':
                require(updated['theme'] in ('light','dark','system'), 'Tema no v\u00e1lido.')
                require(updated['font_size'] in ('normal','large','extra'), 'Tama\u00f1o no v\u00e1lido.')
                require(updated['calendar_start'] in ('month','week','day'), 'Vista no v\u00e1lida.')
            if section == 'billing':
                rate = decimal(updated['labor_rate'], 'Tarifa de mano de obra', 4)
                require(rate >= 0, 'La tarifa de mano de obra no puede ser negativa.')
                updated['labor_rate'] = str(rate)
                require(updated['vat'] in ('21','10','4','0'), 'IVA no admitido.')
                require(updated['payment_method'] in ('cash','card','transfer','bizum','other'), 'Forma de pago no admitida.')
                require(isinstance(updated['due_days'], int) and 0 <= updated['due_days'] <= 365, 'Vencimiento: entre 0 y 365 d\u00edas.')
                require(isinstance(updated['quote_days'], int) and 1 <= updated['quote_days'] <= 365, 'Validez: entre 1 y 365 d\u00edas.')
                require(0 <= updated['watermark_opacity'] <= 0.15, 'Marca de agua: entre 0 y 0,15.')
                require(isinstance(updated['footer'], str) and len(updated['footer']) <= 800, 'Pie demasiado largo.')
            if section == 'agenda':
                require(updated['reminder_minutes'] in (0,5,10,15,30,60,120,1440,2880,10080), 'Aviso no admitido.')
                require(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', updated['work_start']) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', updated['work_end']), 'Horario no v\u00e1lido.')
                require(updated['work_start'] < updated['work_end'], 'La hora de fin debe ser posterior.')
                require(set(updated['work_days']) <= {0,1,2,3,4,5,6}, 'D\u00edas no v\u00e1lidos.')
            if section == 'fiscal':
                require(all(isinstance(updated[key],str) for key in ('mode','producer_name','producer_tax_id','system_id','declaration_text')),
                        'Los datos de configuración fiscal deben ser texto.')
                require(updated['mode'] in ('local_test','aeat_test','production'), 'Entorno fiscal no admitido.')
                require(len(updated['producer_name'])<=120,'El nombre del productor supera 120 caracteres.')
                if updated['producer_tax_id']:
                    require(valid_tax_id(updated['producer_tax_id']), 'El NIF del productor no es v\u00e1lido.')
                    updated['producer_tax_id'] = plate(updated['producer_tax_id'])
                require(re.fullmatch(r'[A-Za-z0-9]{2}', updated['system_id']), 'El identificador del SIF debe tener 2 caracteres.')
                require(len(updated['declaration_text']) <= 15000, 'Declaraci\u00f3n demasiado larga.')
                if updated['mode'] != config['fiscal']['mode']:
                    pending = conn.execute("SELECT count(*) FROM fiscal_outbox WHERE status IN ('pending','retry','sending','uncertain','duplicate_review','invalid_local','reconciliation_conflict')").fetchone()[0]
                    require(pending == 0, 'Resuelve primero los env\u00edos pendientes antes de cambiar de entorno.')
                if updated['mode']=='production':
                    from .certificates import Certificates
                    from .fiscal import Fiscal
                    candidate={**config,'fiscal':updated}
                    readiness=Fiscal(self.db,self,Certificates(self.db,self))._readiness(candidate)
                    require(readiness['production_ready'],
                            'Producción bloqueada: '+'; '.join(item['message'] for item in readiness['problems']),
                            'production_blocked')
            if section == 'assistant':
                require(isinstance(updated['enabled'], bool), 'La activación de asistencia debe ser sí o no.')
                require(isinstance(updated['model'], str) and len(updated['model']) <= 100 and not re.search(r'[^a-zA-Z0-9_:.\-/]',updated['model']), 'Modelo local no v\u00e1lido.')
                require(not updated['model'].lower().endswith((':cloud','-cloud')), 'Selecciona un modelo local; los modelos cloud no están habilitados.')
                require(updated['send_customer_data'] is False, 'Esta versi\u00f3n no env\u00eda datos identificativos al asistente.')
            if section == 'backup':
                require(isinstance(updated['external_directory'],str) and len(updated['external_directory']) <= 1000, 'Ruta no v\u00e1lida.')
                if updated['external_directory']:
                    from pathlib import Path
                    p = Path(updated['external_directory'])
                    require(p.is_absolute(), 'Selecciona una ruta absoluta para la segunda copia.')
                    require(p.resolve() != self.db.root, 'No utilices la carpeta de trabajo como segunda copia.')
            config[section] = updated
            conn.execute('UPDATE settings SET data=? WHERE id=1', (dumps(config),))
            self.db.audit(conn, 'settings.' + section, '1', {'changed_fields': list(values)})
            return config

    def internal_update(self, section, key, value):
        with self.db.transaction() as conn:
            config = self.get(conn)
            config[section][key] = value
            conn.execute('UPDATE settings SET data=? WHERE id=1', (dumps(config),))

    def logo(self, content=None):
        if content:
            require(len(content) <= 7_000_000, 'El logo debe pesar menos de 4 MB.')
            try:
                data = base64.b64decode(content, validate=True)
                require(len(data) <= 4_000_000, 'El logo debe pesar menos de 4 MB.')
                image = Image.open(io.BytesIO(data))
                require(image.format in ('PNG','JPEG','WEBP'), 'Utiliza PNG, JPEG o WebP. No se admiten SVG activos.')
                require(image.width*image.height <= 16_000_000, 'La imagen es demasiado grande.')
                image = ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((1600,1600))
                output = io.BytesIO(); image.save(output, format='PNG', optimize=True)
                digest = hashlib.sha256(output.getvalue()).hexdigest() + '.png'
            except (UnidentifiedImageError, ValueError, OSError) as error:
                raise AppError('No se ha podido leer el logo.') from error
        else:
            digest = ''
        with self.db.lock:
            if digest:
                atomic_write(self.db.root/'assets'/digest,output.getvalue())
            self.internal_update('billing','logo_id',digest)
        return {'logo_id': digest}

    def list_series(self):
        with self.db.read() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM series ORDER BY year DESC,kind,label')]

    @staticmethod
    def format_number(series, number=None):
        prefix = series['prefix'].replace('{YYYY}', str(series['year'])).replace('{YY}', str(series['year'])[-2:])
        return prefix + str(number if number is not None else series['next_number']).zfill(series['padding'])

    def save_series(self, data):
        kind = data.get('kind','invoice')
        require(kind in ('invoice','rectification','quote','order'), 'Tipo de serie no v\u00e1lido.')
        label, prefix = str(data.get('label','')).strip(), str(data.get('prefix','')).strip()
        require(label and len(label) <= 100, 'Pon un nombre a la serie.')
        require(len(prefix) <= 35 and re.fullmatch(r'[A-Za-z0-9/{}_. -]*', prefix), 'Prefijo de serie no v\u00e1lido.')
        require('{' not in prefix.replace('{YYYY}','').replace('{YY}',''), 'Usa {YYYY} o {YY} para el a\u00f1o.')
        year, padding, next_number = data.get('year'), data.get('padding'), data.get('next_number')
        require(all(isinstance(x,int) and not isinstance(x,bool) for x in (year,padding,next_number)), 'A\u00f1o, cifras y siguiente n\u00famero deben ser enteros.')
        require((year == 0 or 2000 <= year <= 2200) and 1 <= padding <= 8 and 1 <= next_number <= 999999999, 'Numeraci\u00f3n fuera de rango.')
        require(year != 0 or ('{YYYY}' not in prefix and '{YY}' not in prefix), 'Una serie continua no lleva un año variable en el prefijo.')
        identifier = data.get('id') or uid()
        with self.db.transaction() as conn:
            existing = conn.execute('SELECT * FROM series WHERE id=?',(identifier,)).fetchone()
            if existing and existing['used']:
                require(all(existing[k] == data.get(k) for k in ('kind','prefix','year','padding','next_number')), 'Una serie utilizada no permite reiniciar ni alterar la numeraci\u00f3n. Crea una serie nueva.')
            if existing:
                conn.execute('UPDATE series SET kind=?,label=?,prefix=?,year=?,padding=?,next_number=?,archived=? WHERE id=?', (kind,label,prefix,year,padding,next_number,int(bool(data.get('archived',False))),identifier))
            else:
                conn.execute('INSERT INTO series(id,kind,label,prefix,year,padding,next_number) VALUES(?,?,?,?,?,?,?)', (identifier,kind,label,prefix,year,padding,next_number))
            self.db.audit(conn,'series.save',identifier,{'label':label,'next_number':next_number})
        return {'id':identifier}
