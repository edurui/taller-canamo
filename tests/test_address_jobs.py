"""Deterministic background/JSONL tests with synthetic data and no network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
from queue import Queue
import threading

import pytest

from taller import address_jobs, stdio
from taller.address_jobs import AddressJobs, UNAVAILABLE
from taller.app import App
from taller.errors import AppError


RESULT = {'status': 'ok', 'items': [{'id': 'synthetic', 'label': 'Calle sintética 7',
          'address': 'Calle sintética 7', 'postal_code': '', 'city': '', 'province': '', 'country': 'ES'}]}


class ObservedJobs(AddressJobs):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.finished = Queue()

    def _run(self, identifier, params):
        try:
            super()._run(identifier, params)
        finally:
            # Signals after both storing/discarding the result and active cleanup.
            self.finished.put(identifier)


class Search:
    def __init__(self, block=False):
        self.entered = Queue()
        self.release = threading.Event()
        if not block:
            self.release.set()

    def search(self, **params):
        self.entered.put(params)
        assert self.release.wait(3), 'Synthetic test did not release provider'
        return deepcopy(RESULT)


def test_active_limit_counts_cancelled_but_still_running_workers():
    search = Search(block=True)
    jobs = ObservedJobs(search)
    try:
        identifiers = [jobs.start(f'Calle sintética {index}')['identifier'] for index in range(address_jobs.MAX_WORKERS)]
        assert len(set(identifiers)) == 8 and all(identifiers)
        for _ in identifiers:
            search.entered.get(timeout=1)
        assert jobs._active == 8
        assert jobs.start('Calle sin hueco') == {'identifier': None}
        assert jobs.cancel(identifiers[0]) == {'ok': True}
        assert jobs._active == 8
        assert jobs.start('Calle aún sin hueco') == {'identifier': None}
        assert jobs.result(identifiers[0]) == {'ready': True, 'result': UNAVAILABLE}
    finally:
        search.release.set()
    assert {jobs.finished.get(timeout=1) for _ in identifiers} == set(identifiers)
    assert jobs._active == 0 and identifiers[0] not in jobs._jobs
    new = jobs.start('Calle con hueco')['identifier']
    assert new and jobs.finished.get(timeout=1) == new
    assert jobs.result(new) == {'ready': True, 'result': RESULT}


def test_results_are_bounded_to_32_copied_and_expire_at_60_seconds():
    clock = [100.0]
    jobs = ObservedJobs(Search(), clock=lambda: clock[0])
    identifiers = []
    for index in range(address_jobs.MAX_RESULTS + 1):
        identifier = jobs.start(f'Calle sintética {index}')['identifier']
        assert jobs.finished.get(timeout=1) == identifier
        identifiers.append(identifier)
    assert len(jobs._jobs) == 32 and jobs._active == 0
    assert jobs.result(identifiers[0]) == {'ready': True, 'result': UNAVAILABLE}
    last = identifiers[-1]
    result = jobs.result(last)
    result['result']['items'][0]['address'] = 'Caller mutation'
    assert jobs.result(last) == {'ready': True, 'result': RESULT}
    clock[0] = 159.999
    assert jobs.result(last) == {'ready': True, 'result': RESULT}
    clock[0] = 160
    assert jobs.result(last) == {'ready': True, 'result': UNAVAILABLE}
    assert jobs._jobs == {}


@pytest.mark.parametrize('finish', ['cancel', 'expire'])
def test_late_completion_cannot_restore_cancelled_or_expired_job(finish):
    clock = [0.0]
    search = Search(block=True)
    jobs = ObservedJobs(search, clock=lambda: clock[0])
    identifier = jobs.start('Calle sintética')['identifier']
    try:
        search.entered.get(timeout=1)
        assert jobs.result(identifier) == {'ready': False}
        if finish == 'cancel':
            assert jobs.cancel(identifier) == jobs.cancel(identifier) == {'ok': True}
        else:
            clock[0] = 60
        assert jobs.result(identifier) == {'ready': True, 'result': UNAVAILABLE}
        assert jobs._active == 1
    finally:
        search.release.set()
    assert jobs.finished.get(timeout=1) == identifier
    assert jobs._active == 0 and identifier not in jobs._jobs
    assert jobs.result(identifier) == {'ready': True, 'result': UNAVAILABLE}


def test_worker_exceptions_are_private_and_capacity_is_recovered(caplog):
    class FailingSearch:
        def search(self, **_params):
            raise RuntimeError('SENSITIVE_SYNTHETIC_PROVIDER_QUERY')

    jobs = ObservedJobs(FailingSearch())
    identifier = jobs.start('Calle sintética')['identifier']
    assert jobs.finished.get(timeout=1) == identifier
    assert jobs.result(identifier) == {'ready': True, 'result': UNAVAILABLE}
    assert jobs._active == 0 and caplog.text == ''


def test_thread_start_failure_recovers_capacity_and_leaves_no_result(monkeypatch):
    class UnavailableThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError('Synthetic thread creation failure')

    monkeypatch.setattr(threading, 'Thread', UnavailableThread)
    jobs = AddressJobs(Search())
    assert jobs.start('Calle sintética') == {'identifier': None}
    assert jobs._active == 0 and jobs._jobs == {}


@pytest.mark.parametrize('identifier', [None, 7, [], 'x' * 65])
def test_job_identifiers_are_bounded_and_typed(identifier):
    jobs = AddressJobs(Search())
    for method in (jobs.result, jobs.cancel):
        with pytest.raises(AppError):
            method(identifier)


def test_geographic_only_signature_and_unknown_job_are_private():
    search = Search()
    jobs = ObservedJobs(search)
    identifier = jobs.start('Calle sintética', '28003', 'Villa sintética', 'Provincia sintética', 'ES')['identifier']
    assert search.entered.get(timeout=1) == {
        'query': 'Calle sintética', 'postal_code': '28003', 'city': 'Villa sintética',
        'province': 'Provincia sintética', 'country': 'ES'}
    assert jobs.finished.get(timeout=1) == identifier
    assert jobs.result('unknown') == {'ready': True, 'result': UNAVAILABLE}
    for key in ('url', 'endpoint', 'transport', 'conn', 'name', 'phone', 'nif', 'email', 'notes'):
        with pytest.raises(TypeError):
            jobs.start('Calle sintética', **{key: 'SENSITIVE_SYNTHETIC_INPUT'})
    assert search.entered.empty()


def test_network_search_does_not_acquire_database_lock_or_block_saving_customer(app):
    entered, release = threading.Event(), threading.Event()

    def transport(_url, **_kwargs):
        entered.set()
        assert release.wait(3)
        return b'[]'

    app.addresses._transport = transport
    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            # If dispatch took this lock, search could not reach the transport.
            with app.db.lock:
                pending = pool.submit(app.dispatch, 'addresses.search', {'query': 'Calle sintética'})
                assert entered.wait(1)
            saved = pool.submit(app.dispatch, 'customers.save', {'data': {'name': 'Cliente sintético concurrente'}}).result(timeout=1)
            assert saved['name'] == 'Cliente sintético concurrente'
            assert not pending.done() and not release.is_set()
        finally:
            release.set()
        assert pending.result(timeout=1) == {'status': 'ok', 'items': []}
    assert app.contacts.customer(saved['id'])['name'] == 'Cliente sintético concurrente'


def test_real_sequential_stdio_serves_customer_save_before_remote_job_finishes(tmp_path, monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    application = App(tmp_path / 'synthetic-stdio')

    def transport(_url, **_kwargs):
        entered.set()
        assert release.wait(3)
        return b'[]'

    application.addresses._transport = transport
    original_run = application.address_jobs._run

    def observe_completion(*args):
        try:
            original_run(*args)
        finally:
            finished.set()

    application.address_jobs._run = observe_completion
    monkeypatch.setattr(stdio, 'App', lambda _root: application)
    output = io.StringIO()

    class SequentialInput:
        def __init__(self):
            self.line = 0

        def readline(self, _limit):
            self.line += 1
            if self.line == 1:
                request = {'id': 1, 'action': 'addresses.start', 'params': {'query': 'Calle sintética'}}
            elif self.line == 2:
                assert entered.wait(1)
                request = {'id': 2, 'action': 'customers.save', 'params': {'data': {'name': 'Cliente sintético por JSONL'}}}
            elif self.line == 3:
                replies = [json.loads(line) for line in output.getvalue().splitlines()]
                assert [reply['id'] for reply in replies] == [1, 2]
                assert all(reply['ok'] for reply in replies)
                assert replies[0]['result']['identifier']
                assert replies[1]['result']['name'] == 'Cliente sintético por JSONL'
                assert not release.is_set() and not finished.is_set()
                release.set()
                request = {'id': 3, 'action': 'app.shutdown'}
            else:
                return b''
            return (json.dumps(request) + '\n').encode()

    try:
        stdio.serve(application.db.root, SequentialInput(), output, background=False)
    finally:
        release.set()
    assert finished.wait(1)
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [reply['id'] for reply in replies] == [1, 2, 3]
    assert all(reply['ok'] for reply in replies)
    assert application.address_jobs._active == 0


@pytest.mark.parametrize('action', ['addresses.search', 'addresses.start'])
def test_rpc_rejects_personal_fields_internal_dependencies_and_arbitrary_endpoint_before_work(app, action):
    calls = []
    app.addresses._transport = lambda *_args, **_kwargs: calls.append(True) or b'[]'
    for key in ('url', 'endpoint', 'transport', 'conn', 'name', 'phone', 'nif', 'email', 'notes'):
        with pytest.raises(AppError) as failure:
            app.dispatch(action, {'query': 'Calle sintética', key: 'SENSITIVE_SYNTHETIC_INPUT'})
        assert 'SENSITIVE' not in str(failure.value)
    assert calls == [] and app.address_jobs._active == 0


def test_unknown_rpc_and_invalid_parameter_shape_are_rejected_without_work(app):
    for action, params in [('addresses.arbitrary_url', {'query': 'Calle sintética'}),
                           ('addresses.search', ['Calle sintética']),
                           ('addresses.start', {'query': 'Calle sintética', 'data': {'name': 'PRIVATE'}}),
                           ('addresses.result', {'identifier': 'unknown', 'url': 'https://other.invalid'})]:
        with pytest.raises(AppError):
            app.dispatch(action, params)
    assert app.address_jobs._jobs == {} and app.address_jobs._active == 0
