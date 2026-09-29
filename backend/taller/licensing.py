"""Read-only access to the dependency notices shipped with this application."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

from . import __version__
from .errors import AppError, require

LEGAL_ROOT = Path(__file__).parent / 'legal'


def status():
    available = (LEGAL_ROOT / 'manifest.json').is_file()
    return {'version': __version__, 'available': available,
            'description': 'Licencias, avisos y fuentes de los componentes incluidos y del entorno de construcción.'}


def export():
    require((LEGAL_ROOT / 'manifest.json').is_file(),
            'No se encuentra el inventario de licencias. Repara la instalación.', 'licenses_missing')
    try:
        raw_manifest = (LEGAL_ROOT / 'manifest.json').read_bytes()
        manifest = json.loads(raw_manifest)
        require(manifest.get('format') == 'canamo-third-party-notices-v1', 'Inventario de licencias no reconocido.')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', raw_manifest)
            for name, expected in manifest['files_sha256'].items():
                source = (LEGAL_ROOT / name).resolve()
                require(source.is_relative_to(LEGAL_ROOT.resolve()) and not Path(name).is_absolute()
                        and '..' not in Path(name).parts and source.is_file(),
                        'El inventario de licencias contiene un archivo no válido.', 'licenses_changed')
                content = source.read_bytes()
                require(hashlib.sha256(content).hexdigest() == expected,
                        'Un aviso de licencia ha cambiado. Repara la instalación.', 'licenses_changed')
                archive.writestr(name, content)
        data = output.getvalue()
        return {'name': 'taller-canamo-licencias-' + __version__ + '.zip', 'mime': 'application/zip',
                'content': base64.b64encode(data).decode(), 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AppError('No se puede leer el inventario de licencias. Repara la instalación.', 'licenses_missing') from exc
