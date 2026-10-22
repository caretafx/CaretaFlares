"""Monta dist/CaretaFlares: uma pasta-plugin que funciona copiada para qualquer PC.

    python tools/make_dist.py            (com presets e texturas)
    python tools/make_dist.py --sem-dados

Resultado:
    dist/CaretaFlares/init.py, menu.py, caretaflares_*.py, LEIA-ME.txt, icons/
    dist/CaretaFlares/Nuke15.2/CaretaFlares.dll + CaretaFlaresThumb.dll
    dist/CaretaFlares/Nuke17.0/CaretaFlares.dll + CaretaFlaresThumb.dll
    dist/CaretaFlares/Presets/    (presets)
    dist/CaretaFlares/Textures/   (texturas: Elements/ e Glass/)

Os presets e texturas sao copiados da pasta de dados do usuario (fora do git;
dist/ esta no .gitignore).
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDS = {'Nuke15.2': 'Nuke15.2v9', 'Nuke17.0': 'Nuke17.0v2'}
PACKAGE_FILES = ('init.py', 'menu.py', 'caretaflares_browser.py', 'caretaflares_options.py',
                 'caretaflares_preset.py', 'caretaflares_params.py', 'LEIA-ME.txt')
DLLS = ('CaretaFlares.dll', 'CaretaFlaresThumb.dll')
# pasta no pacote <- pasta na origem dos dados
DATA = {'Presets': 'Optical Flares Presets', 'Textures': 'Optical Flares Textures'}


def data_dir():
    p = os.environ.get('CARETAFLARES_DATA') or os.environ.get('OPTICAL_FLARES_PATH') \
        or os.path.expanduser('~/.nuke/OpticalFlares')
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
    dist = os.path.join(ROOT, 'dist', 'CaretaFlares')
    os.makedirs(dist, exist_ok=True)
    for f in PACKAGE_FILES:
        shutil.copy2(os.path.join(ROOT, 'package', f), dist)
    sync_tree(os.path.join(ROOT, 'package', 'icons'), os.path.join(dist, 'icons'))
    ok = True
    for sub, build in BUILDS.items():
        os.makedirs(os.path.join(dist, sub), exist_ok=True)
        for dll in DLLS:
            src = os.path.join(ROOT, 'build', build, dll)
            if not os.path.isfile(src):
                print('faltando: ' + src)
                ok = False
                continue
            shutil.copy2(src, os.path.join(dist, sub, dll))
        print('ok: ' + sub)
    if with_data:
        for name, src_name in DATA.items():
            src = os.path.join(data_dir(), src_name)
            if not os.path.isdir(src):
                print('sem dados: ' + src)
                ok = False
                continue
            n = sync_tree(src, os.path.join(dist, name))
            print('ok: %s (%d arquivos copiados)' % (name, n))
    print(dist)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
