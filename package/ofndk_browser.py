# -*- coding: utf-8 -*-
"""Browser de presets do OpticalFlares (plugin novo, NDK).

Abre pelo botao "Preset Browser" do no. Lista os .ofp da instalacao do usuario
(~/.nuke/OpticalFlares/Optical Flares Presets ou OPTICAL_FLARES_PRESET_PATH),
com miniaturas renderizadas pelo ofthumb.dll (mesmo renderizador do no) e guardadas
em %LOCALAPPDATA%/OpticalFlaresNDK/thumbs.

Funciona no Nuke 15 (PySide2) e 17 (PySide6). Fora do Nuke serve para teste:
    python ofndk_browser.py [--shot SAIDA.png]
"""
from __future__ import print_function

import ctypes
import hashlib
import os
import sys
import threading

try:  # Nuke 16+
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Nuke 13-15
    from PySide2 import QtCore, QtGui, QtWidgets

try:
    import nuke
except ImportError:
    nuke = None

HERE = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
THUMB_W, THUMB_H = 256, 144
PREVIEW_W, PREVIEW_H = 640, 360
# o teste do Nuke (tools/nuke_test.py) aponta para o build; no pacote fica ao lado do DLL do no
THUMB_DLL = os.environ.get('OFNDK_THUMB_DLL', '')

_window = None


# ----------------------------------------------------------------- caminhos
def _install_dir():
    base = os.environ.get('OPTICAL_FLARES_PATH') or os.path.expanduser('~/.nuke/OpticalFlares')
    return base.replace('\\', '/')


def presets_root():
    p = os.environ.get('OPTICAL_FLARES_PRESET_PATH') or _install_dir() + '/Optical Flares Presets'
    return p.replace('\\', '/')


def textures_root():
    p = os.environ.get('OPTICAL_FLARES_TEXTURE_PATH') or _install_dir() + '/Optical Flares Textures'
    return p.replace('\\', '/')


def cache_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'OpticalFlaresNDK', 'thumbs')
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def _nuke_folder():
    if nuke is None:
        return 'Nuke17.0'
    return 'Nuke%d.%d' % (nuke.NUKE_VERSION_MAJOR, nuke.NUKE_VERSION_MINOR)


def _thumb_dll_path():
    if THUMB_DLL and os.path.isfile(THUMB_DLL):
        return THUMB_DLL
    return os.path.join(HERE, _nuke_folder(), 'ofthumb.dll')


# ----------------------------------------------------------------- renderizador
class Renderer(object):
    """ofthumb.dll via ctypes. A chamada solta o GIL, entao roda bem numa thread."""

    def __init__(self):
        path = _thumb_dll_path()
        self.dll = ctypes.CDLL(path)
        f = self.dll.ofthumb_render
        f.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int,
                      ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_void_p]
        f.restype = ctypes.c_int
        self.dll.ofthumb_count.argtypes = [ctypes.c_char_p]
        self.dll.ofthumb_count.restype = ctypes.c_int
        self.tex = textures_root().encode('utf-8')

    def render(self, ofp, w, h, light=(0.3, 0.6), center=(0.5, 0.5)):
        buf = ctypes.create_string_buffer(w * h * 3)
        n = self.dll.ofthumb_render(ofp.encode('utf-8'), self.tex, w, h,
                                    light[0], light[1], center[0], center[1], buf)
        return (buf.raw if n >= 0 else None), n

    def count(self, ofp):
        return self.dll.ofthumb_count(ofp.encode('utf-8'))


def _to_image(raw, w, h):
    img = QtGui.QImage(raw, w, h, w * 3, QtGui.QImage.Format_RGB888)
    return img.copy()  # desacopla do buffer do Python


def _cache_file(ofp, w, h):
    st = os.stat(ofp)
    key = '%s|%d|%d|%dx%d|v1' % (ofp, int(st.st_mtime), st.st_size, w, h)
    return os.path.join(cache_dir(), hashlib.md5(key.encode('utf-8')).hexdigest() + '.png')


class ThumbWorker(QtCore.QObject):
    """Uma thread so (a maquina e sensivel); pedidos de preview passam na frente."""
    done = QtCore.Signal(str, object, int)  # chave, QImage, objetos

    def __init__(self, renderer):
        super(ThumbWorker, self).__init__()
        self.renderer = renderer
        self.cond = threading.Condition()
        self.queue = []
        self.alive = True
        self.thread = threading.Thread(target=self._run, name='ofndk-thumbs')
        self.thread.daemon = True
        self.thread.start()

    def request(self, key, ofp, w, h, light=(0.3, 0.6), center=(0.5, 0.5), urgent=False, cache=True):
        with self.cond:
            item = (key, ofp, w, h, light, center, cache)
            if urgent:
                self.queue.insert(0, item)
            else:
                self.queue.append(item)
            self.cond.notify()

    def clear(self):
        with self.cond:
            self.queue = []

    def stop(self):
        with self.cond:
            self.alive = False
            self.queue = []
            self.cond.notify()

    def _run(self):
        while True:
            with self.cond:
                while self.alive and not self.queue:
                    self.cond.wait()
                if not self.alive:
                    return
                key, ofp, w, h, light, center, cache = self.queue.pop(0)
            try:
                path = _cache_file(ofp, w, h) if cache else None
                if path and os.path.isfile(path):
                    img = QtGui.QImage(path)
                    n = -2
                else:
                    raw, n = self.renderer.render(ofp, w, h, light, center)
                    if raw is None:
                        continue
                    img = _to_image(raw, w, h)
                    if path:
                        img.save(path, 'PNG')
                self.done.emit(key, img, n)
            except Exception as exc:  # nunca derruba o Nuke por causa de miniatura
                print('OpticalFlares browser: %s: %s' % (ofp, exc))


# ----------------------------------------------------------------- janela
STYLE = """
QDialog { background: #262626; }
QTreeWidget, QListWidget, QLineEdit { background: #1d1d1d; border: 1px solid #3a3a3a; color: #d0d0d0; }
QListWidget::item { color: #c8c8c8; border-radius: 3px; padding: 4px; }
QListWidget::item:selected { background: #c26a1b; color: white; }
QListWidget::item:hover { background: #333; }
QTreeWidget::item:selected { background: #c26a1b; color: white; }
QLabel#title { color: #f0f0f0; font-size: 15px; font-weight: bold; }
QLabel#info { color: #9a9a9a; }
QLabel#preview { background: black; border: 1px solid #3a3a3a; }
QPushButton { background: #3a3a3a; color: #e0e0e0; border: 1px solid #4a4a4a; padding: 6px 16px; border-radius: 3px; }
QPushButton:hover { background: #474747; }
QPushButton#apply { background: #c26a1b; border-color: #e07b22; color: white; font-weight: bold; }
QPushButton#apply:hover { background: #d97a26; }
"""


class PresetBrowser(QtWidgets.QDialog):
    def __init__(self, node=None, parent=None):
        super(PresetBrowser, self).__init__(parent)
        self.node_name = node.fullName() if node is not None else None
        self.setWindowTitle('Optical Flares  -  Preset Browser')
        self.setStyleSheet(STYLE)
        self.resize(1280, 760)
        self.root = presets_root()
        self.items = {}       # caminho -> QListWidgetItem
        self.current = None   # caminho selecionado
        self.renderer = Renderer()
        self.worker = ThumbWorker(self.renderer)
        self.worker.done.connect(self._on_image, QtCore.Qt.QueuedConnection)
        self._build()
        self._fill_tree()
        self._select_initial()

    # ---- layout
    def _build(self):
        lay = QtWidgets.QHBoxLayout(self)
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        lay.addWidget(split)

        left = QtWidgets.QWidget()
        ll = QtWidgets.QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Buscar preset...')
        self.search.textChanged.connect(self._filter)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._folder_changed)
        ll.addWidget(self.search)
        ll.addWidget(self.tree)
        split.addWidget(left)

        self.grid = QtWidgets.QListWidget()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setIconSize(QtCore.QSize(THUMB_W, THUMB_H))
        self.grid.setGridSize(QtCore.QSize(THUMB_W + 16, THUMB_H + 34))
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.currentItemChanged.connect(self._item_changed)
        self.grid.itemDoubleClicked.connect(lambda _item: self._apply(close=True))
        split.addWidget(self.grid)

        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        self.preview = QtWidgets.QLabel()
        self.preview.setObjectName('preview')
        self.preview.setFixedSize(PREVIEW_W // 3 * 2 + 2, PREVIEW_H // 3 * 2 + 2)
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.title = QtWidgets.QLabel('')
        self.title.setObjectName('title')
        self.info = QtWidgets.QLabel('')
        self.info.setObjectName('info')
        self.info.setWordWrap(True)
        rl.addWidget(self.preview)
        rl.addWidget(self.title)
        rl.addWidget(self.info)
        rl.addStretch(1)
        buttons = QtWidgets.QHBoxLayout()
        cancel = QtWidgets.QPushButton('Fechar')
        cancel.clicked.connect(self.close)
        apply_btn = QtWidgets.QPushButton('Aplicar')
        apply_btn.clicked.connect(lambda: self._apply(close=False))
        ok = QtWidgets.QPushButton('OK')
        ok.setObjectName('apply')
        ok.clicked.connect(lambda: self._apply(close=True))
        buttons.addWidget(cancel)
        buttons.addStretch(1)
        buttons.addWidget(apply_btn)
        buttons.addWidget(ok)
        rl.addLayout(buttons)
        split.addWidget(right)
        split.setSizes([220, 760, 440])

    # ---- pastas
    def _fill_tree(self):
        self.tree.clear()
        top = QtWidgets.QTreeWidgetItem(['Todos os presets'])
        top.setData(0, QtCore.Qt.UserRole, '')
        self.tree.addTopLevelItem(top)
        self.folders = {'': top}
        if not os.path.isdir(self.root):
            self.info.setText('Pasta de presets nao encontrada:\n%s' % self.root)
            return
        for dp, dirs, files in os.walk(self.root):
            dirs.sort()
            rel = os.path.relpath(dp, self.root).replace('\\', '/')
            if rel == '.':
                continue
            parent = self.folders.get(os.path.dirname(rel), top)
            it = QtWidgets.QTreeWidgetItem([os.path.basename(rel)])
            it.setData(0, QtCore.Qt.UserRole, rel)
            parent.addChild(it)
            self.folders[rel] = it
        top.setExpanded(True)

    def _presets_in(self, rel, recursive):
        base = self.root if not rel else self.root + '/' + rel
        out = []
        if recursive:
            for dp, dirs, files in os.walk(base):
                # flares completos primeiro; "Custom Objects" (elementos soltos) por ultimo
                dirs.sort(key=lambda d: ('custom' in d.lower(), d.lower()))
                out += [os.path.join(dp, f).replace('\\', '/') for f in sorted(files) if f.lower().endswith('.ofp')]
        elif os.path.isdir(base):
            out = [base + '/' + f for f in sorted(os.listdir(base)) if f.lower().endswith('.ofp')]
        return out

    def _folder_changed(self):
        sel = self.tree.selectedItems()
        rel = sel[0].data(0, QtCore.Qt.UserRole) if sel else ''
        # cada pasta mostra tudo o que tem dentro; "Todos" mostra a instalacao inteira
        self._populate(self._presets_in(rel, recursive=True))

    def _populate(self, paths):
        self.worker.clear()
        self.grid.clear()
        self.items = {}
        placeholder = QtGui.QPixmap(THUMB_W, THUMB_H)
        placeholder.fill(QtGui.QColor(18, 18, 18))
        icon = QtGui.QIcon(placeholder)
        for p in paths:
            name = os.path.splitext(os.path.basename(p))[0]
            it = QtWidgets.QListWidgetItem(icon, name)
            it.setData(QtCore.Qt.UserRole, p)
            it.setToolTip(p)
            it.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
            self.grid.addItem(it)
            self.items[p] = it
            self.worker.request('t:' + p, p, THUMB_W, THUMB_H)
        self._filter(self.search.text())

    def _filter(self, text):
        text = (text or '').lower().strip()
        for p, it in self.items.items():
            it.setHidden(bool(text) and text not in os.path.basename(p).lower())

    # ---- miniaturas e preview
    def _on_image(self, key, img, count):
        kind, _, path = key.partition(':')
        if kind == 't':
            it = self.items.get(path)
            if it is not None:
                it.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(img)))
        elif kind == 'p' and path == self.current:
            pm = QtGui.QPixmap.fromImage(img).scaled(self.preview.width() - 2, self.preview.height() - 2,
                                                     QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.preview.setPixmap(pm)

    def _node_geometry(self):
        """Luz e centro do no em fracao do formato, para o preview ficar igual ao viewer."""
        node = self._node()
        if node is None:
            return (0.3, 0.6), (0.5, 0.5), PREVIEW_W, PREVIEW_H
        try:
            fmt = node.format()
            w, h = float(fmt.width()), float(fmt.height())
            lx, ly = node['PositionXY'].value()
            cx, cy = node['CenterPosition'].value()
            pw = PREVIEW_W
            ph = max(90, min(480, int(round(pw * h / w))))
            return (lx / w, ly / h), (cx / w, cy / h), pw, ph
        except Exception:
            return (0.3, 0.6), (0.5, 0.5), PREVIEW_W, PREVIEW_H

    def _item_changed(self, item, _prev=None):
        if item is None:
            return
        path = item.data(QtCore.Qt.UserRole)
        self.current = path
        rel = os.path.relpath(os.path.dirname(path), self.root).replace('\\', '/')
        self.title.setText(os.path.splitext(os.path.basename(path))[0])
        n = self.renderer.count(path)
        self.info.setText('%s\n%d objetos' % ('Presets' if rel == '.' else rel, n))
        light, center, pw, ph = self._node_geometry()
        self.worker.request('p:' + path, path, pw, ph, light, center, urgent=True, cache=False)

    # ---- aplicar no no
    def _node(self):
        if nuke is None or not self.node_name:
            return None
        return nuke.toNode(self.node_name)

    def _select_initial(self):
        top = self.tree.topLevelItem(0)
        self.tree.setCurrentItem(top)
        node = self._node()
        current = ''
        if node is not None and 'ofpPresetFile' in node.knobs():
            current = node['ofpPresetFile'].value()
        if current and current.replace('\\', '/') in self.items:
            it = self.items[current.replace('\\', '/')]
            self.grid.setCurrentItem(it)
            self.grid.scrollToItem(it)
        elif self.grid.count():
            self.grid.setCurrentRow(0)

    def _apply(self, close):
        path = self.current
        node = self._node()
        if not path:
            return
        if node is None:
            if nuke is None:
                print('aplicaria: %s' % path)
                if close:
                    self.close()
                return
            QtWidgets.QMessageBox.warning(self, 'Optical Flares', 'O no %s nao existe mais.' % self.node_name)
            return
        with open(path, 'rb') as fh:
            data = fh.read()
        state = '%d;%s' % (len(data), ''.join('%02x' % b for b in bytearray(data)))
        nuke.Undo.begin('Optical Flares: preset')
        try:
            node['renderOptions'].setValue(state)
            if 'ofpPresetName' in node.knobs():
                node['ofpPresetName'].setValue(os.path.splitext(os.path.basename(path))[0])
            if 'ofpPresetFile' in node.knobs():
                node['ofpPresetFile'].setValue(path)
        finally:
            nuke.Undo.end()
        if close:
            self.close()

    def closeEvent(self, event):
        self.worker.stop()
        super(PresetBrowser, self).closeEvent(event)


def open_browser(node=None):
    """Chamado pelo botao do no: ofndk_browser.open_browser(nuke.thisNode())."""
    global _window
    if _window is not None:
        try:
            _window.close()
        except Exception:
            pass
    parent = QtWidgets.QApplication.activeWindow()
    _window = PresetBrowser(node, parent)
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = open_browser(None)
    if '--shot' in sys.argv:
        out = sys.argv[sys.argv.index('--shot') + 1]

        def shot():
            w.grab().save(out)
            app.quit()

        # espera as miniaturas da pasta raiz
        QtCore.QTimer.singleShot(int(os.environ.get('OFNDK_SHOT_MS', '6000')), shot)
    app.exec_() if hasattr(app, 'exec_') else app.exec()
