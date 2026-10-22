# -*- coding: utf-8 -*-
"""Leitura e escrita de presets .ofp (mesmo formato do src/OfpPreset.cpp, docs/02).

Arquivo = b"OFP\\x03" + registros (u16 tag, u16 tamanho, payload). O modelo guarda
os payloads originais dos marcadores para regravar o arquivo byte a byte igual
quando nada muda (conferido no teste de ida e volta).
"""
from __future__ import print_function

import copy
import struct

T_OBJ_TYPE, T_OBJ_NAME, T_OBJ_HIDDEN, T_OBJ_SOLO = 1, 2, 3, 4
T_PID, T_PTYPE, T_PVAL = 50, 51, 52
T_OBJ_END, T_PARAM_END, T_GLOB_BEGIN, T_GLOB_END = 1000, 2000, 3000, 4000

FLOAT, FLOAT2, COLOR, ENUM, BOOL, TEXTURE, DIVIDER = 0, 1, 2, 3, 4, 5, 6

TYPE_NAMES = {1: 'Glow', 2: 'Streak', 4: 'Multi Iris', 5: 'Shimmer', 6: 'Ring', 7: 'Hoop',
              8: 'Glint', 9: 'Sparkle', 11: 'Spike Ball', 12: 'Caustic', 14: 'Lens Orbs', 15: 'Iris'}


class Param(object):
    __slots__ = ('rid', 'type', 'raw', 'id_payload', 'type_payload', 'end_payload')

    def __init__(self, rid, ptype, raw, id_payload=None, type_payload=None, end_payload=b'\x00'):
        self.rid = rid            # id gravado (91 e lido como 7, como no plugin)
        self.type = ptype
        self.raw = bytearray(raw[:32].ljust(32, b'\x00'))
        self.id_payload = id_payload if id_payload is not None else struct.pack('<i', rid)
        self.type_payload = type_payload if type_payload is not None else struct.pack('<i', ptype)
        self.end_payload = end_payload

    @property
    def id(self):
        return 7 if self.rid == 91 else self.rid

    # ---- valores
    def f(self, i=0):
        return struct.unpack_from('<f', self.raw, 4 * i)[0]

    def set_f(self, v, i=0):
        struct.pack_into('<f', self.raw, 4 * i, float(v))

    def i(self):
        return struct.unpack_from('<i', self.raw, 0)[0]

    def set_i(self, v):
        struct.pack_into('<i', self.raw, 0, int(v))

    def rgb(self):
        v = struct.unpack_from('<I', self.raw, 0)[0]
        return (v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff)

    def set_rgb(self, r, g, b):
        old = struct.unpack_from('<I', self.raw, 0)[0]
        v = (old & 0xff000000) | (int(r) & 0xff) | ((int(g) & 0xff) << 8) | ((int(b) & 0xff) << 16)
        struct.pack_into('<I', self.raw, 0, v)

    def color_enabled(self):  # Color Shift usa o 2o dword como "ligado"
        return struct.unpack_from('<I', self.raw, 4)[0] != 0

    def set_color_enabled(self, on):
        struct.pack_into('<f', self.raw, 4, 1.0 if on else 0.0)

    def texture_name(self):
        s = bytes(self.raw[4:32])
        return s.split(b'\x00', 1)[0].decode('latin-1')

    def set_texture(self, index, name):
        struct.pack_into('<i', self.raw, 0, int(index))
        b = name.encode('latin-1', 'replace')[:27]
        self.raw[4:32] = b.ljust(28, b'\x00')

    def value(self):
        if self.type in (FLOAT,):
            return self.f()
        if self.type == FLOAT2:
            return (self.f(0), self.f(1))
        if self.type == COLOR:
            return self.rgb()
        if self.type in (ENUM, BOOL):
            return self.i()
        if self.type == TEXTURE:
            return (self.i(), self.texture_name())
        return None


class FlareObject(object):
    def __init__(self, otype=1, name='', hidden=False, solo=False):
        self.type = otype
        self.name = name
        self.hidden = hidden
        self.solo = solo
        self.params = []
        self.type_payload = struct.pack('<i', otype)
        self.name_len = 64
        self.name_payload = None  # original (tem bytes de lixo depois do \x00 nos presets da VC)
        self.hidden_payload = None
        self.solo_payload = None
        self.end_payload = b'\x00'

    @property
    def type_name(self):
        return TYPE_NAMES.get(self.type, 'Tipo %d' % self.type)

    def find(self, pid):
        found = None
        for p in self.params:
            if p.id == pid:
                found = p
        return found

    def get(self, pid, default=None):
        p = self.find(pid)
        return p.value() if p is not None else default


class Preset(object):
    def __init__(self):
        self.version = 3
        self.globals = FlareObject(0, 'GLOBAL PARAMETERS')
        self.globals_begin = b'\x00'
        self.globals_end = b'\x00'
        self.has_globals = True
        self.objects = []

    def clone(self):
        return copy.deepcopy(self)


def _records(data):
    pos = 4
    n = len(data)
    while pos + 4 <= n:
        tag, ln = struct.unpack_from('<HH', data, pos)
        payload = data[pos + 4:pos + 4 + ln]
        pos += 4 + ln
        yield tag, payload


def parse(data):
    if len(data) < 4 or data[:3] != b'OFP':
        raise ValueError('nao e um preset .ofp')
    pre = Preset()
    pre.version = data[3] if isinstance(data[3], int) else ord(data[3])
    pre.has_globals = False
    target = None
    obj = None
    pid = ptype = None
    pid_payload = ptype_payload = None
    pending = None
    for tag, payload in _records(data):
        if tag == T_GLOB_BEGIN:
            pre.has_globals = True
            pre.globals_begin = payload
            target = pre.globals
        elif tag == T_GLOB_END:
            pre.globals_end = payload
            target = None
        elif tag == T_OBJ_TYPE:
            obj = FlareObject(struct.unpack('<i', payload[:4])[0])
            obj.type_payload = payload
            pre.objects.append(obj)
            target = obj
        elif tag == T_OBJ_NAME and obj is not None:
            obj.name = payload.split(b'\x00', 1)[0].decode('latin-1')
            obj.name_len = len(payload)
            obj.name_payload = payload
        elif tag == T_OBJ_HIDDEN and obj is not None:
            obj.hidden = bool(payload[:1] and payload[:1] != b'\x00')
            obj.hidden_payload = payload
        elif tag == T_OBJ_SOLO and obj is not None:
            obj.solo = bool(payload[:1] and payload[:1] != b'\x00')
            obj.solo_payload = payload
        elif tag == T_OBJ_END:
            if obj is not None:
                obj.end_payload = payload
            obj = None
            target = None
        elif tag == T_PID:
            pid = struct.unpack('<i', payload[:4])[0]
            pid_payload = payload
        elif tag == T_PTYPE:
            ptype = struct.unpack('<i', payload[:4])[0]
            ptype_payload = payload
        elif tag == T_PVAL:
            if target is not None and pid is not None and ptype is not None:
                pending = Param(pid, ptype, payload, pid_payload, ptype_payload)
                target.params.append(pending)
        elif tag == T_PARAM_END:
            if pending is not None:
                pending.end_payload = payload
            pending = None
            pid = ptype = None
    return pre


def _rec(out, tag, payload):
    out += struct.pack('<HH', tag, len(payload))
    out += payload


def _write_params(out, params):
    for p in params:
        _rec(out, T_PID, p.id_payload)
        _rec(out, T_PTYPE, p.type_payload)
        _rec(out, T_PVAL, bytes(p.raw))
        _rec(out, T_PARAM_END, p.end_payload)


def serialize(pre):
    out = bytearray(b'OFP' + bytes(bytearray([pre.version])))
    if pre.has_globals:
        _rec(out, T_GLOB_BEGIN, pre.globals_begin)
        _write_params(out, pre.globals.params)
        _rec(out, T_GLOB_END, pre.globals_end)
    for o in pre.objects:
        _rec(out, T_OBJ_TYPE, o.type_payload if struct.unpack('<i', o.type_payload[:4])[0] == o.type
             else struct.pack('<i', o.type))
        name = o.name.encode('latin-1', 'replace')[:max(1, o.name_len) - 1]
        if o.name_payload is not None and o.name_payload.split(b'\x00', 1)[0] == name:
            _rec(out, T_OBJ_NAME, o.name_payload)
        else:
            _rec(out, T_OBJ_NAME, name.ljust(o.name_len, b'\x00'))
        hp = o.hidden_payload or b'\x00'
        sp = o.solo_payload or b'\x00'
        _rec(out, T_OBJ_HIDDEN, (b'\x01' if o.hidden else b'\x00') + hp[1:])
        _rec(out, T_OBJ_SOLO, (b'\x01' if o.solo else b'\x00') + sp[1:])
        _write_params(out, o.params)
        _rec(out, T_OBJ_END, o.end_payload)
    return bytes(out)


def load(path):
    with open(path, 'rb') as fh:
        return parse(fh.read())


def encode_state(data):
    """Texto do knob renderOptions: "<N>;<hex>"."""
    return '%d;%s' % (len(data), ''.join('%02x' % b for b in bytearray(data)))


def decode_state(text):
    n, _, hx = (text or '').partition(';')
    data = bytes(bytearray.fromhex(hx.strip()))
    if n.strip() and int(n) != len(data):
        raise ValueError('renderOptions com tamanho errado')
    return data


if __name__ == '__main__':  # teste de ida e volta em todos os presets
    import os
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                              '..', 'data', 'Presets')
    total = bad = 0
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith('.ofp'):
                total += 1
                data = open(os.path.join(dp, f), 'rb').read()
                if serialize(parse(data)) != data:
                    bad += 1
                    print('difere:', f)
    print('%d presets, %d diferentes' % (total, bad))
