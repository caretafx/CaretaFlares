# -*- coding: utf-8 -*-
"""Botao "Link to Tracker..." do CaretaFlares.

Liga o knob Track Position a um track de um Tracker (Tracker4 ou o Tracker3 antigo) por
expressao, usa o frame atual como Reference Frame e liga o Use Track. Assim o flare segue o
movimento do track mas continua onde voce o posicionou (Position XY no frame de referencia).
"""
from __future__ import print_function

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets

import nuke

MAX_TRACKS = 500


def _expr_ok(expr):
    try:
        nuke.expression(expr)
        return True
    except Exception:
        return False


def _tracks(tracker):
    """Lista (rotulo, expressao_x, expressao_y) dos tracks de um Tracker."""
    name = tracker.fullName()
    out = []
    if tracker.Class() == 'Tracker4':
        for i in range(1, MAX_TRACKS + 1):
            ex = '%s.tracks.%d.track_x' % (name, i)
            if not _expr_ok(ex):
                break
            out.append(('track %d' % i, ex, '%s.tracks.%d.track_y' % (name, i)))
    else:  # Tracker3: track1..track4 sao knobs XY
        for i in range(1, 5):
            k = tracker.knob('track%d' % i)
            if k is None:
                break
            out.append(('track%d' % i, '%s.track%d.x' % (name, i), '%s.track%d.y' % (name, i)))
    return out


def _trackers():
    nodes = [n for n in nuke.allNodes(recurseGroups=True) if n.Class() in ('Tracker4', 'Tracker3')]
    selected = [n for n in nuke.selectedNodes() if n in nodes]
    return selected + [n for n in nodes if n not in selected]


class LinkDialog(QtWidgets.QDialog):
    def __init__(self, trackers, parent=None):
        super(LinkDialog, self).__init__(parent)
        self.setWindowTitle('CaretaFlares  -  Link to Tracker')
        self.trackers = trackers
        lay = QtWidgets.QFormLayout(self)
        self.tracker_box = QtWidgets.QComboBox()
        self.tracker_box.addItems([t.fullName() for t in trackers])
        self.track_box = QtWidgets.QComboBox()
        lay.addRow('Tracker', self.tracker_box)
        lay.addRow('Track', self.track_box)
        self.center_box = QtWidgets.QCheckBox('Mover o centro do flare junto')
        lay.addRow('', self.center_box)
        note = QtWidgets.QLabel('O frame atual vira o Reference Frame: deixe o flare onde quiser\n'
                                'neste frame; nos outros ele acompanha o movimento do track.')
        note.setStyleSheet('color: #9a9a9a;')
        lay.addRow(note)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addRow(buttons)
        self.tracker_box.currentIndexChanged.connect(self._fill_tracks)
        self._fill_tracks(0)

    def _fill_tracks(self, idx):
        self.track_box.clear()
        self.current_tracks = _tracks(self.trackers[idx]) if self.trackers else []
        self.track_box.addItems([t[0] for t in self.current_tracks] or ['(sem tracks)'])

    def choice(self):
        i = self.track_box.currentIndex()
        if not self.current_tracks or i < 0:
            return None
        return self.current_tracks[i]


def link_tracker(node):
    trackers = _trackers()
    if not trackers:
        nuke.message('CaretaFlares: nao ha nenhum Tracker no script.\n\n'
                     'Crie e rode um Tracker, ou ligue o knob Track Position por expressao '
                     'a qualquer ponto que se mova; depois marque Use Track.')
        return
    dlg = LinkDialog(trackers, QtWidgets.QApplication.activeWindow())
    ok = dlg.exec_() if hasattr(dlg, 'exec_') else dlg.exec()
    if not ok:
        return
    pick = dlg.choice()
    if pick is None:
        nuke.message('CaretaFlares: esse Tracker ainda nao tem tracks.')
        return
    _, ex, ey = pick
    nuke.Undo.begin('CaretaFlares: Link to Tracker')
    try:
        k = node['TrackPosition']
        k.setExpression(ex, 0)
        k.setExpression(ey, 1)
        node['TrackReferenceFrame'].setValue(nuke.frame())
        node['TrackCenter'].setValue(dlg.center_box.isChecked())
        node['UseTrack'].setValue(True)
    finally:
        nuke.Undo.end()
