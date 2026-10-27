"""Optional address suggestions from the fixed, public CartoCiudad endpoint.

Only the typed address query leaves the process; geographic preferences stay
local. Suggestions are not validation, and this module never reads workshop data.
Provider contract: https://github.com/IDEESpain/Cartociudad#1-candidates
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import http.client
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import require
from .validation import normalized

ENDPOINT = 'https://www.cartociudad.es/geocoder/api/geocoder/candidates'
HTTP_TIMEOUT = 2.5
MAX_BYTES = 256 * 1024
REMOTE_LIMIT = 12
MAX_ITEMS = 8
CACHE_SIZE = 192
CACHE_TTL = 15 * 60
NO_PROCESS = 'municipio,provincia,comunidad autonoma,poblacion,toponimo,expendeduria,punto_recarga_electrica,ngbe'
POSTAL_CODE = re.compile(r'(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Even a same-host redirect is unnecessary for this fixed JSON endpoint.
        return None


def _http_get(url, *, timeout, max_bytes):
    target = urllib.parse.urlsplit(url)
    if (target.scheme, target.netloc, target.path) != (
            'https', 'www.cartociudad.es', '/geocoder/api/geocoder/candidates') or target.fragment:
        raise ValueError('Unexpected address provider.')
    request = urllib.request.Request(url, headers={
        'Accept': 'application/json', 'Accept-Encoding': 'identity',
        'User-Agent': 'TallerCanamo/0.9 address-suggestions',
    })
    opener = urllib.request.build_opener(
        _NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        error.close()
        raise
    with response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Unexpected address response.')
        content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if content_type != 'application/json' or response.headers.get('Content-Encoding', 'identity') != 'identity':
            raise ValueError('Unexpected address format.')
        length = response.headers.get('Content-Length')
        if length is not None and (not length.isdecimal() or int(length) > max_bytes):
            raise ValueError('Address response too large.')
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError('Address response too large.')
        return raw


def _input(value, maximum):
    require(isinstance(value, str) and len(value) <= maximum,
            'La búsqueda de direcciones no es válida.')
    require(not any((ord(char) < 32 and not char.isspace()) or 0xD800 <= ord(char) <= 0xDFFF for char in value),
            'La búsqueda de direcciones no es válida.')
    return ' '.join(value.split())


def _text(value, maximum=120):
    if not isinstance(value, str) or len(value) > maximum:
        return ''
    if any((ord(char) < 32 and not char.isspace()) or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        return ''
    return ' '.join(value.split())


def _reject_constant(_value):
    raise ValueError('Invalid JSON constant.')


def _candidate(row, query, postal_code, city, province):
    if not isinstance(row, dict):
        return None
    kind = _text(row.get('type')).casefold()
    if kind not in ('portal', 'callejero', 'carretera', 'carreteras'):
        return None
    country_code = row.get('countryCode')
    if country_code is not None and (not isinstance(country_code, str)
                                    or (country_code and _text(country_code).upper() not in ('011', 'ES'))):
        return None
    raw_id = row.get('id')
    if type(raw_id) is int:
        raw_id = str(raw_id)
    identifier, address = _text(raw_id, 160), _text(row.get('address'), 500)
    if not identifier or not address:
        return None
    municipality = _text(row.get('muni'))
    population = _text(row.get('poblacion'))
    candidate_city = population or municipality
    candidate_province = _text(row.get('province'))
    # candidates.address already contains the portal, extension or S-N. Never
    # reconstruct these from nullable numbers, nor remove unmatched address text.
    locality_names = sorted({name for name in (population, municipality, candidate_province) if name},
                            key=len, reverse=True)
    # Remove only a suffix explicitly supplied by structured geography. Commas
    # elsewhere remain part of the provider's complete postal address.
    while True:
        for name in locality_names:
            shortened = re.sub(r',\s*' + re.escape(name) + r'\s*$', '', address, flags=re.IGNORECASE)
            if shortened != address:
                address = shortened
                break
        else:
            break
    raw_postal = _text(row.get('postalCode'), 128)
    postal_tokens = re.split(r'[\s,;]+', raw_postal) if raw_postal else []
    postals = set(postal_tokens) if all(POSTAL_CODE.fullmatch(code) for code in postal_tokens) else set()
    # A road can span several codes. Empty is intentional: do not pick the first
    # or claim that the user's preferred code was confirmed by this candidate.
    candidate_postal = next(iter(postals)) if len(postals) == 1 else ''
    locality = ' '.join(part for part in (candidate_postal, candidate_city) if part)
    label_parts = [address]
    if locality:
        label_parts.append(locality)
    if candidate_province and normalized(candidate_province) != normalized(candidate_city):
        label_parts.append(candidate_province)
    identity = [normalized(value) for value in (address, candidate_postal, candidate_city, candidate_province)]
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
    item = {'id': f'cartociudad:{kind}:{identifier}:{digest}', 'label': ', '.join(label_parts),
            'address': address, 'postal_code': candidate_postal, 'city': candidate_city,
            'province': candidate_province, 'country': 'ES'}
    has_number = any(char.isdigit() for char in query)
    type_rank = 2 if kind == ('portal' if has_number else 'callejero') else 1
    score = (bool(postal_code and postal_code in postals),
             bool(city and normalized(city) in {normalized(population), normalized(municipality)}),
             bool(province and normalized(province) == normalized(candidate_province)), type_rank)
    return score, item


@dataclass
class _Pending:
    ready: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None


class Addresses:
    def __init__(self, transport=None, clock=None):
        self._transport = transport or _http_get
        self._clock = clock or time.monotonic
        self._cache = OrderedDict()
        self._pending = {}
        self._lock = threading.Lock()

    def search(self, query, postal_code='', city='', province='', country='ES'):
        query = _input(query, 250)
        postal_code = _input(postal_code, 20)
        city, province = _input(city, 120), _input(province, 120)
        country = _input(country, 80).upper()
        if country != 'ES' or len(query) < 3 or not any(char.isalpha() for char in query):
            return {'status': 'ok', 'items': []}
        key = tuple(normalized(value) for value in (query, postal_code, city, province, country))
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                expires, result = cached
                if self._clock() < expires:
                    self._cache.move_to_end(key)
                    return deepcopy(result)
                del self._cache[key]
            pending = self._pending.get(key)
            owner = pending is None
            if owner:
                pending = self._pending[key] = _Pending()
        if not owner:
            # Single-flight for the same normalized request. Neither waiting nor
            # network I/O holds the cache lock; unrelated cached reads stay fast.
            if pending.ready.wait(HTTP_TIMEOUT + 0.25):
                return deepcopy(pending.result)
            return {'status': 'unavailable', 'items': []}
        result = {'status': 'unavailable', 'items': []}
        try:
            result = self._search(query, postal_code, city, province)
            return deepcopy(result)
        finally:
            with self._lock:
                if result['status'] == 'ok':
                    self._cache[key] = (self._clock() + CACHE_TTL, deepcopy(result))
                    self._cache.move_to_end(key)
                    while len(self._cache) > CACHE_SIZE:
                        self._cache.popitem(last=False)
                pending.result = result
                self._pending.pop(key, None)
                pending.ready.set()

    def _search(self, query, postal_code, city, province):
        # Stored locality is only a ranking preference. Appending it to q could
        # suppress another city explicitly typed by the user. One national call
        # preserves that choice and avoids exact-spelling geographic filters.
        url = ENDPOINT + '?' + urllib.parse.urlencode({
            'q': query, 'limit': REMOTE_LIMIT,
            'countrycodes': 'es', 'no_process': NO_PROCESS,
        })
        try:
            raw = self._transport(url, timeout=HTTP_TIMEOUT, max_bytes=MAX_BYTES)
            if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
                raise ValueError('Invalid address response.')
            rows = json.loads(raw.decode('utf-8'), parse_constant=_reject_constant)
            if (not isinstance(rows, list) or len(rows) > 64
                    or (rows and not any(isinstance(row, dict) for row in rows))):
                raise ValueError('Invalid address candidates.')
            ranked = [_candidate(row, query, postal_code, city, province) for row in rows]
            ranked = sorted((row for row in ranked if row is not None), key=lambda row: row[0], reverse=True)
            seen, items = set(), []
            for _, item in ranked:
                identity = tuple(normalized(item[key]) for key in ('address', 'postal_code', 'city', 'province'))
                if identity not in seen:
                    seen.add(identity)
                    items.append(item)
                if len(items) == MAX_ITEMS:
                    break
            return {'status': 'ok', 'items': items}
        except (OSError, urllib.error.URLError, http.client.HTTPException,
                ValueError, TypeError, RecursionError, OverflowError):
            # Never return provider errors or log a URL containing typed address text.
            return {'status': 'unavailable', 'items': []}
