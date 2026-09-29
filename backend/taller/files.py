"""Atomic replacement for generated resources stored in the application's data directory."""
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: bytes) -> None:
    path = Path(path)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.tmp', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
