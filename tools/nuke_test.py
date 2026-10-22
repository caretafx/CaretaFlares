"""Teste do CaretaFlares sem alterar o ~/.nuke.

Abra um Nuke 15.2 ou 17.0 NOVO (sessao em que nenhum CaretaFlares foi criado
nem nenhum script com ele foi aberto; uma sessao so registra o no uma vez) e rode no Script Editor:

    exec(open(r'E:/Careta/OpticalFlaresNDK/tools/nuke_test.py').read())

O Nuke procura plugins pelo nome no plugin path, e la esta a pasta do plugin
antigo (que nao carrega no 15/17). Para nao depender dessa busca, este script
carrega o DLL novo direto pelo caminho completo com o carregador do Windows; o
DLL registra o no "CaretaFlares" ao carregar. Cada passo vai para
E:/Careta/OpticalFlaresNDK/build/nuke_test.log.
"""
import ctypes
import os
import traceback
from ctypes import wintypes

import nuke

_OF_ROOT = 'E:/Careta/OpticalFlaresNDK'
_OF_LOG = _OF_ROOT + '/build/nuke_test.log'
_OF_BUILDS = {(15, 2): 'Nuke15.2v9', (17, 0): 'Nuke17.0v2'}


def _of_log(msg):
    with open(_OF_LOG, 'a', encoding='utf-8', errors='replace') as fh:
        fh.write(msg + '\n')
    print(msg)


def _of_run():
    open(_OF_LOG, 'w').close()
    _of_log('Nuke %s' % nuke.NUKE_VERSION_STRING)
    key = (nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR)
    if key not in _OF_BUILDS:
        _of_log('sem build para esta versao')
        return
    dll = _OF_ROOT + '/build/' + _OF_BUILDS[key] + '/CaretaFlares.dll'
    _of_log('dll: %s (existe=%s)' % (dll, os.path.isfile(dll)))
    _of_log('plugin path: %s' % nuke.pluginPath())
    try:
        _of_log('ja carregados: %s' % nuke.plugins(nuke.ALL, 'CaretaFlares*'))
    except Exception as exc:
        _of_log('nuke.plugins falhou: %r' % (exc,))

    # 1) carrega uma COPIA do DLL novo pelo caminho completo; assim o arquivo do
    #    build nao fica travado e da para recompilar com o Nuke aberto
    import shutil
    import time
    run_dir = os.path.dirname(dll) + '/run'
    os.makedirs(run_dir, exist_ok=True)
    copy = '%s/CaretaFlares_%d.dll' % (run_dir, int(time.time()))
    shutil.copy2(dll, copy)
    _of_log('copia carregada: %s' % copy)
    dll = copy
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    LOAD_WITH_ALTERED_SEARCH_PATH = 0x8
    handle = k32.LoadLibraryExW(dll.replace('/', '\\'), None, LOAD_WITH_ALTERED_SEARCH_PATH)
    if not handle:
        _of_log('LoadLibrary FALHOU, erro Windows %d' % ctypes.get_last_error())
        return
    _of_log('LoadLibrary ok')

    # browser de presets: modulo do pacote + copia do CaretaFlaresThumb.dll (tambem nao trava o build)
    import sys
    pkg = _OF_ROOT + '/package'
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    thumb = os.path.dirname(os.path.dirname(copy)) + '/CaretaFlaresThumb.dll'
    if os.path.isfile(thumb):
        thumb_copy = '%s/CaretaFlaresThumb_%d.dll' % (run_dir, int(time.time()))
        shutil.copy2(thumb, thumb_copy)
        os.environ['CARETAFLARES_THUMB_DLL'] = thumb_copy
        try:
            import importlib
            import caretaflares_browser, caretaflares_preset, caretaflares_params, caretaflares_options
            for mod in (caretaflares_browser, caretaflares_preset, caretaflares_params, caretaflares_options):
                importlib.reload(mod)
            caretaflares_browser.THUMB_DLL = thumb_copy
            _of_log('browser pronto (miniaturas: %s)' % thumb_copy)
        except Exception as exc:
            _of_log('browser falhou ao importar: %r' % (exc,))

    # 2) cria o no solto (sem ligar no que estiver selecionado) e mostra no viewer
    for sel in nuke.selectedNodes():
        sel.setSelected(False)
    try:
        node = nuke.createNode('CaretaFlares', inpanel=True)
    except Exception as exc:
        _of_log('createNode falhou: %r' % (exc,))
        _of_log(traceback.format_exc())
        return
    _of_log('no criado: %s (classe %s)' % (node.name(), node.Class()))
    _of_log('knobs: %d, tem renderOptions=%s, tem ofpPresetFile=%s' % (
        len(node.knobs()), 'renderOptions' in node.knobs(), 'ofpPresetFile' in node.knobs()))

    # 3) posicao, centro e preset
    fmt = node.format()
    node['PositionXY'].setValue([fmt.width() * 0.3, fmt.height() * 0.6])
    node['CenterPosition'].setValue([fmt.width() * 0.5, fmt.height() * 0.5])
    os.environ.setdefault('CARETAFLARES_DATA', _OF_ROOT + '/data')  # texturas para o DLL do build
    presets = _OF_ROOT + '/data/Presets/Lens Flares/Pro Presets'
    # troque o nome para testar outro preset (OF_TEST_PRESET tambem funciona)
    preset = presets + '/' + os.environ.get('OF_TEST_PRESET', 'Natural Light') + '.ofp'
    _of_log('preset: %s (existe=%s)' % (preset, os.path.isfile(preset)))
    node['ofpPresetFile'].setValue(preset)
    _of_log('renderOptions: %d caracteres' % len(node['renderOptions'].value()))

    # 4) amostra um pixel no centro do glow (forca um render pequeno)
    try:
        x, y = fmt.width() * 0.3, fmt.height() * 0.6
        rgb = [node.sample(c, x, y) for c in ('rgba.red', 'rgba.green', 'rgba.blue')]
        _of_log('pixel na luz: %s' % rgb)
    except Exception as exc:
        _of_log('sample falhou: %r' % (exc,))
    viewers = nuke.allNodes('Viewer')
    if viewers:
        viewers[0].setInput(0, node)
        _of_log('viewer %s ligado no no' % viewers[0].name())
    _of_log('FIM OK')


try:
    _of_run()
except Exception:
    _of_log('ERRO:\n' + traceback.format_exc())
