"""Builds MDL3Setup.exe (dev.47) with PyInstaller, on Windows.

    python tools/installer/build_installer.py build <build variant folder> [--out <folder>]
        e.g. build/preview (preview) or build (full). Takes payload/Native/mdl_native_bridge.dll and BUILD.json from it,
        the Certum intermediate certificate from extras/MDL3-EAC-Fix-Kit-*.zip, and writes <variant>/MDL3Setup.exe.
    python tools/installer/build_installer.py zip <MDL3 release zip> [--out <folder>]
        the same from a finished release package (its Native/mdl_native_bridge.dll and BUILD.json); default out: dist/
    python tools/installer/build_installer.py sign <exe>
        signs it with YOUR code-signing certificate (signtool /a, RFC 3161 timestamp). Run it yourself; optional,
        but a signed exe is flagged far less often by antivirus programs.

Needs: pip install pyinstaller  (6.x). The exe is built without UPX (packed exes are flagged more often).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CERT_THUMB = '8d57e2b4008bbe461470a69f3492bc5ae362a7a9'
CERT_NAME = 'Certum_Code_Signing_2021_CA.cer'
SOURCES = ('mdl3_setup.py', 'mdl3setup_core.py', 'mdl3setup_win.py')


def sha(data): return hashlib.sha256(data).hexdigest()


def certificate():
    for kit in sorted((ROOT / 'extras').glob('MDL3-EAC-Fix-Kit-*.zip')):
        with zipfile.ZipFile(kit) as z:
            for n in z.namelist():
                if n.endswith('/' + CERT_NAME) or n == CERT_NAME:
                    der = z.read(n)
                    if hashlib.sha1(der).hexdigest() == CERT_THUMB: return der
    raise SystemExit('certificate %s (%s) not found in extras/MDL3-EAC-Fix-Kit-*.zip' % (CERT_NAME, CERT_THUMB))


def payload(variant, folder):
    meta = json.loads((variant / 'BUILD.json').read_text(encoding='utf-8'))
    dll = (variant / 'payload/Native/mdl_native_bridge.dll').read_bytes()
    if sha(dll) != meta['native_sha256']: raise SystemExit('the DLL does not match %s/BUILD.json' % variant)
    minimal = {k: meta.get(k) for k in ('version', 'native_version', 'native_sha256', 'native_thumbprint', 'requires_signature',
                                         'native_path', 'patch_sha256', 'preview')}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'mdl_native_bridge.dll').write_bytes(dll)
    (folder / 'BUILD.json').write_text(json.dumps(minimal, sort_keys=True, indent=1), encoding='ascii')
    (folder / CERT_NAME).write_bytes(certificate())
    return minimal


def version_file(path, version):
    import re
    nums = [int(x) for x in re.findall(r'\d+', version)[:4]] + [0, 0, 0, 0]
    t = tuple(nums[:4])
    path.write_text('''VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)s, prodvers=%(t)s, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'MDL3'),
      StringStruct('FileDescription', 'MDL3 Setup - install, repair and remove MDL3 for Helldivers 2'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', 'MDL3Setup'),
      StringStruct('OriginalFilename', 'MDL3Setup.exe'),
      StringStruct('ProductName', 'MDL3'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''' % {'t': t, 'v': version}, encoding='utf-8')


def build(variant, out=None):
    if os.name != 'nt': raise SystemExit('MDL3Setup.exe is built on Windows (PyInstaller makes executables for the system it runs on)')
    try: import PyInstaller  # noqa: F401
    except ImportError: raise SystemExit('PyInstaller is missing: python -m pip install pyinstaller')
    variant = Path(variant).resolve()
    out = Path(out).resolve() if out else variant
    work = Path(tempfile.mkdtemp(prefix='mdl3setup_'))
    try:
        src = work / 'src'; src.mkdir()
        for n in SOURCES: shutil.copyfile(HERE / n, src / n)
        meta = payload(variant, src / 'payload')
        version_file(work / 'version.txt', meta['version'])
        cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--noconsole', '--noupx',
               '--name', 'MDL3Setup', '--paths', str(src), '--hidden-import', 'mdl3setup_core', '--hidden-import', 'mdl3setup_win',
               '--add-data', str(src / 'payload') + os.pathsep + 'payload', '--version-file', str(work / 'version.txt'),
               '--distpath', str(work / 'dist'), '--workpath', str(work / 'build'), '--specpath', str(work),
               str(src / 'mdl3_setup.py')]
        p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if p.returncode: raise SystemExit('PyInstaller failed:\n' + p.stdout[-3000:] + p.stderr[-3000:])
        exe = work / 'dist/MDL3Setup.exe'
        out.mkdir(parents=True, exist_ok=True)
        target = out / 'MDL3Setup.exe'
        shutil.copyfile(exe, target)
        info = {'version': meta['version'], 'native_sha256': meta['native_sha256'], 'exe_sha256': sha(target.read_bytes()),
                'bytes': target.stat().st_size, 'signed': False}
        (out / 'MDL3Setup.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
        print('MDL3Setup.exe ->', target, info['bytes'], 'bytes')
        return target
    finally:
        shutil.rmtree(work, ignore_errors=True)


def from_zip(package, out=None):
    """MDL3Setup.exe from a release ZIP (no build folder needed)."""
    package = Path(package).resolve()
    work = Path(tempfile.mkdtemp(prefix='mdl3setup_zip_'))
    try:
        with zipfile.ZipFile(package) as z:
            names = set(z.namelist())
            for need in ('Native/mdl_native_bridge.dll', 'BUILD.json'):
                if need not in names: raise SystemExit('%s has no %s: not an MDL3 package' % (package.name, need))
            (work / 'payload/Native').mkdir(parents=True)
            (work / 'payload/Native/mdl_native_bridge.dll').write_bytes(z.read('Native/mdl_native_bridge.dll'))
            (work / 'BUILD.json').write_bytes(z.read('BUILD.json'))
        print('package:', package.name)
        return build(work, out or (ROOT / 'dist'))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def signtool():
    found = shutil.which('signtool')
    if found: return found
    kits = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10/bin'
    for p in sorted(kits.glob('*/x64/signtool.exe'), reverse=True): return str(p)
    raise SystemExit('signtool.exe not found (Windows SDK)')


def sign(exe):
    exe = Path(exe).resolve()
    cmd = [signtool(), 'sign', '/a', '/fd', 'sha256', '/tr', 'http://time.certum.pl', '/td', 'sha256',
           '/d', 'MDL3 Setup', str(exe)]
    print(' '.join(cmd))
    subprocess.run(cmd, check=True)
    subprocess.run([signtool(), 'verify', '/pa', str(exe)], check=True)
    meta = exe.with_suffix('.json')
    if meta.exists():
        info = json.loads(meta.read_text(encoding='utf-8')); info.update(signed=True, exe_sha256=sha(exe.read_bytes()))
        meta.write_text(json.dumps(info, indent=2), encoding='utf-8')


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'build': build(a[1], a[a.index('--out') + 1] if '--out' in a else None)
    elif len(a) >= 2 and a[0] == 'zip': from_zip(a[1], a[a.index('--out') + 1] if '--out' in a else None)
    elif len(a) == 2 and a[0] == 'sign': sign(a[1])
    else: raise SystemExit(__doc__)
