"""Monta dist/CaretaFlares: uma pasta-plugin que funciona copiada para qualquer PC.

    python tools/make_dist.py            (com presets e texturas)
    python tools/make_dist.py --sem-dados

Resultado:
    dist/CaretaFlares/init.py, menu.py, caretaflares_*.py, LEIA-ME.txt, icons/
    dist/CaretaFlares/Nuke15.2/CaretaFlares.dll + CaretaFlaresThumb.dll
    dist/CaretaFlares/Nuke17.0/CaretaFlares.dll + CaretaFlaresThumb.dll
    dist/CaretaFlares/Presets/    (presets; Pro Presets 1 e 2 dentro de Lens Flares)
    dist/CaretaFlares/Textures/   (texturas: Elements/ e Glass/)
    dist/CaretaFlares/default.ofp (flare que o no ganha ao ser criado)

Presets, texturas e default.ofp vem de data/ no projeto (fora do git, como dist/).
As pastas de dados sao espelhadas: o que nao existe em data/ sai do pacote.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDS = {'Nuke15.2': 'Nuke15.2v9', 'Nuke17.0': 'Nuke17.0v2'}
PACKAGE_FILES = ('init.py', 'menu.py', 'caretaflares_browser.py', 'caretaflares_options.py',
                 'caretaflares_preset.py', 'caretaflares_params.py', 'LEIA-ME.txt')
DLLS = ('CaretaFlares.dll', 'CaretaFlaresThumb.dll')
DATA = ('Presets', 'Textures')


def data_dir():
    return os.environ.get('CARETAFLARES_DATA') or os.path.join(ROOT, 'data')


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


def mirror_extras(src, dst):
    """Apaga do destino o que nao existe mais na origem (dados reorganizados)."""
    removed = 0
    for dp, dirs, files in os.walk(dst, topdown=False):
        rel = os.path.relpath(dp, dst)
        for f in files:
            if not os.path.isfile(os.path.join(src, rel, f)):
                os.remove(os.path.join(dp, f))
                removed += 1
        if dp != dst and not os.listdir(dp):
            os.rmdir(dp)
    return removed


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
        for name in DATA:
            src = os.path.join(data_dir(), name)
            if not os.path.isdir(src):
                print('sem dados: ' + src)
                ok = False
                continue
            n = sync_tree(src, os.path.join(dist, name))
            r = mirror_extras(src, os.path.join(dist, name))
            print('ok: %s (%d copiados, %d removidos)' % (name, n, r))
        default = os.path.join(data_dir(), 'default.ofp')
        if os.path.isfile(default):
            shutil.copy2(default, os.path.join(dist, 'default.ofp'))
            print('ok: default.ofp')
        else:
            print('sem default.ofp em ' + data_dir())
            ok = False
    print(dist)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
