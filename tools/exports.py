import sys, struct
def exports(p):
    d = open(p,'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec, optsz = struct.unpack_from('<H', d, pe+6)[0], struct.unpack_from('<H', d, pe+20)[0]
    opt = pe+24; is64 = struct.unpack_from('<H', d, opt)[0] == 0x20b
    linker = (d[opt+2], d[opt+3])
    ddoff = opt + (112 if is64 else 96)
    erva = struct.unpack_from('<I', d, ddoff)[0]
    so = opt+optsz
    secs=[struct.unpack_from('<8sIIII', d, so+40*i) for i in range(nsec)]
    def r2o(rva):
        for n,vs,va,rs,ro in secs:
            if va<=rva<va+max(vs,rs): return ro+rva-va
    eo = r2o(erva)
    nn = struct.unpack_from('<I', d, eo+24)[0]; nptr = r2o(struct.unpack_from('<I', d, eo+32)[0])
    names=set()
    for i in range(nn):
        o = r2o(struct.unpack_from('<I', d, nptr+4*i)[0]); e = d.index(b'\0', o); names.add(d[o:e].decode('latin1'))
    return linker, names
if __name__ == "__main__":
  plugin_imports = set(l.strip() for l in open(sys.argv[1]) if l.strip())
  print("plugin imports from DDImage:", len(plugin_imports))
  for p in sys.argv[2:]:
      linker, names = exports(p)
      missing = plugin_imports - names
      print("%s: linker=%d.%d exports=%d  missing=%d" % (p, linker[0], linker[1], len(names), len(missing)))
      if missing and len(missing) < 60:
          for m in sorted(missing): print("    MISSING", m)
