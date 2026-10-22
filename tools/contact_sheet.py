"""Renderiza varios presets com o oftool e monta uma folha de contatos PNG.

uso: python tools/contact_sheet.py SAIDA.png PRESET1.ofp [PRESET2.ofp ...]
     (aceita pastas: renderiza todos os .ofp dentro delas)

Variaveis: OFTOOL (caminho do oftool.exe), OF_W / OF_H (tamanho de cada quadro).
O trabalho roda um preset por vez, em prioridade baixa.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFTOOL = os.environ.get("OFTOOL", os.path.join(ROOT, "build", "Nuke15.2v9", "oftool.exe"))
W = int(os.environ.get("OF_W", "480"))
H = int(os.environ.get("OF_H", "270"))
BELOW_NORMAL = 0x00004000


def presets(args):
    for a in args:
        if os.path.isdir(a):
            for dp, _, fs in os.walk(a):
                for f in sorted(fs):
                    if f.lower().endswith(".ofp"):
                        yield os.path.join(dp, f)
        else:
            yield a


def main():
    out = sys.argv[1]
    files = list(presets(sys.argv[2:]))
    cols = int(os.environ.get("OF_COLS", "4"))
    cols = cols if len(files) > cols - 1 else max(1, len(files))
    rows = (len(files) + cols - 1) // cols
    label = 16
    sheet = Image.new("RGB", (cols * W, rows * (H + label)), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    tmp = tempfile.mkdtemp()
    for n, f in enumerate(files):
        ppm = os.path.join(tmp, "f%d.ppm" % n)
        # luz no terco superior esquerdo, centro no meio (como o teste do Nuke)
        r = subprocess.run([OFTOOL, "render", f, str(W), str(H), str(int(W * 0.3)), str(int(H * 0.6)), ppm],
                           capture_output=True, text=True, creationflags=BELOW_NORMAL)
        name = os.path.splitext(os.path.basename(f))[0]
        info = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()
        print("%-32s %s" % (name, info))
        x, y = (n % cols) * W, (n // cols) * (H + label)
        if os.path.exists(ppm):
            sheet.paste(Image.open(ppm), (x, y))
        draw.text((x + 4, y + H + 2), name, fill=(220, 220, 220))
    sheet.save(out)
    print("salvo", out)


if __name__ == "__main__":
    main()
