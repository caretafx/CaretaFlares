"""Monta dist/OpticalFlaresNDK a partir dos builds.

    python tools/make_dist.py

Resultado (para copiar, quando aprovado, para o _AutoInstaller):
    dist/OpticalFlaresNDK/init.py
    dist/OpticalFlaresNDK/Nuke15.2/OpticalFlares.dll
    dist/OpticalFlaresNDK/Nuke17.0/OpticalFlares.dll
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDS = {'Nuke15.2': 'Nuke15.2v9', 'Nuke17.0': 'Nuke17.0v2'}


def main():
    dist = os.path.join(ROOT, 'dist', 'OpticalFlaresNDK')
    os.makedirs(dist, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, 'package', 'init.py'), dist)
    ok = True
    for sub, build in BUILDS.items():
        src = os.path.join(ROOT, 'build', build, 'OpticalFlares.dll')
        if not os.path.isfile(src):
            print('faltando: ' + src)
            ok = False
            continue
        os.makedirs(os.path.join(dist, sub), exist_ok=True)
        shutil.copy2(src, os.path.join(dist, sub, 'OpticalFlares.dll'))
        print('ok: ' + sub)
    print(dist)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
