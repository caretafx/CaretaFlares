# CaretaFlares - entrada no menu Nodes (barra lateral), com icone proprio.
import os

import nuke

_cf_icons = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/') + '/icons'
_cf_toolbar = nuke.toolbar('Nodes')
if _cf_toolbar is not None:
    _cf_menu = _cf_toolbar.findItem('CaretaFlares') or _cf_toolbar.addMenu(
        'CaretaFlares', icon=_cf_icons + '/CaretaFlares_menu.png')
    if _cf_menu.findItem('CaretaFlares') is None:
        _cf_menu.addCommand('CaretaFlares', "nuke.createNode('CaretaFlares')",
                            icon=_cf_icons + '/CaretaFlares_menu.png')
