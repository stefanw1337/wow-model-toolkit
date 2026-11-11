"""Download m3addon (SC2Mapster, GPL-2), the .m3 reader the ogre builder uses, into tools/m3addon.
It is fetched at setup and never committed here."""
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

COMMIT = '58935005c4465a219a740f6b740253533eda773f'
URL = f'https://github.com/SC2Mapster/m3addon/archive/{COMMIT}.zip'
TARGET = Path(__file__).resolve().parents[2] / 'tools' / 'm3addon'


def main():
    if (TARGET / 'm3.py').exists():
        print(f'm3addon is already in {TARGET}')
        return
    with urllib.request.urlopen(URL, timeout=120) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    prefix = f'm3addon-{COMMIT}/'
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in archive.namelist():
        if name.startswith(prefix) and not name.endswith('/'):
            target = TARGET / name[len(prefix):]
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, open(target, 'wb') as out:
                shutil.copyfileobj(source, out)
    if not (TARGET / 'm3.py').exists():
        sys.exit(f'{URL} did not contain m3.py')
    print(f'm3addon {COMMIT[:7]} is in {TARGET}')


if __name__ == '__main__':
    main()
