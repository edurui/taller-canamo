"""Run the built UI + loopback service. No cloud or fiscal production calls."""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", default=str(Path.home() / ".canamo-handoff-demo"))
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    if not (ROOT / "dist" / "index.html").is_file():
        parser.error("Falta compilar la interfaz. Ejecuta npm install y npm run build.")
    from taller.server import run
    run(args.data, ROOT / "dist", args.port, not args.no_open)

if __name__ == "__main__":
    main()
