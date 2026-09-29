"""Exercise the shipped engines via JSONL on a disposable, synthetic workshop.

No AEAT request, WhatsApp message, printer or configured workshop is used. The
source mode checks this verifier itself and never counts as packaged evidence.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


class Service:
    def __init__(self, command, directory):
        self.started = time.perf_counter()
        self.calls = []
        self.counter = 0
        self.output = queue.Queue()
        self.errors = bytearray()
        env = {**os.environ, 'PYTHONPATH': str(ROOT/'backend')}
        self.process = subprocess.Popen([*command, '--data', str(directory), '--no-background'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, start_new_session=os.name != 'nt')

        def read_output():
            for line in self.process.stdout:
                self.output.put(line)
            self.output.put(None)

        def read_errors():
            while block := self.process.stderr.read(65536):
                self.errors.extend(block)
                if len(self.errors) > 300_000:
                    del self.errors[:-300_000]

        threading.Thread(target=read_output, daemon=True).start()
        threading.Thread(target=read_errors, daemon=True).start()

    def call(self, action, params=None, timeout=180):
        self.counter += 1
        started = time.perf_counter()
        request = {'id': self.counter, 'action': action, 'params': params or {}}
        self.process.stdin.write((json.dumps(request, ensure_ascii=False)+'\n').encode('utf-8'))
        self.process.stdin.flush()
        try:
            line = self.output.get(timeout=timeout)
        except queue.Empty as exc:
            raise AssertionError(f'{action}: tiempo agotado tras {timeout} segundos') from exc
        if line is None:
            raise AssertionError(f'{action}: servicio finalizado sin respuesta; {self.errors.decode("utf-8", "replace")[-3000:]}')
        result = json.loads(line)
        if result.get('id') != self.counter or result.get('ok') is not True:
            raise AssertionError(f'{action}: {result}')
        self.calls.append({'action': action, 'seconds': round(time.perf_counter()-started, 4)})
        return result['result']

    def shutdown(self):
        self.call('app.shutdown')
        self.process.stdin.close()
        assert self.process.wait(timeout=20) == 0

    def proposal(self, operation, params):
        job = self.call('assistant.start', {'operation': operation, 'params': params,
                'idempotency_key': 'verificacion-empaquetado-'+operation})
        # The business RPC remains available while the optional engine works.
        self.call('bootstrap', timeout=10)
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            current = self.call('assistant.job_status', {'identifier': job['id']})
            if current['status']=='completed' and not current['worker_active']:
                return current['result']
            if current['status'] in ('failed','cancelled'):
                raise AssertionError(f'Trabajo {operation}: {current}')
            time.sleep(.2)
        raise AssertionError(f'Trabajo {operation}: tiempo agotado')

    def download(self, export, destination):
        if 'capability' not in export:
            raise AssertionError('El archivo no ofrece el contrato de descarga por fragmentos')
        checksum, position = hashlib.sha256(), 0
        try:
            with Path(destination).open('wb') as target:
                while position < export['bytes']:
                    part = self.call('backup.download_chunk', {'capability': export['capability'], 'offset': position, 'length': 1048576})
                    raw = base64.b64decode(part['content'], validate=True)
                    assert 0 < len(raw) <= 1048576 and len(raw) == part['bytes']
                    assert part['offset'] == position and part['total_bytes'] == export['bytes']
                    assert hashlib.sha256(raw).hexdigest() == part['sha256']
                    checksum.update(raw); target.write(raw); position += len(raw)
                    assert part['eof'] == (position == export['bytes'])
            assert checksum.hexdigest() == export['sha256']
        finally:
            self.call('backup.release_download', {'capability': export['capability']})

    def abort(self):
        if self.process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True, timeout=15)
            else:
                os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=20)


def verify(command, output, *, packaged, expected_policy=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
    evidence = {'ok': False, 'platform': sys.platform, 'packaged': packaged, 'checks': [],
                'limits': ['Datos y voz sintéticos; no usa el Access real.', 'No acredita instalación Windows, impresión física, entrega B2B ni validación externa AEAT.']}
    service = None
    try:
        with contextlib.ExitStack() as cleanup:
            temporary = cleanup.enter_context(tempfile.TemporaryDirectory(prefix='canamo-paquete-con-tildes-á-'))
            cleanup.callback(lambda: service.abort() if service is not None else None)
            folder = Path(temporary)
            service = Service(command, folder/'workshop')
            bootstrap = service.call('bootstrap')
            evidence['startup_seconds'] = round(time.perf_counter()-service.started, 4)
            assert bootstrap['version'] == expected
            readiness = service.call('fiscal.readiness')
            policy = readiness['build_policy']
            assert readiness['production_ready'] is False and bootstrap['production_released'] is False
            assert policy['policy_sha256']
            if expected_policy:
                assert policy['edition'] == expected_policy['edition']
                assert policy['policy_sha256'] == expected_policy['sha256']
                assert policy['candidate_build'] == (packaged and sys.platform == 'win32' and expected_policy['edition'] == 'release_candidate')
            evidence['build_policy'] = {key: policy[key] for key in ('edition', 'candidate_build', 'policy_sha256')}
            service.call('demo.load')
            invoices = service.call('documents.list')
            invoice = next(item for item in invoices['items'] if item['status'] == 'issued' and item['kind'] == 'invoice')
            pdf = service.call('documents.pdf', {'identifier': invoice['id']})
            pdf_bytes = base64.b64decode(pdf['content'], validate=True)
            assert pdf_bytes.startswith(b'%PDF-') and b'/FontFile2' in pdf_bytes
            chain = service.call('fiscal.check')
            assert chain['ok'] and chain['checked'] > 0
            evidence['checks'].append('Demostración, PDF con fuente TrueType incrustada y cadena fiscal con esquemas oficiales locales')

            sample = ROOT/'backend/taller/schemas/b2b_ubl21/en16931/examples/ubl-tc434-example1.xml'
            semantic = service.call('b2b.validate', {'xml': sample.read_text(encoding='utf-8')})
            assert semantic['ok'] and semantic['network_called'] is False
            b2b = service.call('b2b.prepare', {'document_id': invoice['id'], 'recipient_business': True})
            assert b2b['validation']['ok'] and b2b['remote_delivered'] is False
            evidence['checks'].append('SaxonC nativo: ejemplo CEN y factura generada superan XSD/EN16931 sin envío')

            service.call('settings.save', {'section': 'assistant', 'values': {'enabled': True}})
            fixtures = ROOT/'tests/fixtures/assistance'
            voice = service.proposal('transcribe', {'content': base64.b64encode((fixtures/'dictado-sintetico.wav').read_bytes()).decode(), 'name': 'dictado-sintetico.wav'})
            assert 'cambio de aceite' in voice['text'] and voice['network_called'] is False
            picture = service.proposal('extract', {'content': base64.b64encode((fixtures/'ficha-sintetica.png').read_bytes()).decode(), 'name': 'ficha-sintetica.png'})
            candidates = {item['field']: item['value'] for item in picture['candidates']}
            assert candidates['plate'] == '1234BCD' and candidates['tax_id'] == '12345678Z'
            assert picture['network_called'] is False
            evidence['checks'].append('Vosk español y RapidOCR/ONNX reales reconocen audio e imagen sintéticos')

            # Generate an actual Access file using the development fixture tool;
            # the frozen service must read it with its own shipped JRE/JARs.
            sys.path.insert(0, str(ROOT/'backend'))
            from taller.access import java_command
            access = folder/'Copia sintética.accdb'
            subprocess.run([*java_command(), 'fixture', str(access), 'accdb'], check=True, capture_output=True, timeout=90)
            before = digest(access)
            origin = service.call('import.source_save', {'name': 'Prueba de lector empaquetado'})
            upload = service.call('import.upload_start', {'name': access.name, 'size': access.stat().st_size, 'source_id': origin['id']})
            with access.open('rb') as source:
                offset = 0
                while block := source.read(upload['chunk_bytes']):
                    service.call('import.upload_chunk', {'upload_id': upload['upload_id'], 'offset': offset, 'content': base64.b64encode(block).decode()})
                    offset += len(block)
            diagnosed = service.call('import.diagnose', {'upload_id': upload['upload_id']})
            diagnostic = diagnosed['diagnostic']
            assert diagnostic['read_only'] and diagnostic['links_followed'] == 0 and diagnostic['expressions'] is False
            assert digest(access) == before
            mapped = service.call('import.map', {'batch_id': diagnosed['batch_id'], 'profile': diagnosed['profile']})
            assert mapped['counts'] == {'customers': 2, 'vehicles': 2, 'invoices': 2}
            assert mapped['incident_counts']['error'] == 0
            service.call('import.discard', {'upload_id': upload['upload_id'], 'reason': 'Fin de comprobación sintética del lector distribuido'})
            evidence['checks'].append('JRE/Jackcess incluidos leen ACCDB real, conservan hash y rechazan vínculo remoto')

            notices = service.call('licenses.status')
            assert notices['available']
            exported = service.call('licenses.export')
            assert exported['bytes'] > 0 and hashlib.sha256(base64.b64decode(exported['content'])).hexdigest() == exported['sha256']
            evidence['checks'].append('Avisos de licencias incluidos: manifiesto y archivos verificados antes de exportar')

            backup = service.call('backup.create', {'password': 'clave-sintetica-no-real-2026'})
            downloaded = folder/'copia guardada.canamo'
            service.download(backup, downloaded)
            evidence['checks'].append('Copia cifrada descargada en bloques con tamaño/huellas/EOF verificados y token revocado')
            portable = service.call('data.export', {'kind': 'portable'})
            portable_path = folder/'portable.zip'
            service.download(portable, portable_path)
            with zipfile.ZipFile(portable_path) as archive:
                assert archive.testzip() is None and 'manifest.json' in archive.namelist()
            evidence['checks'].append('Exportación portable ZIP descargada por capability y comprobada íntegramente')

            calls = service.calls
            service.shutdown()
            reopened = Service(command, folder/'workshop')
            service = reopened
            historic = service.call('documents.get', {'identifier': invoice['id']})
            assert historic['id'] == invoice['id']
            evidence['reopen_seconds'] = round(time.perf_counter()-service.started, 4)
            service.shutdown()
            evidence['checks'].append('Cierre con acuse y reapertura conservan el documento')
            # Exercise the dedicated, read-only entry point against the same
            # synthetic database. Missing release evidence must never pass.
            database = folder/'workshop/taller.sqlite3'
            before_database = digest(database)
            release_command = command if packaged else [sys.executable, str(ROOT/'scripts/sidecar_entry.py')]
            release = subprocess.run([*release_command, '--data', str(folder/'workshop'), '--verify-release-evidence'],
                    capture_output=True, text=True, encoding='utf-8', timeout=90,
                    env={**os.environ, 'PYTHONPATH': str(ROOT/'backend')})
            release_result = json.loads(release.stdout)
            assert release.returncode == 1 and release_result['ok'] is False
            assert release_result['production_activated'] is False and release_result['network_called'] is False
            assert release_result['release_evidence']['ok'] is False
            assert digest(database) == before_database
            evidence['checks'].append('CLI de expediente rechaza evidencias ausentes sin modificar la base ni activar producción')
            evidence['calls'] = calls + service.calls
            evidence['ok'] = True
    except BaseException as error:
        evidence['error'] = str(error)
        if service is not None:
            evidence['calls'] = service.calls
        raise
    finally:
        if service is not None:
            service.abort()
            errors = service.errors.decode('utf-8', 'replace')
            if errors:
                output.with_suffix('.stderr.txt').write_text(errors, encoding='utf-8')
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: evidence[key] for key in ('ok', 'packaged', 'startup_seconds', 'reopen_seconds', 'checks')}, ensure_ascii=False))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--executable', type=Path)
    mode.add_argument('--source-check', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/sidecar-functional.json')
    args = parser.parse_args()
    command = [str(args.executable.resolve())] if args.executable else [sys.executable, '-m', 'taller.stdio']
    verify(command, args.output, packaged=args.executable is not None)


if __name__ == '__main__':
    main()
