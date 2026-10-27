"""Versioned estimates beside immutable Access evidence, never accounting amounts.

Policy v1 is intentionally fixed: changes need a new policy and explicit review,
not silent recomputation of previously stored estimates.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from .errors import require
from .validation import now


POLICY = ('Estimación orientativa v1: se supone que cada importe original de línea es anterior al IVA. '
          'Se suman los decimales exactos y se redondea la base a céntimos (HALF_UP); '
          'se calcula y redondea el IVA sobre esa base y el total es base más IVA. '
          'El tipo general sugerido por fecha es 16 % desde 2003 hasta 30/06/2010, '
          '18 % hasta 31/08/2012 y 21 % desde 01/09/2012. La fecha es una orientación, '
          'no acredita el devengo ni el régimen fiscal. No modifica el original ni habilita cobros, '
          'rectificaciones o envíos fiscales.')
MAX_CENTS = 10_000_000_000_000
MAX_LINES = 10_000
FIELDS = ('state', 'version', 'tax_rate', 'base_cents', 'tax_cents', 'total_cents',
          'issues', 'reason', 'evidence', 'policy')


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def _payload(document):
    value = document.get('payload')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def eligible(document):
    return (document['kind'] == 'invoice' and document['status'] in ('historical', 'import_reverted')
            and any(document[key] is None for key in ('base_cents', 'tax_cents', 'total_cents')))


def _decimal(value):
    # Bounded coefficient AND exponent prevent tiny/huge scientific inputs from
    # expanding into unbounded Decimal arithmetic. Do not use binary floats.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('decimal')
    text = str(value).strip()
    if not text or len(text) > 256:
        raise ValueError('decimal')
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('decimal') from exc
    if not number.is_finite():
        raise ValueError('decimal')
    parts = number.as_tuple()
    if len(parts.digits) > 128 or not -128 <= parts.exponent <= 128 or abs(number) >= Decimal(MAX_CENTS) / 100:
        raise ValueError('decimal')
    return number


def _rate(value):
    require(isinstance(value, str), 'Indica un porcentaje de IVA válido.')
    try:
        number = _decimal(value)
        valid = 0 <= number <= 100 and number.as_tuple().exponent >= -6
    except ValueError:
        valid = False
    require(valid, 'El porcentaje debe estar entre 0 y 100, con hasta seis decimales.')
    return format(number, 'f').rstrip('0').rstrip('.') if '.' in format(number, 'f') else format(number, 'f')


def estimate(document, tax_rate=None, *, version=0):
    """Pure, bounded calculation. Issues suppress ALL estimated monetary values."""
    require(eligible(document), 'Sólo se revisan facturas históricas con importes incompletos.', 'historical_review_unavailable')
    payload = _payload(document)
    result = dict(state='pending_review', version=version, tax_rate=None, base_cents=None,
                  tax_cents=None, total_cents=None, issues=[], reason='', evidence='', policy=POLICY)

    def issue(code, message):
        if not any(item['code'] == code for item in result['issues']):
            result['issues'].append({'code': code, 'message': message})

    issued = None
    try:
        raw_date = document['issue_date']
        if not isinstance(raw_date, str) or len(raw_date) != 10:
            raise ValueError('date')
        issued = date.fromisoformat(raw_date)
    except (ValueError, TypeError):
        issue('date_missing', 'No consta una fecha válida y única para estimar esta factura.')
    candidates = payload.get('date_candidates', [])
    if payload.get('date_state') in ('unknown', 'conflict') or (isinstance(candidates, list) and len(set(map(str, candidates))) > 1):
        issue('date_ambiguous', 'La fecha original está ausente o presenta alternativas en conflicto.')
        issued = None
    if tax_rate is not None:
        result['tax_rate'] = _rate(tax_rate)
    elif issued is not None:
        if issued < date(2003, 1, 1):
            issue('date_outside_policy', 'La fecha queda fuera del período de tipos automáticos; requiere revisión y tipo explícito.')
        else:
            result['tax_rate'] = '16' if issued < date(2010, 7, 1) else '18' if issued < date(2012, 9, 1) else '21'
    lines = payload.get('lines')
    if not isinstance(lines, list) or not lines:
        issue('lines_missing', 'No constan líneas originales con las que calcular la estimación.')
        lines = []
    elif len(lines) > MAX_LINES:
        issue('lines_limit', 'El número de líneas supera el límite de cálculo revisable.')
        lines = []
    source_rates = set()

    def inspect_tax(item, rate_field, kind_field):
        raw_rate = item.get(rate_field)
        if raw_rate not in (None, ''):
            try:
                rate = _decimal(raw_rate)
                if not 0 <= rate <= 100:
                    raise ValueError('rate')
                source_rates.add(rate)
            except ValueError:
                issue('original_tax_invalid', 'Un tipo de IVA conservado no tiene un valor válido.')
        if item.get(kind_field) not in (None, '', 'historical', 'subject', 'S1'):
            issue('original_tax_regime', 'El original declara un régimen fiscal que requiere revisión específica; no se sustituye por un tipo general.')

    groups = payload.get('taxes', [])
    if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
        issue('original_tax_invalid', 'El desglose fiscal original no tiene un formato válido.')
        groups = []
    for group in groups:
        inspect_tax(group, 'rate', 'kind')
    with localcontext() as context:
        # Each bounded operand has at most 128 digits/exponent. This precision
        # preserves the exact sum and quantity × price across MAX_LINES.
        context.prec = 600
        subtotal = Decimal(0)
        for line in lines:
            if not isinstance(line, dict):
                issue('line_invalid', 'Una línea original no tiene un formato válido.')
                continue
            inspect_tax(line, 'tax_rate', 'tax_kind')
            raw = line.get('amount_raw')
            if raw is None or raw == '':
                issue('amount_missing', 'Falta el importe original de una o más líneas; no se sustituye por cantidad × precio.')
                continue
            try:
                amount = _decimal(raw)
            except ValueError:
                issue('amount_invalid', 'Un importe original no es un decimal finito dentro de los límites admitidos.')
                continue
            subtotal += amount
            if line.get('base_cents') is not None:
                original_base = line['base_cents']
                if type(original_base) is not int or abs(original_base) >= MAX_CENTS:
                    issue('original_line_amount_invalid', 'Una base de línea conservada no es válida.')
                elif Decimal(original_base) != amount * 100:
                    issue('original_line_amount_mismatch', 'La hipótesis de importe antes de IVA contradice una base de línea conservada.')
            if line.get('tax_cents') is not None:
                original_tax = line['tax_cents']
                if type(original_tax) is not int or abs(original_tax) >= MAX_CENTS:
                    issue('original_line_amount_invalid', 'Una cuota de línea conservada no es válida.')
                elif result['tax_rate'] is not None:
                    line_tax = int((amount * Decimal(result['tax_rate'])).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                    if original_tax != line_tax:
                        issue('original_line_amount_mismatch', 'La hipótesis de IVA contradice una cuota de línea conservada.')
            quantity, price = line.get('quantity'), line.get('unit_price')
            try:
                quantity = _decimal(quantity) if quantity not in (None, '') else None
                price = _decimal(price) if price not in (None, '') else None
                if quantity is not None and price is not None and quantity * price != amount:
                    issue('line_amount_mismatch', 'Cantidad × precio no coincide exactamente con el importe original de una o más líneas.')
            except ValueError:
                issue('line_operand_invalid', 'Una cantidad o precio no es un decimal finito dentro de los límites admitidos.')
        if len(source_rates) > 1:
            issue('original_tax_mixed', 'El original conserva varios tipos de IVA; una estimación con un único porcentaje no es suficiente.')
        elif source_rates and result['tax_rate'] is not None and Decimal(result['tax_rate']) not in source_rates:
            issue('original_tax_mismatch', 'El porcentaje propuesto contradice un tipo de IVA conservado en el original.')
        if not result['issues'] and result['tax_rate'] is not None:
            base = int((subtotal * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            tax = int((Decimal(base) * Decimal(result['tax_rate']) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            amounts = {'base_cents': base, 'tax_cents': tax, 'total_cents': base + tax}
            if any(abs(value) >= MAX_CENTS for value in amounts.values()):
                issue('amount_limit', 'La estimación supera el límite de importes admitido.')
            if any(document[key] is not None and document[key] != value for key, value in amounts.items()):
                issue('original_amount_mismatch', 'La hipótesis de cálculo contradice un importe que sí consta en el original.')
            for key in ('base_cents', 'tax_cents'):
                known = [group.get(key) for group in groups]
                if known and all(value is not None for value in known):
                    if any(type(value) is not int or abs(value) >= MAX_CENTS for value in known):
                        issue('original_tax_invalid', 'El desglose fiscal original contiene importes no válidos.')
                    elif sum(known) != amounts[key]:
                        issue('original_tax_amount_mismatch', 'La hipótesis de cálculo contradice los importes del desglose fiscal conservado.')
            if not result['issues']:
                result.update(amounts, state='estimated')
    return result


def synchronize_defaults(conn):
    """Consume the SQL-only queue in one atomic batch, including direct SQL imports.

    Normal reads do one indexed empty-queue check and never write. No UDF is used
    by schema objects, so offline backup validation with trusted_schema=OFF works.
    """
    if not conn.execute('SELECT 1 FROM historical_review_pending LIMIT 1').fetchone():
        return
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        # Serialize two independent App connections before reading the queue;
        # upgrading a shared read snapshot later can otherwise fail with BUSY.
        conn.execute('BEGIN IMMEDIATE')
    conn.execute('SAVEPOINT historical_review_defaults')
    try:
        cursor = conn.execute('''SELECT d.* FROM historical_review_pending p
            JOIN documents d ON d.id=p.document_id
            LEFT JOIN historical_review_current h ON h.document_id=d.id
            WHERE h.document_id IS NULL''')
        columns = [item[0] for item in cursor.description]
        for row in cursor.fetchall():
            document = dict(zip(columns, row))
            if eligible(document):
                review = estimate(document)
                conn.execute('INSERT INTO historical_review_versions VALUES(?,?,?,?,?,?)',
                             (document['id'], 0, review['state'], _dump(review), 'automatic', now()))
        conn.execute('DELETE FROM historical_review_pending')
        conn.execute('RELEASE historical_review_defaults')
        if owns_transaction:
            conn.commit()
    except BaseException:
        conn.execute('ROLLBACK TO historical_review_defaults')
        conn.execute('RELEASE historical_review_defaults')
        if owns_transaction:
            conn.rollback()
        raise


def current_review(conn, identifier, *, history=False):
    row = conn.execute('SELECT payload FROM historical_review_current WHERE document_id=?', (identifier,)).fetchone()
    if row is None:
        return None
    review = json.loads(row[0])
    if history:
        review['history'] = [{**json.loads(item[0]), 'action': item[1], 'created_at': item[2]}
                             for item in conn.execute('SELECT payload,action,created_at FROM historical_review_versions WHERE document_id=? ORDER BY version DESC', (identifier,))]
    return review


class HistoricalReviews:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _document(conn, identifier):
        require(isinstance(identifier, str) and 0 < len(identifier) <= 128, 'Identificador no válido.')
        row = conn.execute('SELECT * FROM documents WHERE id=?', (identifier,)).fetchone()
        require(row, 'No se encuentra el documento.', 'not_found')
        document = dict(row)
        require(document['status'] == 'historical' and eligible(document),
                'Sólo se revisan facturas históricas activas con importes incompletos.', 'historical_review_unavailable')
        return document

    def preview(self, identifier, tax_rate=None):
        # Preview never materializes defaults or appends audit/history.
        with self.db.read() as conn:
            document = self._document(conn, identifier)
            row = conn.execute('SELECT version FROM historical_review_current WHERE document_id=?', (identifier,)).fetchone()
            return estimate(document, tax_rate, version=row[0] if row else 0)

    def save(self, identifier, expected_version, tax_rate, reason, verified=False, evidence=''):
        require(type(verified) is bool, 'La confirmación del contraste debe ser explícita.')
        require(isinstance(evidence, str) and len(evidence) <= 4000, 'La evidencia debe ser un texto de hasta 4.000 caracteres.')
        require(not verified or evidence.strip(), 'Indica la evidencia documental que contrasta el resultado completo.')
        return self._save(identifier, expected_version, tax_rate, reason, verified, evidence.strip(), 'verify' if verified else 'adjust')

    def reset(self, identifier, expected_version, reason):
        return self._save(identifier, expected_version, None, reason, False, '', 'reset')

    def _save(self, identifier, expected_version, tax_rate, reason, verified, evidence, action):
        require(type(expected_version) is int and expected_version >= 0, 'Versión de revisión no válida.')
        require(isinstance(reason, str) and reason.strip() and len(reason) <= 2000, 'Indica un motivo de hasta 2.000 caracteres.')
        if action != 'reset':
            tax_rate = _rate(tax_rate)
        with self.db.transaction() as conn:
            document = self._document(conn, identifier)
            synchronize_defaults(conn)
            current = current_review(conn, identifier)
            require(current is not None and current['version'] == expected_version,
                    'Otra revisión ha cambiado estos importes. Recarga y revisa antes de guardar.', 'conflict')
            review = estimate(document, tax_rate, version=expected_version + 1)
            require(not verified or not review['issues'], 'Resuelve las incidencias originales antes de marcar el resultado como contrastado.')
            review.update(reason=reason.strip(), evidence=evidence)
            if verified:
                review['state'] = 'verified'
            conn.execute('INSERT INTO historical_review_versions VALUES(?,?,?,?,?,?)',
                         (identifier, review['version'], review['state'], _dump(review), action, now()))
            self.db.audit(conn, 'historical.review_' + action, identifier, review)
            return current_review(conn, identifier, history=True)
