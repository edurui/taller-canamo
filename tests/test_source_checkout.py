"""A Windows-style Git checkout must preserve the bytes of pinned resources."""
from pathlib import Path
import subprocess


def test_checkout_with_autocrlf_preserves_pinned_resources(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / '.gitattributes').write_bytes((root / '.gitattributes').read_bytes())
    resources = {
        'backend/taller/schemas/synthetic/source.xsd': b'<schema>\r\n</schema>\r\n',
        'backend/taller/fonts/LICENSE.txt': b'Synthetic font license\n',
        'tools/legal/supplemental/synthetic/LICENSE': b'Synthetic supplemental license\n',
        'tools/access/licenses/LICENSE.txt': b'Synthetic reader license\r\n',
        'tools/assistant/licenses/LICENSE.txt': b'Synthetic model license\n',
    }
    for name, data in resources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (tmp_path / 'synthetic.py').write_bytes(b'print("synthetic")\n')
    (tmp_path / 'src-tauri').mkdir(exist_ok=True)
    (tmp_path / 'src-tauri/Cargo.toml').write_bytes(b'[package]\nname = "synthetic"\n')
    (tmp_path / 'synthetic.cmd').write_bytes(b'@echo synthetic\n')

    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args],
                              check=True, capture_output=True)

    git('init', '--quiet')
    git('-c', 'core.autocrlf=false', 'add', '--all')
    git('-c', 'user.name=Synthetic test', '-c', 'user.email=synthetic@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic checkout fixture')
    checkout = tmp_path / 'fresh-windows-checkout'
    git('-c', 'core.autocrlf=true', 'checkout-index', '--all', '--prefix=' + checkout.as_posix() + '/')
    for name, data in resources.items():
        assert (checkout / name).read_bytes() == data, name
    assert (checkout / 'synthetic.py').read_bytes() == b'print("synthetic")\n'
    assert (checkout / 'src-tauri/Cargo.toml').read_bytes() == b'[package]\nname = "synthetic"\n'
    assert (checkout / 'synthetic.cmd').read_bytes() == b'@echo synthetic\r\n'
