# CaretaFlares - entrada no menu Nodes (barra lateral) e flare padrao ao criar o no.
import os

import nuke

_cf_root = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
_cf_icons = _cf_root + '/icons'
_cf_toolbar = nuke.toolbar('Nodes')
if _cf_toolbar is not None:
    _cf_menu = _cf_toolbar.findItem('CaretaFlares') or _cf_toolbar.addMenu(
        'CaretaFlares', icon=_cf_icons + '/CaretaFlares_menu.png')
    if _cf_menu.findItem('CaretaFlares') is None:
        _cf_menu.addCommand('CaretaFlares', "nuke.createNode('CaretaFlares')",
                            icon=_cf_icons + '/CaretaFlares_menu.png')


def _cf_default_flare():
    """No criado pelo usuario (menu/Tab) ja nasce com o default.ofp do pacote, a luz no
    terco superior esquerdo e o centro no meio. Scripts abertos nao passam por aqui."""
    node = nuke.thisNode()
    try:
        if node['renderOptions'].value():
            return
        path = _cf_root + '/default.ofp'
        if not os.path.isfile(path):
            return
        with open(path, 'rb') as fh:
            data = fh.read()
        node['renderOptions'].setValue('%d;%s' % (len(data), ''.join('%02x' % b for b in bytearray(data))))
        if 'ofpPresetName' in node.knobs():
            node['ofpPresetName'].setValue('Default')
        fmt = node.format()
        w, h = float(fmt.width()), float(fmt.height())
        node['PositionXY'].setValue([w * 0.3, h * 0.65])
        node['CenterPosition'].setValue([w * 0.5, h * 0.5])
    except Exception as exc:
        nuke.tprint('CaretaFlares: flare padrao nao aplicado: %s' % exc)


nuke.addOnUserCreate(_cf_default_flare, nodeClass='CaretaFlares')
