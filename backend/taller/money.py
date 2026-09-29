"""Deterministic EUR arithmetic. Tax is rounded per rate, not by JS float."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from .errors import AppError, require

CENT = Decimal('0.01')
LIMIT = Decimal('99999999.99')


def decimal(value, label='Importe', places=4) -> Decimal:
    require(not isinstance(value, (float, bool)) and value is not None,
            f'{label}: utiliza un decimal en texto, no un flotante.')
    try:
        number = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise AppError(f'{label}: introduce un n\u00famero v\u00e1lido.')
    require(number.is_finite() and abs(number) <= LIMIT, f'{label}: fuera de rango.')
    require(number.as_tuple().exponent >= -places, f'{label}: m\u00e1ximo {places} decimales.')
    return number


def cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def amount(value: int) -> str:
    return format(Decimal(value) / 100, '.2f')


def canonical_tax_rate(value) -> str:
    rate = decimal(value, 'IVA', 2)
    require(rate not in (Decimal('7'), Decimal('8'), Decimal('16'), Decimal('18')),
            f'El IVA histórico del {rate.normalize():f} % se conserva en el original, pero su emisión no está admitida por la validación VERI*FACTU S1 revisada (regla 15.1). Revisa el caso fiscal conservando su tipo original.',
            'unsupported_historical_tax_rate')
    require(rate in (Decimal('21'), Decimal('10'), Decimal('4'), Decimal('0')), 'Tipo de IVA no admitido.')
    # The accepted rates are integral. One representation prevents separate rounding
    # groups for numerically identical inputs such as 21, 21.0 and 21.00.
    return str(int(rate))


def normalize_tax_adjustments(adjustments, invoice_type):
    require(invoice_type in ('R2','R3'), 'La rectificación exclusiva de cuota requiere R2 o R3.', 'tax_adjustment')
    require(isinstance(adjustments,list) and 1<=len(adjustments)<=3,
            'Indica entre una y tres cuotas de IVA que se rectifican.', 'tax_adjustment')
    result, seen = [], set()
    for item in adjustments:
        require(isinstance(item,dict),'La cuota rectificativa no es válida.','tax_adjustment')
        rate=canonical_tax_rate(item.get('tax_rate'))
        require(rate!='0' and rate not in seen,'Cada tipo de IVA positivo debe aparecer una sola vez.','tax_adjustment')
        value=item.get('tax_cents')
        require(isinstance(value,int) and not isinstance(value,bool) and 0<abs(value)<=cents(LIMIT),
                'La cuota rectificada debe ser un importe no nulo en céntimos exactos.','tax_adjustment')
        result.append({'tax_rate':rate,'tax_cents':value});seen.add(rate)
    return sorted(result,key=lambda item:Decimal(item['tax_rate']))


def calculate(lines: list, *, corrective: bool = False, invoice_type=None, tax_adjustments=None) -> dict:
    require(isinstance(lines, list) and 0 < len(lines) <= 500, 'A\u00f1ade entre 1 y 500 conceptos.')
    adjustments=None
    if tax_adjustments is not None:
        require(corrective,'Las cuotas rectificativas requieren una factura rectificativa.','tax_adjustment')
        adjustments=normalize_tax_adjustments(tax_adjustments,invoice_type)
    result, groups = [], {}
    with localcontext() as context:
        context.prec = 32
        for pos, raw in enumerate(lines):
            require(isinstance(raw, dict), f'Linea {pos+1}: datos no validos.')
            description = str(raw.get('description', '')).strip()
            require(0 < len(description) <= 1500, f'L\u00ednea {pos+1}: falta el concepto o es demasiado largo.')
            quantity = decimal(raw.get('quantity', '1'), 'Cantidad', 3)
            price = decimal(raw.get('unit_price', '0'), 'Precio', 4)
            discount = decimal(raw.get('discount', '0'), 'Descuento', 2)
            rate = canonical_tax_rate(raw.get('tax_rate', '21'))
            require(quantity != 0, 'La cantidad no puede ser cero.')
            require(corrective or (quantity > 0 and price >= 0), 'Los importes negativos requieren una rectificativa.')
            require(0 <= discount <= 100, 'El descuento debe estar entre 0 y 100 %.')
            tax_kind = raw.get('tax_kind', 'S1')
            require(tax_kind in ('S1', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6'), 'Tratamiento fiscal no admitido.')
            if tax_kind != 'S1':
                require(rate == '0', 'Una operaci\u00f3n exenta debe tener IVA cero.')
                require(str(raw.get('tax_reason', '')).strip(), 'Indica el motivo legal de la exenci\u00f3n.')
            base = cents(quantity * price * (1 - discount / 100))
            require(abs(base) <= cents(LIMIT), 'El importe de la l\u00ednea es demasiado grande.')
            item = {'description': description, 'quantity': str(quantity), 'unit_price': str(price),
                    'discount': str(discount), 'tax_rate': rate, 'tax_kind': tax_kind,
                    'tax_reason': str(raw.get('tax_reason', '')).strip()[:400], 'base_cents': base,
                    'position': pos, 'product_id': raw.get('product_id') or None}
            result.append(item)
            key = (tax_kind, rate)
            groups[key] = groups.get(key, 0) + base
        taxes = [{'kind': kind, 'rate': rate, 'base_cents': base,
                  'tax_cents': cents(Decimal(base) / 100 * Decimal(rate) / 100) if kind == 'S1' else 0}
                 for (kind, rate), base in sorted(groups.items())]
        if adjustments is not None:
            require(all(item['tax_kind']=='S1' and Decimal(item['unit_price'])==0
                        and Decimal(item['discount'])==0 and not item['product_id'] for item in result),
                    'Una rectificación exclusiva de cuota tiene conceptos de base cero, sin descuentos ni artículos.','tax_adjustment')
            require({item['tax_rate'] for item in result}=={item['tax_rate'] for item in adjustments},
                    'Los conceptos deben identificar los tipos de las cuotas rectificadas.','tax_adjustment')
            taxes=[{'kind':'S1','rate':item['tax_rate'],'base_cents':0,'tax_cents':item['tax_cents']} for item in adjustments]
        subtotal = sum(row['base_cents'] for row in result)
        tax = sum(row['tax_cents'] for row in taxes)
        require(abs(subtotal + tax) <= cents(LIMIT), 'El total supera el l\u00edmite admitido.')
        totals={'lines': result, 'taxes': taxes, 'base_cents': subtotal, 'tax_cents': tax,
                'total_cents': subtotal + tax}
        if adjustments is not None:
            totals.update(tax_adjustments=adjustments,correction_mode='tax_only')
        return totals
