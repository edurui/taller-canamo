"""Allowlisted optional SQL ordering; unspecified order preserves existing queries."""
from decimal import Decimal, InvalidOperation

from .errors import require


def text_order(expression):
    # Missing and blank labels are both displayed as absent in the interface.
    return "nullif(normalized(" + expression + "),'')"


def label_order(expression, labels):
    # Expressions/labels are application constants, never RPC input.
    pairs = ' '.join("WHEN '" + key.replace("'", "''") + "' THEN '" + label.replace("'", "''") + "'"
                     for key, label in labels.items())
    return text_order('CASE ' + expression + ' ' + pairs + ' ELSE ' + expression + ' END')


def order_by(sort_by, sort_direction, columns, *, default, tie):
    require(isinstance(sort_by, str) and (sort_by == '' or sort_by in columns),
            'Columna de ordenación no válida.')
    require(isinstance(sort_direction, str) and sort_direction in ('asc', 'desc'),
            'Dirección de ordenación no válida.')
    if not sort_by:
        return default
    return columns[sort_by] + ' ' + sort_direction.upper() + ' NULLS LAST,' + tie


def decimal_collation(conn):
    """Sort persisted decimal strings exactly without REAL rounding or lexical order."""
    def compare(left, right):
        try:
            a, b = Decimal(left), Decimal(right)
            if a.is_finite() and b.is_finite():
                return (a > b) - (a < b)
        except InvalidOperation:
            pass
        return (left > right) - (left < right)
    conn.create_collation('decimal_number', compare)


STATUS_LABELS = {
    'draft': 'Borrador', 'issued': 'Emitida', 'historical': 'Histórica', 'void': 'Anulada',
    'sent': 'Enviado', 'accepted': 'Aceptado', 'rejected': 'Rechazado', 'expired': 'Caducado',
    'received': 'Recibido', 'repairing': 'En reparación', 'waiting_parts': 'Esperando piezas',
    'ready': 'Terminado', 'delivered': 'Entregado', 'local_only': 'Prueba local',
    'pending': 'Pendiente', 'retry': 'Reintento pendiente', 'sending': 'Enviando',
    'accepted_with_errors': 'Aceptado con errores', 'duplicate_review': 'Revisar duplicado',
    'uncertain': 'Resultado por confirmar', 'reconciliation_conflict': 'Diferencia en la consulta',
    'invalid_local': 'Error de validación local', 'superseded': 'Sustituido por subsanación',
}
