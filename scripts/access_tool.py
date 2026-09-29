"""Offline Access extraction and portable CSV-table packages, without Office drivers."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from taller.access import extract_access, json_write
from taller.errors import AppError


def pack(directory, destination):
    destination = Path(destination)
    if destination.exists():
        raise AppError('El destino existe. Elige otro nombre; no se sobrescribe.')
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.write(directory / 'manifest.json', 'manifest.json')
            for table in manifest['tables']:
                if not table.get('linked'):
                    archive.write(directory / table['file'], table['file'])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    native = sub.add_parser('extract', help='Lee una copia MDB/ACCDB sin macros ni vínculos y crea un paquete ZIP.')
    native.add_argument('source', type=Path); native.add_argument('destination', type=Path)
    csv_parser = sub.add_parser('csv-package', help='Empaqueta tablas CSV exportadas explícitamente desde Access.')
    csv_parser.add_argument('destination', type=Path)
    csv_parser.add_argument('--table', action='append', required=True, help='Nombre=archivo.csv; puede repetirse')
    csv_parser.add_argument('--encoding', choices=('utf-8-sig', 'cp1252', 'utf-16'), default='utf-8-sig')
    csv_parser.add_argument('--delimiter', choices=(';', ',', '\t'), default=';')
    report = sub.add_parser('report', help='Copia el informe completo ya preparado por el asistente, sin límite de memoria.')
    report.add_argument('source', type=Path, help='imports/UUID/report.jsonl dentro de la carpeta de datos')
    report.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise AppError('El destino ya existe. Usa otro nombre.')
    if args.command == 'report':
        if args.source.name != 'report.jsonl' or not args.source.is_file():
            raise AppError('Selecciona el informe report.jsonl generado por el asistente.')
        with args.source.open('rb') as source, args.destination.open('xb') as output:
            shutil.copyfileobj(source, output)
        print(args.destination); return
    with tempfile.TemporaryDirectory(prefix='canamo-access-export-') as temporary:
        directory = Path(temporary) / 'tables'
        if args.command == 'extract':
            manifest = extract_access(args.source.resolve(), directory)
        else:
            directory.mkdir()
            manifest = {'format': 'canamo-access-raw-v1', 'engine': 'CSV exportado explícitamente; no es lectura nativa MDB', 'tables': [], 'encoding': args.encoding}
            seen = set()
            for number, specification in enumerate(args.table):
                name, separator, filename = specification.partition('=')
                if not separator or not name or name in seen:
                    raise AppError('Usa nombres únicos con --table Nombre=archivo.csv.')
                seen.add(name); target = directory / ('table-' + str(number) + '.jsonl'); count = 0
                with Path(filename).open(encoding=args.encoding, newline='') as source, target.open('w', encoding='utf-8') as output:
                    reader = csv.DictReader(source, delimiter=args.delimiter); columns = reader.fieldnames or []
                    if not columns or len(columns) != len(set(columns)):
                        raise AppError('CSV con cabeceras vacías/duplicadas: ' + name)
                    for count, row in enumerate(reader, 1):
                        if None in row or any(value is None for value in row.values()):
                            raise AppError(f'{name}, fila {count+1}: número de campos no válido.')
                        output.write(json.dumps(row, ensure_ascii=False) + '\n')
                manifest['tables'].append({'name': name, 'file': target.name, 'linked': False, 'rows': count, 'primary_key': [], 'columns': [{'name': name, 'type': 'TEXT'} for name in columns]})
            json_write(directory / 'manifest.json', manifest)
        pack(directory, args.destination)
        print(json.dumps({'package': str(args.destination), 'tables': [{key: table.get(key) for key in ('name', 'rows', 'linked')} for table in manifest['tables']]}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (AppError, OSError, UnicodeError, csv.Error) as failure:
        raise SystemExit(str(failure))
