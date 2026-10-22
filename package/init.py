# CaretaFlares - lens flares para Nuke 15.2 e 17.0 (Windows).
# Adiciona ao plugin path a subpasta compilada para a versao do Nuke em uso e carrega o
# plugin ja na abertura, para que scripts antigos com nos "OpticalFlares" abram direto
# (o mesmo DLL registra os dois nomes).
# A pasta e autossuficiente: DLLs, janela Options, icone, presets e texturas ficam aqui.
import os

import nuke

_cf_root = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
_cf_sub = {
    (15, 2): 'Nuke15.2',
    (17, 0): 'Nuke17.0',
}.get((nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR))

if _cf_sub:
    _cf_dir = _cf_root + '/' + _cf_sub
    if os.path.isdir(_cf_dir):
        if _cf_dir not in nuke.pluginPath():
            nuke.pluginAddPath(_cf_dir)
        try:
            nuke.load('CaretaFlares')
        except Exception as _cf_exc:
            nuke.tprint('CaretaFlares: nao carregou o plugin: %s' % _cf_exc)
else:
    nuke.tprint('CaretaFlares: sem build para Nuke %s (ha builds para 15.2 e 17.0)'
                % nuke.NUKE_VERSION_STRING)
