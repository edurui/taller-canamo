"""Exact aliases for verified local schema files, including libxml's Windows URIs.

Only aliases generated from the caller's verified allowlist are accepted. There
is no basename fallback, arbitrary file lookup, network access or path traversal.
"""
from urllib.parse import unquote


def verified_file_aliases(paths):
    allowed = {}
    for path in paths:
        uri = path.as_uri()
        aliases = {str(path), path.as_posix(), uri, unquote(uri)}
        if uri.startswith('file:///'):
            short = 'file:/' + uri[len('file:///'):]
            aliases.update((short, unquote(short)))
        for alias in aliases:
            allowed[alias] = path
    return allowed
