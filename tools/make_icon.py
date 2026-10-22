"""Desenha o icone do no (arte propria): brilho laranja com estrela de 4 pontas.

    python tools/make_icon.py   ->  package/icons/CaretaFlares.png (e _menu 24px)
"""
import math
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def draw(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    px = img.load()
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            dx, dy = (x - c) / c, (y - c) / c
            r = math.hypot(dx, dy)
            glow = max(0.0, 1.0 - r) ** 2.2
            core = math.exp(-(r / 0.16) ** 2)
            # raios fininhos nos eixos e nas diagonais
            star = math.exp(-(abs(dx) / 0.05) ** 2) * max(0.0, 1 - abs(dy)) + \
                math.exp(-(abs(dy) / 0.05) ** 2) * max(0.0, 1 - abs(dx))
            diag = (math.exp(-(abs(dx - dy) / 0.07) ** 2) + math.exp(-(abs(dx + dy) / 0.07) ** 2)) * max(0.0, 1 - r) * 0.45
            v = glow * 0.9 + core + star * 0.9 + diag
            # laranja por fora, branco no centro
            w = min(1.0, core * 1.2 + star * 0.4)
            rr = 1.0
            gg = 0.55 + 0.45 * w
            bb = 0.15 + 0.85 * w
            a = min(1.0, v)
            px[x, y] = (int(255 * rr), int(255 * gg), int(255 * bb), int(255 * a))
    return img


def main():
    out = os.path.join(ROOT, 'package', 'icons')
    os.makedirs(out, exist_ok=True)
    draw(64).save(os.path.join(out, 'CaretaFlares.png'))
    draw(64).resize((24, 24), Image.LANCZOS).save(os.path.join(out, 'CaretaFlares_menu.png'))
    print(out)


if __name__ == '__main__':
    main()
