#!/usr/bin/env python3
"""ofp_dump.py - leitor/validador do formato de preset .ofp (Optical Flares).

Escrito do zero a partir da descricao em docs/02-formato-ofp.md. Nao contem
codigo nem dados da Video Copilot: so interpreta os arquivos da instalacao
do usuario.

Uso:
    python ofp_dump.py ARQUIVO.ofp            # lista globais e objetos
    python ofp_dump.py ARQUIVO.ofp -v         # ... com todos os parametros
    python ofp_dump.py --scan PASTA           # valida todos os .ofp da pasta
    python ofp_dump.py --json ARQUIVO.ofp     # saida JSON

O modulo tambem pode ser importado: parse_ofp(bytes) -> Preset.
"""
from __future__ import annotations

import json
import os
import struct
import sys
from dataclasses import dataclass, field

MAGIC = b"OFP"
VERSION = 3

# tags do container (u16 little-endian) -------------------------------------
TAG_OBJ_TYPE = 1        # i32: tipo do objeto; abre um objeto
TAG_OBJ_NAME = 2        # 64 bytes: nome, terminado em NUL
TAG_OBJ_HIDDEN = 3      # u8: objeto desligado (nao renderiza, salvo solo)
TAG_OBJ_SOLO = 4        # u8: solo
TAG_PARAM_ID = 50       # i32
TAG_PARAM_TYPE = 51     # i32
TAG_PARAM_VALUE = 52    # 32 bytes (8 floats ou int + nome de textura)
TAG_OBJ_END = 1000      # u8 (0)
TAG_PARAM_END = 2000    # u8 (0)
TAG_GLOBALS_BEGIN = 3000  # u8 (0)
TAG_GLOBALS_END = 4000    # u8 (0)

PARAM_TYPES = {
    0: "float",
    1: "float2",
    2: "color",
    3: "enum",
    4: "bool",
    5: "texture",
    6: "divider",
}

OBJECT_TYPES = {
    1: "Glow",
    2: "Streak",
    4: "Multi Iris",
    5: "Shimmer",
    6: "Ring",
    7: "Hoop",
    8: "Glint",
    9: "Sparkle",
    11: "Spike Ball",
    12: "Caustic",
    14: "Lens Orbs",
    15: "Iris",
}


@dataclass
class Param:
    pid: int
    ptype: int
    raw: bytes

    @property
    def type_name(self) -> str:
        return PARAM_TYPES.get(self.ptype, "tipo%d" % self.ptype)

    @property
    def value(self):
        if self.ptype == 5:
            index = struct.unpack_from("<i", self.raw, 0)[0]
            name = self.raw[4:].split(b"\0", 1)[0].decode("latin-1")
            return {"index": index, "name": name}
        floats = struct.unpack("<8f", self.raw)
        if self.ptype == 0:
            return floats[0]
        if self.ptype == 1:
            return [floats[0], floats[1]]
        if self.ptype == 2:
            packed = struct.unpack_from("<I", self.raw, 0)[0]
            return {"r": packed & 0xFF, "g": (packed >> 8) & 0xFF, "b": (packed >> 16) & 0xFF}
        if self.ptype in (3, 4):
            return struct.unpack_from("<i", self.raw, 0)[0]
        if self.ptype == 6:
            return None
        return list(floats)


@dataclass
class FlareObject:
    otype: int
    name: str = ""
    hidden: int = 0
    solo: int = 0
    params: list = field(default_factory=list)

    @property
    def type_name(self) -> str:
        return OBJECT_TYPES.get(self.otype, "tipo%d" % self.otype)


@dataclass
class Preset:
    globals: list = field(default_factory=list)
    objects: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


class OfpError(ValueError):
    pass


def records(data: bytes):
    """Itera (tag, payload) sobre o corpo do arquivo."""
    if data[:3] != MAGIC:
        raise OfpError("assinatura invalida: %r" % data[:4])
    if data[3] != VERSION:
        raise OfpError("versao nao suportada: %d" % data[3])
    pos = 4
    end = len(data)
    while pos < end:
        if pos + 4 > end:
            raise OfpError("registro truncado em %d" % pos)
        tag, size = struct.unpack_from("<HH", data, pos)
        payload = data[pos + 4 : pos + 4 + size]
        if len(payload) != size:
            raise OfpError("payload truncado em %d (tag %d)" % (pos, tag))
        yield tag, payload
        pos += 4 + size


def parse_ofp(data: bytes) -> Preset:
    preset = Preset()
    target = None          # lista de parametros que recebe o proximo valor
    obj: FlareObject | None = None
    pid = ptype = None
    for tag, payload in records(data):
        if tag == TAG_GLOBALS_BEGIN:
            target = preset.globals
        elif tag == TAG_GLOBALS_END:
            target = None
        elif tag == TAG_OBJ_TYPE:
            obj = FlareObject(struct.unpack("<i", payload)[0])
            preset.objects.append(obj)
            target = obj.params
        elif tag == TAG_OBJ_NAME and obj is not None:
            obj.name = payload.split(b"\0", 1)[0].decode("latin-1")
        elif tag == TAG_OBJ_HIDDEN and obj is not None:
            obj.hidden = payload[0]
        elif tag == TAG_OBJ_SOLO and obj is not None:
            obj.solo = payload[0]
        elif tag == TAG_OBJ_END:
            obj = None
            target = None
        elif tag == TAG_PARAM_ID:
            pid = struct.unpack("<i", payload)[0]
        elif tag == TAG_PARAM_TYPE:
            ptype = struct.unpack("<i", payload)[0]
        elif tag == TAG_PARAM_VALUE:
            if pid is None or ptype is None:
                preset.warnings.append("valor sem id/tipo")
            elif target is None:
                preset.warnings.append("parametro %d fora de contexto" % pid)
            else:
                target.append(Param(pid, ptype, bytes(payload[:32]).ljust(32, b"\0")))
        elif tag == TAG_PARAM_END:
            pid = ptype = None
        else:
            preset.warnings.append("tag desconhecida %d (%d bytes)" % (tag, len(payload)))
    return preset


def describe(preset: Preset, verbose: bool) -> str:
    out = []
    out.append("globais: %d parametros" % len(preset.globals))
    if verbose:
        for p in preset.globals:
            out.append("  id=%-4d %-8s %s" % (p.pid, p.type_name, p.value))
    for o in preset.objects:
        flags = ("hidden " if o.hidden else "") + ("solo" if o.solo else "")
        out.append("objeto %-11s %-28r %3d params %s" % (o.type_name, o.name, len(o.params), flags))
        if verbose:
            for p in o.params:
                out.append("    id=%-4d %-8s %s" % (p.pid, p.type_name, p.value))
    for w in preset.warnings:
        out.append("aviso: " + w)
    return "\n".join(out)


def to_json(preset: Preset) -> str:
    return json.dumps(
        {
            "globals": [{"id": p.pid, "type": p.type_name, "value": p.value} for p in preset.globals],
            "objects": [
                {
                    "type": o.otype,
                    "type_name": o.type_name,
                    "name": o.name,
                    "hidden": o.hidden,
                    "solo": o.solo,
                    "params": [{"id": p.pid, "type": p.type_name, "value": p.value} for p in o.params],
                }
                for o in preset.objects
            ],
            "warnings": preset.warnings,
        },
        indent=1,
    )


def scan(folder: str) -> int:
    total = ok = 0
    types = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if not name.lower().endswith(".ofp"):
                continue
            total += 1
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as fh:
                    preset = parse_ofp(fh.read())
            except OfpError as exc:
                print("FALHA %s: %s" % (path, exc))
                continue
            ok += 1
            for o in preset.objects:
                types[o.otype] = types.get(o.otype, 0) + 1
            for w in preset.warnings:
                print("AVISO %s: %s" % (path, w))
    print("%d arquivos, %d lidos sem erro" % (total, ok))
    for t in sorted(types):
        print("  tipo %2d %-11s %5d objetos" % (t, OBJECT_TYPES.get(t, "?"), types[t]))
    return 0 if ok == total else 1


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--scan":
        return scan(argv[1])
    as_json = "--json" in argv
    verbose = "-v" in argv
    paths = [a for a in argv if not a.startswith("-")]
    for path in paths:
        with open(path, "rb") as fh:
            preset = parse_ofp(fh.read())
        if as_json:
            print(to_json(preset))
        else:
            print("== " + path)
            print(describe(preset, verbose))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
