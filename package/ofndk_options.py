# -*- coding: utf-8 -*-
"""Janela "Optical Flares Options" do plugin novo: Preview, Stack, Editor e Browser,
no mesmo arranjo da janela do plugin original (docs da Video Copilot para Nuke).

Abre pelo botao Options do no. Edita uma copia do preset; OK grava no no
(knob renderOptions, num unico undo), Cancel descarta.

Fora do Nuke (teste): python ofndk_options.py [--shot SAIDA.png] [PRESET.ofp]
"""
from __future__ import print_function

import ctypes
import os
import sys
import threading

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    import nuke
except ImportError:
    nuke = None

import ofndk_browser as fb
import ofndk_params as P
import ofndk_preset as ofp

QAction = getattr(QtGui, 'QAction', None) or QtWidgets.QAction
VERSION = 'OpticalFlaresNDK 1.1'
_window = None


# =================================================================== estilo
STYLE = """
QWidget { color: #d2d5d8; font-family: Segoe UI, Arial; font-size: 11px; }
QDialog#ofOptions { background: #141516; }
QFrame#panel { background: #26282a; border: 1px solid #0c0d0e; }
QLabel#panelTitle { background: #1b1c1d; color: #c9ccd0; font-weight: bold; padding: 4px 8px;
                    border-bottom: 1px solid #0c0d0e; }
QFrame#bar { background: #202224; border-bottom: 1px solid #0c0d0e; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3c3f42, stop:1 #2a2c2f);
              border: 1px solid #0f1011; border-radius: 3px; padding: 4px 14px; color: #d8dadc; }
QPushButton:hover { background: #47494c; }
QPushButton:checked { background: #1f6fb2; color: white; border-color: #164f80; }
QPushButton:disabled { color: #6b6e72; }
QPushButton#pill { border-radius: 9px; padding: 2px 10px; font-size: 10px; font-weight: bold; }
QPushButton#ok { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a4d50, stop:1 #36383b); font-weight: bold; }
QPushButton#tab { font-size: 12px; font-weight: bold; padding: 8px 16px; border-radius: 0; }
QPushButton#panelToggle { border-radius: 0; padding: 3px 26px; background: #1b1c1d; }
QPushButton#panelToggle:checked { background: #2d3033; color: #ffffff; }
QFrame#globalBand { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2a7cc4, stop:1 #1a5d97);
                    border: 1px solid #0c3a62; }
QLabel#globalTitle { color: white; font-size: 13px; font-weight: bold; background: transparent; }
QFrame#row { background: #2b2d30; border-bottom: 1px solid #17181a; }
QFrame#row[selected="true"] { background: #3a4a5a; }
QLabel#rowName { font-weight: bold; color: #e6e8ea; background: transparent; }
QFrame#editorHead { background: #3a3d40; border-bottom: 1px solid #0c0d0e; }
QLabel#editorTitle { font-size: 13px; font-weight: bold; color: #f0f2f4; background: transparent; }
QLabel#section { font-weight: bold; color: #eceef0; padding: 10px 6px 2px 6px; background: transparent; }
QFrame#prow { border-bottom: 1px solid #333639; background: transparent; }
QLabel#plabel { color: #b4b8bc; padding-left: 18px; background: transparent; }
QLabel#value { color: #79c2ff; text-decoration: underline; background: transparent; }
QLabel#value:disabled { color: #6a6e72; }
QComboBox { background: #3a3d40; border: 1px solid #111; padding: 1px 6px; min-width: 90px; }
QCheckBox { background: transparent; spacing: 6px; }
QCheckBox::indicator { width: 11px; height: 11px; border: 1px solid #0d0e0f; background: #1b1c1d; }
QCheckBox::indicator:checked { background: #79c2ff; border-color: #2d6ea3; }
QCheckBox::indicator:disabled { background: #2a2c2e; border-color: #3a3c3e; }
QScrollArea, QScrollArea > QWidget > QWidget { background: #26282a; border: none; }
QListWidget { background: #1f2123; border: none; }
QListWidget::item { color: #d0d3d6; padding: 2px; }
QListWidget::item:selected { background: #1f6fb2; color: white; }
QMenuBar { background: #1b1c1d; }
QMenuBar::item:selected { background: #2f3236; }
QMenu { background: #2a2c2f; border: 1px solid #111; }
QMenu::item:selected { background: #1f6fb2; }
QSplitter::handle { background: #0c0d0e; }
"""


def _pos(event):
    return event.position().toPoint() if hasattr(event, 'position') else event.pos()


# =================================================================== render
class Renderer(fb.Renderer):
    def __init__(self):
        super(Renderer, self).__init__()
        f = self.dll.ofthumb_render_mem
        f.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                      ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_int,
                      ctypes.c_float, ctypes.c_float, ctypes.c_void_p]
        f.restype = ctypes.c_int

    def render_mem(self, data, w, h, light, center, solo=-1, bright=1.0, scale=1.0):
        buf = ctypes.create_string_buffer(w * h * 3)
        n = self.dll.ofthumb_render_mem(data, len(data), self.tex, w, h, light[0], light[1],
                                        center[0], center[1], solo, bright, scale, buf)
        return buf.raw if n >= 0 else None


class RenderWorker(QtCore.QObject):
    """Uma thread. O preview usa "o ultimo pedido vale" (arrastar valores nao enfileira);
    miniaturas do stack e do browser vao numa fila atras do preview."""
    ready = QtCore.Signal(str, object)

    def __init__(self, renderer):
        super(RenderWorker, self).__init__()
        self.r = renderer
        self.cond = threading.Condition()
        self.preview = None
        self.queue = []
        self.alive = True
        t = threading.Thread(target=self._run, name='ofndk-options')
        t.daemon = True
        t.start()

    def set_preview(self, job):
        with self.cond:
            self.preview = job
            self.cond.notify()

    def add(self, job):
        with self.cond:
            self.queue.append(job)
            self.cond.notify()

    def clear_queue(self, prefix=None):
        with self.cond:
            self.queue = [j for j in self.queue if prefix and not j[0].startswith(prefix)]

    def stop(self):
        with self.cond:
            self.alive = False
            self.cond.notify()

    def _run(self):
        while True:
            with self.cond:
                while self.alive and self.preview is None and not self.queue:
                    self.cond.wait()
                if not self.alive:
                    return
                if self.preview is not None:
                    job, self.preview = self.preview, None
                else:
                    job = self.queue.pop(0)
            try:
                key, fn = job
                img = fn()
                if img is not None:
                    self.ready.emit(key, img)
            except Exception as exc:
                print('OpticalFlares Options: %s' % exc)


def _image(raw, w, h):
    return QtGui.QImage(raw, w, h, w * 3, QtGui.QImage.Format_RGB888).copy()


# =================================================================== widgets de valor
class ScrubValue(QtWidgets.QLabel):
    """Valor em azul sublinhado: arraste para os lados para mudar, duplo clique para digitar."""
    changed = QtCore.Signal(float, bool)  # valor, final (soltou o mouse / digitou)

    def __init__(self, value, unit='', step=0.5, integer=False, parent=None):
        super(ScrubValue, self).__init__(parent)
        self.setObjectName('value')
        self.unit, self.step, self.integer = unit, step, integer
        self.v = float(value)
        self._press = None
        self.setCursor(QtCore.Qt.SizeHorCursor)
        self._show()

    def _fmt(self, v):
        if self.integer:
            return '%d' % int(round(v))
        return '%.1f' % v if abs(v) >= 10 or self.unit else '%.2f' % v

    def _show(self):
        sep = ' ' if self.unit == '%' else ''
        self.setText(self._fmt(self.v) + sep + self.unit)

    def set_value(self, v):
        self.v = float(v)
        self._show()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self._press = (_pos(e).x(), self.v)

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        dx = _pos(e).x() - self._press[0]
        mult = 0.1 if (e.modifiers() & QtCore.Qt.ShiftModifier) else (10.0 if e.modifiers() & QtCore.Qt.ControlModifier else 1.0)
        v = self._press[1] + dx * self.step * mult
        if self.integer:
            v = round(v)
        if v != self.v:
            self.v = v
            self._show()
            self.changed.emit(self.v, False)

    def mouseReleaseEvent(self, e):
        if self._press is not None:
            moved = self._press[1] != self.v
            self._press = None
            if moved:
                self.changed.emit(self.v, True)

    def mouseDoubleClickEvent(self, e):
        self._press = None
        v, ok = QtWidgets.QInputDialog.getDouble(self, 'Valor', 'Valor:', self.v, -1e9, 1e9,
                                                 0 if self.integer else 3)
        if ok:
            self.set_value(v)
            self.changed.emit(self.v, True)


class ColorSwatch(QtWidgets.QPushButton):
    changed = QtCore.Signal(tuple)

    def __init__(self, rgb, parent=None):
        super(ColorSwatch, self).__init__(parent)
        self.setFixedSize(30, 14)
        self.rgb = tuple(rgb)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet('background: rgb(%d,%d,%d); border: 1px solid #000; border-radius: 0; padding: 0;'
                           % self.rgb)

    def set_rgb(self, rgb):
        self.rgb = tuple(rgb)
        self._paint()

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(*self.rgb), self, 'Cor')
        if c.isValid():
            self.set_rgb((c.red(), c.green(), c.blue()))
            self.changed.emit(self.rgb)


def _label(text, name=None):
    l = QtWidgets.QLabel(text)
    if name:
        l.setObjectName(name)
    return l


def _panel(title):
    frame = QtWidgets.QFrame()
    frame.setObjectName('panel')
    lay = QtWidgets.QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(_label(title, 'panelTitle'))
    return frame, lay


# =================================================================== janela
class OptionsWindow(QtWidgets.QDialog):
    def __init__(self, node=None, preset_bytes=None, parent=None):
        super(OptionsWindow, self).__init__(parent)
        self.setObjectName('ofOptions')
        self.setWindowTitle('Optical Flares Options')
        self.setStyleSheet(STYLE)
        self.resize(1360, 860)
        self.node_name = node.fullName() if node is not None else None
        self.renderer = Renderer()
        self.worker = RenderWorker(self.renderer)
        self.worker.ready.connect(self._on_image, QtCore.Qt.QueuedConnection)
        self.preset = ofp.parse(preset_bytes) if preset_bytes else ofp.Preset()
        self.original = self.preset.clone()
        self.preset_name = ''
        self.sel = -1  # -1 = Global Parameters
        self.undo, self.redo = [ofp.serialize(self.preset)], []
        self.light, self.center, self.aspect = self._node_geometry()
        self.pv_bright, self.pv_scale = 100.0, 100.0
        self.stack_rows = []
        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(15)
        self._preview_timer.timeout.connect(self._request_preview)
        self._build()
        self._refresh_all()

    # ------------------------------------------------------------------ dados do no
    def _node(self):
        if nuke is None or not self.node_name:
            return None
        return nuke.toNode(self.node_name)

    def _node_geometry(self):
        node = self._node()
        if node is None:
            return [0.3, 0.6], [0.5, 0.5], 16.0 / 9.0
        try:
            fmt = node.format()
            w, h = float(fmt.width()), float(fmt.height())
            lx, ly = node['PositionXY'].value()
            cx, cy = node['CenterPosition'].value()
            return [lx / w, ly / h], [cx / w, cy / h], w / h
        except Exception:
            return [0.3, 0.6], [0.5, 0.5], 16.0 / 9.0

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_menubar())
        root.addWidget(self._build_toolbar())

        self.hsplit = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.vsplit = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.preview_panel = self._build_preview()
        self.stack_panel = self._build_stack()
        self.vsplit.addWidget(self.preview_panel)
        self.vsplit.addWidget(self.stack_panel)
        self.editor_panel = self._build_editor()
        self.browser_panel = self._build_browser()
        self.hsplit.addWidget(self.vsplit)
        self.hsplit.addWidget(self.editor_panel)
        self.hsplit.addWidget(self.browser_panel)
        root.addWidget(self.hsplit, 1)
        self._reset_panels()

    def _reset_panels(self):
        self.hsplit.setSizes([560, 420, 360])
        self.vsplit.setSizes([420, 400])
        for b in self.panel_buttons.values():
            b.setChecked(True)

    def _build_menubar(self):
        bar = QtWidgets.QMenuBar()
        m_file = bar.addMenu('File')
        self._act(m_file, 'Load Preset...', self._load_preset_dialog, 'Ctrl+O')
        self._act(m_file, 'Save Preset...', self._save_preset, 'Ctrl+S')
        m_file.addSeparator()
        self._act(m_file, 'Close', self.reject)
        m_edit = bar.addMenu('Edit')
        self._act(m_edit, 'Undo', self._undo, 'Ctrl+Z')
        self._act(m_edit, 'Redo', self._redo, 'Ctrl+Shift+Z')
        m_edit.addSeparator()
        self._act(m_edit, 'Duplicate', self._duplicate, 'Ctrl+D')
        self._act(m_edit, 'Delete', self._delete_selected, 'Del')
        self._act(m_edit, 'Move Up', lambda: self._move(-1), 'Ctrl+Up')
        self._act(m_edit, 'Move Down', lambda: self._move(1), 'Ctrl+Down')
        self._act(m_edit, 'Clear All', self._clear_all)
        m_view = bar.addMenu('View')
        self._act(m_view, 'Reset Panels', self._reset_panels)
        return bar

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QtGui.QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        self.addAction(a)
        return a

    def _build_toolbar(self):
        frame = QtWidgets.QFrame()
        frame.setObjectName('bar')
        lay = QtWidgets.QVBoxLayout(frame)
        lay.setContentsMargins(8, 4, 8, 6)
        top = QtWidgets.QHBoxLayout()
        top.addStretch(1)
        top.addWidget(_label('Panels:'))
        self.panel_buttons = {}
        for name in ('Preview', 'Stack', 'Editor', 'Browser'):
            b = QtWidgets.QPushButton(name)
            b.setObjectName('panelToggle')
            b.setCheckable(True)
            b.setChecked(True)
            b.toggled.connect(lambda on, n=name: self._toggle_panel(n, on))
            top.addWidget(b)
            self.panel_buttons[name] = b
        top.addStretch(1)
        ver = _label(VERSION)
        ver.setStyleSheet('color:#8a8e92;')
        top.addWidget(ver)
        lay.addLayout(top)
        row = QtWidgets.QHBoxLayout()
        self.btn_undo = QtWidgets.QPushButton('Undo (0)')
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo = QtWidgets.QPushButton('Redo (0)')
        self.btn_redo.clicked.connect(self._redo)
        dup = QtWidgets.QPushButton('Duplicate')
        dup.clicked.connect(self._duplicate)
        clear = QtWidgets.QPushButton('Clear All')
        clear.clicked.connect(self._clear_all)
        for b in (self.btn_undo, self.btn_redo, dup, clear):
            b.setMinimumWidth(110)
            row.addWidget(b)
        row.addStretch(1)
        cancel = QtWidgets.QPushButton('Cancel')
        cancel.setMinimumWidth(110)
        cancel.clicked.connect(self.reject)
        ok = QtWidgets.QPushButton('OK')
        ok.setObjectName('ok')
        ok.setMinimumWidth(110)
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        return frame

    def _toggle_panel(self, name, on):
        w = {'Preview': self.preview_panel, 'Stack': self.stack_panel,
             'Editor': self.editor_panel, 'Browser': self.browser_panel}[name]
        w.setVisible(on)

    # ------------------------------------------------------------------ preview
    def _build_preview(self):
        frame, lay = _panel('Preview')
        self.preview = QtWidgets.QLabel()
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(320, 180)
        self.preview.setStyleSheet('background: black;')
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.preview.installEventFilter(self)
        lay.addWidget(self.preview, 1)
        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(12, 6, 12, 8)
        grid.setHorizontalSpacing(14)
        self.pv_b = ScrubValue(100, '%', 1.0)
        self.pv_b.changed.connect(lambda v, f: self._set_pv('b', v))
        self.pv_s = ScrubValue(100, '%', 1.0)
        self.pv_s.changed.connect(lambda v, f: self._set_pv('s', v))
        self.pv_x = ScrubValue(self.light[0] * 100, '', 0.2)
        self.pv_x.changed.connect(lambda v, f: self._set_pv('x', v))
        self.pv_y = ScrubValue((1 - self.light[1]) * 100, '', 0.2)
        self.pv_y.changed.connect(lambda v, f: self._set_pv('y', v))
        self.guides = QtWidgets.QCheckBox('Guides')
        self.guides.toggled.connect(lambda _on: self._schedule_preview())
        self.show_bg = QtWidgets.QCheckBox('Show BG')
        self.show_bg.setEnabled(False)
        self.show_bg.setToolTip('O fundo do no ainda nao aparece neste preview.')
        grid.addWidget(_label('Preview Brightness'), 0, 0)
        grid.addWidget(self.pv_b, 0, 1)
        grid.addWidget(_label('Preview Position'), 0, 2)
        pos = QtWidgets.QHBoxLayout()
        pos.addWidget(self.pv_x)
        pos.addWidget(_label(','))
        pos.addWidget(self.pv_y)
        pos.addStretch(1)
        grid.addLayout(pos, 0, 3)
        grid.addWidget(_label('Preview Scale'), 1, 0)
        grid.addWidget(self.pv_s, 1, 1)
        chk = QtWidgets.QHBoxLayout()
        chk.addWidget(self.guides)
        chk.addWidget(self.show_bg)
        chk.addStretch(1)
        grid.addLayout(chk, 1, 3)
        lay.addLayout(grid)
        return frame

    def _set_pv(self, what, v):
        if what == 'b':
            self.pv_bright = v
        elif what == 's':
            self.pv_scale = v
        elif what == 'x':
            self.light[0] = v / 100.0
        elif what == 'y':
            self.light[1] = 1 - v / 100.0
        self._schedule_preview()

    def eventFilter(self, obj, ev):
        # clicar/arrastar no preview move a luz (so no preview, como no original)
        if obj is self.preview and ev.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseMove):
            if ev.type() == QtCore.QEvent.MouseMove and not (ev.buttons() & QtCore.Qt.LeftButton):
                return False
            pm = self.preview.pixmap()
            if pm is not None and not pm.isNull():
                p = _pos(ev)
                ox = (self.preview.width() - pm.width()) / 2.0
                oy = (self.preview.height() - pm.height()) / 2.0
                x = (p.x() - ox) / float(pm.width())
                y = (p.y() - oy) / float(pm.height())
                self.light = [min(1.5, max(-0.5, x)), min(1.5, max(-0.5, 1 - y))]
                self.pv_x.set_value(self.light[0] * 100)
                self.pv_y.set_value((1 - self.light[1]) * 100)
                self._schedule_preview()
                return True
        if obj is self.preview and ev.type() == QtCore.QEvent.Resize:
            self._schedule_preview()
        return super(OptionsWindow, self).eventFilter(obj, ev)

    def _schedule_preview(self):
        self._preview_timer.start()

    def _request_preview(self):
        w = max(64, self.preview.width())
        h = max(36, self.preview.height())
        if w / float(h) > self.aspect:
            w = int(h * self.aspect)
        else:
            h = int(w / self.aspect)
        data = ofp.serialize(self.preset)
        light, center = list(self.light), list(self.center)
        b, s = self.pv_bright / 100.0, self.pv_scale / 100.0

        def job():
            raw = self.renderer.render_mem(data, w, h, light, center, -1, b, s)
            return _image(raw, w, h) if raw else None

        self.worker.set_preview(('preview', job))

    # ------------------------------------------------------------------ stack
    def _build_stack(self):
        frame, lay = _panel('Stack')
        band = QtWidgets.QFrame()
        band.setObjectName('globalBand')
        bl = QtWidgets.QHBoxLayout(band)
        bl.setContentsMargins(8, 6, 8, 6)
        self.global_thumb = QtWidgets.QLabel()
        self.global_thumb.setFixedSize(80, 45)
        self.global_thumb.setStyleSheet('background:black; border:1px solid #0c3a62;')
        bl.addWidget(self.global_thumb)
        mid = QtWidgets.QVBoxLayout()
        title = _label('GLOBAL PARAMETERS', 'globalTitle')
        mid.addWidget(title)
        seg = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton('ADD')
        self.btn_scn = QtWidgets.QPushButton('SCN')
        for b in (self.btn_add, self.btn_scn):
            b.setObjectName('pill')
            b.setCheckable(True)
            seg.addWidget(b)
        self.btn_add.clicked.connect(lambda: self._set_global_enum(9, 0))
        self.btn_scn.clicked.connect(lambda: self._set_global_enum(9, 1))
        seg.addSpacing(12)
        self.global_color = ColorSwatch((126, 146, 180))
        self.global_color.changed.connect(lambda rgb: self._set_global_color(4, rgb))
        seg.addWidget(self.global_color)
        gc = _label('Global Color')
        gc.setStyleSheet('background:transparent; color:#dfe9f3;')
        seg.addWidget(gc)
        seg.addStretch(1)
        mid.addLayout(seg)
        bl.addLayout(mid, 1)
        save = QtWidgets.QPushButton('SAVE PRESET')
        save.setObjectName('pill')
        save.clicked.connect(self._save_preset)
        bl.addWidget(save)
        band.mousePressEvent = lambda e: self._select(-1)
        lay.addWidget(band)

        self.stack_scroll = QtWidgets.QScrollArea()
        self.stack_scroll.setWidgetResizable(True)
        self.stack_host = QtWidgets.QWidget()
        self.stack_lay = QtWidgets.QVBoxLayout(self.stack_host)
        self.stack_lay.setContentsMargins(0, 0, 0, 0)
        self.stack_lay.setSpacing(0)
        self.stack_lay.addStretch(1)
        self.stack_scroll.setWidget(self.stack_host)
        lay.addWidget(self.stack_scroll, 1)
        return frame

    def _rebuild_stack(self):
        while self.stack_lay.count() > 1:
            it = self.stack_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.stack_rows = []
        for i, o in enumerate(self.preset.objects):
            row = self._make_row(i, o)
            self.stack_lay.insertWidget(i, row)
            self.stack_rows.append(row)
        g = self.preset.globals
        blend = g.get(9, 0) or 0
        self.btn_add.setChecked(blend == 0)
        self.btn_scn.setChecked(blend == 1)
        self.global_color.set_rgb(g.get(4, (126, 146, 180)))
        self._mark_selection()
        self._request_stack_thumbs()

    def _make_row(self, i, o):
        row = QtWidgets.QFrame()
        row.setObjectName('row')
        row.setFixedHeight(56)
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(6, 4, 8, 4)
        thumb = QtWidgets.QLabel()
        thumb.setFixedSize(80, 45)
        thumb.setStyleSheet('background:black; border:1px solid #111;')
        lay.addWidget(thumb)
        col = QtWidgets.QVBoxLayout()
        name = _label(o.name or o.type_name, 'rowName')
        name.setToolTip('%s (duplo clique para renomear)' % o.type_name)
        name.mouseDoubleClickEvent = lambda e, k=i: self._rename(k)
        col.addWidget(name)
        vals = QtWidgets.QHBoxLayout()
        sun = _label(u'☀')
        vals.addWidget(sun)
        bv = ScrubValue(o.get(0, 100.0) or 0.0, '', 0.5)
        bv.changed.connect(lambda v, f, k=i: self._set_obj_float(k, 0, v, f))
        vals.addWidget(bv)
        vals.addSpacing(14)
        vals.addWidget(_label(u'▣'))
        sv = ScrubValue(o.get(1, 100.0) or 0.0, '', 0.5)
        sv.changed.connect(lambda v, f, k=i: self._set_obj_float(k, 1, v, f))
        vals.addWidget(sv)
        vals.addStretch(1)
        col.addLayout(vals)
        lay.addLayout(col, 1)
        hide = QtWidgets.QPushButton('HIDE')
        solo = QtWidgets.QPushButton('SOLO')
        for b, flag in ((hide, o.hidden), (solo, o.solo)):
            b.setObjectName('pill')
            b.setCheckable(True)
            b.setChecked(flag)
            lay.addWidget(b)
        hide.toggled.connect(lambda on, k=i: self._set_flag(k, 'hidden', on))
        solo.toggled.connect(lambda on, k=i: self._set_flag(k, 'solo', on))
        x = QtWidgets.QPushButton('X')
        x.setObjectName('pill')
        x.setFixedSize(24, 18)
        x.setStyleSheet('padding: 0;')
        x.clicked.connect(lambda _c=False, k=i: self._delete(k))
        lay.addWidget(x)
        row.thumb, row.bv, row.sv = thumb, bv, sv
        row.mousePressEvent = lambda e, k=i: self._select(k)
        row.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        row.customContextMenuRequested.connect(lambda p, k=i, r=row: self._row_menu(k, r.mapToGlobal(p)))
        return row

    def _row_menu(self, k, gpos):
        self._select(k)
        m = QtWidgets.QMenu(self)
        m.addAction('Rename', lambda: self._rename(k))
        m.addAction('Duplicate', self._duplicate)
        m.addAction('Move Up', lambda: self._move(-1))
        m.addAction('Move Down', lambda: self._move(1))
        m.addSeparator()
        m.addAction('Delete', lambda: self._delete(k))
        m.exec_(gpos) if hasattr(m, 'exec_') else m.exec(gpos)

    def _mark_selection(self):
        for i, r in enumerate(self.stack_rows):
            r.setProperty('selected', 'true' if i == self.sel else 'false')
            r.style().unpolish(r)
            r.style().polish(r)

    def _request_stack_thumbs(self):
        self.worker.clear_queue('stack:')
        base = self.preset.clone()
        for o in base.objects:
            o.hidden = False
            o.solo = False
        data = ofp.serialize(base)
        light, center = list(self.light), list(self.center)
        for i in range(len(self.preset.objects)):
            def job(i=i):
                raw = self.renderer.render_mem(data, 80, 45, light, center, i, 1.0, 1.0)
                return _image(raw, 80, 45) if raw else None
            self.worker.add(('stack:%d' % i, job))

        def gjob():
            raw = self.renderer.render_mem(ofp.serialize(self.preset), 80, 45, light, center, -1, 1.0, 1.0)
            return _image(raw, 80, 45) if raw else None
        self.worker.add(('stack:global', gjob))

    # ------------------------------------------------------------------ editor
    def _build_editor(self):
        frame, lay = _panel('Editor')
        head = QtWidgets.QFrame()
        head.setObjectName('editorHead')
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(10, 8, 10, 8)
        self.editor_title = _label('GLOBAL PARAMETERS', 'editorTitle')
        hl.addWidget(self.editor_title, 1)
        reset = QtWidgets.QPushButton('RESET')
        reset.setObjectName('pill')
        reset.setToolTip('Volta este item ao estado de quando a janela abriu.')
        reset.clicked.connect(self._reset_selected)
        hl.addWidget(reset)
        lay.addWidget(head)
        self.editor_scroll = QtWidgets.QScrollArea()
        self.editor_scroll.setWidgetResizable(True)
        lay.addWidget(self.editor_scroll, 1)
        return frame

    def _target(self):
        return self.preset.globals if self.sel < 0 else self.preset.objects[self.sel]

    def _rebuild_editor(self):
        target = self._target()
        is_global = self.sel < 0
        self.editor_title.setText('GLOBAL PARAMETERS' if is_global else (target.name or target.type_name))
        host = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(host)
        lay.setContentsMargins(4, 0, 10, 10)
        lay.setSpacing(0)
        sections, cur = [], []
        for p in target.params:
            if p.id == 24:
                sections.append(cur)
                cur = []
            else:
                cur.append(p)
        sections.append(cur)
        tname = target.type_name if not is_global else ''
        for sec in sections:
            if not sec:
                continue
            lay.addWidget(_label(P.section_name(sec[0].id, tname, is_global), 'section'))
            for p in sec:
                lay.addWidget(self._param_row(target, p, is_global))
        lay.addStretch(1)
        self.editor_scroll.setWidget(host)

    def _param_row(self, target, p, is_global):
        row = QtWidgets.QFrame()
        row.setObjectName('prow')
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 3, 0, 3)
        lab = _label(P.label(p.id, getattr(target, 'type', None), is_global), 'plabel')
        lab.setFixedWidth(190)
        hl.addWidget(lab)
        unit = P.unit(p.id, is_global)
        step = P.drag_step(p.id, is_global)
        integer = P.is_integer(p.id, is_global)
        if p.type == ofp.FLOAT:
            w = ScrubValue(p.f(), unit, step, integer)
            w.changed.connect(lambda v, f, p=p: self._edit(p, lambda: p.set_f(v), f))
            hl.addWidget(w)
        elif p.type == ofp.FLOAT2:
            a = ScrubValue(p.f(0), unit, step, integer)
            b = ScrubValue(p.f(1), unit, step, integer)
            a.changed.connect(lambda v, f, p=p: self._edit(p, lambda: p.set_f(v, 0), f))
            b.changed.connect(lambda v, f, p=p: self._edit(p, lambda: p.set_f(v, 1), f))
            hl.addWidget(a)
            hl.addWidget(_label(','))
            hl.addWidget(b)
        elif p.type == ofp.COLOR:
            sw = ColorSwatch(p.rgb())
            sw.changed.connect(lambda rgb, p=p: self._edit(p, lambda: p.set_rgb(*rgb), True))
            hl.addWidget(sw)
            if p.id == 83:  # Color Shift tem "ligado"
                on = QtWidgets.QCheckBox()
                on.setChecked(p.color_enabled())
                on.toggled.connect(lambda v, p=p: self._edit(p, lambda: p.set_color_enabled(v), True))
                hl.addWidget(on)
        elif p.type == ofp.ENUM:
            opts = P.enum_options(p.id, is_global)
            cb = QtWidgets.QComboBox()
            cur = p.i()
            items = list(opts) if opts else []
            while len(items) <= cur:
                items.append(str(len(items)))
            cb.addItems(items)
            cb.setCurrentIndex(max(0, cur))
            cb.currentIndexChanged.connect(lambda ix, p=p: self._edit(p, lambda: p.set_i(ix), True))
            hl.addWidget(cb)
        elif p.type == ofp.BOOL:
            ck = QtWidgets.QCheckBox()
            ck.setChecked(bool(p.i()))
            ck.toggled.connect(lambda v, p=p: self._edit(p, lambda: p.set_i(1 if v else 0), True))
            hl.addWidget(ck)
        elif p.type == ofp.TEXTURE:
            folder = 'Glass' if is_global else 'Elements'
            names = self._texture_names(folder)
            cb = QtWidgets.QComboBox()
            cb.addItem('None')
            cb.addItems(names)
            current = p.texture_name()
            if current.endswith(' (U)'):
                current = current[:-4]
            if p.i() == 0 and is_global or current.lower() in ('', 'none'):
                current = ''  # textura da lente desligada (indice 0) ou "None"
            low = [n.lower() for n in names]
            if current and current.lower() in low:
                current = names[low.index(current.lower())]
            if current and current not in names:
                cb.addItem(current + ' (faltando)')
                cb.setCurrentIndex(cb.count() - 1)
            elif current:
                cb.setCurrentIndex(names.index(current) + 1)
            cb.currentIndexChanged.connect(
                lambda ix, p=p, names=names: self._edit(
                    p, lambda: p.set_texture(ix if 0 < ix <= len(names) else 0,
                                             names[ix - 1] if 0 < ix <= len(names) else ''), True)
                if ix <= len(names) else None)
            hl.addWidget(cb)
        hl.addStretch(1)
        return row

    def _texture_names(self, folder):
        d = os.path.join(fb.textures_root(), folder)
        try:
            return sorted((os.path.splitext(f)[0] for f in os.listdir(d)
                           if f.lower().endswith(('.png', '.jpg', '.tif', '.tiff', '.bmp'))), key=str.lower)
        except OSError:
            return []

    # ------------------------------------------------------------------ edicao
    def _edit(self, p, fn, final):
        fn()
        self._changed(final, thumbs=final)

    def _changed(self, final, thumbs=True, rebuild=False):
        self._schedule_preview()
        if final:
            self._push_undo()
        if rebuild:
            self._rebuild_stack()
        elif thumbs:
            self._request_stack_thumbs()

    def _set_obj_float(self, k, pid, v, final):
        p = self.preset.objects[k].find(pid)
        if p is not None:
            p.set_f(v)
            if k == self.sel and final:
                self._rebuild_editor()
            self._changed(final, thumbs=final)

    def _set_flag(self, k, attr, on):
        setattr(self.preset.objects[k], attr, on)
        self._changed(True, thumbs=False)

    def _set_global_enum(self, pid, v):
        p = self.preset.globals.find(pid)
        if p is not None:
            p.set_i(v)
        self.btn_add.setChecked(v == 0)
        self.btn_scn.setChecked(v == 1)
        if self.sel < 0:
            self._rebuild_editor()
        self._changed(True)

    def _set_global_color(self, pid, rgb):
        p = self.preset.globals.find(pid)
        if p is not None:
            p.set_rgb(*rgb)
        if self.sel < 0:
            self._rebuild_editor()
        self._changed(True)

    def _select(self, k):
        self.sel = k
        self._mark_selection()
        self._rebuild_editor()

    def _rename(self, k):
        o = self.preset.objects[k]
        text, ok = QtWidgets.QInputDialog.getText(self, 'Renomear', 'Nome:', text=o.name)
        if ok and text.strip():
            o.name = text.strip()[:60]
            self._changed(True, rebuild=True)
            if k == self.sel:
                self._rebuild_editor()

    def _delete(self, k):
        del self.preset.objects[k]
        self.sel = min(self.sel, len(self.preset.objects) - 1) if self.sel >= 0 else -1
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    def _delete_selected(self):
        if self.sel >= 0:
            self._delete(self.sel)

    def _duplicate(self):
        if self.sel < 0:
            return
        import copy
        o = copy.deepcopy(self.preset.objects[self.sel])
        self.preset.objects.insert(self.sel + 1, o)
        self.sel += 1
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    def _move(self, d):
        k = self.sel
        j = k + d
        if k < 0 or j < 0 or j >= len(self.preset.objects):
            return
        objs = self.preset.objects
        objs[k], objs[j] = objs[j], objs[k]
        self.sel = j
        self._changed(True, rebuild=True)

    def _clear_all(self):
        self.preset.objects = []
        self.sel = -1
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    def _reset_selected(self):
        import copy
        if self.sel < 0:
            self.preset.globals = copy.deepcopy(self.original.globals)
        else:
            o = self.preset.objects[self.sel]
            same = [x for x in self.original.objects if x.type == o.type and x.name == o.name]
            if not same:
                return
            self.preset.objects[self.sel] = copy.deepcopy(same[0])
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    # ------------------------------------------------------------------ undo
    def _push_undo(self):
        data = ofp.serialize(self.preset)
        if self.undo and self.undo[-1] == data:
            return
        self.undo.append(data)
        self.redo = []
        self._undo_buttons()

    def _undo_buttons(self):
        self.btn_undo.setText('Undo (%d)' % (len(self.undo) - 1))
        self.btn_redo.setText('Redo (%d)' % len(self.redo))

    def _restore(self, data):
        self.preset = ofp.parse(data)
        if self.sel >= len(self.preset.objects):
            self.sel = len(self.preset.objects) - 1
        self._refresh_all()

    def _undo(self):
        if len(self.undo) > 1:
            self.redo.append(self.undo.pop())
            self._restore(self.undo[-1])

    def _redo(self):
        if self.redo:
            self.undo.append(self.redo.pop())
            self._restore(self.undo[-1])

    def _refresh_all(self):
        self._rebuild_stack()
        self._rebuild_editor()
        self._schedule_preview()
        self._undo_buttons()

    # ------------------------------------------------------------------ browser
    def _build_browser(self):
        frame, lay = _panel('Browser')
        tabs = QtWidgets.QHBoxLayout()
        tabs.setSpacing(0)
        self.tab_objects = QtWidgets.QPushButton('OBJECTS')
        self.tab_browser = QtWidgets.QPushButton('BROWSER')
        for b in (self.tab_objects, self.tab_browser):
            b.setObjectName('tab')
            b.setCheckable(True)
            tabs.addWidget(b)
        self.tab_objects.clicked.connect(lambda: self._browser_mode('objects'))
        self.tab_browser.clicked.connect(lambda: self._browser_mode('browser'))
        lay.addLayout(tabs)

        nav = QtWidgets.QHBoxLayout()
        nav.setContentsMargins(6, 6, 6, 6)
        self.folder_combo = QtWidgets.QComboBox()
        self.folder_combo.currentIndexChanged.connect(lambda _i: self._fill_presets())
        self.show_basic = QtWidgets.QPushButton('Basic')
        self.show_custom = QtWidgets.QPushButton('Custom')
        for b in (self.show_basic, self.show_custom):
            b.setObjectName('pill')
            b.setCheckable(True)
        self.show_basic.clicked.connect(lambda: self._objects_mode('basic'))
        self.show_custom.clicked.connect(lambda: self._objects_mode('custom'))
        self.show_label = _label('Show')
        nav.addWidget(self.show_label)
        nav.addWidget(self.show_basic)
        nav.addWidget(self.show_custom)
        nav.addWidget(self.folder_combo, 1)
        lay.addLayout(nav)

        self.blist = QtWidgets.QListWidget()
        # miniatura grande com o nome embaixo, uma por linha (como no original)
        self.blist.setViewMode(QtWidgets.QListView.IconMode)
        self.blist.setFlow(QtWidgets.QListView.TopToBottom)
        self.blist.setWrapping(False)
        self.blist.setMovement(QtWidgets.QListView.Static)
        self.blist.setIconSize(QtCore.QSize(220, 124))
        self.blist.setGridSize(QtCore.QSize(236, 150))
        self.blist.setUniformItemSizes(True)
        self.blist.itemClicked.connect(self._browser_click)
        self.blist.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.blist.customContextMenuRequested.connect(self._browser_menu)
        lay.addWidget(self.blist, 1)
        self.browser_items = {}
        self._fill_folders()
        self._objects_mode('basic', switch=False)
        self._browser_mode('browser')
        return frame

    def _browser_mode(self, mode):
        self.mode = mode
        self.tab_objects.setChecked(mode == 'objects')
        self.tab_browser.setChecked(mode == 'browser')
        for w in (self.show_label, self.show_basic, self.show_custom):
            w.setVisible(mode == 'objects')
        self.folder_combo.setVisible(mode == 'browser')
        if mode == 'browser':
            self._fill_presets()
        else:
            self._fill_objects()

    def _objects_mode(self, which, switch=True):
        self.obj_mode = which
        self.show_basic.setChecked(which == 'basic')
        self.show_custom.setChecked(which == 'custom')
        if switch:
            self._fill_objects()

    def _fill_folders(self):
        root = fb.presets_root()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem('Todos os presets', '')
        for dp, dirs, files in os.walk(root):
            dirs.sort(key=lambda d: ('custom' in d.lower(), d.lower()))
            rel = os.path.relpath(dp, root).replace('\\', '/')
            if rel != '.':
                self.folder_combo.addItem(rel.replace('/', ' > '), rel)
        self.folder_combo.blockSignals(False)

    def _list_presets(self, rel):
        root = fb.presets_root()
        base = root + ('/' + rel if rel else '')
        out = []
        for dp, dirs, files in os.walk(base):
            dirs.sort(key=lambda d: ('custom' in d.lower(), d.lower()))
            out += [os.path.join(dp, f).replace('\\', '/') for f in sorted(files) if f.lower().endswith('.ofp')]
        return out

    def _placeholder(self):
        pm = QtGui.QPixmap(220, 124)
        pm.fill(QtGui.QColor(10, 10, 10))
        return QtGui.QIcon(pm)

    def _fill_presets(self):
        self.worker.clear_queue('browse:')
        self.blist.clear()
        self.browser_items = {}
        rel = self.folder_combo.currentData() or ''
        icon = self._placeholder()
        for p in self._list_presets(rel):
            it = QtWidgets.QListWidgetItem(icon, os.path.splitext(os.path.basename(p))[0])
            it.setData(QtCore.Qt.UserRole, ('preset', p))
            self.blist.addItem(it)
            self.browser_items[p] = it
            self.worker.add(('browse:' + p, lambda p=p: self._thumb_file(p)))

    def _thumb_file(self, path):
        cache = fb._cache_file(path, 220, 124)
        if os.path.isfile(cache):
            return QtGui.QImage(cache)
        raw, n = self.renderer.render(path, 220, 124)
        if raw is None:
            return None
        img = _image(raw, 220, 124)
        img.save(cache, 'PNG')
        return img

    def _basic_objects(self):
        """Um objeto de cada tipo, tirado da propria biblioteca do usuario."""
        if hasattr(self, '_basic_cache'):
            return self._basic_cache
        found = {}
        for path in self._list_presets(''):
            if len(found) == len(ofp.TYPE_NAMES):
                break
            try:
                pre = ofp.load(path)
            except Exception:
                continue
            for o in pre.objects:
                if o.type in ofp.TYPE_NAMES and o.type not in found:
                    found[o.type] = (pre, o)
        order = [1, 2, 15, 4, 6, 5, 7, 8, 9, 11, 12, 14]
        self._basic_cache = [(t, found[t]) for t in order if t in found]
        return self._basic_cache

    def _fill_objects(self):
        self.worker.clear_queue('browse:')
        self.blist.clear()
        self.browser_items = {}
        icon = self._placeholder()
        if self.obj_mode == 'basic':
            for t, (pre, o) in self._basic_objects():
                one = ofp.Preset()
                one.globals = pre.globals
                one.has_globals = pre.has_globals
                import copy
                obj = copy.deepcopy(o)
                obj.name = ofp.TYPE_NAMES[t]
                obj.hidden = obj.solo = False
                one.objects = [obj]
                data = ofp.serialize(one)
                key = 'obj:%d' % t
                it = QtWidgets.QListWidgetItem(icon, ofp.TYPE_NAMES[t])
                it.setData(QtCore.Qt.UserRole, ('objects', data))
                self.blist.addItem(it)
                self.browser_items[key] = it

                def job(data=data):
                    raw = self.renderer.render_mem(data, 220, 124, [0.35, 0.6], [0.5, 0.5])
                    return _image(raw, 220, 124) if raw else None
                self.worker.add(('browse:' + key, job))
        else:
            for p in self._list_presets('Custom Objects') or self._list_presets(''):
                it = QtWidgets.QListWidgetItem(icon, os.path.splitext(os.path.basename(p))[0])
                it.setData(QtCore.Qt.UserRole, ('objfile', p))
                self.blist.addItem(it)
                self.browser_items[p] = it
                self.worker.add(('browse:' + p, lambda p=p: self._thumb_file(p)))

    def _browser_click(self, item):
        kind, ref = item.data(QtCore.Qt.UserRole)
        if kind == 'preset':
            self._load_preset(ref)
        elif kind == 'objects':
            self._add_objects(ofp.parse(ref).objects)
        elif kind == 'objfile':
            self._add_objects(ofp.load(ref).objects)

    def _browser_menu(self, pos):
        item = self.blist.itemAt(pos)
        if item is None:
            return
        kind, ref = item.data(QtCore.Qt.UserRole)
        m = QtWidgets.QMenu(self)
        if kind == 'preset':
            m.addAction('Load', lambda: self._load_preset(ref))
            m.addAction('Combine With Current', lambda: self._add_objects(ofp.load(ref).objects))
        else:
            m.addAction('Add To Stack', lambda: self._browser_click(item))
        gpos = self.blist.viewport().mapToGlobal(pos)
        m.exec_(gpos) if hasattr(m, 'exec_') else m.exec(gpos)

    def _add_objects(self, objs):
        import copy
        for o in objs:
            self.preset.objects.append(copy.deepcopy(o))
        self.sel = len(self.preset.objects) - 1
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    def _load_preset(self, path):
        try:
            self.preset = ofp.load(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, 'Optical Flares', 'Nao abriu: %s' % exc)
            return
        self.original = self.preset.clone()
        self.preset_name = os.path.splitext(os.path.basename(path))[0]
        self.preset_path = path
        self.sel = -1
        self._push_undo()
        self._refresh_all()

    def _load_preset_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load Preset', fb.presets_root(), 'Optical Flares (*.ofp)')
        if path:
            self._load_preset(path)

    def _save_preset(self):
        start = os.path.join(fb.presets_root(), (self.preset_name or 'Meu Flare') + '.ofp')
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save Preset', start, 'Optical Flares (*.ofp)')
        if not path:
            return
        with open(path, 'wb') as fh:
            fh.write(ofp.serialize(self.preset))
        self.preset_name = os.path.splitext(os.path.basename(path))[0]
        self.preset_path = path
        if self.mode == 'browser':
            self._fill_folders()
            self._fill_presets()

    # ------------------------------------------------------------------ imagens prontas
    def _on_image(self, key, img):
        if key == 'preview':
            pm = QtGui.QPixmap.fromImage(img)
            if self.guides.isChecked():
                p = QtGui.QPainter(pm)
                p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 90), 1, QtCore.Qt.DashLine))
                lx, ly = self.light[0] * pm.width(), (1 - self.light[1]) * pm.height()
                cx, cy = self.center[0] * pm.width(), (1 - self.center[1]) * pm.height()
                p.drawLine(QtCore.QPointF(lx, ly), QtCore.QPointF(2 * cx - lx, 2 * cy - ly))
                p.drawEllipse(QtCore.QPointF(cx, cy), 4, 4)
                p.end()
            self.preview.setPixmap(pm)
        elif key == 'stack:global':
            self.global_thumb.setPixmap(QtGui.QPixmap.fromImage(img))
        elif key.startswith('stack:'):
            i = int(key.split(':')[1])
            if i < len(self.stack_rows):
                self.stack_rows[i].thumb.setPixmap(QtGui.QPixmap.fromImage(img))
        elif key.startswith('browse:'):
            it = self.browser_items.get(key[7:])
            if it is not None:
                it.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(img)))

    # ------------------------------------------------------------------ OK / Cancel
    def _ok(self):
        node = self._node()
        data = ofp.serialize(self.preset)
        if node is None:
            print('OK (sem no): %d bytes, %d objetos' % (len(data), len(self.preset.objects)))
            self.accept()
            return
        nuke.Undo.begin('Optical Flares: Options')
        try:
            node['renderOptions'].setValue(ofp.encode_state(data))
            if 'ofpPresetName' in node.knobs():
                node['ofpPresetName'].setValue(self.preset_name or node['ofpPresetName'].value())
            if getattr(self, 'preset_path', None) and 'ofpPresetFile' in node.knobs():
                node['ofpPresetFile'].setValue(self.preset_path)
                node['renderOptions'].setValue(ofp.encode_state(data))  # edicoes valem sobre o arquivo
        finally:
            nuke.Undo.end()
        self.accept()

    def done(self, r):
        self.worker.stop()
        super(OptionsWindow, self).done(r)


def open_options(node=None):
    """Botao Options do no: ofndk_options.open_options(nuke.thisNode())."""
    global _window
    data = None
    name = ''
    if node is not None:
        try:
            data = ofp.decode_state(node['renderOptions'].value())
        except Exception:
            data = None
        if 'ofpPresetName' in node.knobs():
            name = node['ofpPresetName'].value()
    if _window is not None:
        try:
            _window.close()
        except Exception:
            pass
    _window = OptionsWindow(node, data, QtWidgets.QApplication.activeWindow())
    _window.preset_name = name
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    shot = sys.argv[sys.argv.index('--shot') + 1] if '--shot' in sys.argv else None
    if shot in args:
        args.remove(shot)
    data = open(args[0], 'rb').read() if args else None
    w = OptionsWindow(None, data)
    w.show()
    if shot:
        def grab():
            w.grab().save(shot)
            app.quit()
        QtCore.QTimer.singleShot(int(os.environ.get('OFNDK_SHOT_MS', '6000')), grab)
    app.exec_() if hasattr(app, 'exec_') else app.exec()
