// FlareRenderer.cpp - ver FlareRenderer.h e docs/03-comportamento-render.md.
//
// Convencoes internas:
//  - coordenadas normalizadas "OF": X = px / largura, Y = 1 - py / altura
//    (origem no canto superior esquerdo), igual ao original;
//  - parametros dos presets em percentual ou graus, convertidos no uso.
#include "FlareRenderer.h"

#include <algorithm>
#include <cmath>

namespace ofndk {

namespace {

const float kPi = 3.14159265358979f;
const float kDeg = kPi / 180.0f;

// ids de parametros (docs/02-formato-ofp.md §5)
enum ParamId : int {
    pBrightness = 0,
    pScale = 1,
    pDistance = 2,
    pOffset = 3,
    pColor1 = 4,
    pRotation = 5,
    pTranslation = 6,
    pColorSource = 7,
    pAspect = 8,
    pIgnore3D = 10,
    pIgnoreGlobalRotation = 22,
    pCustomTranslation = 23,
    pIgnoreGlobalBrightness = 26,
    pIgnoreGlobalScale = 27,
    pGamma = 29,
    pAutoRotate = 41,
    pStretch = 85,
    pGradientLoops = 92,
    pGradientOffset = 97,
    pReverseGradient = 98,
    pColor2 = 102,
};

// ids globais
enum GlobalId : int {
    gBrightness = 0,
    gColor = 4,
    gAspect = 8,
    gSaturation = 54,
    gContrast = 66,
    gScale = 112,
};

// ---------------------------------------------------------------- cor HSL
// Conversoes HSL com matiz em graus, na mesma forma usada pelo original
// (inclui o desvio de +0,002 perto de L = 1).
void rgbToHsl(const float c[3], float& h, float& l, float& s)
{
    float mn = std::min(std::min(c[0], c[1]), c[2]);
    const float mxOrig = std::max(std::max(c[0], c[1]), c[2]);
    float mx = mxOrig;
    float sum = mn + mx;
    l = sum * 0.5f;
    if (l >= 0.999f && l <= 1.001f) {
        mx += 0.002f;
        sum = mn + mx;
        l = sum * 0.5f;
    }
    const float d = mx - mn;
    if (std::fabs(d) < 1e-5f) {
        s = 0.0f;
        h = 0.0f;
        return;
    }
    if (l > 0.5f) sum = (2.0f - mx) - mn;
    s = d / sum;
    const float rc = (mx - c[0]) / d;
    const float gc = (mx - c[1]) / d;
    const float bc = (mx - c[2]) / d;
    float hh;
    if (c[0] == mxOrig) hh = bc - gc;
    else if (c[1] == mxOrig) hh = (rc + 2.0f) - bc;
    else hh = (gc + 4.0f) - rc;
    hh *= 60.0f;
    if (hh < 0.0f) hh += 360.0f;
    h = hh;
}

float hueChannel(float m1, float m2, float hue)
{
    if (hue > 360.0f) hue -= 360.0f;
    else if (hue < 0.0f) hue += 360.0f;
    if (hue < 60.0f) return ((m2 - m1) * hue) / 60.0f + m1;
    if (hue < 180.0f) return m2;
    if (hue < 240.0f) return ((m2 - m1) * (240.0f - hue)) / 60.0f + m1;
    return m1;
}

void hslToRgb(float h, float l, float s, float out[3])
{
    if (s == 0.0f) {
        out[0] = out[1] = out[2] = l;
        return;
    }
    const float m2 = (l > 0.5f) ? (l + s) - l * s : (s + 1.0f) * l;
    const float m1 = 2.0f * l - m2;
    out[0] = hueChannel(m1, m2, h + 120.0f);
    out[1] = hueChannel(m1, m2, h);
    out[2] = hueChannel(m1, m2, h - 120.0f);
}

// ---------------------------------------------------------------- contexto
struct LightContext {
    float lightX, lightY;    // normalizados OF
    float centerX, centerY;  // normalizados OF
    float brightness;        // brilho global efetivo
    float scale;             // escala global efetiva
    float rotation;          // radianos
    float offsetScale;
    float aspectBase;        // (altura / largura) * AspectRatio
    float lightColor[3];
    float colorize;          // 0 = sem colorizacao
    float colorizeColor[3];  // cor da luz saturada (L = 0,5)
    float globalColor[3];
    float globalScale;       // id 112 * 0,01
    float globalAspect;      // id 8
    bool multiply;
};

// Estado comum de um objeto depois da preparacao (doc 03 §5).
struct ObjectState {
    float distX, distY;
    float sx, sy;  // escala (unidades de altura da imagem)
    float aspect;
    float brightness;
    float color[3];
    float color2[3];
    int colorMode;  // 0 cor fixa, 1 espectro, 2 gradiente
    float loops;
    float gradOffset;
    bool invertGradient;
    float offsetScale;
};

void prepareObject(const LightContext& L, const FlareObject& o, ObjectState& s)
{
    s.offsetScale = L.offsetScale;
    s.distX = o.getFloat2(pDistance, 0, 0.0f) * 0.01f;
    s.distY = o.getFloat2(pDistance, 1, 0.0f) * 0.01f;

    float sc = o.getBool(pIgnoreGlobalScale, false) ? 1.0f : L.scale;
    // profundidade 3D ainda nao existe: fator 1
    (void)o.getBool(pIgnore3D, false);
    s.sx = sc * L.globalScale * o.getFloat2(pStretch, 0, 100.0f) * 0.01f;
    s.sy = sc * L.globalScale * o.getFloat2(pStretch, 1, 100.0f) * 0.01f;

    s.aspect = o.getFloat(pAspect, 1.0f) * L.aspectBase * L.globalAspect;
    s.brightness = o.getBool(pIgnoreGlobalBrightness, false) ? 1.0f : L.brightness;

    const int source = o.getInt(pColorSource, 0);
    if (source == 0) {
        std::copy(L.globalColor, L.globalColor + 3, s.color);
    } else {
        o.getColor(pColor1, s.color, 1.0f, 1.0f, 1.0f);
    }
    s.color2[0] = s.color2[1] = s.color2[2] = 0.0f;
    if (source == 3) o.getColor(pColor2, s.color2, 1.0f, 1.0f, 1.0f);
    if (L.multiply) {
        for (int k = 0; k < 3; ++k) {
            s.color[k] *= L.lightColor[k];
            s.color2[k] *= L.lightColor[k];
        }
    }
    s.colorMode = std::max(0, source - 1);
    s.loops = o.getFloat(pGradientLoops, 1.0f);
    s.gradOffset = (o.getFloat(pGradientOffset, 0.0f) + 30.0f) / 360.0f;
    s.invertGradient = o.getInt(pReverseGradient, 0) != 1;
}

// Posicao do objeto no eixo luz -> centro (doc 03 §5).
void objectPosition(const LightContext& L, const FlareObject& o, const ObjectState& s, float& x, float& y)
{
    const float vx = L.centerX - L.lightX;
    const float vy = L.centerY - L.lightY;
    const int mode = o.find(pTranslation) ? o.getInt(pTranslation, 0) : 0;
    bool addSecondary = true;
    switch (mode) {
    case 1:  // Horizontal
        x = L.lightX + vx * s.distX;
        y = L.lightY;
        break;
    case 2:  // Vertical
        x = L.lightX;
        y = L.lightY + vy * s.distX;
        break;
    case 3:  // None
        x = L.centerX;
        y = L.centerY;
        break;
    case 4:  // Custom
        x = L.lightX + vx * s.distX * o.getFloat2(pCustomTranslation, 0, 100.0f) * 0.01f;
        y = L.lightY + vy * s.distX * o.getFloat2(pCustomTranslation, 1, 100.0f) * 0.01f;
        break;
    default:  // Free
        x = L.lightX + vx * s.distX;
        y = L.lightY + vy * s.distX;
        addSecondary = false;
        break;
    }
    if (addSecondary) {
        x += vx * s.distY;
        y += vy * s.distY;
    }
    x += o.getFloat2(pOffset, 0, 0.0f) * s.offsetScale * 0.01f;
    y += o.getFloat2(pOffset, 1, 0.0f) * s.offsetScale * 0.01f;
}

void spectrumColor(float t, float out[3])
{
    auto frac = [](float v) { return v - std::floor(v); };
    const float a = frac(t - 0.3f) * 2.5f - 1.0f;
    const float b = t * 2.5f - 1.0f;
    const float c = frac(t + 0.3f) * 2.5f - 1.0f;
    out[0] = std::max(0.0f, 1.0f - a * a);
    out[1] = std::max(0.0f, 1.0f - b * b);
    out[2] = std::max(0.0f, 1.0f - c * c);
}

// Cor do objeto num ponto, dado o parametro u do gradiente.
void shadeColor(const ObjectState& s, float u, float out[3])
{
    if (s.colorMode == 0) {
        std::copy(s.color, s.color + 3, out);
        return;
    }
    float t = u * s.loops + s.gradOffset;
    if (s.colorMode == 2) {
        float w = std::sin(2.0f * kPi * t) * 0.5f + 0.5f;
        if (s.invertGradient) w = 1.0f - w;
        for (int k = 0; k < 3; ++k) out[k] = (1.0f - w) * s.color[k] + w * s.color2[k];
        return;
    }
    t = std::fmod(t, 1.0f);
    if (s.invertGradient) t = 1.0f - t;
    spectrumColor(t, out);
}

float autoRotation(const LightContext& L, int mode, float x, float y)
{
    if (mode == 0) return 0.0f;
    const float tx = (mode == 1) ? L.lightX : L.centerX;
    const float ty = (mode == 1) ? L.lightY : L.centerY;
    const float dx = x - tx;
    const float dy = y - ty;
    if (dx == 0.0f && dy == 0.0f) return 0.0f;
    return std::atan2(dx, dy * L.aspectBase) + kPi;
}

// ---------------------------------------------------------------- Glow
void drawGlow(const LightContext& L, const FlareObject& o, int W, int H, float* buf)
{
    ObjectState s;
    prepareObject(L, o, s);

    const float gamma = o.getFloat(pGamma, 1.0f);
    if (gamma < 0.05f) return;
    const float invGamma = 1.0f / gamma;

    float sx = s.sx * o.getFloat(pScale, 25.0f) * 0.002f;
    float sy = s.sy * o.getFloat(pScale, 25.0f) * 0.002f;
    float b = s.brightness * o.getFloat(pBrightness, 125.0f) * 0.008f;
    s.loops *= 0.2f;

    // a cor e normalizada pelo maior componente, que vai para o brilho
    const float mx = std::max(std::max(s.color[0], s.color[1]), s.color[2]);
    if (!(mx > 0.0f)) return;
    b *= mx;
    for (float& c : s.color) c /= mx;

    float rot = o.getFloat(pRotation, 0.0f) * kDeg;
    if (!o.getBool(pIgnoreGlobalRotation, false)) rot += L.rotation;

    float px, py;
    objectPosition(L, o, s, px, py);

    if (!(sx > 0.0f && sy > 0.0f && b > 0.0f)) return;
    if (b <= 1.0f) {
        const float k = b * b * 0.7f + b * 0.3f;
        sx *= k;
        sy *= k;
        b = 1.0f;
    } else {
        b = b * (b * 0.5f + 0.5f);
    }
    rot -= autoRotation(L, o.getInt(pAutoRotate, 0), px, py);

    // alcance onde o brilho passa do limiar de 0,005
    const float reach = 2.0f * (b / std::pow(0.005f, gamma) - 0.5f);
    if (!(reach > 0.0f)) return;
    const float c = std::cos(-rot);
    const float sn = std::sin(-rot);
    const float hx = sx * reach;
    const float hy = sy * reach;
    const float ex = (std::fabs(std::sin(rot) * hy) + std::fabs(std::cos(rot) * hx)) * s.aspect;
    const float ey = std::fabs(std::cos(rot) * hy) + std::fabs(std::sin(rot) * hx);

    const int x0 = std::max(0, int(std::floor((px - ex) * W)));
    const int x1 = std::min(W, int(std::ceil((px + ex) * W)) + 1);
    const int y0 = std::max(0, int(std::floor((py - ey) * H)));
    const int y1 = std::min(H, int(std::ceil((py + ey) * H)) + 1);
    if (x0 >= x1 || y0 >= y1) return;

    const float invSx = 0.5f / sx;
    const float invSy = 0.5f / sy;
    const float invAspect = 1.0f / s.aspect;
    float col[3];
    for (int j = y0; j < y1; ++j) {
        const float dy = float(j) / float(H) - py;
        float* row = buf + size_t(j) * size_t(W) * 4;
        for (int i = x0; i < x1; ++i) {
            const float dxa = (float(i) / float(W) - px) * invAspect;
            const float u = (c * dxa - sn * dy) * invSx;
            const float v = (c * dy + sn * dxa) * invSy;
            const float d = std::sqrt(u * u + v * v + 1e-10f);
            const float val = std::pow(b / (d + 0.5f), invGamma) - 0.005f;
            if (val <= 0.0f) continue;
            shadeColor(s, d, col);
            float* p = row + size_t(i) * 4;
            p[0] += col[0] * val;
            p[1] += col[1] * val;
            p[2] += col[2] * val;
        }
    }
}

// Colorizacao da luz (modo Tint com luz colorida), doc 03 §4.
void applyColorize(const LightContext& L, float* lightBuf, float* out, size_t pixels)
{
    const float k = L.colorize;
    const float* C = L.colorizeColor;
    for (size_t n = 0; n < pixels; ++n) {
        float* p = lightBuf + n * 4;
        const float lum = (std::min(std::min(p[0], p[1]), p[2]) + std::max(std::max(p[0], p[1]), p[2])) * 0.5f;
        float t[3];
        if (lum > 0.5f) {
            const float e = lum - 0.5f;
            const float w = 1.0f - std::min(1.0f, e * 0.5f);
            for (int c = 0; c < 3; ++c) t[c] = w * C[c] + e;
        } else {
            for (int c = 0; c < 3; ++c) t[c] = C[c] * (lum * 2.0f);
        }
        for (int c = 0; c < 3; ++c) {
            out[n * 4 + c] += t[c] * k + p[c] * (1.0f - k);
            p[c] = 0.0f;
        }
        out[n * 4 + 3] += p[3];
        p[3] = 0.0f;
    }
}

// Saturacao e contraste globais (doc 03 §7, item 3).
void applyColorCorrection(const Preset& preset, float* buf, size_t pixels)
{
    const float sat = preset.globals.getFloat(gSaturation, 0.0f) * 0.01f + 1.0f;
    const float con = preset.globals.getFloat(gContrast, 0.0f) * 0.01f + 1.0f;
    if (sat == 1.0f && con == 1.0f) return;
    for (size_t n = 0; n < pixels; ++n) {
        float* p = buf + n * 4;
        float h, l, s;
        rgbToHsl(p, h, l, s);
        float c[3];
        hslToRgb(h, l, s * sat, c);
        if (con < 1.0f) {
            const float k = (1.0f - con) * 0.5f;
            for (float& v : c) v = con * v + k;
        } else if (con > 1.0f) {
            const float a = 2.0f - con;
            const float e = con - 1.0f;
            for (float& v : c) {
                float q = (0.5f / v) * (0.5f / v);
                q = q * q;
                v = (1.0f / (q * q + 1.0f)) * e + a * v;
            }
        }
        for (int k = 0; k < 3; ++k) p[k] = std::max(0.0f, c[k]);
    }
}

}  // namespace

void FlareRenderer::render(const Preset& preset, const RenderSettings& st, const std::vector<Light>& lights,
                           std::vector<float>& rgba, RenderStats* stats) const
{
    const int W = st.width;
    const int H = st.height;
    rgba.assign(size_t(std::max(W, 0)) * size_t(std::max(H, 0)) * 4, 0.0f);
    if (W <= 0 || H <= 0 || preset.objects.empty()) return;
    const size_t pixels = size_t(W) * size_t(H);

    bool anySolo = false;
    for (const FlareObject& o : preset.objects) anySolo = anySolo || o.solo;

    std::vector<float> lightBuf;
    RenderStats local;

    for (const Light& light : lights) {
        LightContext L;
        L.lightX = light.x / float(W);
        L.lightY = 1.0f - light.y / float(H);
        L.centerX = st.centerX / float(W);
        L.centerY = 1.0f - st.centerY / float(H);

        float b = st.brightness * light.brightness;
        if (b > 1.0f) b = b * 0.7f + 0.3f;
        L.brightness = (preset.globals.getFloat(gBrightness, 0.0f) * 0.01f + 1.0f) * b;
        L.scale = st.scale * light.scale;
        L.rotation = st.rotationDeg * kDeg;
        L.globalScale = preset.globals.getFloat(gScale, 100.0f) * 0.01f;
        L.globalAspect = preset.globals.getFloat(gAspect, 1.0f);
        L.offsetScale = st.scaleOffset ? L.globalScale * L.scale : 1.0f;
        L.aspectBase = (float(H) / float(W)) * st.aspectRatio;
        for (int k = 0; k < 3; ++k) L.lightColor[k] = std::min(1.0f, std::max(0.0f, light.color[k]));
        preset.globals.getColor(gColor, L.globalColor, 126.0f / 255.0f, 146.0f / 255.0f, 180.0f / 255.0f);
        L.multiply = st.colorMode == 1;

        L.colorize = 0.0f;
        if (!L.multiply) {
            float h, l, s;
            rgbToHsl(L.lightColor, h, l, s);
            hslToRgb(h, 0.5f, std::min(1.0f, l * 2.0f) * s, L.colorizeColor);
            const float s1 = std::min(1.0f, s);
            float t = std::max(0.0f, l - s1 * 0.5f) / (1.0f - s1 * 0.5f);
            t = std::min(1.0f, t);
            L.colorize = std::min(1.0f, 2.0f * (1.0f - t));
        }

        float* target = rgba.data();
        if (L.colorize > 0.0f) {
            lightBuf.assign(pixels * 4, 0.0f);
            target = lightBuf.data();
        }

        for (size_t idx = 0; idx < preset.objects.size(); ++idx) {
            const FlareObject& o = preset.objects[idx];
            if (anySolo ? !o.solo : o.hidden) continue;
            if (st.soloFlareId >= 0 && int(idx) != st.soloFlareId) continue;
            switch (o.type) {
            case kGlow:
                drawGlow(L, o, W, H, target);
                ++local.objectsDrawn;
                break;
            default:
                ++local.objectsSkipped;
                break;
            }
        }

        if (L.colorize > 0.0f) applyColorize(L, lightBuf.data(), rgba.data(), pixels);
    }

    applyColorCorrection(preset, rgba.data(), pixels);
    if (stats) *stats = local;
}

}  // namespace ofndk
