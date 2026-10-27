"""Bounded address jobs for the sequential desktop JSONL bridge, with no DB I/O."""
from collections import OrderedDict
from copy import deepcopy
import threading
import time
import uuid

from .errors import require

MAX_WORKERS = 8
MAX_RESULTS = 32
RESULT_TTL = 60
UNAVAILABLE = {'status': 'unavailable', 'items': []}


class AddressJobs:
    def __init__(self, addresses, clock=None):
        self._addresses = addresses
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._jobs = OrderedDict()
        self._active = 0

    def _prune(self):
        stamp = self._clock()
        for identifier, job in list(self._jobs.items()):
            if job['expires'] <= stamp:
                del self._jobs[identifier]

    def start(self, query, postal_code='', city='', province='', country='ES'):
        # Explicit signature keeps customer details and provider URLs out of IPC.
        params = dict(query=query, postal_code=postal_code, city=city,
                      province=province, country=country)
        with self._lock:
            self._prune()
            if self._active >= MAX_WORKERS:
                return {'identifier': None}
            while len(self._jobs) >= MAX_RESULTS:
                self._jobs.popitem(last=False)
            identifier = uuid.uuid4().hex
            self._jobs[identifier] = {'expires': self._clock() + RESULT_TTL,
                                      'ready': False, 'result': None}
            self._active += 1
            try:
                threading.Thread(target=self._run, args=(identifier, params), daemon=True,
                                 name='address-suggestion').start()
            except RuntimeError:
                self._active -= 1
                del self._jobs[identifier]
                return {'identifier': None}
        return {'identifier': identifier}

    def _run(self, identifier, params):
        try:
            result = self._addresses.search(**params)
        except Exception:
            # Neither typed text nor provider errors belong in permanent logs.
            result = deepcopy(UNAVAILABLE)
        with self._lock:
            self._active -= 1
            self._prune()
            if identifier in self._jobs:
                self._jobs[identifier].update(ready=True, result=result)

    def result(self, identifier):
        require(isinstance(identifier, str) and len(identifier) <= 64,
                'Consulta de direcciones no válida.')
        with self._lock:
            self._prune()
            job = self._jobs.get(identifier)
            if job is None:
                return {'ready': True, 'result': deepcopy(UNAVAILABLE)}
            if not job['ready']:
                return {'ready': False}
            return {'ready': True, 'result': deepcopy(job['result'])}

    def cancel(self, identifier):
        require(isinstance(identifier, str) and len(identifier) <= 64,
                'Consulta de direcciones no válida.')
        with self._lock:
            self._prune()
            self._jobs.pop(identifier, None)
        # urllib cannot interrupt DNS/socket I/O. The bounded daemon finishes
        # independently; a late result is discarded, never restoring this job.
        return {'ok': True}
