"""Monta dist/OpticalFlaresNDK: uma pasta-plugin que funciona copiada para qualquer PC.

    python tools/make_dist.py            (com presets e texturas)
    python tools/make_dist.py --sem-dados

Resultado:
    dist/OpticalFlaresNDK/init.py, menu.py, ofndk_browser.py, LEIA-ME.txt, icons/
    dist/OpticalFlaresNDK/Nuke15.2/OpticalFlares.dll + ofthumb.dll
    dist/OpticalFlaresNDK/Nuke17.0/OpticalFlares.dll + ofthumb.dll
    dist/OpticalFlaresNDK/Optical Flares Presets/   (copiados da instalacao do usuario)
    dist/OpticalFlaresNDK/Optical Flares Textures/  (idem)

Os presets e texturas sao da Video Copilot (licenca do usuario): entram so no
pacote local, nunca no git (dist/ esta no .gitignore).
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDS = {'Nuke15.2': 'Nuke15.2v9', 'Nuke17.0': 'Nuke17.0v2'}
PACKAGE_FILES = ('init.py', 'menu.py', 'ofndk_browser.py', 'ofndk_options.py', 'ofndk_preset.py',
                 'ofndk_params.py', 'LEIA-ME.txt')
DATA = ('Optical Flares Presets', 'Optical Flares Textures')


def install_dir():
    p = os.environ.get('OPTICAL_FLARES_PATH') or os.path.expanduser('~/.nuke/OpticalFlares')
    return p


def sync_tree(src, dst):
    """Copia so o que mudou (tamanho ou data)."""
    copied = 0
    for dp, dirs, files in os.walk(src):
        rel = os.path.relpath(dp, src)
        out = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(out, exist_ok=True)
        for f in files:
            s, d = os.path.join(dp, f), os.path.join(out, f)
            if os.path.isfile(d):
                a, b = os.stat(s), os.stat(d)
                if a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
                    continue
            shutil.copy2(s, d)
            copied += 1
    return copied


def main():
    with_data = '--sem-dados' not in sys.argv
    dist = os.path.join(ROOT, 'dist', 'OpticalFlaresNDK')
    os.makedirs(dist, exist_ok=True)
    for f in PACKAGE_FILES:
        shutil.copy2(os.path.join(ROOT, 'package', f), dist)
    sync_tree(os.path.join(ROOT, 'package', 'icons'), os.path.join(dist, 'icons'))
    ok = True
    for sub, build in BUILDS.items():
        os.makedirs(os.path.join(dist, sub), exist_ok=True)
        for dll in ('OpticalFlares.dll', 'ofthumb.dll'):
            src = os.path.join(ROOT, 'build', build, dll)
            if not os.path.isfile(src):
                print('faltando: ' + src)
                ok = False
                continue
            shutil.copy2(src, os.path.join(dist, sub, dll))
        print('ok: ' + sub)
    if with_data:
        for d in DATA:
            src = os.path.join(install_dir(), d)
            if not os.path.isdir(src):
                print('sem dados da instalacao: ' + src)
                ok = False
                continue
            n = sync_tree(src, os.path.join(dist, d))
            print('ok: %s (%d arquivos copiados)' % (d, n))
    print(dist)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
