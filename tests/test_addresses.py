"""Offline contract tests; all candidate records below are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from taller import addresses
from taller.addresses import Addresses
from taller.errors import AppError


def candidate(identifier='synthetic-1', **changes):
    return {'id': identifier, 'type': 'portal', 'address': 'CALLE SINTÉTICA 7, Villa Prueba',
            'postalCode': '28003', 'muni': 'Villa Prueba', 'poblacion': 'Villa Prueba',
            'province': 'Provincia Prueba', 'portalNumber': 7, 'extension': None,
            'noNumber': False, 'countryCode': '011', 'lat': 0, 'lng': 0,
            'geom': None, 'refCatastral': 'NOT-A-REAL-REFERENCE', **changes}


class Transport:
    def __init__(self, rows=None):
        self.rows = [candidate()] if rows is None else rows
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return json.dumps(self.rows, ensure_ascii=False).encode()


def test_fixed_provider_query_and_minimal_structured_contract():
    transport = Transport()
    result = Addresses(transport).search('  Calle Sintética  7 ', city='Villa Prueba', province='Provincia Prueba')
    identifier = result['items'][0]['id']
    assert isinstance(identifier, str) and identifier.startswith('cartociudad:portal:synthetic-1:')
    assert result == {'status': 'ok', 'items': [{
        'id': identifier,
        'label': 'CALLE SINTÉTICA 7, 28003 Villa Prueba, Provincia Prueba',
        'address': 'CALLE SINTÉTICA 7', 'postal_code': '28003',
        'city': 'Villa Prueba', 'province': 'Provincia Prueba', 'country': 'ES',
    }]}
    assert len(transport.calls) == 1
    url, options = transport.calls[0]
    assert options == {'timeout': 2.5, 'max_bytes': 256 * 1024}
    parsed = urllib.parse.urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        'https', 'www.cartociudad.es', '/geocoder/api/geocoder/candidates')
    params = urllib.parse.parse_qs(parsed.query)
    assert params == {'q': ['Calle Sintética 7'],
                      'limit': ['12'], 'countrycodes': ['es'], 'no_process': [addresses.NO_PROCESS]}
    assert not {'lat', 'lng', 'geom', 'refCatastral'} & result['items'][0].keys()


def test_queries_are_encoded_and_no_client_supplied_url_or_extra_personal_fields_are_accepted():
    transport = Transport([])
    search = Addresses(transport)
    text = 'Calle % &limit=999#https://other.invalid/path'
    search.search(text)
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(transport.calls[0][0]).query)
    assert params['q'] == [text] and params['limit'] == ['12']
    for forbidden in ('url', 'endpoint', 'name', 'nif', 'phone', 'email', 'notes'):
        with pytest.raises(TypeError):
            search.search('Calle sintética', **{forbidden: 'unrelated'})
    assert len(transport.calls) == 1


@pytest.mark.parametrize('query,country', [('', 'ES'), ('ab', 'ES'), ('  a  ', 'ES'),
                                         ('12345', 'ES'), ('---', 'ES'), ('Calle sintética', 'FR'),
                                         ('Calle sintética', ''), ('Calle sintética', 'España')])
def test_short_non_address_and_non_spanish_searches_do_not_use_network(query, country):
    transport = Transport()
    assert Addresses(transport).search(query, country=country) == {'status': 'ok', 'items': []}
    assert transport.calls == []


@pytest.mark.parametrize('values', [dict(query=None), dict(query=12), dict(query='x' * 251),
                                  dict(query='Calle\x00prueba'), dict(query='Calle\ud800'),
                                  dict(query='Calle prueba', postal_code='1' * 21),
                                  dict(query='Calle prueba', city=[]),
                                  dict(query='Calle prueba', province='x' * 121),
                                  dict(query='Calle prueba', country=False)])
def test_input_shape_and_lengths_are_bounded_before_transport(values):
    transport = Transport()
    with pytest.raises(AppError, match='búsqueda'):
        Addresses(transport).search(**values)
    assert transport.calls == []


def test_context_ranking_deduplication_and_national_fallback_need_one_request():
    rows = [candidate('elsewhere', address='CALLE SINTETICA 7, Otro Lugar', poblacion='Otro Lugar', muni='Otro Lugar', province='Otra Provincia', postalCode='41001'),
            candidate('province', address='CALLE SINTETICA 7, Tercera Villa', poblacion='Tercera Villa', muni='Tercera Villa', postalCode='28002'),
            candidate('city', postalCode='28002'),
            candidate('postal', postalCode='28003'),
            candidate('duplicate', address='Calle Sintetica 7, Villa Prueba', poblacion='Villa prueba')]
    transport = Transport(rows)
    result = Addresses(transport).search('Calle sintética 7', '28003', 'Villa Prueba', 'Provincia Prueba')
    assert [row['id'].split(':')[2] for row in result['items']] == ['postal', 'city', 'province', 'elsewhere']
    assert len(transport.calls) == 1
    assert not any(key.endswith('_filter') for key in urllib.parse.parse_qs(urllib.parse.urlsplit(transport.calls[0][0]).query))


def test_only_addresses_are_offered_with_portals_prioritized_for_number_queries():
    rows = [candidate('road', type='callejero', address='CALLE SINTETICA, Villa Prueba', portalNumber=None),
            candidate('portal'), candidate('town', type='municipio'), candidate('poi', type='toponimo'),
            candidate('foreign', countryCode='FR'), candidate('bad-country', countryCode={}),
            candidate('long-country', countryCode='x' * 121),
            None, [], {'id': 'missing'}, candidate('bad-address', address={}),
            candidate('bad-id', id=True), candidate('long', address='x' * 501)]
    service = Addresses(Transport(rows))
    assert [row['id'].split(':')[2] for row in service.search('Calle sintética 7')['items']] == ['portal', 'road']
    assert [row['id'].split(':')[2] for row in service.search('Calle sintética')['items']] == ['road', 'portal']


@pytest.mark.parametrize('postal', ['28003 28004', '28003,28004', None, 28003, '99999', '28003 / 28004'])
def test_unknown_or_multiple_postcodes_are_never_inferred_from_preferred_context(postal):
    item = Addresses(Transport([candidate(postalCode=postal)])).search('Calle sintética', '28003')['items'][0]
    assert item['postal_code'] == ''
    assert '28003' not in item['label']


def test_provider_portal_suffix_and_unknown_locality_are_preserved_without_reconstruction():
    rows = [candidate('extension', address='CALLE SINTÉTICA 7-B, Pedanía Prueba, Villa Prueba',
                      poblacion='Pedanía Prueba', portalNumber=7, extension='B'),
            candidate('unnumbered', address='CAMINO SINTÉTICO S-N', muni=None, poblacion=None,
                      province=None, postalCode=None, portalNumber=None, noNumber=True),
            candidate('comma', address='AVENIDA PRUEBA, SECTOR NORTE, Villa Prueba')]
    items = Addresses(Transport(rows)).search('Calle sintética')['items']
    assert items[0]['address'] == 'CALLE SINTÉTICA 7-B' and items[0]['city'] == 'Pedanía Prueba'
    assert items[1]['address'] == 'CAMINO SINTÉTICO S-N' and items[1]['city'] == ''
    assert items[1]['label'] == 'CAMINO SINTÉTICO S-N'
    assert items[2]['address'] == 'AVENIDA PRUEBA, SECTOR NORTE'


def test_same_provider_id_for_distinct_portals_gets_distinct_stable_selection_ids():
    rows = [candidate('same'), candidate('same', address='OTRA CALLE 10, Villa Prueba')]
    items = Addresses(Transport(rows)).search('Calle sintética 7')['items']
    assert len(items) == 2 and len({item['id'] for item in items}) == 2
    assert [item['address'] for item in items] == ['CALLE SINTÉTICA 7', 'OTRA CALLE 10']
    assert Addresses(Transport(rows)).search('Calle sintética 7')['items'] == items


def test_numeric_id_and_missing_portal_metadata_preserve_provider_address_with_commas():
    row = candidate(17, address='CALLE PRUEBA, SECTOR 2, 7-B, Villa [Prueba]',
                    poblacion='Villa [Prueba]', muni='Villa [Prueba]')
    for key in ('portalNumber', 'extension', 'noNumber'):
        row.pop(key)
    item = Addresses(Transport([row])).search('Calle prueba')['items'][0]
    assert item['id'].startswith('cartociudad:portal:17:')
    assert item['address'] == 'CALLE PRUEBA, SECTOR 2, 7-B'


def test_missing_provider_geography_is_not_filled_from_user_preferences():
    rows = [candidate(muni=None, poblacion=None, province=None, postalCode=None, address='CALLE SINTÉTICA 7')]
    item = Addresses(Transport(rows)).search('Calle sintética', '28003', 'Villa preferida', 'Provincia preferida')['items'][0]
    assert item['postal_code'] == item['city'] == item['province'] == ''


def test_stored_locality_cannot_override_an_explicit_other_city_and_results_are_capped():
    transport = Transport([candidate(str(index), address=f'CALLE SINTETICA {index}, Villa Prueba') for index in range(12)])
    result = Addresses(transport).search('Calle sintética, Villa Prueba', city='Otra ciudad', province='Otra provincia')
    assert len(result['items']) == 8
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(transport.calls[0][0]).query)['q'] == ['Calle sintética, Villa Prueba']


def test_cache_normalizes_keys_returns_copies_and_expires():
    clock = [100.0]
    transport = Transport()
    service = Addresses(transport, clock=lambda: clock[0])
    first = service.search('CALLE SINTÉTICA', city='Villa Prueba')
    expected = deepcopy(first)
    first['items'][0]['address'] = 'caller mutation'
    first['items'].append({'id': 'caller-added'})
    assert service.search(' calle  sintetica ', city='villa prueba', country='es') == expected
    clock[0] += 899
    assert service.search('Calle sintética', city='Villa Prueba') == expected
    assert len(transport.calls) == 1
    clock[0] += 1
    service.search('Calle sintética', city='Villa Prueba')
    assert len(transport.calls) == 2


def test_cache_is_lru_bounded_and_context_is_part_of_key():
    transport = Transport([])
    service = Addresses(transport)
    for index in range(addresses.CACHE_SIZE):
        service.search(f'Calle sintética {index}')
    service.search('Calle sintética 0')
    service.search('Calle sintética nueva')
    assert len(service._cache) == addresses.CACHE_SIZE
    service.search('Calle sintética 0')
    assert len(transport.calls) == addresses.CACHE_SIZE + 1
    service.search('Calle sintética 1')
    assert len(transport.calls) == addresses.CACHE_SIZE + 2
    service.search('Calle sintética 0', city='Otra villa')
    service.search('Calle sintética 0', postal_code='28003')
    service.search('Calle sintética 0', province='Otra provincia')
    assert len(transport.calls) == addresses.CACHE_SIZE + 5


def test_concurrent_identical_searches_share_transport_without_blocking_cached_or_other_searches():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def transport(url, **_kwargs):
        calls.append(url)
        if 'Bloqueada' in url:
            entered.set()
            assert release.wait(2)
        return json.dumps([candidate()]).encode()

    service = Addresses(transport)
    cached = service.search('Calle cacheada')
    with ThreadPoolExecutor(max_workers=4) as pool:
        owner = pool.submit(service.search, 'Calle Bloqueada')
        assert entered.wait(1)
        follower = pool.submit(service.search, 'Calle bloqueada')
        assert pool.submit(service.search, 'Calle cacheada').result(timeout=1) == cached
        assert pool.submit(service.search, 'Calle distinta').result(timeout=1) == cached
        release.set()
        first, second = owner.result(timeout=1), follower.result(timeout=1)
    assert first == second and len(calls) == 3
    first['items'][0]['address'] = 'caller change'
    assert second['items'][0]['address'] != 'caller change'
    assert service._pending == {}


@pytest.mark.parametrize('error', [TimeoutError('synthetic'), OSError('synthetic'),
                                  urllib.error.URLError('synthetic'),
                                  http.client.IncompleteRead(b'synthetic', 10),
                                  http.client.BadStatusLine('synthetic'),
                                  urllib.error.HTTPError('https://www.cartociudad.es/?q=private', 503, 'private', {}, None)])
def test_transport_failures_are_generic_not_cached_and_next_attempt_can_recover(error):
    calls = []

    def transport(_url, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise error
        return b'[]'

    service = Addresses(transport)
    assert service.search('Calle sintética') == {'status': 'unavailable', 'items': []}
    assert service.search('Calle sintética') == {'status': 'ok', 'items': []}
    assert len(calls) == 2 and service._pending == {}


@pytest.mark.parametrize('raw', [b'<html>Unavailable</html>', b'{}', b'null', b'"text"', b'NaN',
                               b'\xff', b' ' * (addresses.MAX_BYTES + 1),
                               json.dumps([{}] * 65).encode(), b'[' * 1500 + b']' * 1500, '[]'],
                         ids=['html', 'object', 'null', 'string', 'nan', 'utf8', 'oversized',
                              'too-many-rows', 'nested-arrays', 'not-bytes'])
def test_invalid_json_encoding_size_or_shape_is_unavailable(raw):
    assert Addresses(lambda *_a, **_k: raw).search('Calle sintética') == {'status': 'unavailable', 'items': []}


class Response:
    def __init__(self, raw=b'[]', status=200, headers=None, final_url=None):
        self.raw, self.status = raw, status
        self.headers = {'Content-Type': 'application/json; charset=UTF-8', **(headers or {})}
        self.final_url = final_url
        self.read_sizes, self.closed = [], False

    def geturl(self):
        return self.final_url or addresses.ENDPOINT + '?q=Calle+Prueba'

    def read(self, size):
        self.read_sizes.append(size)
        return self.raw[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True


def test_default_transport_uses_json_timeout_bounded_read_and_rejects_all_redirects(monkeypatch):
    response = Response()
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen.update(request=request, timeout=timeout)
            return response

    def build(*handlers):
        seen['handlers'] = handlers
        return Opener()

    monkeypatch.setattr(urllib.request, 'build_opener', build)
    url = addresses.ENDPOINT + '?q=Calle+Prueba'
    assert addresses._http_get(url, timeout=2.5, max_bytes=addresses.MAX_BYTES) == b'[]'
    assert seen['request'].get_header('Accept') == 'application/json'
    assert seen['request'].get_header('Accept-encoding') == 'identity'
    assert seen['timeout'] == 2.5 and response.read_sizes == [addresses.MAX_BYTES + 1]
    assert response.closed
    redirect = next(handler for handler in seen['handlers'] if isinstance(handler, addresses._NoRedirect))
    for destination in ('https://other.invalid/', 'http://www.cartociudad.es/', addresses.ENDPOINT):
        assert redirect.redirect_request(None, None, 302, '', {}, destination) is None


@pytest.mark.parametrize('response', [Response(status=503), Response(headers={'Content-Type': 'text/html'}),
                                    Response(headers={'Content-Encoding': 'gzip'}),
                                    Response(headers={'Content-Length': str(addresses.MAX_BYTES + 1)}),
                                    Response(headers={'Content-Length': 'invalid'}),
                                    Response(raw=b' ' * (addresses.MAX_BYTES + 1)),
                                    Response(final_url='https://other.invalid/')])
def test_default_transport_rejects_http_content_size_encoding_and_final_url(monkeypatch, response):
    class Opener:
        def open(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(urllib.request, 'build_opener', lambda *_args: Opener())
    with pytest.raises(ValueError):
        addresses._http_get(addresses.ENDPOINT + '?q=Calle+Prueba', timeout=2.5, max_bytes=addresses.MAX_BYTES)
    assert response.closed


def test_http_error_body_is_closed_without_being_read_or_returned(monkeypatch):
    from io import BytesIO
    body = BytesIO(b'synthetic provider error containing query')

    class Opener:
        def open(self, request, **_kwargs):
            raise urllib.error.HTTPError(request.full_url, 503, 'Unavailable', {}, body)

    monkeypatch.setattr(urllib.request, 'build_opener', lambda *_args: Opener())
    assert Addresses().search('Calle sintética') == {'status': 'unavailable', 'items': []}
    assert body.closed


@pytest.mark.parametrize('url', ['http://www.cartociudad.es/geocoder/api/geocoder/candidates',
                               'https://www.cartociudad.es.other.invalid/geocoder/api/geocoder/candidates',
                               'https://user@www.cartociudad.es/geocoder/api/geocoder/candidates',
                               'https://www.cartociudad.es/geocoder/api/geocoder/find',
                               addresses.ENDPOINT + '#fragment'])
def test_transport_cannot_be_repurposed_for_another_endpoint(url):
    with pytest.raises(ValueError):
        addresses._http_get(url, timeout=2.5, max_bytes=addresses.MAX_BYTES)
