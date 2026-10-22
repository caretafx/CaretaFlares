"""Teste do OpticalFlaresNDK sem alterar o ~/.nuke.

Abra um Nuke 15.2 ou 17.0 NOVO (sessao em que nenhum OpticalFlares foi criado
nem nenhum script com ele foi aberto) e rode no Script Editor:

    exec(open(r'E:/Careta/OpticalFlaresNDK/tools/nuke_test.py').read())

O Nuke procura o plugin pelo nome "OpticalFlares" no plugin path, e o seu
~/.nuke/init.py coloca nele a pasta do plugin antigo (que nao carrega no 15/17).
Este script poe a pasta do build novo NA FRENTE do plugin path, so nesta
sessao, carrega o plugin e mostra de qual arquivo ele veio. Depois cria um no
com o preset "Hot Glow".
"""
import os

import nuke

_OF_BUILDS = {(15, 2): 'Nuke15.2v9', (17, 0): 'Nuke17.0v2'}
_of_key = (nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR)
if _of_key not in _OF_BUILDS:
    raise RuntimeError('Sem build do OpticalFlaresNDK para Nuke %s' % nuke.NUKE_VERSION_STRING)

_of_dir = 'E:/Careta/OpticalFlaresNDK/build/' + _OF_BUILDS[_of_key]
nuke.pluginAddPath(_of_dir)
print('plugin path (inicio): %s' % nuke.pluginPath()[:3])

try:
    nuke.load('OpticalFlares')
except Exception as exc:  # a mensagem do Windows pode vir com acento quebrado
    print('nuke.load falhou: %r' % (exc,))
    raise

for _of_p in nuke.plugins(nuke.ALL | nuke.NODIR, 'OpticalFlares*'):
    print('carregado: ' + _of_p)
for _of_p in nuke.plugins(nuke.ALL, 'OpticalFlares*'):
    print('arquivo:   ' + _of_p)

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
