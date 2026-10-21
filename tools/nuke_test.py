"""Teste do OpticalFlaresNDK sem alterar o ~/.nuke.

No Script Editor do Nuke 15.2 ou 17.0, logo depois de abrir o Nuke
(antes de criar qualquer no OpticalFlares), rode:

    exec(open(r'E:/Careta/OpticalFlaresNDK/tools/nuke_test.py').read())

O script carrega o DLL novo pelo caminho completo (assim o DLL antigo em
~/.nuke/OpticalFlares/plugin nao e usado), cria um no e carrega o preset
"Hot Glow". Depois disso voce pode abrir scripts antigos com OpticalFlares
na mesma sessao: o no novo le o estado salvo neles.
"""
import os

import nuke

_OF_BUILDS = {(15, 2): 'Nuke15.2v9', (17, 0): 'Nuke17.0v2'}
_of_key = (nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR)
if _of_key not in _OF_BUILDS:
    raise RuntimeError('Sem build do OpticalFlaresNDK para Nuke %s' % nuke.NUKE_VERSION_STRING)

_of_dll = 'E:/Careta/OpticalFlaresNDK/build/%s/OpticalFlares.dll' % _OF_BUILDS[_of_key]
nuke.load(_of_dll)
print('OpticalFlaresNDK carregado de ' + _of_dll)

_of_presets = os.environ.get(
    'OPTICAL_FLARES_PRESET_PATH',
    os.path.expanduser('~/.nuke/OpticalFlares/Optical Flares Presets'),
).replace('\\', '/')

_of_node = nuke.createNode('OpticalFlares')
_of_fmt = _of_node.format()
_of_node['PositionXY'].setValue([_of_fmt.width() * 0.3, _of_fmt.height() * 0.6])
_of_node['CenterPosition'].setValue([_of_fmt.width() * 0.5, _of_fmt.height() * 0.5])
_of_node['ofpPresetFile'].setValue(_of_presets + '/Custom Objects/Hot Glow.ofp')
print('renderOptions: %d caracteres' % len(_of_node['renderOptions'].value()))
