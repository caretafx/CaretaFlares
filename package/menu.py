# OpticalFlaresNDK - entrada no menu Nodes.
# Se o ~/.nuke/menu.py ja tiver "VideoCopilot/OpticalFlares" (como no PC original),
# nao duplica: o item existente ja cria o no novo.
import os

import nuke

_of_icons = os.path.dirname(__file__).replace('\\', '/') + '/icons'
_of_toolbar = nuke.toolbar('Nodes')
if _of_toolbar is not None and _of_toolbar.findItem('VideoCopilot/OpticalFlares') is None:
    _of_menu = _of_toolbar.findItem('VideoCopilot') or _of_toolbar.addMenu(
        'VideoCopilot', icon=_of_icons + '/OpticalFlaresNDK_menu.png')
    _of_menu.addCommand('OpticalFlares', "nuke.createNode('OpticalFlares')",
                        icon=_of_icons + '/OpticalFlaresNDK_menu.png')
