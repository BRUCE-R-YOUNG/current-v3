"""Synchronize shared manuals and package only distributable source files."""
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package():
    for role in ('raspi', 'pc'):
        base = ROOT / role
        for source in (ROOT / 'docs').glob('*.md'):
            (base / 'docs').mkdir(exist_ok=True)
            shutil.copy2(source, base / 'docs' / source.name)
        files = [p for p in base.glob('*.py')]
        files += list(base.glob('requirements*.txt')) + [base / 'README.md']
        files += [p for p in (base / 'app').rglob('*')
                  if p.suffix in {'.py', '.html', '.css', '.js'} and '__pycache__' not in p.parts]
        files += list((base / 'docs').glob('*.md'))
        files += list((base / 'config').glob('*.example.yaml'))
        files += list((base / 'deploy').glob('*.service'))
        target = ROOT / f'svl-{role}.zip'
        temporary = target.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(set(files)):
                archive.write(file, file.relative_to(ROOT))
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert not any('/runtime/' in n or '/.venv/' in n or n.endswith('.env') for n in names)
        temporary.replace(target)
        print(f'{target.name}: {len(files)} files')


if __name__ == '__main__':
    package()
