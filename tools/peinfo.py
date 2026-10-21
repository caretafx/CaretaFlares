import sys, struct, re
p = sys.argv[1]
d = open(p,'rb').read()
pe = struct.unpack_from('<I', d, 0x3c)[0]
assert d[pe:pe+4] == b'PE\0\0'
mach, nsec, ts, _, _, optsz, chars = struct.unpack_from('<HHIIIHH', d, pe+4)
opt = pe+24
magic = struct.unpack_from('<H', d, opt)[0]
is64 = magic == 0x20b
linker_major, linker_minor = d[opt+2], d[opt+3]
import datetime
print("machine=%#x sections=%d timestamp=%s linker=%d.%d pe32+=%s" % (mach, nsec, datetime.datetime.utcfromtimestamp(ts), linker_major, linker_minor, is64))
osmaj, osmin = struct.unpack_from('<HH', d, opt+40)
subsys = struct.unpack_from('<H', d, opt+68)[0]
print("os ver=%d.%d subsystem=%d" % (osmaj, osmin, subsys))
ddoff = opt + (112 if is64 else 96)
dirs = [struct.unpack_from('<II', d, ddoff+8*i) for i in range(16)]
secs = []
so = opt + optsz
for i in range(nsec):
    name, vs, va, rs, ro = struct.unpack_from('<8sIIII', d, so+40*i)
    secs.append((name.rstrip(b'\0').decode(), va, vs, ro, rs))
print("sections:", [(n, hex(va), vs) for n,va,vs,ro,rs in secs])
def rva2off(rva):
    for n,va,vs,ro,rs in secs:
        if va <= rva < va+max(vs,rs): return ro + (rva-va)
    return None
def cstr(off):
    e = d.index(b'\0', off); return d[off:e].decode('latin1')
# imports
irva, isz = dirs[1]
off = rva2off(irva)
print("=== imports")
while True:
    ilt, ts_, fc, name, iat = struct.unpack_from('<IIIII', d, off)
    if name == 0: break
    dll = cstr(rva2off(name))
    funcs = []
    t = rva2off(ilt or iat)
    while True:
        v = struct.unpack_from('<Q' if is64 else '<I', d, t)[0]
        if v == 0: break
        if v >> (63 if is64 else 31): funcs.append("ord%d" % (v & 0xffff))
        else: funcs.append(cstr(rva2off(v & 0x7fffffff)+2))
        t += 8 if is64 else 4
    print(dll, len(funcs))
    if len(sys.argv) > 2 and sys.argv[2] == 'full' or dll.lower().startswith('ddimage'):
        for f in funcs: print("   ", f)
    off += 20
# exports
erva, esz = dirs[0]
if erva:
    eo = rva2off(erva)
    nn = struct.unpack_from('<I', d, eo+24)[0]; nptr = rva2off(struct.unpack_from('<I', d, eo+32)[0])
    print("=== exports", nn)
    for i in range(min(nn, 40)):
        print("   ", cstr(rva2off(struct.unpack_from('<I', d, nptr+4*i)[0])))
