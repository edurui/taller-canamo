"""libxml path spellings are allowed only for the exact verified resource."""
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from taller.schema_paths import verified_file_aliases


@pytest.mark.parametrize('path,accepted', [
    (PureWindowsPath('D:/schema con ñ/source.xsd'), [
        r'D:\schema con ñ\source.xsd', 'D:/schema con ñ/source.xsd',
        'file:/D:/schema%20con%20%C3%B1/source.xsd',
        'file:///D:/schema%20con%20%C3%B1/source.xsd',
        'file:/D:/schema con ñ/source.xsd',
    ]),
    (PurePosixPath('/schema con ñ/source.xsd'), [
        '/schema con ñ/source.xsd', 'file:/schema%20con%20%C3%B1/source.xsd',
        'file:///schema%20con%20%C3%B1/source.xsd',
    ]),
])
def test_verified_schema_accepts_native_and_libxml_file_uri_spellings(path, accepted):
    allowed = verified_file_aliases([path])
    for reference in accepted:
        assert allowed[reference] == path
    for forbidden in ('https://example.invalid/source.xsd', 'file://remote/source.xsd',
                      'file:/D:/other/source.xsd', 'file:///other/source.xsd',
                      '../source.xsd', 'source.xsd',
                      'file:/D:/schema%20con%20%C3%B1/../source.xsd'):
        assert forbidden not in allowed
