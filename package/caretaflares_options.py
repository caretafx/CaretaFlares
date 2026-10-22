# -*- coding: utf-8 -*-
"""Janela "CaretaFlares Options": Preview, Stack, Editor e Browser,
no mesmo arranjo e visual da janela do plugin original (imagens da documentacao da
Video Copilot para Nuke). Desenho e codigo proprios.

Abre pelo botao Options do no. Edita uma copia do preset; OK grava no no
(knob renderOptions, num unico undo), Cancel descarta.

Fora do Nuke (teste): python caretaflares_options.py [--shot SAIDA.png] [PRESET.ofp]
"""
from __future__ import print_function

import copy
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

import caretaflares_browser as fb
import caretaflares_params as P
import caretaflares_preset as ofp

QAction = getattr(QtGui, 'QAction', None) or QtWidgets.QAction
VERSION = '1.2.0'
DEFAULT_PREVIEW_POS = (23.6, 27.4)  # % da largura, % da altura a partir do topo (como no original)
_window = None

# =================================================================== estilo
# Cinzas neutros, Tahoma pequena, valores em azul claro sublinhado, pilulas escuras
# com borda clara, faixa azul dos Global Parameters.
STYLE = """
QWidget { color: #d6d6d6; font-family: Tahoma, Verdana, Arial; font-size: 11px; }
QDialog#ofOptions { background: #1a1a1a; }
QFrame#top { background: #262626; border-bottom: 1px solid #111; }
QFrame#tools { background: #262626; border-bottom: 1px solid #0d0d0d; }
QMenuBar { background: transparent; color: #cfcfcf; }
QMenuBar::item { background: transparent; padding: 3px 7px; }
QMenuBar::item:selected { background: #3a3a3a; }
QMenu { background: #2c2c2c; border: 1px solid #0f0f0f; }
QMenu::item { padding: 4px 22px; }
QMenu::item:selected { background: #1d65a6; color: white; }
QLabel#dim { color: #8c8c8c; background: transparent; }
QLabel#brand { color: #e8e8e8; font-weight: bold; background: transparent; }

QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4b4b4b, stop:1 #3a3a3a);
              border: 1px solid #141414; border-radius: 2px; padding: 3px 12px; color: #e2e2e2; }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #575757, stop:1 #444); }
QPushButton:pressed { background: #2f2f2f; }
QPushButton#tool { min-width: 120px; }
QPushButton#ok { font-weight: bold; }

QPushButton#paneltab { background: #1c1c1c; border: 1px solid #333; border-radius: 0; padding: 2px 30px;
                       color: #bdbdbd; min-width: 70px; }
QPushButton#paneltab:checked { background: #1c1c1c; color: #f2f2f2; border-color: #4a4a4a; }
QPushButton#paneltab:!checked { color: #6f6f6f; }

QPushButton#pill { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3a3a, stop:1 #1f1f1f);
                   border: 1px solid #9a9a9a; border-radius: 8px; padding: 2px 12px;
                   font-size: 9px; font-weight: bold; color: #e6e6e6; }
QPushButton#pill:checked { background: #6a6a6a; color: white; }
QPushButton#pillx { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3a3a3a, stop:1 #1f1f1f);
                    border: 1px solid #9a9a9a; border-radius: 8px; padding: 0;
                    font-size: 9px; font-weight: bold; color: #e6e6e6; }
QPushButton#seg { background: #141414; border: 1px solid #0a2a48; border-radius: 0; padding: 1px 7px;
                  font-size: 9px; font-weight: bold; color: #bfcfdf; }
QPushButton#seg:checked { background: #3f93dc; color: white; }
QPushButton#segl { background: #141414; border: 1px solid #0a2a48; border-top-left-radius: 8px;
                   border-bottom-left-radius: 8px; border-top-right-radius: 0; border-bottom-right-radius: 0;
                   padding: 1px 8px; font-size: 9px; font-weight: bold; color: #bfcfdf; }
QPushButton#segl:checked { background: #3f93dc; color: white; }
QPushButton#segr { background: #141414; border: 1px solid #0a2a48; border-top-right-radius: 8px;
                   border-bottom-right-radius: 8px; border-top-left-radius: 0; border-bottom-left-radius: 0;
                   padding: 1px 8px; font-size: 9px; font-weight: bold; color: #bfcfdf; }
QPushButton#segr:checked { background: #3f93dc; color: white; }

QFrame#panel { background: #2b2b2b; border: 1px solid #0b0b0b; }
QFrame#panelHead { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2e2e2e, stop:1 #222);
                   border-bottom: 1px solid #0b0b0b; }
QLabel#panelTitle { color: #e9e9e9; font-weight: bold; background: transparent; padding: 3px 8px; }
QToolButton#wing { background: #3d3d3d; border: 1px solid #111; color: #ddd; padding: 0 3px; }

QFrame#previewBar { background: #2b2b2b; border-top: 1px solid #111; }
QLabel#plab { color: #e4e4e4; background: transparent; }

QFrame#globalBand { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2873b8, stop:1 #1b5b97);
                    border: 1px solid #0d3459; }
QFrame#globalBand[selected="true"] { border: 1px solid #9cc9f0; }
QLabel#globalTitle { color: white; font-size: 12px; font-weight: bold; background: transparent; }
QLabel#onBlue { color: #e3eef8; background: transparent; }

QFrame#row { background: #2a2a2a; border-bottom: 1px solid #181818; }
QFrame#row[selected="true"] { background: #3d4650; }
QLabel#rowName { font-weight: bold; color: #f0f0f0; font-size: 11px; background: transparent; }
QLabel#icon { color: #c8c8c8; background: transparent; }

QFrame#editorHead { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4e5052, stop:1 #424446);
                    border-bottom: 1px solid #0b0b0b; }
QLabel#editorTitle { font-size: 12px; font-weight: bold; color: #f4f4f4; background: transparent; }
QLabel#section { font-weight: bold; color: #f0f0f0; padding: 12px 6px 3px 8px; background: transparent; }
QFrame#prow { border-bottom: 1px solid #3a3a3a; background: transparent; }
QLabel#plabel { color: #d2d2d2; padding-left: 20px; background: transparent; }
QLabel#value { color: #8fcbff; text-decoration: underline; background: transparent; }
QLabel#value:disabled { color: #6c6c6c; }

QComboBox { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a4a4a, stop:1 #3a3a3a);
            border: 1px solid #121212; border-radius: 2px; padding: 0 6px; min-width: 96px; color: #e6e6e6; }
QComboBox::drop-down { border: none; width: 14px; }
QComboBox QAbstractItemView { background: #2c2c2c; selection-background-color: #1d65a6; }
QCheckBox { background: transparent; spacing: 5px; color: #e4e4e4; }
QCheckBox::indicator { width: 10px; height: 10px; border: 1px solid #0d0d0d; background: #3a3a3a; }
QCheckBox::indicator:checked { background: #d8d8d8; }
QCheckBox::indicator:disabled { background: #2a2a2a; border-color: #3a3a3a; }

QScrollArea { background: #2b2b2b; border: none; }
QScrollArea > QWidget > QWidget { background: #2b2b2b; }
QScrollBar:vertical { background: #232323; width: 12px; border-left: 1px solid #111; }
QScrollBar::handle:vertical { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5a5a5a, stop:1 #484848);
                              min-height: 30px; border: 1px solid #1a1a1a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { background: #3a3a3a; height: 11px; border: 1px solid #111; }

QPushButton#tabOff { background: #2a2a2a; border: 1px solid #111; border-radius: 0; padding: 6px 10px;
                     font-weight: bold; font-size: 11px; color: #e0e0e0; text-align: left; }
QPushButton#tabOn { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2a7fca, stop:1 #1b64a6);
                    border: 1px solid #0d3459; border-radius: 0; padding: 6px 10px;
                    font-weight: bold; font-size: 11px; color: white; text-align: left; }
QFrame#crumbs { background: #232323; border-bottom: 1px solid #111; }
QPushButton#crumb { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a4a4a, stop:1 #393939);
                    border: 1px solid #111; border-radius: 1px; padding: 1px 8px; font-size: 9px; color: #e8e8e8; }
QLabel#crumbSep { color: #cfcfcf; background: transparent; }
QListWidget#blist { background: #262626; border: none; }
QSplitter::handle { background: #1a1a1a; }
QSlider::groove:horizontal { height: 4px; background: #151515; border: 1px solid #0a0a0a; }
QSlider::sub-page:horizontal { background: #2a6fb0; }
QSlider::handle:horizontal { width: 10px; margin: -5px 0; border-radius: 5px; border: 1px solid #111;
                             background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #8a8a8a, stop:1 #555); }
"""


def _pos(event):
    return event.position().toPoint() if hasattr(event, 'position') else event.pos()


def _exec(menu, pos):
    return menu.exec_(pos) if hasattr(menu, 'exec_') else menu.exec(pos)


def _lens_icon(size=22, color=QtGui.QColor(230, 230, 230)):
    """Iconezinho de lente (desenhado aqui) para as abas OBJECTS/BROWSER."""
    pm = QtGui.QPixmap(size, size)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    g = QtGui.QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QtGui.QColor(200, 200, 200))
    g.setColorAt(1, QtGui.QColor(70, 70, 70))
    p.setBrush(QtGui.QBrush(g))
    p.setPen(QtGui.QPen(QtGui.QColor(20, 20, 20), 1))
    p.drawRoundedRect(2, 5, size - 6, size - 10, 3, 3)
    p.setBrush(QtGui.QColor(25, 25, 25))
    p.drawEllipse(QtCore.QPointF(size * 0.42, size * 0.5), size * 0.24, size * 0.24)
    p.setBrush(QtGui.QColor(120, 170, 220))
    p.drawEllipse(QtCore.QPointF(size * 0.42, size * 0.5), size * 0.1, size * 0.1)
    p.end()
    return QtGui.QIcon(pm)


def _settings():
    """Preferencias da janela (tamanho das miniaturas etc.), por usuario."""
    return QtCore.QSettings('CaretaFlares', 'Options')


def _arrow_style():
    """Setinha branca dos menus suspensos (PNG gerado no cache; o QSS so aceita arquivo)."""
    try:
        path = os.path.join(os.path.dirname(fb.cache_dir()), 'combo_arrow.png')
        if not os.path.isfile(path):
            pm = QtGui.QPixmap(9, 5)
            pm.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pm)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(230, 230, 230))
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(0, 0), QtCore.QPointF(9, 0), QtCore.QPointF(4.5, 5)]))
            p.end()
            pm.save(path, 'PNG')
        return '\nQComboBox::down-arrow { image: url(%s); width: 9px; height: 5px; }\n' % path.replace(os.sep, '/')
    except Exception:
        return ''


def _folder_pixmap(w, h, name):
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor(16, 16, 16))
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(90, 90, 90), 1))
    p.setBrush(QtGui.QColor(55, 55, 55))
    fw, fh = w * 0.34, h * 0.42
    x0, y0 = (w - fw) / 2, (h - fh) / 2
    p.drawRoundedRect(QtCore.QRectF(x0, y0 - fh * 0.12, fw * 0.4, fh * 0.2), 2, 2)
    p.drawRoundedRect(QtCore.QRectF(x0, y0, fw, fh), 3, 3)
    p.end()
    return pm


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
        t = threading.Thread(target=self._run, name='caretaflares-options')
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

    def clear_queue(self, prefix):
        with self.cond:
            self.queue = [j for j in self.queue if not j[0].startswith(prefix)]

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
            except RuntimeError:
                return  # janela ja fechada
            except Exception as exc:
                print('CaretaFlares Options: %s' % exc)


def _image(raw, w, h):
    return QtGui.QImage(raw, w, h, w * 3, QtGui.QImage.Format_RGB888).copy()


# =================================================================== widgets de valor
class ScrubValue(QtWidgets.QLabel):
    """Valor em azul sublinhado: arraste para os lados para mudar (Shift fino, Ctrl rapido),
    duplo clique para digitar."""
    changed = QtCore.Signal(float, bool)  # valor, final

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
        return '%.1f' % v if (abs(v) >= 10 or self.unit) else '%.2f' % v

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
        mods = e.modifiers()
        mult = 0.1 if (mods & QtCore.Qt.ShiftModifier) else (10.0 if mods & QtCore.Qt.ControlModifier else 1.0)
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

    def __init__(self, rgb, w=30, h=14, parent=None):
        super(ColorSwatch, self).__init__(parent)
        self.setFixedSize(w, h)
        self.rgb = tuple(rgb)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet('background: rgb(%d,%d,%d); border: 1px solid #d0d0d0; border-radius: 0; padding: 0;'
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


def _panel(title, wing_menu=None):
    """Painel com barra de titulo (e o botao de "asa" no canto, como no original)."""
    frame = QtWidgets.QFrame()
    frame.setObjectName('panel')
    lay = QtWidgets.QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    head = QtWidgets.QFrame()
    head.setObjectName('panelHead')
    hl = QtWidgets.QHBoxLayout(head)
    hl.setContentsMargins(0, 0, 2, 0)
    hl.addWidget(_label(title, 'panelTitle'))
    hl.addStretch(1)
    if wing_menu is not None:
        wing = QtWidgets.QToolButton()
        wing.setObjectName('wing')
        wing.setText(u'▸')
        wing.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        wing.setMenu(wing_menu)
        hl.addWidget(wing)
    lay.addWidget(head)
    return frame, lay


class ThumbDelegate(QtWidgets.QStyledItemDelegate):
    """Miniatura com o nome embaixo, alinhado a esquerda, em negrito (lista do Browser)."""

    def __init__(self, owner):
        super(ThumbDelegate, self).__init__(owner)
        self.owner = owner

    def sizeHint(self, option, index):
        w, h = self.owner.thumb_size
        return QtCore.QSize(w + 12, h + 26)

    def paint(self, p, option, index):
        w, h = self.owner.thumb_size
        r = option.rect
        selected = option.state & QtWidgets.QStyle.State_Selected
        if selected:
            p.fillRect(r.adjusted(2, 1, -2, -1), QtGui.QColor(29, 101, 166))
        icon = index.data(QtCore.Qt.DecorationRole)
        x, y = r.x() + 6, r.y() + 4
        if isinstance(icon, QtGui.QIcon):
            pm = icon.pixmap(w, h)
            p.drawPixmap(QtCore.QRect(x, y, w, h), pm)
        p.setPen(QtGui.QColor(10, 10, 10))
        p.drawRect(QtCore.QRect(x, y, w - 1, h - 1))
        font = QtGui.QFont(p.font())
        font.setBold(True)
        p.setFont(font)
        p.setPen(QtGui.QColor(240, 240, 240))
        text = QtGui.QFontMetrics(font).elidedText(index.data(QtCore.Qt.DisplayRole) or '',
                                                   QtCore.Qt.ElideRight, w)
        p.drawText(QtCore.QRect(x, y + h + 3, w, 18), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)


# =================================================================== janela
class OptionsWindow(QtWidgets.QDialog):
    def __init__(self, node=None, preset_bytes=None, parent=None):
        super(OptionsWindow, self).__init__(parent)
        self.setObjectName('ofOptions')
        self.setWindowTitle('CaretaFlares Options')
        self.setStyleSheet(STYLE + _arrow_style())
        self.resize(1240, 900)
        self.node_name = node.fullName() if node is not None else None
        self.renderer = Renderer()
        self.worker = RenderWorker(self.renderer)
        self.worker.ready.connect(self._on_image, QtCore.Qt.QueuedConnection)
        self.preset = ofp.parse(preset_bytes) if preset_bytes else ofp.Preset()
        self.original = self.preset.clone()
        self.preset_name = ''
        self.preset_path = None
        self.sel = -1  # -1 = Global Parameters
        self.undo, self.redo = [ofp.serialize(self.preset)], []
        # preview independente do no, como no original: luz em 23,6 / 27,4 e centro no meio
        self.light = [DEFAULT_PREVIEW_POS[0] / 100.0, 1 - DEFAULT_PREVIEW_POS[1] / 100.0]
        self.center = [0.5, 0.5]
        self.pv_bright, self.pv_scale = 100.0, 100.0
        self.stack_rows = []
        self._editor_values = {}
        self._interactive = False
        tw = int(_settings().value('thumbWidth', 180) or 180)
        tw = max(70, min(420, tw))
        self.thumb_size = (tw, int(round(tw * 9 / 16.0)))
        self.browse_rel = ''
        self.mode = 'browser'
        self.obj_mode = 'basic'
        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(15)
        self._preview_timer.timeout.connect(self._request_preview)
        self._build()
        self._refresh_all()

    # ------------------------------------------------------------------ no
    def _node(self):
        if nuke is None or not self.node_name:
            return None
        return nuke.toNode(self.node_name)

    # ------------------------------------------------------------------ layout
    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_top())
        root.addWidget(self._build_tools())

        body = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(body)
        bl.setContentsMargins(6, 6, 6, 6)
        # 2x2 como no original: Preview/Stack a esquerda, Editor/Browser a direita
        self.hsplit = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.hsplit.setHandleWidth(6)
        self.vsplit = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.vsplit.setHandleWidth(6)
        self.vsplit_r = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.vsplit_r.setHandleWidth(6)
        self.preview_panel = self._build_preview()
        self.stack_panel = self._build_stack()
        self.vsplit.addWidget(self.preview_panel)
        self.vsplit.addWidget(self.stack_panel)
        self.editor_panel = self._build_editor()
        self.browser_panel = self._build_browser()
        self.vsplit_r.addWidget(self.editor_panel)
        self.vsplit_r.addWidget(self.browser_panel)
        self.hsplit.addWidget(self.vsplit)
        self.hsplit.addWidget(self.vsplit_r)
        bl.addWidget(self.hsplit)
        root.addWidget(body, 1)
        self._reset_panels()

    def _reset_panels(self):
        self.hsplit.setSizes([620, 620])
        self.vsplit.setSizes([400, 400])
        self.vsplit_r.setSizes([400, 400])
        for b in self.panel_buttons.values():
            b.setChecked(True)

    def _build_top(self):
        frame = QtWidgets.QFrame()
        frame.setObjectName('top')
        lay = QtWidgets.QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 10, 2)
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
        lay.addWidget(bar)
        lay.addStretch(2)
        lay.addWidget(_label('Panels:', 'dim'))
        lay.addSpacing(6)
        self.panel_buttons = {}
        for name in ('Preview', 'Stack', 'Editor', 'Browser'):
            b = QtWidgets.QPushButton(name)
            b.setObjectName('paneltab')
            b.setCheckable(True)
            b.setChecked(True)
            b.toggled.connect(lambda on, n=name: self._toggle_panel(n, on))
            lay.addWidget(b)
            self.panel_buttons[name] = b
        lay.addStretch(3)
        lay.addWidget(_label('CaretaFlares', 'brand'))
        lay.addSpacing(8)
        lay.addWidget(_label(VERSION, 'dim'))
        return frame

    def _act(self, menu, text, fn, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QtGui.QKeySequence(shortcut))
        a.triggered.connect(fn)
        menu.addAction(a)
        self.addAction(a)
        return a

    def _build_tools(self):
        frame = QtWidgets.QFrame()
        frame.setObjectName('tools')
        row = QtWidgets.QHBoxLayout(frame)
        row.setContentsMargins(10, 4, 10, 6)
        row.setSpacing(10)
        self.btn_undo = QtWidgets.QPushButton('Undo (0)')
        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo = QtWidgets.QPushButton('Redo (0)')
        self.btn_redo.clicked.connect(self._redo)
        dup = QtWidgets.QPushButton('Duplicate')
        dup.clicked.connect(self._duplicate)
        clear = QtWidgets.QPushButton('Clear All')
        clear.clicked.connect(self._clear_all)
        for b in (self.btn_undo, self.btn_redo, dup, clear):
            b.setObjectName('tool')
            row.addWidget(b)
        row.addStretch(1)
        cancel = QtWidgets.QPushButton('Cancel')
        cancel.setObjectName('tool')
        cancel.clicked.connect(self.reject)
        ok = QtWidgets.QPushButton('OK')
        ok.setObjectName('tool')
        ok.setStyleSheet('font-weight: bold;')
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
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
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.preview.installEventFilter(self)
        lay.addWidget(self.preview, 1)
        bar = QtWidgets.QFrame()
        bar.setObjectName('previewBar')
        grid = QtWidgets.QGridLayout(bar)
        grid.setContentsMargins(22, 5, 22, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        self.pv_b = ScrubValue(100, '%', 1.0)
        self.pv_b.changed.connect(lambda v, f: self._set_pv('b', v, f))
        self.pv_s = ScrubValue(100, '%', 1.0)
        self.pv_s.changed.connect(lambda v, f: self._set_pv('s', v, f))
        self.pv_x = ScrubValue(DEFAULT_PREVIEW_POS[0], '', 0.2)
        self.pv_x.changed.connect(lambda v, f: self._set_pv('x', v, f))
        self.pv_y = ScrubValue(DEFAULT_PREVIEW_POS[1], '', 0.2)
        self.pv_y.changed.connect(lambda v, f: self._set_pv('y', v, f))
        self.guides = QtWidgets.QCheckBox('Guides')
        self.guides.toggled.connect(lambda _on: self._schedule_preview())
        self.show_bg = QtWidgets.QCheckBox('Show BG')
        self.show_bg.setEnabled(False)
        self.show_bg.setToolTip('O fundo do no ainda nao aparece neste preview.')
        grid.addWidget(_label('Preview Brightness', 'plab'), 0, 0)
        grid.addWidget(self.pv_b, 0, 1)
        grid.addWidget(_label('Preview Position', 'plab'), 0, 3)
        pos = QtWidgets.QHBoxLayout()
        pos.setSpacing(4)
        pos.addWidget(self.pv_x)
        pos.addWidget(_label(',', 'plab'))
        pos.addWidget(self.pv_y)
        pos.addStretch(1)
        grid.addLayout(pos, 0, 4)
        grid.addWidget(_label('Preview Scale', 'plab'), 1, 0)
        grid.addWidget(self.pv_s, 1, 1)
        grid.addWidget(self.guides, 1, 3)
        grid.addWidget(self.show_bg, 1, 4)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(5, 1)
        lay.addWidget(bar)
        return frame

    def _set_pv(self, what, v, final=True):
        if what == 'b':
            self.pv_bright = v
        elif what == 's':
            self.pv_scale = v
        elif what == 'x':
            self.light[0] = v / 100.0
        elif what == 'y':
            self.light[1] = 1 - v / 100.0
        self._schedule_preview(interactive=not final)

    def eventFilter(self, obj, ev):
        if obj is self.preview:
            t = ev.type()
            if t in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseMove):
                if t == QtCore.QEvent.MouseMove and not (ev.buttons() & QtCore.Qt.LeftButton):
                    return False
                p = _pos(ev)
                x = p.x() / float(max(1, self.preview.width()))
                y = p.y() / float(max(1, self.preview.height()))
                self.light = [min(1.5, max(-0.5, x)), min(1.5, max(-0.5, 1 - y))]
                self.pv_x.set_value(x * 100)
                self.pv_y.set_value(y * 100)
                self._schedule_preview(interactive=True)
                return True
            if t == QtCore.QEvent.MouseButtonRelease:
                self._schedule_preview()
                return True
            if t == QtCore.QEvent.Resize:
                self._schedule_preview()
        return super(OptionsWindow, self).eventFilter(obj, ev)

    def _schedule_preview(self, interactive=False):
        # arrastando: meia resolucao (o dobro de quadros); ao soltar, resolucao cheia
        self._interactive = interactive
        self._preview_timer.start(0 if interactive else 15)

    def _request_preview(self):
        # o preview ocupa o painel inteiro (sem tarjas), como no original
        div = 2 if getattr(self, '_interactive', False) else 1
        w = max(64, self.preview.width() // div)
        h = max(36, self.preview.height() // div)
        data = ofp.serialize(self.preset)
        light, center = list(self.light), list(self.center)
        b, s = self.pv_bright / 100.0, self.pv_scale / 100.0

        def job():
            raw = self.renderer.render_mem(data, w, h, light, center, -1, b, s)
            if not raw:
                return None
            img = _image(raw, w, h)
            if div > 1:
                img = img.scaled(w * div, h * div, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.FastTransformation)
            return img

        self.worker.set_preview(('preview', job))

    # ------------------------------------------------------------------ stack
    def _build_stack(self):
        wing = QtWidgets.QMenu(self)
        wing.addAction('Duplicate', self._duplicate)
        wing.addAction('Move Up', lambda: self._move(-1))
        wing.addAction('Move Down', lambda: self._move(1))
        wing.addAction('Delete', self._delete_selected)
        wing.addSeparator()
        wing.addAction('Clear All', self._clear_all)
        frame, lay = _panel('Stack', wing)
        band = QtWidgets.QFrame()
        band.setObjectName('globalBand')
        self.global_band = band
        bl = QtWidgets.QHBoxLayout(band)
        bl.setContentsMargins(8, 7, 10, 7)
        bl.setSpacing(10)
        self.global_thumb = QtWidgets.QLabel()
        self.global_thumb.setFixedSize(76, 43)
        self.global_thumb.setStyleSheet('background:black; border:1px solid #0d3459;')
        bl.addWidget(self.global_thumb)
        mid = QtWidgets.QVBoxLayout()
        mid.setSpacing(5)
        mid.addWidget(_label('GLOBAL PARAMETERS', 'globalTitle'))
        seg = QtWidgets.QHBoxLayout()
        seg.setSpacing(0)
        self.btn_add = QtWidgets.QPushButton('ADD')
        self.btn_add.setObjectName('segl')
        self.btn_scn = QtWidgets.QPushButton('SCN')
        self.btn_scn.setObjectName('segr')
        for b in (self.btn_add, self.btn_scn):
            b.setCheckable(True)
            seg.addWidget(b)
        self.btn_add.clicked.connect(lambda: self._set_global_enum(9, 0))
        self.btn_scn.clicked.connect(lambda: self._set_global_enum(9, 1))
        seg.addSpacing(28)
        self.global_color = ColorSwatch((126, 146, 180), 30, 16)
        self.global_color.changed.connect(lambda rgb: self._set_global_color(4, rgb))
        seg.addWidget(self.global_color)
        seg.addSpacing(10)
        seg.addWidget(_label('Global Color', 'onBlue'))
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
        row.setFixedHeight(54)
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(6, 4, 8, 4)
        lay.setSpacing(8)
        thumb = QtWidgets.QLabel()
        thumb.setFixedSize(72, 41)
        thumb.setStyleSheet('background:black; border:1px solid #4a4a4a;')
        lay.addWidget(thumb)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        name = _label(o.name or o.type_name, 'rowName')
        name.setToolTip('%s (duplo clique para renomear)' % o.type_name)
        name.mouseDoubleClickEvent = lambda e, k=i: self._rename(k)
        col.addWidget(name)
        vals = QtWidgets.QHBoxLayout()
        vals.setSpacing(4)
        vals.addWidget(_label(u'☀', 'icon'))
        bv = ScrubValue(o.get(0, 100.0) or 0.0, '', 0.5)
        bv.changed.connect(lambda v, f, k=i: self._set_obj_float(k, 0, v, f))
        vals.addWidget(bv)
        vals.addSpacing(22)
        vals.addWidget(_label(u'▣', 'icon'))
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
            b.setFixedSize(54, 18)
            lay.addWidget(b)
        hide.toggled.connect(lambda on, k=i: self._set_flag(k, 'hidden', on))
        solo.toggled.connect(lambda on, k=i: self._set_flag(k, 'solo', on))
        x = QtWidgets.QPushButton('X')
        x.setObjectName('pillx')
        x.setFixedSize(20, 18)
        x.clicked.connect(lambda _c=False, k=i: self._delete(k))
        lay.addWidget(x)
        row.thumb = thumb
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
        _exec(m, gpos)

    def _mark_selection(self):
        for i, r in enumerate(self.stack_rows):
            r.setProperty('selected', 'true' if i == self.sel else 'false')
            r.style().unpolish(r)
            r.style().polish(r)
        self.global_band.setProperty('selected', 'true' if self.sel < 0 else 'false')
        self.global_band.style().unpolish(self.global_band)
        self.global_band.style().polish(self.global_band)

    def _request_stack_thumbs(self, only=None):
        """Miniaturas por objeto: renderiza 3x maior e reduz (objetos pequenos nao somem).
        only = indice do objeto que mudou (refaz so ele e a do Global); None = todas."""
        if only is None:
            self.worker.clear_queue('stack:')
        else:
            self.worker.clear_queue('stack:global')
        # miniatura mostra o objeto mesmo se estiver HIDE/SOLO: grava sem esses flags
        # (sem copiar o preset inteiro, que custava ~20 ms)
        flags = [(o.hidden, o.solo) for o in self.preset.objects]
        for o in self.preset.objects:
            o.hidden = o.solo = False
        try:
            data = ofp.serialize(self.preset)
        finally:
            for o, (h, so) in zip(self.preset.objects, flags):
                o.hidden, o.solo = h, so
        light, center = list(self.light), list(self.center)
        W, H = 216, 123

        def small(raw):
            img = _image(raw, W, H)
            return img.scaled(72, 41, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)

        targets = range(len(self.preset.objects)) if only is None or only < 0 else [only]
        for i in targets:
            def job(i=i):
                raw = self.renderer.render_mem(data, W, H, light, center, i, 1.0, 1.0)
                return small(raw) if raw else None
            self.worker.add(('stack:%d' % i, job))
        full = ofp.serialize(self.preset)

        def gjob():
            raw = self.renderer.render_mem(full, W, H, light, center, -1, 1.0, 1.0)
            return small(raw) if raw else None
        self.worker.add(('stack:global', gjob))

    # ------------------------------------------------------------------ editor
    def _build_editor(self):
        wing = QtWidgets.QMenu(self)
        wing.addAction('Reset', self._reset_selected)
        frame, lay = _panel('Editor', wing)
        head = QtWidgets.QFrame()
        head.setObjectName('editorHead')
        hl = QtWidgets.QHBoxLayout(head)
        hl.setContentsMargins(12, 9, 10, 9)
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
        lay.setContentsMargins(4, 0, 12, 12)
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
        self._editor_values = {}
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
        row.setFixedHeight(22)
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        lab = _label(P.label(p.id, getattr(target, 'type', None), is_global), 'plabel')
        lab.setFixedWidth(205)
        hl.addWidget(lab)
        unit = P.unit(p.id, is_global)
        step = P.drag_step(p.id, is_global)
        integer = P.is_integer(p.id, is_global)
        if p.type == ofp.FLOAT:
            w = ScrubValue(p.f(), unit, step, integer)
            w.changed.connect(lambda v, f, p=p: self._edit(lambda: p.set_f(v), f))
            self._editor_values[p.id] = w
            hl.addWidget(w)
        elif p.type == ofp.FLOAT2:
            a = ScrubValue(p.f(0), unit, step, integer)
            b = ScrubValue(p.f(1), unit, step, integer)
            a.changed.connect(lambda v, f, p=p: self._edit(lambda: p.set_f(v, 0), f))
            b.changed.connect(lambda v, f, p=p: self._edit(lambda: p.set_f(v, 1), f))
            hl.addWidget(a)
            hl.addWidget(_label(',', 'plab'))
            hl.addWidget(b)
        elif p.type == ofp.COLOR:
            sw = ColorSwatch(p.rgb())
            sw.changed.connect(lambda rgb, p=p: self._edit(lambda: p.set_rgb(*rgb), True))
            hl.addWidget(sw)
            if p.id == 83:  # Color Shift tem "ligado"
                on = QtWidgets.QCheckBox()
                on.setChecked(p.color_enabled())
                on.toggled.connect(lambda v, p=p: self._edit(lambda: p.set_color_enabled(v), True))
                hl.addWidget(on)
        elif p.type == ofp.ENUM:
            opts = P.enum_options(p.id, is_global)
            cb = QtWidgets.QComboBox()
            cb.setFixedHeight(17)
            cur = p.i()
            items = list(opts) if opts else []
            while len(items) <= cur:
                items.append(str(len(items)))
            cb.addItems(items)
            cb.setCurrentIndex(max(0, cur))
            cb.currentIndexChanged.connect(lambda ix, p=p: self._edit(lambda: p.set_i(ix), True))
            hl.addWidget(cb)
        elif p.type == ofp.BOOL:
            ck = QtWidgets.QCheckBox()
            ck.setChecked(bool(p.i()))
            ck.toggled.connect(lambda v, p=p: self._edit(lambda: p.set_i(1 if v else 0), True))
            hl.addWidget(ck)
        elif p.type == ofp.TEXTURE:
            hl.addWidget(self._texture_combo(p, is_global))
        hl.addStretch(1)
        return row

    def _texture_combo(self, p, is_global):
        names = self._texture_names('Glass' if is_global else 'Elements')
        cb = QtWidgets.QComboBox()
        cb.setFixedHeight(17)
        cb.addItem('None')
        cb.addItems(names)
        current = p.texture_name()
        if current.endswith(' (U)'):
            current = current[:-4]
        if (is_global and p.i() == 0) or current.lower() in ('', 'none'):
            current = ''  # desligada
        low = [n.lower() for n in names]
        if current and current.lower() in low:
            cb.setCurrentIndex(low.index(current.lower()) + 1)
        elif current:
            cb.addItem(current + ' (faltando)')
            cb.setCurrentIndex(cb.count() - 1)

        def pick(ix, p=p, names=names):
            if ix > len(names):
                return
            if ix == 0:
                p.set_texture(0, '')
            else:
                p.set_texture(ix, names[ix - 1])
            self._edit(lambda: None, True)
        cb.currentIndexChanged.connect(pick)
        return cb

    def _texture_names(self, folder):
        d = os.path.join(fb.textures_root(), folder)
        try:
            return sorted((os.path.splitext(f)[0] for f in os.listdir(d)
                           if f.lower().endswith(('.png', '.jpg', '.tif', '.tiff', '.bmp'))), key=str.lower)
        except OSError:
            return []

    # ------------------------------------------------------------------ edicao
    def _edit(self, fn, final):
        fn()
        self._changed(final, thumbs=final, only=self.sel)

    def _changed(self, final, thumbs=True, rebuild=False, only=None):
        self._schedule_preview(interactive=not final)
        if final:
            self._push_undo()
        if rebuild:
            self._rebuild_stack()
        elif thumbs:
            self._request_stack_thumbs(only)

    def _set_obj_float(self, k, pid, v, final):
        p = self.preset.objects[k].find(pid)
        if p is not None:
            p.set_f(v)
            if k == self.sel and final:
                w = self._editor_values.get(pid)
                if w is not None:
                    w.set_value(v)  # atualiza so o valor no Editor, sem reconstruir
            self._changed(final, thumbs=final, only=k)

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
        self.tab_objects = QtWidgets.QPushButton('  LENS OBJECTS')
        self.tab_browser = QtWidgets.QPushButton('  PRESET BROWSER')
        icon = _lens_icon(24)
        for b in (self.tab_objects, self.tab_browser):
            b.setIcon(icon)
            b.setIconSize(QtCore.QSize(24, 24))
            tabs.addWidget(b)
        self.tab_objects.clicked.connect(lambda: self._browser_mode('objects'))
        self.tab_browser.clicked.connect(lambda: self._browser_mode('browser'))
        lay.addLayout(tabs)

        self.crumbs = QtWidgets.QFrame()
        self.crumbs.setObjectName('crumbs')
        self.crumbs_lay = QtWidgets.QHBoxLayout(self.crumbs)
        self.crumbs_lay.setContentsMargins(6, 5, 6, 5)
        self.crumbs_lay.setSpacing(5)
        lay.addWidget(self.crumbs)

        # grade de miniaturas: quantas couberem por linha, no tamanho escolhido
        self.blist = QtWidgets.QListWidget()
        self.blist.setObjectName('blist')
        self.blist.setItemDelegate(ThumbDelegate(self))
        self.blist.setViewMode(QtWidgets.QListView.IconMode)
        self.blist.setFlow(QtWidgets.QListView.LeftToRight)
        self.blist.setWrapping(True)
        self.blist.setResizeMode(QtWidgets.QListView.Adjust)
        self.blist.setMovement(QtWidgets.QListView.Static)
        self.blist.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.blist.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.blist.setUniformItemSizes(True)
        self.blist.itemClicked.connect(self._browser_click)
        self.blist.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.blist.customContextMenuRequested.connect(self._browser_menu)
        self.blist.viewport().installEventFilter(self._make_wheel_zoom())
        lay.addWidget(self.blist, 1)

        # barra de tamanho das miniaturas (tambem Ctrl + roda do mouse na lista)
        sizebar = QtWidgets.QFrame()
        sizebar.setObjectName('crumbs')
        sl = QtWidgets.QHBoxLayout(sizebar)
        sl.setContentsMargins(8, 3, 8, 4)
        sl.setSpacing(6)
        small = _label(u'▪', 'plab')
        big = _label(u'■', 'plab')
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setRange(70, 420)
        self.size_slider.setValue(self.thumb_size[0])
        self.size_slider.setToolTip('Tamanho das miniaturas (Ctrl + roda do mouse na lista)')
        self.size_slider.valueChanged.connect(self._set_thumb_width)
        sl.addWidget(_label('Size', 'plab'))
        sl.addWidget(small)
        sl.addWidget(self.size_slider, 1)
        sl.addWidget(big)
        lay.addWidget(sizebar)

        self.browser_items = {}
        self._browser_mode('browser')
        return frame

    def _set_thumb_width(self, w):
        self.thumb_size = (int(w), int(round(w * 9 / 16.0)))
        self.blist.doItemsLayout()
        self.blist.viewport().update()
        _settings().setValue('thumbWidth', int(w))

    def _make_wheel_zoom(self):
        win = self

        class Wheel(QtCore.QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QtCore.QEvent.Wheel and ev.modifiers() & QtCore.Qt.ControlModifier:
                    d = ev.angleDelta().y()
                    if d:
                        win.size_slider.setValue(win.size_slider.value() + (20 if d > 0 else -20))
                    return True
                return False
        self._wheel = Wheel(self)
        return self._wheel

    def _browser_mode(self, mode):
        self.mode = mode
        self.tab_objects.setObjectName('tabOn' if mode == 'objects' else 'tabOff')
        self.tab_browser.setObjectName('tabOn' if mode == 'browser' else 'tabOff')
        for b in (self.tab_objects, self.tab_browser):
            b.style().unpolish(b)
            b.style().polish(b)
        self._fill_browser()

    def _set_crumbs(self, widgets):
        while self.crumbs_lay.count():
            it = self.crumbs_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for w in widgets:
            self.crumbs_lay.addWidget(w)
        self.crumbs_lay.addStretch(1)

    def _crumb(self, text, fn):
        b = QtWidgets.QPushButton(text)
        b.setObjectName('crumb')
        b.clicked.connect(fn)
        return b

    def _fill_browser(self):
        self.worker.clear_queue('browse:')
        self.blist.clear()
        self.browser_items = {}
        if self.mode == 'objects':
            show = _label('Show', 'plab')
            basic = QtWidgets.QPushButton('Basic')
            basic.setObjectName('segl')
            custom = QtWidgets.QPushButton('Custom')
            custom.setObjectName('segr')
            for b, m in ((basic, 'basic'), (custom, 'custom')):
                b.setCheckable(True)
                b.setChecked(self.obj_mode == m)
                b.clicked.connect(lambda _c=False, m=m: self._objects_mode(m))
            self._set_crumbs([show, basic, custom])
            self._fill_objects()
            return
        # trilha de pastas: Presets > Pro Presets > ...
        parts = [x for x in self.browse_rel.split('/') if x]
        widgets = [self._crumb('Presets', lambda: self._go(''))]
        for i, part in enumerate(parts):
            sep = _label(u'▸', 'crumbSep')
            widgets.append(sep)
            rel = '/'.join(parts[:i + 1])
            widgets.append(self._crumb(part, lambda _c=False, rel=rel: self._go(rel)))
        self._set_crumbs(widgets)
        root = fb.presets_root()
        base = root + ('/' + self.browse_rel if self.browse_rel else '')
        try:
            entries = os.listdir(base)
        except OSError:
            entries = []
        folders = sorted((e for e in entries if os.path.isdir(os.path.join(base, e))),
                         key=lambda d: ('custom' in d.lower(), d.lower()))
        files = sorted((e for e in entries if e.lower().endswith('.ofp')), key=str.lower)
        for d in folders:
            rel = (self.browse_rel + '/' + d) if self.browse_rel else d
            it = QtWidgets.QListWidgetItem(QtGui.QIcon(_folder_pixmap(220, 124, d)), d)
            it.setData(QtCore.Qt.UserRole, ('folder', rel))
            self.blist.addItem(it)
        ph = self._placeholder()
        for f in files:
            p = (base + '/' + f).replace('\\', '/')
            it = QtWidgets.QListWidgetItem(ph, os.path.splitext(f)[0])
            it.setData(QtCore.Qt.UserRole, ('preset', p))
            self.blist.addItem(it)
            self.browser_items[p] = it
            self.worker.add(('browse:' + p, lambda p=p: self._thumb_file(p)))

    def _go(self, rel):
        self.browse_rel = rel
        self._fill_browser()

    def _objects_mode(self, which):
        self.obj_mode = which
        self._fill_browser()

    def _placeholder(self):
        pm = QtGui.QPixmap(220, 124)
        pm.fill(QtGui.QColor(10, 10, 10))
        return QtGui.QIcon(pm)

    def _list_presets(self, rel):
        root = fb.presets_root()
        base = root + ('/' + rel if rel else '')
        out = []
        for dp, dirs, files in os.walk(base):
            dirs.sort(key=lambda d: ('custom' in d.lower(), d.lower()))
            out += [os.path.join(dp, f).replace('\\', '/') for f in sorted(files) if f.lower().endswith('.ofp')]
        return out

    def _thumb_file(self, path):
        cache = fb._cache_file(path, 320, 180)
        if os.path.isfile(cache):
            return QtGui.QImage(cache)
        raw, n = self.renderer.render(path, 320, 180)
        if raw is None:
            return None
        img = _image(raw, 320, 180)
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
        ph = self._placeholder()
        if self.obj_mode == 'basic':
            for t, (pre, o) in self._basic_objects():
                one = ofp.Preset()
                one.globals = pre.globals
                one.has_globals = pre.has_globals
                obj = copy.deepcopy(o)
                obj.name = ofp.TYPE_NAMES[t]
                obj.hidden = obj.solo = False
                one.objects = [obj]
                data = ofp.serialize(one)
                key = 'obj:%d' % t
                it = QtWidgets.QListWidgetItem(ph, ofp.TYPE_NAMES[t])
                it.setData(QtCore.Qt.UserRole, ('objects', data))
                self.blist.addItem(it)
                self.browser_items[key] = it

                def job(data=data):
                    raw = self.renderer.render_mem(data, 320, 180, [0.35, 0.6], [0.5, 0.5])
                    return _image(raw, 320, 180) if raw else None
                self.worker.add(('browse:' + key, job))
        else:
            for p in self._list_presets('Custom Objects') or self._list_presets(''):
                it = QtWidgets.QListWidgetItem(ph, os.path.splitext(os.path.basename(p))[0])
                it.setData(QtCore.Qt.UserRole, ('objfile', p))
                self.blist.addItem(it)
                self.browser_items[p] = it
                self.worker.add(('browse:' + p, lambda p=p: self._thumb_file(p)))

    def _browser_click(self, item):
        kind, ref = item.data(QtCore.Qt.UserRole)
        if kind == 'folder':
            self._go(ref)
        elif kind == 'preset':
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
        elif kind == 'folder':
            m.addAction('Open', lambda: self._go(ref))
        else:
            m.addAction('Add To Stack', lambda: self._browser_click(item))
        _exec(m, self.blist.viewport().mapToGlobal(pos))

    def _add_objects(self, objs):
        for o in objs:
            self.preset.objects.append(copy.deepcopy(o))
        self.sel = len(self.preset.objects) - 1
        self._changed(True, rebuild=True)
        self._rebuild_editor()

    def _load_preset(self, path):
        try:
            self.preset = ofp.load(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, 'CaretaFlares', 'Nao abriu: %s' % exc)
            return
        self.original = self.preset.clone()
        self.preset_name = os.path.splitext(os.path.basename(path))[0]
        self.preset_path = path
        self.sel = -1
        self._push_undo()
        self._refresh_all()

    def _load_preset_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load Preset', fb.presets_root(),
                                                        'CaretaFlares preset (*.ofp)')
        if path:
            self._load_preset(path)

    def _save_preset(self):
        start = os.path.join(fb.presets_root(), self.browse_rel, (self.preset_name or 'Meu Flare') + '.ofp')
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save Preset', start, 'CaretaFlares preset (*.ofp)')
        if not path:
            return
        with open(path, 'wb') as fh:
            fh.write(ofp.serialize(self.preset))
        self.preset_name = os.path.splitext(os.path.basename(path))[0]
        self.preset_path = path
        if self.mode == 'browser':
            self._fill_browser()

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
                p.drawLine(QtCore.QPointF(cx - 6, cy), QtCore.QPointF(cx + 6, cy))
                p.drawLine(QtCore.QPointF(cx, cy - 6), QtCore.QPointF(cx, cy + 6))
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
        nuke.Undo.begin('CaretaFlares: Options')
        try:
            if self.preset_path and 'ofpPresetFile' in node.knobs():
                node['ofpPresetFile'].setValue(self.preset_path)
            node['renderOptions'].setValue(ofp.encode_state(data))  # as edicoes valem sobre o arquivo
            if 'ofpPresetName' in node.knobs() and self.preset_name:
                node['ofpPresetName'].setValue(self.preset_name)
        finally:
            nuke.Undo.end()
        self.accept()

    def done(self, r):
        self.worker.stop()
        super(OptionsWindow, self).done(r)


def open_options(node=None):
    """Botao Options do no: caretaflares_options.open_options(nuke.thisNode())."""
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
    if os.environ.get('CARETAFLARES_SHOT_BROWSE'):
        w._go(os.environ['CARETAFLARES_SHOT_BROWSE'])
    w.show()
    if shot:
        def grab():
            w.grab().save(shot)
            app.quit()
        QtCore.QTimer.singleShot(int(os.environ.get('CARETAFLARES_SHOT_MS', '6000')), grab)
    app.exec_() if hasattr(app, 'exec_') else app.exec()
