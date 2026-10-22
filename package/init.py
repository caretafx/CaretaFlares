# OpticalFlaresNDK - reimplementacao do Optical Flares para Nuke 15.2 e 17.0.
# Adiciona ao plugin path a subpasta compilada para a versao do Nuke em uso.
# A pasta e autossuficiente: DLLs, browser, icone, presets e texturas ficam aqui dentro.
import os

import nuke

_of_root = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
_of_sub = {
    (15, 2): 'Nuke15.2',
    (17, 0): 'Nuke17.0',
}.get((nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR))

if _of_sub:
    _of_dir = _of_root + '/' + _of_sub
    if os.path.isdir(_of_dir) and _of_dir not in nuke.pluginPath():
        nuke.pluginAddPath(_of_dir)
else:
    nuke.tprint('OpticalFlaresNDK: sem build para Nuke %s (ha builds para 15.2 e 17.0)'
                % nuke.NUKE_VERSION_STRING)
