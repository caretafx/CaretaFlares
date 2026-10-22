// FlareRenderer.cpp - ver FlareRenderer.h e docs/03-comportamento-render.md.
//
// Convencoes internas (iguais as do original, para os presets baterem):
//  - coordenadas normalizadas "OF": X = px / largura, Y = 1 - py / altura
//    (origem no canto superior esquerdo);
//  - os elementos viram triangulos com 4 atributos por vertice, rasterizados
//    em CPU com um "shader" por pixel que SOMA no buffer RGBA;
//  - numeros aleatorios: o mesmo LCG do rand() da Microsoft, com estado proprio.
#include "FlareRenderer.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

#include "TextureCache.h"

namespace ofndk {

namespace {

const float kPi = 3.14159265358979f;
const float kTwoPi = 6.2831855f;
const float kDeg = 0.017453292f;
const float kSqrt2 = 1.4142135f;

// ------------------------------------------------------------- aleatorio
struct Rng {
    uint32_t s = 0;
    void seed(int v) { s = uint32_t(v); }
    int next()
    {
        s = s * 214013u + 2531011u;
        return int((s >> 16) & 0x7fff);
    }
    float f() { return float(next()) / 32767.0f; }
};

// ------------------------------------------------------------- HSL / HSV
void rgbToHsl(const float c[3], float& h, float& l, float& s)
{
    const float mn = std::min(std::min(c[0], c[1]), c[2]);
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

// gira a matiz (HSV) de uma cor 0..1 em graus
void rotateHue(float c[3], float degrees)
{
    const float mx = std::max(std::max(c[0], c[1]), c[2]);
    const float mn = std::min(std::min(c[0], c[1]), c[2]);
    const float d = mx - mn;
    if (d <= 0.0f) return;
    float h;
    if (mx == c[0]) h = 60.0f * std::fmod((c[1] - c[2]) / d, 6.0f);
    else if (mx == c[1]) h = 60.0f * ((c[2] - c[0]) / d + 2.0f);
    else h = 60.0f * ((c[0] - c[1]) / d + 4.0f);
    h = std::fmod(h + degrees, 360.0f);
    if (h < 0.0f) h += 360.0f;
    const float s = d / mx;
    const float v = mx;
    const float cc = v * s;
    const float x = cc * (1.0f - std::fabs(std::fmod(h / 60.0f, 2.0f) - 1.0f));
    const float m = v - cc;
    float r = 0, g = 0, b = 0;
    if (h < 60) { r = cc; g = x; }
    else if (h < 120) { r = x; g = cc; }
    else if (h < 180) { g = cc; b = x; }
    else if (h < 240) { g = x; b = cc; }
    else if (h < 300) { r = x; b = cc; }
    else { r = cc; b = x; }
    c[0] = r + m;
    c[1] = g + m;
    c[2] = b + m;
}

float wrapPi(float a)
{
    while (a > kPi) a -= kTwoPi;
    while (a < -kPi) a += kTwoPi;
    return a;
}

// ------------------------------------------------------------- contexto (R)
struct Ctx {
    int W = 0, H = 0;
    float* buf = nullptr;
    int clip[4] = {0, 0, 0, 0};
    bool allowBack = false;

    const Preset* preset = nullptr;
    float lightX = 0, lightY = 0, centerX = 0, centerY = 0;
    float aspectBase = 1;   // (altura/largura) * AspectRatio
    float scaleOffFlag = 0;  // knob ScaleOffset
    float scale = 1;         // escala global da luz
    float depth = 1;         // escala 3D (sempre 1 em 2D)
    float bright = 1;        // brilho global da luz
    float rot = 0;           // RotationOffset em radianos
    float lightColor[3] = {1, 1, 1};
    float globalColor[3] = {1, 1, 1};
    bool multiply = false;
    int seed = 0;
    int matteShape = 0;
    float matteStart = 0, matteFade = 0;
    float evolution = 0;
    float g112 = 1, g8 = 1;
    std::string texRoot;
    RenderStats* stats = nullptr;

    float flicker(const FlareObject& o) const { return o.getBool(110, false) ? evolution : 0.0f; }
};

// ------------------------------------------------------------- rasterizador
struct Vtx {
    float x = 0, y = 0;  // normalizados OF
    float a[4] = {0, 0, 0, 0};
};

int rnd(float v) { return -(int(-0.5f - 2.0f * v) >> 1); }

template <class Shade>
void drawTri(Ctx& R, const Vtx& A, const Vtx& B, const Vtx& C, Shade& shade)
{
    const double ax = double(A.x) * R.W, ay = double(A.y) * R.H;
    const double bx = double(B.x) * R.W, by = double(B.y) * R.H;
    const double cx = double(C.x) * R.W, cy = double(C.y) * R.H;
    const double cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    if (cross == 0.0) return;
    if (cross > 0.0 && !R.allowBack) return;
    const double inv = 1.0 / cross;
    double gx[4], gy[4];
    for (int k = 0; k < 4; ++k) {
        const double db = double(B.a[k]) - A.a[k];
        const double dc = double(C.a[k]) - A.a[k];
        gx[k] = (db * (cy - ay) - dc * (by - ay)) * inv;
        gy[k] = (dc * (bx - ax) - db * (cx - ax)) * inv;
    }
    const double ytop = std::min(ay, std::min(by, cy));
    const double ybot = std::max(ay, std::max(by, cy));
    const int r0 = std::max(rnd(float(ytop)), R.clip[1]);
    const int r1 = std::min(rnd(float(ybot)), R.clip[3]);
    const double ex[3][4] = {{ax, ay, bx, by}, {bx, by, cx, cy}, {cx, cy, ax, ay}};
    float attr[4];
    for (int r = r0; r < r1; ++r) {
        // rnd() cobre a linha r quando r + 0,25 cai dentro do triangulo; a largura
        // e medida nesse mesmo ponto (medir em r deixa buraco em arestas horizontais)
        const double yc = std::min(std::max(double(r) + 0.25, ytop), ybot);
        double xl = 1e30, xr = -1e30;
        for (const auto& e : ex) {
            const double y0 = e[1], y1 = e[3];
            if (y0 == y1) continue;
            if (yc < std::min(y0, y1) || yc > std::max(y0, y1)) continue;
            const double x = e[0] + (yc - y0) * (e[2] - e[0]) / (y1 - y0);
            xl = std::min(xl, x);
            xr = std::max(xr, x);
        }
        if (xl > xr) continue;
        const int c0 = std::max(rnd(float(xl)), R.clip[0]);
        const int c1 = std::min(rnd(float(xr)), R.clip[2]);
        float* row = R.buf + size_t(r) * size_t(R.W) * 4;
        for (int c = c0; c < c1; ++c) {
            const double dx = c - ax, dy = r - ay;
            for (int k = 0; k < 4; ++k) attr[k] = float(A.a[k] + gx[k] * dx + gy[k] * dy);
            shade(attr, row + size_t(c) * 4);
        }
    }
}

// mode 0 = leque, 1 = tira, 2 = lista
template <class Shade>
void drawMesh(Ctx& R, const std::vector<Vtx>& v, int mode, Shade&& shade)
{
    const int n = int(v.size());
    if (mode == 0) {
        for (int i = 1; i + 1 < n; ++i) drawTri(R, v[0], v[size_t(i)], v[size_t(i) + 1], shade);
    } else if (mode == 1) {
        for (int i = 1; i + 1 < n; ++i) {
            if (i & 1) drawTri(R, v[size_t(i) - 1], v[size_t(i)], v[size_t(i) + 1], shade);
            else drawTri(R, v[size_t(i) - 1], v[size_t(i) + 1], v[size_t(i)], shade);
        }
    } else {
        for (int i = 0; i + 2 < n; i += 3) drawTri(R, v[size_t(i)], v[size_t(i) + 1], v[size_t(i) + 2], shade);
    }
}

// ------------------------------------------------------------- estado do objeto (S)
struct Obj {
    const FlareObject* o = nullptr;
    float sx = 0, sy = 0;          // escala final
    float sx0 = 0, sy0 = 0;        // escala antes do stretch
    float stretchX = 1, stretchY = 1;
    float distX = 0, distY = 0;
    float aspect = 1;
    float bright = 0;
    float startRange = 0;
    float loops = 1, gradOffset = 0;
    float offsetScale = 1;
    float color[4] = {0, 0, 0, 0}, color2[4] = {0, 0, 0, 0};
    int colorMode = 0;  // 0 cor, 1 espectro, 2 gradiente
    bool invert = false;
    bool excludeMB = false;
    // trigger
    bool trig = false;
    int trigType = 0, trigMode = 0, falloffType = 0;
    float expansion = 0, outerFall = 0, innerFall = 0, border = 0;
    float brightOff = 0, scaleOff = 0, rotOff = 0, compOff = 0, outlineOff = 0;
    float spreadOff = 0, thickOff = 0, locX = 0, locY = 0, invStrX = 1, invStrY = 1, strOffX = 0, strOffY = 0;
    uint32_t colorShift = 0;
    bool oneWayB = false, oneWayS = false, oneWayC = false, invertTrig = false;
    float t = 0;  // valor do trigger
    // deslocamento das copias (Multi Iris / Lens Orbs)
    float offX = 0, offY = 0;
};

float pf(const FlareObject& o, int id, float def) { return o.getFloat(id, def); }
float pf2(const FlareObject& o, int id, int c, float def) { return o.getFloat2(id, c, def); }
int pi(const FlareObject& o, int id, int def) { return o.getInt(id, def); }

void colorOf(const FlareObject& o, int id, float out[4], float r, float g, float b)
{
    o.getColor(id, out, r, g, b);
    out[3] = 0.0f;
}

// Preparacao comum (doc 03 §5).
void prepare(const Ctx& R, const FlareObject& o, Obj& s)
{
    s = Obj();
    s.o = &o;
    s.offsetScale = R.g112 * R.scale * R.scaleOffFlag + (1.0f - R.scaleOffFlag);
    s.distX = pf2(o, 2, 0, 0.0f) * 0.01f;
    s.distY = pf2(o, 2, 1, 0.0f) * 0.01f;
    float sc = o.getBool(27, false) ? 1.0f : R.scale;
    sc *= o.getBool(10, false) ? 1.0f : R.depth;
    s.sx0 = R.g112 * sc;
    s.sy0 = R.g112 * sc;
    s.stretchX = pf2(o, 85, 0, 100.0f) * 0.01f;
    s.stretchY = pf2(o, 85, 1, 100.0f) * 0.01f;
    s.sx = s.stretchX * s.sx0;
    s.sy = s.stretchY * s.sy0;
    s.aspect = pf(o, 8, 1.0f) * R.aspectBase * R.g8;
    s.bright = o.getBool(26, false) ? 1.0f : R.bright;
    s.excludeMB = o.getBool(40, false);
    s.startRange = pf(o, 39, 0.0f) * 0.01f;

    const int source = pi(o, 7, 0);
    if (source == 0) {
        std::copy(R.globalColor, R.globalColor + 3, s.color);
    } else {
        colorOf(o, 4, s.color, 1, 1, 1);
        if (source == 3) colorOf(o, 102, s.color2, 1, 1, 1);
    }
    if (R.multiply)
        for (int k = 0; k < 3; ++k) {
            s.color[k] *= R.lightColor[k];
            s.color2[k] *= R.lightColor[k];
        }
    s.colorMode = std::max(0, source - 1);
    s.loops = pf(o, 92, 1.0f);
    s.gradOffset = (pf(o, 97, 0.0f) + 30.0f) / 360.0f;
    s.invert = pi(o, 98, 0) != 1;

    if (o.find(71) && o.getBool(106, false)) {
        s.trigType = pi(o, 71, 0);
        s.trigMode = pi(o, 81, 0);
        s.expansion = pf(o, 72, 0.0f) * 0.01f;
        s.border = pf(o, 77, 0.0f) * 0.01f;
        s.outerFall = pf(o, 73, 0.0f) * 0.01f;
        s.innerFall = pf(o, 80, 0.0f) * 0.01f;
        s.falloffType = pi(o, 74, 0);
        s.brightOff = pf(o, 75, 0.0f) * 0.01f;
        s.scaleOff = pf(o, 76, 0.0f) * 0.01f;
        s.rotOff = o.find(107) ? pf(o, 107, 0.0f) * kDeg : 0.0f;
        s.locX = pf2(o, 82, 0, 0.0f) * 0.01f;
        s.locY = pf2(o, 82, 1, 0.0f) * 0.01f;
        s.strOffX = pf2(o, 123, 0, 0.0f) * 0.01f;
        s.strOffY = pf2(o, 123, 1, 0.0f) * 0.01f;
        s.invStrX = 1.0f / std::max(0.001f, pf2(o, 122, 0, 100.0f) * 0.01f);
        s.invStrY = 1.0f / std::max(0.001f, pf2(o, 122, 1, 100.0f) * 0.01f);
        s.outlineOff = o.find(86) ? pf(o, 86, 0.0f) * 0.0015f * s.bright : 0.0f;
        const Param* cs = o.find(83);
        if (cs && cs->f(1) != 0.0f) s.colorShift = uint32_t(cs->i()) | 0xff000000u;
        s.spreadOff = o.find(96) ? pf(o, 96, 0.0f) : 0.0f;
        s.thickOff = o.find(121) ? pf(o, 121, 0.0f) : 0.0f;
        s.oneWayB = o.getBool(88, false);
        s.oneWayS = o.getBool(89, false);
        s.oneWayC = o.getBool(90, false);
        s.invertTrig = o.getBool(99, false);
        if (o.find(78)) s.compOff = pf(o, 78, 0.0f) * kDeg;
        const bool borderOnly = s.trigType == 0 && (s.border > 0.0f || s.innerFall > 0.0f);
        const bool noRange = s.expansion == 0.0f && s.outerFall == 0.0f && !borderOnly;
        const bool noEffect = s.brightOff == 0.0f && s.compOff == 0.0f && s.outlineOff == 0.0f &&
                              s.rotOff == 0.0f && s.scaleOff == 0.0f && s.colorShift == 0 &&
                              s.spreadOff == 0.0f && s.thickOff == 0.0f && s.strOffX == 0.0f && s.strOffY == 0.0f;
        s.trig = !(noRange || noEffect);
    }
}

// Posicao no eixo luz -> centro (6aa00).
void position(const Ctx& R, const Obj& s, float& x, float& y)
{
    const FlareObject& o = *s.o;
    const float vx = R.centerX - R.lightX;
    const float vy = R.centerY - R.lightY;
    const int mode = o.find(6) ? pi(o, 6, 0) : 0;
    bool secondary = true;
    switch (mode) {
    case 1: x = R.lightX + vx * s.distX; y = R.lightY; break;
    case 2: x = R.lightX; y = R.lightY + vy * s.distX; break;
    case 3: x = R.centerX; y = R.centerY; break;
    case 4:
        x = R.lightX + vx * s.distX * pf2(o, 23, 0, 100.0f) * 0.01f;
        y = R.lightY + vy * s.distX * pf2(o, 23, 1, 100.0f) * 0.01f;
        break;
    default:
        x = R.lightX + vx * s.distX;
        y = R.lightY + vy * s.distX;
        secondary = false;
        break;
    }
    if (secondary) {
        x += vx * s.distY;
        y += vy * s.distY;
    }
    x += pf2(o, 3, 0, 0.0f) * s.offsetScale * 0.01f;
    y += pf2(o, 3, 1, 0.0f) * s.offsetScale * 0.01f;
}

// Matte box global (a810).
float matteBox(const Ctx& R, float startOffset)
{
    if (R.matteShape == 0) return 1.0f;
    const float start = std::max(0.0f, startOffset + R.matteStart);
    const float x = 2.0f * R.lightX - 1.0f;
    const float y = 2.0f * R.lightY - 1.0f;
    float d;
    if (R.matteShape == 1) {
        const float e = start + 1.0f;
        const float cx = std::min(std::max(x, -e), e);
        const float cy = std::min(std::max(y, -e), e);
        d = std::sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
        if (R.matteFade == 0.0f) return d == 0.0f ? 1.0f : 0.0f;
        return std::min(1.0f, std::max(0.0f, 1.0f - d / R.matteFade));
    }
    if (R.matteShape == 2) {
        d = std::sqrt(x * x + y * y) - (start + kSqrt2);
        if (R.matteFade == 0.0f) return d > 0.0f ? 0.0f : 1.0f;
        return std::min(1.0f, std::max(0.0f, 1.0f - d / R.matteFade));
    }
    return 0.0f;
}

// Dynamic Triggering (77840).
void trigger(const Ctx& R, Obj& s, float px, float py)
{
    s.t = 0.0f;
    if (!s.trig) return;
    float fall = s.outerFall;
    float fx = s.trigMode ? R.lightX : px;
    float fy = s.trigMode ? R.lightY : py;
    fx -= s.locX;
    fy += s.locY;
    bool outside = false;
    float dist;
    if (s.trigType == 0) {
        const float e = s.expansion;
        const float nx = 2.0f * fx - 1.0f, ny = 2.0f * fy - 1.0f;
        const float lim = 2.0f * e + 1.0f;
        const float cx = std::min(std::max(nx, -lim), lim);
        const float cy = std::min(std::max(ny, -lim), lim);
        const float dx = (nx - cx) * s.invStrX * 0.5f;
        const float dy = (ny - cy) * s.invStrY * 0.5f;
        const float d2 = dx * dx + dy * dy;
        if (d2 == 0.0f) {
            fall = s.innerFall;
            const float ex = std::min(std::fabs((e + 1.0f) - fx), std::fabs(e + fx)) * s.invStrX;
            const float ey = std::min(std::fabs((e + 1.0f) - fy), std::fabs(e + fy)) * s.invStrY;
            dist = std::min(ex, ey) - s.border;
        } else {
            outside = true;
            dist = std::sqrt(d2) - s.border;
        }
    } else {
        const float tx = (s.trigType == 2) ? R.lightX : R.centerX;
        const float ty = (s.trigType == 2) ? R.lightY : R.centerY;
        const float dx = ((fx - tx) / R.aspectBase) * s.invStrX;
        const float dy = (fy - ty) * s.invStrY;
        dist = std::sqrt(dx * dx + dy * dy) - s.expansion;
    }
    float t;
    if (fall == 0.0f) {
        if (dist < 0.0f) t = 1.0f;
        else {
            if (!outside && !s.invertTrig) return;
            t = 0.0f;
        }
    } else {
        const float r = dist / fall;
        if (r >= 1.0f && !outside && !s.invertTrig) return;
        t = 1.0f - std::min(1.0f, std::max(0.0f, r));
        if (s.falloffType == 2) t = t * t;
        else if (s.falloffType == 1) t = std::min(1.0f, std::max(0.0f, 1.02f / (std::exp(5.0f - t * 10.0f) + 1.0f) - 0.01f));
    }
    if (s.invertTrig) t = 1.0f - t;
    const float base = s.o->getBool(26, false) ? 1.0f : R.bright;
    const float tb = (s.oneWayB && outside) ? 1.0f : t;
    const float stY = std::max(0.0f, t * s.strOffY + s.stretchY);
    const float stX = std::max(0.0f, t * s.strOffX + s.stretchX);
    s.t = t;
    s.bright = std::max(0.0f, base * s.brightOff * tb + s.bright);
    const float ts = (s.oneWayS && outside) ? 1.0f : t;
    s.sy = std::max(0.0f, ts * s.scaleOff * s.sy0 * stY + (s.sy / s.stretchY) * stY);
    s.sx = std::max(0.0f, ts * s.scaleOff * s.sx0 * stX + (s.sx / s.stretchX) * stX);
    if (s.colorShift & 0xff000000u) {
        const float tc = (s.oneWayC && outside) ? 1.0f : t;
        const float sh[3] = {float(s.colorShift & 0xff) / 255.0f, float((s.colorShift >> 8) & 0xff) / 255.0f,
                             float((s.colorShift >> 16) & 0xff) / 255.0f};
        for (int k = 0; k < 3; ++k) {
            s.color[k] = (1.0f - tc) * s.color[k] + sh[k] * tc;
            s.color2[k] = (1.0f - tc) * s.color2[k] + sh[k] * tc;
        }
    }
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

void shadeColor(const Obj& s, float u, float out[3])
{
    if (s.colorMode == 0) {
        std::copy(s.color, s.color + 3, out);
        return;
    }
    float t = u * s.loops + s.gradOffset;
    if (s.colorMode == 2) {
        float w = std::sin(2.0f * kPi * t) * 0.5f + 0.5f;
        if (s.invert) w = 1.0f - w;
        for (int k = 0; k < 3; ++k) out[k] = (1.0f - w) * s.color[k] + w * s.color2[k];
        return;
    }
    t = std::fmod(t, 1.0f);
    if (s.invert) t = 1.0f - t;
    spectrumColor(t, out);
}

inline void addColor(float* p, const float c[3], float v)
{
    p[0] += c[0] * v;
    p[1] += c[1] * v;
    p[2] += c[2] * v;
}

// atan2 com aspecto, como os "Auto Rotate" do original
float autoAngleA(const Ctx& R, int mode, float x, float y)  // atan2(dy, dx / aspect)
{
    const float tx = (mode == 1) ? R.lightX : R.centerX;
    const float ty = (mode == 1) ? R.lightY : R.centerY;
    const float dx = x - tx, dy = y - ty;
    if (dx == 0.0f && dy == 0.0f) return 0.0f;
    return std::atan2(dy, dx / R.aspectBase);
}

float autoAngleB(const Ctx& R, int mode, float x, float y)  // atan2(dx, dy * aspect) + pi
{
    const float tx = (mode == 1 || mode == 2) && mode != 3 ? (mode == 1 ? R.lightX : R.lightX) : R.centerX;
    const float ty = (mode == 1 || mode == 2) && mode != 3 ? (mode == 1 ? R.lightY : R.lightY) : R.centerY;
    const float dx = x - tx, dy = y - ty;
    if (dx == 0.0f && dy == 0.0f) return 0.0f;
    return std::atan2(dx, dy * R.aspectBase) + kPi;
}

// alvo da completion: 2 = luz, 3 = centro
float compAngle(const Ctx& R, int mode, float x, float y)
{
    const float tx = (mode == 2) ? R.lightX : R.centerX;
    const float ty = (mode == 2) ? R.lightY : R.centerY;
    const float dx = x - tx, dy = y - ty;
    if (dx == 0.0f && dy == 0.0f) return 0.0f;
    return std::atan2(dx, dy * R.aspectBase) + kPi;
}

float completionFade(float angle, float comp, float feather)
{
    const float a = std::fabs(angle);
    if (a <= comp) return 1.0f;
    return std::max(0.0f, 1.0f - ((a - comp) / (kTwoPi - comp)) / feather);
}

// ================================================================ Glow (1)
void drawGlow(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const float scale = pf(o, 1, 25.0f) * 0.002f;
    s.sx *= scale;
    s.sy *= scale;
    s.sx0 *= scale;
    s.sy0 *= scale;
    s.scaleOff *= 0.2f;
    s.bright *= pf(o, 0, 125.0f) * 0.008f;
    s.brightOff *= 0.8f;
    const float gamma = pf(o, 29, 1.0f);
    if (gamma < 0.05f) return;
    const float invGamma = 1.0f / gamma;
    const float mx = std::max(std::max(s.color[0], s.color[1]), s.color[2]);
    if (!(mx > 0.0f)) return;
    s.bright *= mx;
    for (int k = 0; k < 3; ++k) s.color[k] /= mx;
    s.loops *= 0.2f;
    const float baseRot = pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot;
    const int autoRot = pi(o, 41, 0);

    if (!((s.sx > 0 && s.sy > 0 && s.bright > 0) || s.trig)) return;
    float px, py;
    position(R, s, px, py);
    trigger(R, s, px, py);
    float b = s.bright;
    if (!s.excludeMB) b *= matteBox(R, s.startRange);
    if (!(b > 0.0f)) return;
    float sx = s.sx, sy = s.sy;
    if (b <= 1.0f) {
        const float k = b * b * 0.7f + b * 0.3f;
        sx *= k;
        sy *= k;
        b = 1.0f;
    } else {
        b = b * (b * 0.5f + 0.5f);
    }
    float rot = s.t * s.rotOff + baseRot;
    if (autoRot != 0) rot -= autoAngleB(R, autoRot, px, py);
    const float reach = 2.0f * (b / std::pow(0.005f, gamma) - 0.5f);
    if (!(reach > 0.0f) || !(sx > 0.0f) || !(sy > 0.0f)) return;
    const float c = std::cos(-rot), sn = std::sin(-rot);
    const float hx = sx * reach, hy = sy * reach;
    const float ex = (std::fabs(std::sin(rot) * hy) + std::fabs(std::cos(rot) * hx)) * s.aspect;
    const float ey = std::fabs(std::cos(rot) * hy) + std::fabs(std::sin(rot) * hx);
    const int x0 = std::max(R.clip[0], int((px - ex) * R.W));
    const int x1 = std::min(R.clip[2], int((px + ex) * R.W) + 1);
    const int y0 = std::max(R.clip[1], int((py - ey) * R.H));
    const int y1 = std::min(R.clip[3], int((py + ey) * R.H) + 1);
    const float invSx = 0.5f / sx, invSy = 0.5f / sy, invAspect = 1.0f / s.aspect;
    float col[3];
    for (int j = y0; j < y1; ++j) {
        const float dy = float(j) / float(R.H) - py;
        float* row = R.buf + size_t(j) * size_t(R.W) * 4;
        for (int i = x0; i < x1; ++i) {
            const float dxa = (float(i) / float(R.W) - px) * invAspect;
            const float u = (c * dxa - sn * dy) * invSx;
            const float v = (c * dy + sn * dxa) * invSy;
            const float d = std::sqrt(u * u + v * v + 1e-10f);
            const float val = std::pow(b / (d + 0.5f), invGamma) - 0.005f;
            if (val <= 0.0f) continue;
            shadeColor(s, d, col);
            addColor(row + size_t(i) * 4, col, val);
        }
    }
}

// ================================================================ Streak (2)
void drawStreak(Ctx& R, const FlareObject& o)
{
    Obj s0;
    prepare(R, o, s0);
    s0.bright *= pf(o, 0, 100.0f) * 0.01f;
    s0.loops *= 2.5f;
    const float k1 = pf(o, 1, 100.0f) * 0.01f;
    const float baseSx = s0.sx * k1, baseSy = s0.sy * k1;
    const float length = pf(o, 69, 40.0f), thick = pf(o, 67, 110.0f);
    const float sym = pf(o, 30, 100.0f) * 0.009f + 0.1f;
    const float fanEnds = pf(o, 31, -100.0f) * 0.01f + 1.0f;
    const float core = 0.9f / (pf(o, 68, 200.0f) * 0.01f);
    const float fanFeather = pf(o, 70, 50.0f) * 0.01f;
    const int autoRot = pi(o, 41, 0);
    const float rotBase = pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot;
    const int copies = std::max(0, int(pf(o, 32, 1.0f)));
    const float angle = pf(o, 33, 180.0f);
    const float scaleRand = pf(o, 34, 0.0f);
    const float spacing = pf(o, 65, 0.0f) * 0.01f;
    const float bright0 = s0.bright;
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed);

    for (int i = 0; i < copies; ++i) {
        Obj s = s0;
        const float cr = ((rng.f() - 0.5f) * spacing + float(i)) * ((angle * kDeg) / float(copies)) + rotBase;
        const float k = 1.0f - rng.f() * scaleRand * 0.01f;
        if (!(k > 0.0f)) continue;
        s.sx = k * baseSx * 12.0f * length * 0.01f;
        s.sy = k * baseSy * 0.08f * thick * 0.01f;
        s.sx0 = s.sx / std::max(1e-6f, s.stretchX);
        s.sy0 = s.sy / std::max(1e-6f, s.stretchY);
        s.bright = bright0;
        if (!(s.bright > 0.0f || s.trig)) continue;
        float px, py;
        position(R, s, px, py);
        trigger(R, s, px, py);
        float rot = s.t * s.rotOff + cr;
        if (autoRot != 0) rot -= autoAngleB(R, autoRot, px, py);
        float b = s.bright;
        if (!s.excludeMB) b *= matteBox(R, s.startRange);
        if (!(b > 0.0f)) continue;
        const float L1 = std::min(1.0f, sym * 10.0f) * fanEnds;
        const float L[14] = {1, 1, sym, L1, sym, L1, 1, 1, 1, fanEnds, 1, fanEnds, 1, 1};
        const float A[7] = {0.0f, 0.7853982f, 2.3561945f, kPi, 3.926991f, 5.497787f, 0.0f};
        const float cR = std::cos(rot), sR = std::sin(rot);
        std::vector<Vtx> v(8);
        v[0].x = px;
        v[0].y = py;
        v[0].a[0] = 0.0001f;
        v[0].a[1] = 0.0001f;
        for (int j = 0; j < 7; ++j) {
            const float sa = std::sin(A[j]), ca = std::cos(A[j]);
            const float Lx = L[2 * j], Ly = L[2 * j + 1];
            Vtx& w = v[size_t(j) + 1];
            w.a[0] = sa * 1.42f;
            w.a[1] = ((fanFeather * Ly + 1.0f) - fanFeather) * ca * 1.15f;
            w.a[2] = std::fabs(sa) * Lx;
            const float x = sa * s.sx * Lx, y = ca * s.sy * Ly * 1.15f;
            const float yr = x * sR + y * cR, xr = x * cR - y * sR;
            w.x = xr * s.aspect + px;
            w.y = yr + py;
        }
        const float fan = std::max(0.0f, (fanEnds - 1.0f) * 0.1f) * fanFeather;
        float col[3];
        drawMesh(R, v, 0, [&](const float* a, float* p) {
            float g = ((1.42f - std::fabs(a[0])) / 1.42f) * fan + (1.0f - fan);
            g = g * g * g * g * g;
            const float d = std::sqrt((a[1] * a[1] * g * g + a[0] * a[0]) * 100.0f);
            float val = 1.0f / (d + core) - 0.09f;
            if (!(val > 0.0f)) return;
            shadeColor(s, a[2], col);
            val *= b;
            if (val < 0.06f) {
                const float q = (val - 0.06f) / 0.06f;
                val *= std::max(0.0f, 0.99f - q * q);
            }
            addColor(p, col, val);
        });
    }
}

// ================================================================ Iris e familia
struct IrisParams {
    float outlineThick = 0, outlineFeather = 1, outlineInt = 0;
    float convex = 0, orient = 0, smooth = 0.01f;
    float rot = 0, comp = 4.0f, compFeather = 1, compRot = 0;
    int autoRot = 0, autoRotComp = 0;
    // poligono
    int sides = 6;
    float roundness = 0, notch = 0, distort = 0;
    // anel
    float ringInside = 0.01f, ringThick = 0;
    bool isRing = false;
    // textura
    const Texture* tex = nullptr;
};

// Circulo e anel (66620).
void drawCircle(Ctx& R, Obj& s, IrisParams& ip)
{
    const bool outlineOn = ip.outlineThick > 0.0f && ip.outlineInt != 0.0f;
    if ((s.sx <= 0 || s.sy <= 0 || (s.bright <= 0 && !outlineOn)) && !s.trig) return;
    float px, py;
    position(R, s, px, py);
    px += s.offX;
    py += s.offY;
    trigger(R, s, px, py);
    if (ip.isRing) {
        if (!s.excludeMB) s.bright *= matteBox(R, s.startRange);
        const float th = std::min(1.0f, s.t * s.thickOff * 0.01f + ip.ringThick);
        if (th <= 0.0f) return;
        ip.ringThick = th;
        ip.ringInside = th * ip.ringInside + 0.01f;
        ip.smooth = th * ip.smooth + 0.01f;
    }
    const float comp = s.t * s.compOff + ip.comp;
    const float outlineInt = s.t * s.outlineOff + ip.outlineInt;
    const bool outline = ip.outlineThick > 0.0f && outlineInt != 0.0f;
    float rot = s.t * s.rotOff + ip.rot;
    if (ip.autoRot != 0) rot -= autoAngleA(R, ip.autoRot, px, py);
    float compOffset = rot + ip.compRot;
    if (ip.autoRotComp == 1) compOffset -= ip.rot;
    else if (ip.autoRotComp >= 2) compOffset -= compAngle(R, ip.autoRotComp, px, py);
    const float c = std::cos(-rot), sn = std::sin(-rot);
    float sxe = s.sx, sye = s.sy;
    if (ip.convex > 0.0f) {
        sxe *= 1.0f - std::fabs(px - 0.5f) * 0.5f * ip.convex;
        sye *= 1.0f - std::fabs(py - 0.5f) * 0.5f * ip.convex;
    }
    const float shear = (0.5f - px) * ip.convex * (py - 0.5f);
    std::vector<Vtx> v(4);
    for (int i = 0; i < 4; ++i) {
        const float a = float(i) * 1.5707964f + 0.7853982f;
        const float X = std::sin(a) * kSqrt2 * sxe;
        const float Y = std::cos(a) * kSqrt2 * sye;
        const float yr = Y * c + X * sn, xr = X * c - Y * sn;
        v[size_t(i)].y = yr + py;
        v[size_t(i)].x = xr * s.aspect + yr * shear + px;
        v[size_t(i)].a[0] = 2.0f * (0.5f - float(i >> 1));
        v[size_t(i)].a[1] = 2.0f * (0.5f - float(((i + 1) >> 1) & 1));
    }
    const bool compOn = comp < kPi;
    float col[3];
    drawMesh(R, v, 0, [&](const float* a, float* p) {
        const float r = std::sqrt(a[0] * a[0] + a[1] * a[1]);
        const float f1 = 1.0f - r;
        float q = f1 / ip.smooth;
        if (!(q > 0.0f)) return;
        q = std::min(1.0f, q);
        float g = r;
        float b = q * s.bright;
        if (ip.ringThick <= 0.0f) {
            if (outline) {
                const float o1 = 1.0f - f1 / ip.outlineThick;
                if (o1 >= 0.0f) b += std::min(1.0f, o1 / ip.outlineFeather) * q * outlineInt;
            }
        } else {
            const float rt = std::min(1.0f, std::max(0.0f, ((r - 1.0f) + ip.ringThick) / ip.ringInside));
            g = 1.0f - (1.0f / ip.ringThick) * f1;
            b *= rt;
        }
        if (compOn) b *= completionFade(wrapPi(std::atan2(a[0], a[1]) + compOffset), comp, ip.compFeather);
        if (!(b > 0.0f)) return;
        shadeColor(s, g, col);
        addColor(p, col, b);
    });
}

// Iris poligonal (6baf0).
void drawPolygon(Ctx& R, Obj& s, const IrisParams& ip)
{
    const bool outlineOn0 = ip.outlineThick > 0.0f && ip.outlineInt != 0.0f;
    if (((s.bright <= 0 && !outlineOn0) || s.sx <= 0 || s.sy <= 0) && !s.trig) return;
    float px, py;
    position(R, s, px, py);
    px += s.offX;
    py += s.offY;
    trigger(R, s, px, py);
    const float comp = s.t * s.compOff + ip.comp;
    const float outlineInt = s.t * s.outlineOff + ip.outlineInt;
    const bool outline = ip.outlineThick > 0.0f && outlineInt != 0.0f;
    float rot = s.t * s.rotOff + ip.rot;
    if (ip.autoRot != 0) rot -= autoAngleA(R, ip.autoRot, px, py);
    float compOffset = ip.compRot;
    if (ip.autoRotComp == 1) compOffset -= ip.rot;
    else if (ip.autoRotComp >= 2) compOffset -= compAngle(R, ip.autoRotComp, px, py);

    const int N = std::max(3, ip.sides);
    int M = N;
    const bool shaped = ip.roundness != 0.0f || ip.notch != 0.0f;
    if (shaped) {
        const int k = ip.notch != 0.0f ? 11 : 10;
        M = N + (k - N / 2) * N;
    }
    const float c = std::cos(-rot), sn = std::sin(-rot);
    float sxe = s.sx, sye = s.sy;
    if (ip.convex > 0.0f) {
        sxe *= 1.0f - std::fabs(px - 0.5f) * 0.5f * ip.convex;
        sye *= 1.0f - std::fabs(py - 0.5f) * 0.5f * ip.convex;
    }
    const float shear = (0.5f - px) * ip.convex * (py - 0.5f);
    std::vector<Vtx> v(size_t(M) + 2);
    v[0].x = px;
    v[0].y = py;
    v[0].a[2] = 1.0f;
    const float side = kTwoPi / float(N);
    for (int j = 1; j < M + 2; ++j) {
        const float base = ip.orient;
        float th = (float(j - 1) * kTwoPi) / float(M) + base;
        float x, y;
        if (!shaped) {
            x = std::sin(th) * sxe;
            y = std::cos(th) * sye;
        } else {
            const int si = int((unsigned(j - 1) * unsigned(N)) / unsigned(M));
            const float t0 = float(si) * side + base;
            const float t1 = float(si + 1) * side + base;
            if (int((unsigned(N) * unsigned(j)) / unsigned(M)) != si && ip.notch != 0.0f)
                th = t1 - std::fabs(ip.notch * 0.05f);
            const float f = (th - t0) / side;
            const float bump = f * ip.notch * 0.1f + 1.0f;
            float sm = (std::sin(t0) * (1.0f - f) + std::sin(t1) * f) * (1.0f - ip.roundness) + std::sin(th) * ip.roundness;
            sm = sm * (sm * sm * ip.distort + (1.0f - ip.distort));
            const float fac = sm >= 0.0f ? ip.distort + 1.0f : 1.0f - ip.distort * 0.5f;
            x = fac * sm * sxe * bump;
            y = sye * bump * ((std::cos(t0) * (1.0f - f) + std::cos(t1) * f) * (1.0f - ip.roundness) + std::cos(th) * ip.roundness);
        }
        Vtx& w = v[size_t(j)];
        const float ang = std::atan2(x, y) + rot + compOffset;
        w.a[0] = std::sin(ang);
        w.a[1] = std::cos(ang);
        w.a[2] = 0.0f;
        const float xr = c * x - sn * y, yr = sn * x + c * y;
        w.y = yr + py;
        w.x = yr * shear + xr * s.aspect + px;
    }
    const bool compOn = comp < kPi;
    R.allowBack = (N == 3 && ip.roundness <= -0.7f);
    float col[3];
    drawMesh(R, v, 0, [&](const float* a, float* p) {
        const float f = std::min(1.0f, a[2] / ip.smooth);
        float b = f * s.bright;
        if (outline) {
            const float o1 = 1.0f - a[2] / ip.outlineThick;
            if (o1 >= 0.0f) b += std::min(1.0f, o1 / ip.outlineFeather) * f * outlineInt;
        }
        if (compOn) b *= completionFade(std::atan2(a[0], a[1]), comp, ip.compFeather);
        if (!(b > 0.0f)) return;
        shadeColor(s, 1.0f - a[2], col);
        addColor(p, col, b);
    });
    R.allowBack = false;
}

// Iris com textura (67800).
void drawTextured(Ctx& R, Obj& s, const IrisParams& ip)
{
    if (!ip.tex) return;
    if ((s.bright <= 0 || s.sx <= 0 || s.sy <= 0) && !s.trig) return;
    float px, py;
    position(R, s, px, py);
    px += s.offX;
    py += s.offY;
    trigger(R, s, px, py);
    float rot = s.t * s.rotOff + ip.rot;
    if (ip.autoRot != 0) rot -= autoAngleA(R, ip.autoRot, px, py);
    const float comp = s.t * s.compOff + ip.comp;
    float compOffset = rot + ip.compRot;
    if (ip.autoRotComp == 1) compOffset -= ip.rot;
    else if (ip.autoRotComp >= 2) compOffset -= compAngle(R, ip.autoRotComp, px, py);
    const float ratio = float(ip.tex->width()) / float(std::max(1, ip.tex->height()));
    float kx = 1.0f, ky = 1.0f;
    if (ratio < 1.0f) kx = ratio;
    else if (ratio > 1.0f) ky = 1.0f / ratio;
    float sxe = s.sx, sye = s.sy;
    if (ip.convex > 0.0f) {
        sxe *= 1.0f - std::fabs(px - 0.5f) * 0.5f * ip.convex;
        sye *= 1.0f - std::fabs(py - 0.5f) * 0.5f * ip.convex;
    }
    const float shear = (0.5f - px) * ip.convex * (py - 0.5f);
    const float cO = std::cos(ip.orient), sO = std::sin(ip.orient);
    const float c = std::cos(-rot), sn = std::sin(-rot);
    std::vector<Vtx> v(4);
    for (int i = 0; i < 4; ++i) {
        const float a = float(i) * 1.5707964f + 0.7853982f;
        const float X0 = std::sin(a) * kSqrt2 * kx;
        const float Y0 = std::cos(a) * kSqrt2;
        const float X = (cO * X0 - sO * Y0 * ky) * sxe;
        const float Y = (cO * Y0 * ky + sO * X0) * sye;
        const float yr = X * sn + Y * c, xr = X * c - Y * sn;
        v[size_t(i)].y = yr + py;
        v[size_t(i)].x = xr * s.aspect + yr * shear + px;
        v[size_t(i)].a[0] = 1.0f - float(i >> 1);
        v[size_t(i)].a[1] = 1.0f - float(((i + 1) >> 1) & 1);
    }
    // quantos texels por pixel (para escolher o mip)
    const float quadW = float(R.W) * sxe * 2.828427f, quadH = float(R.H) * sye * 2.828427f;
    const float footprint = std::max(float(ip.tex->width()) / std::max(1.0f, quadW),
                                     float(ip.tex->height()) / std::max(1.0f, quadH));
    const bool compOn = comp < kPi;
    float col[3], tx[4];
    drawMesh(R, v, 0, [&](const float* a, float* p) {
        ip.tex->sample(a[0], a[1], footprint, tx);
        float k = tx[3] * s.bright / 65025.0f;
        if (compOn) {
            const float ang = wrapPi(std::atan2((a[0] - 0.5f) * sxe, (a[1] - 0.5f) * sye) + compOffset);
            k *= completionFade(ang, comp, ip.compFeather);
        }
        if (!(k > 0.0f)) return;
        const float u = (a[0] - 0.5f) * 2.0f, w = (a[1] - 0.5f) * 2.0f;
        shadeColor(s, std::sqrt(u * u + w * w), col);
        p[0] += col[0] * tx[0] * k;
        p[1] += col[1] * tx[1] * k;
        p[2] += col[2] * tx[2] * k;
    });
}

void drawIrisShape(Ctx& R, Obj& s, IrisParams& ip, int shape)
{
    if (shape == 1) {
        IrisParams copy = ip;
        drawCircle(R, s, copy);
    } else if (shape == 2) drawTextured(R, s, ip);
    else drawPolygon(R, s, ip);
}

// Iris (15), Multi Iris (4) e Lens Orbs (14): 613f0.
void drawIrisFamily(Ctx& R, const FlareObject& o)
{
    const int type = o.type;
    const int shape = pi(o, 11, 0);
    Obj s;
    prepare(R, o, s);
    IrisParams ip;
    if (shape == 0) {
        ip.sides = int(pf(o, 12, 6.0f));
        ip.roundness = pf(o, 42, 20.0f) * 0.01f;
        ip.notch = pf(o, 43, 0.0f) * 0.01f;
    } else if (shape == 2) {
        const Param* tp = o.find(19);
        const std::string name = tp ? tp->textureName() : std::string();
        ip.tex = name.empty() ? nullptr : findTexture(R.texRoot + "/Elements", name, tp ? tp->i() : -1);
        if (!ip.tex) {
            if (R.stats && !name.empty()) ++R.stats->texturesMissing;
            return;
        }
    }
    const float compSmooth = pf(o, 17, 0.0f) * 0.01f;
    const float k1 = pf(o, 1, 100.0f) * 0.002f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    s.scaleOff *= 0.2f;
    ip.convex = o.find(93) ? pf(o, 93, 0.0f) * 0.01f : 0.0f;
    ip.orient = o.find(87) ? pf(o, 87, 0.0f) * kDeg : 0.0f;
    ip.outlineThick = pf(o, 44, 10.0f) * 0.01f;
    ip.outlineInt = pf(o, 46, 0.0f) * 0.0015f * s.bright;
    const float outlineFeather = pf(o, 45, 25.0f) * 0.01f;
    s.bright = pf(o, 0, 100.0f) * 0.0015f * s.bright;
    s.brightOff *= 0.15f;
    ip.autoRot = pi(o, 41, 0);
    ip.autoRotComp = pi(o, 59, 0);
    ip.comp = pf(o, 49, 360.0f) * kDeg * 0.515f - 0.065f;
    ip.compFeather = pf(o, 50, 0.0f) * 0.0099f + 0.01f;
    ip.compRot = pf(o, 60, 0.0f) * kDeg;
    if (!s.excludeMB) {
        const float m = matteBox(R, s.startRange);
        s.bright *= m;
        ip.outlineInt *= m;
        s.brightOff *= m;
    }
    ip.rot = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);

    if (type == kIris) {
        const float mx = std::max(s.sx, s.sy);
        ip.outlineFeather = std::min(1.0f, 0.0025f / mx + outlineFeather);
        ip.smooth = std::min(1.0f, 0.0025f / mx + compSmooth);
        drawIrisShape(R, s, ip, shape);
        return;
    }

    const bool orbs = type == kLensOrbs;
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed + 1);
    const float vx = (R.centerX - R.lightX), vy = (R.centerY - R.lightY);
    const float axisLen = std::sqrt(vx * vx + vy * vy);
    const float sx0 = s.sx, sy0 = s.sy, dist0 = s.distX, bright0 = s.bright, rot0 = ip.rot, compRot0 = ip.compRot;
    const float outline0 = ip.outlineInt, brightOff0 = s.brightOff;
    const int count = std::max(0, int(pf(o, 14, 25.0f)));
    const float spread = orbs ? 0.0f : pf(o, 13, 100.0f) * 0.01f;
    const float colorRand = pf(o, 35, 25.0f) * 0.01f;
    const float offRand = orbs ? 1.0f : pf(o, 48, 0.0f) * 0.01f;
    const float rotRand = pf(o, 47, 0.0f) * 0.01f;
    const float scaleRand = pf(o, 15, 82.5f) * 0.01f;
    const float smoothRand = pf(o, 25, 50.0f) * 0.01f;
    const float brightRand = pf(o, 16, 25.0f) * 0.01f;
    const float spreadRand = orbs ? 0.0f : pf(o, 61, 20.0f) * 0.02f;
    const float compRotRand = pf(o, 62, 0.0f) * 0.01f;
    const float offScale = orbs ? 1.0f : s.offsetScale;
    float illum = orbs ? pf(o, 63, 50.0f) * R.depth * 0.01f : 0.0f;
    const float orientRand = o.find(113) ? pf(o, 113, 0.0f) * 0.02f * kPi : 0.0f;
    const float orient0 = ip.orient;
    if (orbs && illum == 0.0f) return;
    if (illum != 0.0f) illum = 1.0f / illum;
    const float baseColor[3] = {s.color[0], s.color[1], s.color[2]};
    const float ox = offScale * pf2(o, 3, 0, 0.0f) * 0.01f;
    const float oy = offScale * pf2(o, 3, 1, 0.0f) * 0.01f;

    for (int i = 0; i < count; ++i) {
        Obj c = s;
        IrisParams q = ip;
        q.orient = (rng.f() - 0.5f) * orientRand + orient0;
        c.distX = dist0 + (1.0f - spread) + 2.0f * (rng.f() * spread);
        c.distX = ((rng.f() - 0.5f) * axisLen * spreadRand + c.distX) * 1.0f;
        c.offX = (rng.f() - 0.5f) * offRand * offScale;
        c.offY = (rng.f() - 0.5f) * offRand * offScale;
        const float k = 1.0f - rng.f() * scaleRand;
        c.sx = sx0 * k;
        c.sy = sy0 * k;
        c.sx0 = c.sx / std::max(1e-6f, c.stretchX);
        c.sy0 = c.sy / std::max(1e-6f, c.stretchY);
        std::copy(baseColor, baseColor + 3, c.color);
        rotateHue(c.color, -(rng.f() - 0.5f) * colorRand * 360.0f);
        const float mn = std::min(c.sx, c.sy), mx = std::max(c.sx, c.sy);
        q.smooth = std::min(1.0f, 0.0025f / std::max(1e-6f, mn) + (1.0f - rng.f() * smoothRand) * compSmooth);
        q.outlineFeather = std::min(1.0f, 0.0025f / std::max(1e-6f, mx) + outlineFeather);
        c.bright = (1.0f - rng.f() * brightRand) * bright0;
        if (orbs) {
            float dx = ox + c.offX;
            float dy = oy + c.offY;
            while (dx < -0.5f) dx += 1.0f;
            while (dx > 0.5f) dx -= 1.0f;
            while (dy < -0.5f) dy += 1.0f;
            while (dy > 0.5f) dy -= 1.0f;
            const float lx = (R.lightX - dx) - 0.5f, ly = (R.lightY - dy) - 0.5f;
            const float kk = std::max(0.0f, 1.0f - std::sqrt(lx * lx + ly * ly) * illum);
            c.brightOff = kk * brightOff0;
            c.bright *= kk;
            q.outlineInt = kk * outline0;
            c.offX = dx - ((ox - 0.5f) + R.centerX);
            c.offY = dy - ((oy - 0.5f) + R.centerY);
        }
        q.rot = (2.0f * rng.f() - 1.0f) * rotRand * kPi + rot0;
        q.compRot = (2.0f * rng.f() - 1.0f) * compRotRand * kPi + compRot0;
        drawIrisShape(R, c, q, shape);
    }
}

// ================================================================ Ring (6)
void drawRing(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    IrisParams ip;
    ip.isRing = true;
    ip.autoRot = pi(o, 41, 0);
    ip.rot = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);
    const float k1 = pf(o, 1, 100.0f) * 0.002f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    s.scaleOff *= 0.2f;
    s.bright *= pf(o, 0, 100.0f) * 0.001f;
    s.brightOff *= 0.1f;
    ip.ringThick = pf(o, 56, 30.0f) * 0.01f;
    ip.smooth = pf(o, 58, 25.0f) * 0.0049f;
    ip.ringInside = pf(o, 57, 25.0f) * 0.0049f;
    ip.convex = pf(o, 93, 0.0f) * 0.01f;
    ip.comp = pf(o, 49, 360.0f) * kDeg * 0.515f - 0.065f;
    ip.compFeather = pf(o, 50, 0.0f) * 0.0099f + 0.01f;
    ip.compRot = pf(o, 60, 0.0f) * kDeg;
    ip.autoRotComp = pi(o, 59, 0);
    drawCircle(R, s, ip);
}

// ================================================================ Caustic (12)
void drawCaustic(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    if (s.distX == 0.0f) s.distX = -0.001f;
    float px, py;
    position(R, s, px, py);
    float d = std::sqrt((R.centerX - px) * (R.centerX - px) + (R.centerY - py) * (R.centerY - py));
    d = std::min(1.0f, d);
    const float k1 = pf(o, 1, 100.0f) * 0.002f;
    const float bright0 = s.bright * pf(o, 0, 100.0f);
    const float matte = s.excludeMB ? 1.0f : matteBox(R, s.startRange);
    {
        Obj c = s;
        c.sx *= (1.0f - d * 0.4f) * k1;
        c.sy *= (1.0f - d * 0.1f) * k1;
        c.sx0 = c.sx / c.stretchX;
        c.sy0 = c.sy / c.stretchY;
        c.scaleOff *= 0.2f;
        const float ringB = pf(o, 118, 100.0f) * 0.05f;
        const float outl = pf(o, 119, 5.0f) * 0.01f;
        IrisParams ip;
        ip.autoRot = 1;
        ip.comp = 3.2f;
        ip.rot = 0.0f;
        ip.outlineThick = 1.0f;
        ip.outlineFeather = 1.0f;
        ip.smooth = std::max(0.0f, outl * 0.5f - 0.05f) + 0.005f / std::max(c.sx, c.sy);
        ip.outlineInt = bright0 * 0.0003f * ringB * matte;
        c.outlineOff = c.brightOff * 0.03f * ringB * matte;
        c.bright = 0.0f;
        c.brightOff = 0.0f;
        IrisParams a = ip;
        drawCircle(R, c, a);
        ip.outlineInt *= 4.0f;
        c.outlineOff *= 4.0f;
        ip.smooth = 0.005f / std::max(c.sx, c.sy) + outl;
        ip.outlineThick = outl;
        ip.outlineFeather = 1.0f;
        IrisParams b = ip;
        Obj c2 = c;
        drawCircle(R, c2, b);
    }
    {
        Obj c = s;
        c.sy *= 1.0f - d * 0.3f;
        c.sx *= pf2(o, 115, 0, 100.0f) * 0.01f * k1 * 0.6f * (d * 0.3f + 1.0f);
        c.sy *= pf2(o, 115, 1, 100.0f) * 0.01f * k1 * 0.6f;
        c.sx0 = c.sx / c.stretchX;
        c.sy0 = c.sy / c.stretchY;
        c.scaleOff *= 0.12f;
        IrisParams ip;
        ip.sides = 4;
        ip.roundness = pf(o, 116, 30.0f) * -0.01f - 0.001f;
        ip.notch = 0.0f;
        ip.orient = 1.5707964f;
        ip.autoRot = 1;
        ip.comp = 3.2f;
        ip.compFeather = 1.0f;
        ip.distort = std::min(1.0f, pf(o, 117, 100.0f) * 0.01f * d * 1.5f);
        ip.smooth = 0.5f;
        const float coreF = std::min(1.0f, std::max(0.0f, d / 0.4f - 0.1f)) * pf(o, 114, 100.0f) * 0.05f;
        c.outlineOff = c.brightOff * 0.08f * coreF * matte;
        c.brightOff = 0.0f;
        c.bright = 0.0f;
        ip.outlineInt = bright0 * 0.0008f * coreF * matte;
        ip.outlineFeather = 0.5f;
        ip.outlineThick = 1.0f;
        drawPolygon(R, c, ip);
        c.sx *= 1.3f;
        c.sy *= 1.3f;
        ip.smooth = 1.0f;
        ip.outlineFeather = 1.0f;
        ip.outlineThick = 1.0f;
        drawPolygon(R, c, ip);
    }
}

// ================================================================ raios (Shimmer 5 / Glint 8)
struct RayParams {
    int n = 0;
    std::vector<float> rays;  // angulo, comprimento
    float rot = 0, comp = 4, compFeather = 1, compRot = 0, thick = 0;
    int autoRot = 0, autoRotComp = 0;
    bool glint = false;
};

void drawRays(Ctx& R, Obj& s, const RayParams& rp)
{
    if (!(s.bright > 0.0f || s.trig)) return;
    float px, py;
    position(R, s, px, py);
    trigger(R, s, px, py);
    const float comp = s.t * s.compOff + rp.comp;
    float rot = s.t * s.rotOff + rp.rot;
    if (rp.autoRot != 0) rot += autoAngleB(R, rp.autoRot, px, py);
    float compOffset = rot + rp.compRot;
    if (rp.autoRotComp == 1) compOffset -= rot;
    else if (rp.autoRotComp >= 2) compOffset -= compAngle(R, rp.autoRotComp, px, py);
    float b = s.bright;
    if (!s.excludeMB) b *= matteBox(R, s.startRange);
    if (!(b > 0.0f)) return;
    const float c = std::cos(-rot), sn = std::sin(-rot);
    auto place = [&](Vtx& w, float x, float y) {
        const float yr = x * sn + y * c, xr = x * c - y * sn;
        w.x = xr * s.aspect + px;
        w.y = yr + py;
    };
    const bool compOn = comp < kPi;
    float col[3];
    if (!rp.glint) {
        std::vector<Vtx> v(size_t(rp.n) + 1);
        v[0].x = px;
        v[0].y = py;
        for (int j = 1; j <= rp.n; ++j) {
            const float a = rp.rays[size_t(2 * j - 2)], L = rp.rays[size_t(2 * j - 1)];
            Vtx& w = v[size_t(j)];
            w.a[0] = std::sin(a + compOffset);
            w.a[1] = std::cos(a + compOffset);
            w.a[2] = 1.0f;
            place(w, std::sin(a) * s.sx * L, std::cos(a) * s.sy * L);
        }
        drawMesh(R, v, 0, [&](const float* a, float* p) {
            float val = (0.5f / (a[2] * 0.3f + 0.05f)) * (1.0f - a[2]) * b;
            if (compOn) val *= completionFade(std::atan2(a[0], a[1]), comp, rp.compFeather);
            if (!(val > 0.0f)) return;
            shadeColor(s, a[2], col);
            addColor(p, col, val);
        });
        return;
    }
    std::vector<Vtx> v(size_t(rp.n) * 4 + 1);
    v[0].x = px;
    v[0].y = py;
    v[0].a[0] = 0.0001f;
    for (int k = 0; k < rp.n; ++k) {
        const float a = rp.rays[size_t(2 * k)], L = rp.rays[size_t(2 * k + 1)];
        const float ap = a + 1.5707964f;
        const float wx = std::sin(ap) * s.sx * 0.03f * rp.thick * L;
        const float wy = std::cos(ap) * s.sy * 0.03f * rp.thick * L;
        Vtx* q = &v[size_t(1 + 4 * k)];
        q[0].a[0] = 1;
        q[0].a[1] = 0;
        q[0].a[2] = -std::sin(ap + compOffset) * 0.03f;
        q[0].a[3] = -std::cos(ap + compOffset) * 0.03f;
        place(q[0], -wx, -wy);
        q[1].a[0] = 1;
        q[1].a[1] = 1;
        q[1].a[2] = std::sin(a + compOffset);
        q[1].a[3] = std::cos(a + compOffset);
        place(q[1], std::sin(a) * s.sx * L, std::cos(a) * s.sy * L);
        q[2].a[0] = 1;
        q[2].a[1] = 0;
        q[2].a[2] = std::sin(ap + compOffset) * 0.03f;
        q[2].a[3] = std::cos(ap + compOffset) * 0.03f;
        place(q[2], wx, wy);
        q[3].a[0] = 0;
        q[3].a[1] = 1;
        q[3].a[2] = std::sin(a + compOffset);
        q[3].a[3] = std::cos(a + compOffset);
        place(q[3], 0.0f, 0.0f);
    }
    drawMesh(R, v, 0, [&](const float* a, float* p) {
        float val = (0.5f / (a[0] * 0.3f + 0.05f)) * (1.0f - a[0]) * b;
        if (compOn) val *= completionFade(std::atan2(a[2], a[3]), comp, rp.compFeather);
        if (!(val > 0.0f)) return;
        shadeColor(s, a[1], col);
        addColor(p, col, val);
    });
}

float flickerWave(Rng& rng, float flick)
{
    const float a = rng.f();
    const float b = rng.f();
    return std::sin(b * 6.15f + (a * 0.5f + 0.5f) * flick);
}

void drawShimmer(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const int n = std::max(0, int(pf(o, 52, 65.0f)));
    if (n < 2) return;
    s.bright *= pf(o, 0, 100.0f) * 0.0002f;
    s.brightOff *= 0.02f;
    const float rot = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);
    const float detail = pf(o, 53, 100.0f);
    RayParams rp;
    rp.n = n;
    rp.comp = pf(o, 49, 360.0f) * kDeg * 0.515f - 0.065f;
    rp.compFeather = pf(o, 50, 0.0f) * 0.0099f + 0.01f;
    rp.compRot = pf(o, 60, 0.0f) * kDeg;
    rp.autoRot = pi(o, 41, 0);
    rp.autoRotComp = pi(o, 59, 0);
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed);
    rng.next();
    rng.next();
    const float k1 = pf(o, 1, 100.0f) * 0.01f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    const float orient = -pf(o, 87, 0.0f) * kDeg;
    const float step = 2.0943952f / float(n);
    const float flick = R.flicker(o);
    const float amount = pf(o, 109, 0.0f) * 0.01f;
    rp.rays.resize(size_t(2 * n));
    for (int leaf = 0; leaf < 3; ++leaf) {
        rp.rot = float(leaf) * step + rot;
        for (int j = 0; j < n; ++j) {
            const float w = flickerWave(rng, flick);
            const float v = ((w * 0.5f + 0.5f) * amount + (1.0f - amount)) * detail * 0.009f;
            rp.rays[size_t(2 * j)] = (float(j) * 2.0f * kPi) / float(n - 1) + orient;
            rp.rays[size_t(2 * j + 1)] = rng.f() * v + (1.0f - v);
        }
        rp.rays[size_t(2 * n - 2)] = rp.rays[0];
        rp.rays[size_t(2 * n - 1)] = rp.rays[1];
        Obj c = s;
        drawRays(R, c, rp);
    }
}

void drawGlint(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const int n = std::max(0, int(pf(o, 52, 100.0f)));
    if (n < 1) return;
    RayParams rp;
    rp.glint = true;
    rp.n = n;
    rp.thick = pf(o, 67, 60.0f) * 0.01f;
    const float k1 = pf(o, 1, 100.0f) * 0.003f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    s.scaleOff *= 0.3f;
    s.bright *= pf(o, 0, 100.0f) * 0.00015f;
    s.brightOff *= 0.015f;
    rp.rot = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);
    rp.comp = pf(o, 49, 360.0f) * kDeg * 0.515f - 0.065f;
    rp.compFeather = pf(o, 50, 0.0f) * 0.0099f + 0.01f;
    rp.compRot = pf(o, 60, 0.0f) * kDeg;
    rp.autoRot = pi(o, 41, 0);
    rp.autoRotComp = pi(o, 59, 0);
    const float orient = -pf(o, 87, 0.0f) * kDeg;
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed);
    rng.seed(rng.next());
    const float length = pf(o, 69, 250.0f) * 0.03f;
    const float lenRand = pf(o, 94, 50.0f) * 0.01f;
    const float spacing = pf(o, 65, 30.0f) * 0.01f;
    const float flick = R.flicker(o);
    const float amount = pf(o, 109, 0.0f) * 0.01f;
    rp.rays.resize(size_t(2 * n));
    for (int j = 0; j < n; ++j) {
        const float w = flickerWave(rng, flick);
        const float v = ((w * 0.5f + 0.5f) * amount + (1.0f - amount)) * lenRand;
        rp.rays[size_t(2 * j)] = (float(j) * 2.0f * kPi) / float(n) + orient + (rng.f() - 0.5f) * 360.0f * kDeg * spacing;
        rp.rays[size_t(2 * j + 1)] = (rng.f() * v + (1.0f - v)) * length;
    }
    drawRays(R, s, rp);
}

// ================================================================ Sparkle (9)
void drawSparkle(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const int n = std::max(0, int(pf(o, 52, 150.0f)));
    if (n < 1) return;
    s.bright *= pf(o, 0, 100.0f) * 0.002f;
    s.brightOff *= 0.2f;
    float rot0 = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);
    const float thick = pf(o, 67, 50.0f) * 0.02f;
    const float orient = -pf(o, 87, 0.0f) * kDeg;
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed);
    rng.next();
    rng.next();
    const float k1 = pf(o, 1, 100.0f) * 0.01f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    const int autoRot = pi(o, 41, 0);
    const float comp0 = pf(o, 49, 360.0f) * kDeg * 0.515f - 0.065f;
    const float compFeather = pf(o, 50, 0.0f) * 0.0099f + 0.01f;
    const float compRot = pf(o, 60, 0.0f) * kDeg;
    const int autoRotComp = pi(o, 59, 0);
    const float length = pf(o, 69, 120.0f) * 0.03f;
    const float lenRand = pf(o, 94, 80.0f) * 0.01f;
    const float spacing = pf(o, 65, 50.0f) * 0.01f;
    const float brightRand = pf(o, 16, 20.0f) * 0.01f;
    const float thickRand = pf(o, 111, 20.0f) * 0.01f;
    const float flick = R.flicker(o);
    const float amount = pf(o, 109, 0.0f) * 0.01f;
    std::vector<float> arr(size_t(4 * n)), th(static_cast<size_t>(n), 0.0f);
    for (int j = 0; j < n; ++j) {
        const float w = flickerWave(rng, flick);
        arr[size_t(4 * j)] = (float(j) * 2.0f * kPi) / float(n) + orient + (rng.f() - 0.5f) * 360.0f * kDeg * spacing;
        arr[size_t(4 * j + 1)] = (1.0f - rng.f() * lenRand * ((w * 0.25f + 0.75f) * amount + (1.0f - amount))) * length;
        const float w2 = flickerWave(rng, flick);
        arr[size_t(4 * j + 3)] = 1.0f - rng.f() * brightRand * ((w2 * 0.5f + 0.5f) * amount + (1.0f - amount));
        th[size_t(j)] = (1.0f - rng.f() * thickRand) * thick;
    }

    if (!(s.bright > 0.0f || s.trig)) return;
    float px, py;
    position(R, s, px, py);
    trigger(R, s, px, py);
    const float comp = s.compOff * s.t + comp0;
    const float spread = std::max(0.0f, s.spreadOff * s.t + pf(o, 13, 100.0f));
    const float spreadRand = pf(o, 95, 50.0f);
    for (int j = 0; j < n; ++j) arr[size_t(4 * j + 2)] = (1.0f - rng.f() * spreadRand * 0.01f) * spread * 0.003f;
    float rot = s.t * s.rotOff + rot0;
    if (autoRot != 0) rot += autoAngleB(R, autoRot, px, py);
    float compOffset = rot + compRot;
    if (autoRotComp == 1) compOffset -= rot;
    else if (autoRotComp >= 2) compOffset -= compAngle(R, autoRotComp, px, py);
    if (comp < kPi)
        for (int j = 0; j < n; ++j)
            arr[size_t(4 * j + 3)] *= completionFade(wrapPi(arr[size_t(4 * j)] + compOffset), comp, compFeather);
    float b = s.bright;
    if (!s.excludeMB) b *= matteBox(R, s.startRange);
    if (!(b > 0.0f)) return;
    const float c = std::cos(-rot), sn = std::sin(-rot);
    std::vector<Vtx> v(size_t(6 * n));
    for (int j = 0; j < n; ++j) {
        const float a = arr[size_t(4 * j)], L = arr[size_t(4 * j + 1)], sp = arr[size_t(4 * j + 2)],
                    br = arr[size_t(4 * j + 3)];
        const float sa = std::sin(a), ca = std::cos(a);
        const float f27 = sa * s.sx * 0.1f, f28 = ca * s.sy * 0.1f;
        const float Lx = L * f27, Ly = L * f28;
        const float Wx = f28 * 0.03f * th[size_t(j)], Wy = f27 * -0.03f * th[size_t(j)];
        const float sp10 = sp * 10.0f;
        const float g0 = sp10 - L * 0.5f, g1 = sp10 + L * 0.5f;
        const float offx = sa * s.sx * sp, offy = ca * s.sy * sp;
        struct P { float x, y, a0, a1, g; } pts[4] = {
            {Lx + Wx, Ly + Wy, 1.4142135f, 1.4142135f, g0},
            {Wx - Lx, Wy - Ly, -1.4142135f, 1.4142135f, g1},
            {Lx - Wx, Ly - Wy, 1.4142135f, -1.4142135f, g0},
            {-Lx - Wx, -Ly - Wy, -1.4142135f, -1.4142135f, g1},
        };
        const int order[6] = {0, 1, 2, 2, 1, 3};
        for (int k = 0; k < 6; ++k) {
            const P& p = pts[order[k]];
            Vtx& w = v[size_t(6 * j + k)];
            const float x = p.x + offx, y = p.y + offy;
            const float xr = x * c - y * sn, yr = y * c + x * sn;
            w.x = xr * s.aspect + px;
            w.y = yr + py;
            w.a[0] = p.a0;
            w.a[1] = p.a1;
            w.a[2] = p.g;
            w.a[3] = br;
        }
    }
    float col[3];
    drawMesh(R, v, 2, [&](const float* a, float* p) {
        const float r = std::sqrt(a[0] * a[0] + a[1] * a[1]);
        const float val = std::max(0.0f, 1.0f - r) * b * a[3];
        if (!(val > 0.0f)) return;
        shadeColor(s, a[2], col);
        addColor(p, col, val);
    });
}

// ================================================================ Spike Ball (11)
void drawSpikeBall(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const int n = std::max(0, int(pf(o, 52, 20.0f)));
    if (n < 1) return;
    const float k1 = pf(o, 1, 100.0f) * 0.003f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    s.scaleOff *= 0.3f;
    s.bright *= pf(o, 0, 100.0f) * 0.008f;
    s.brightOff *= 0.8f;
    const float rot0 = -(pf(o, 5, 0.0f) * kDeg + float(1 - pi(o, 22, 0)) * R.rot);
    const int autoRot = pi(o, 41, 0);
    const float orient = -pf(o, 87, 0.0f) * kDeg;
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed + 4);
    rng.next();
    rng.seed(rng.next());
    const float length = pf(o, 69, 100.0f) * 0.03f;
    const float lenRand = pf(o, 94, 50.0f) * 0.01f;
    const float thick = pf(o, 67, 110.0f) * 0.0025f;
    const float thickRand = pf(o, 111, 50.0f) * 0.01f;
    const float spacing = pf(o, 65, 15.0f) * 0.01f;
    const float brightRand = pf(o, 16, 80.0f) * 0.01f;
    const float flick = R.flicker(o);
    const float amount = pf(o, 109, 0.0f) * 0.01f;
    std::vector<float> arr(size_t(4 * n));
    for (int j = 0; j < n; ++j) {
        const float w = flickerWave(rng, flick);
        const float v = ((w * 0.5f + 0.5f) * amount + (1.0f - amount)) * lenRand;
        arr[size_t(4 * j)] = (float(j) * 2.0f * kPi) / float(n) + orient + (rng.f() - 0.5f) * 360.0f * kDeg * spacing;
        arr[size_t(4 * j + 1)] = (rng.f() * v + (1.0f - v)) * length;
        arr[size_t(4 * j + 2)] = (rng.f() * thickRand + (1.0f - thickRand)) * thick;
        const float w2 = flickerWave(rng, flick);
        arr[size_t(4 * j + 3)] = 1.0f - rng.f() * ((w2 * 0.5f + 0.5f) * amount + (1.0f - amount)) * brightRand;
    }
    if (!(s.bright > 0.0f || s.trig)) return;
    float px, py;
    position(R, s, px, py);
    trigger(R, s, px, py);
    float rot = s.t * s.rotOff + rot0;
    if (autoRot != 0) rot += autoAngleB(R, autoRot, px, py);
    float b = s.bright;
    if (!s.excludeMB) b *= matteBox(R, s.startRange);
    if (!(b > 0.0f)) return;
    const float c = std::cos(-rot), sn = std::sin(-rot);
    std::vector<Vtx> v(size_t(6 * n));
    for (int j = 0; j < n; ++j) {
        const float a = arr[size_t(4 * j)], L = arr[size_t(4 * j + 1)], t = arr[size_t(4 * j + 2)],
                    br = arr[size_t(4 * j + 3)];
        const float f22 = std::sin(a) * L, f23 = std::cos(a) * L;
        const float tipY = s.sy * f23, tipX = s.sx * f22;
        const float wx = s.sx * f23 * t, wy = -(s.sy * f22 * t);
        struct P { float x, y, a0, a1; } pts[4] = {
            {wx, wy, 0, 1}, {-wx, -wy, 0, -1}, {wx + tipX, wy + tipY, 1, 1}, {tipX - wx, tipY - wy, 1, -1}};
        const int order[6] = {0, 1, 2, 2, 1, 3};
        for (int k = 0; k < 6; ++k) {
            const P& p = pts[order[k]];
            Vtx& w = v[size_t(6 * j + k)];
            const float yr = sn * p.x + c * p.y, xr = c * p.x - sn * p.y;
            w.x = xr * s.aspect + px;
            w.y = yr + py;
            w.a[0] = p.a0;
            w.a[1] = p.a1;
            w.a[2] = br;
        }
    }
    float col[3];
    drawMesh(R, v, 2, [&](const float* a, float* p) {
        const float r1 = std::sqrt(a[0] * a[0] + a[1] * a[1] + 1e-5f);
        const float r2 = std::sqrt((a[0] * a[0] * 5.0f + a[1] * a[1]) * 5.0f + 1e-5f);
        const float wedge = std::max(0.0f, 1.0f - std::fabs(std::atan2(a[1], a[0])) * 0.77f);
        const float val = wedge * ((std::max(0.0f, 1.0f - r1) * a[2] * b) / (r2 + 0.25f));
        if (!(val > 0.0f)) return;
        shadeColor(s, a[0], col);
        addColor(p, col, val);
    });
}

// ================================================================ Hoop (7)
void drawHoop(Ctx& R, const FlareObject& o)
{
    Obj s;
    prepare(R, o, s);
    const float k1 = pf(o, 1, 100.0f) * 0.003f;
    s.sx *= k1;
    s.sy *= k1;
    s.sx0 *= k1;
    s.sy0 *= k1;
    s.scaleOff *= 0.3f;
    s.bright *= pf(o, 0, 100.0f) * 0.0075f;
    s.brightOff *= 0.75f;
    const float length = pf(o, 67, 135.0f) * 0.01f;
    const float comp = pf(o, 49, 130.0f) * kDeg * 0.515f - 0.065f;
    const float compFeather = pf(o, 50, 100.0f) * 0.0099f + 0.01f;
    const float compRot = -pf(o, 60, 0.0f) * kDeg;
    const int n = std::max(1, int(pf(o, 52, 300.0f)));
    const float radiusK = pf(o, 103, 0.0f) * 0.015f;
    if (radiusK == 0.0f) return;
    const bool band = o.getBool(104, false);
    const float lineThick = pf(o, 105, 40.0f) * 0.01f;
    const float detail = pf(o, 53, 25.0f);
    Rng rng;
    rng.seed(int(pf(o, 18, 5000.0f)) + R.seed);
    rng.next();
    rng.next();
    const float flick = R.flicker(o);
    const float amount = pf(o, 109, 0.0f) * 0.01f;
    std::vector<float> arr(size_t(2 * n + 2));
    for (float& a : arr) {
        const float w = flickerWave(rng, flick);
        a = rng.f() * ((w * 0.5f + 0.5f) * amount + (1.0f - amount)) * detail * 0.01f * 0.4f;
    }

    float px, py;
    position(R, s, px, py);
    trigger(R, s, px, py);
    float b = s.bright;
    if (!s.excludeMB) b *= matteBox(R, s.startRange);
    if (!(b > 0.0f)) return;
    const float dlx = (R.lightX - R.centerX) / R.aspectBase, dly = R.lightY - R.centerY;
    const float d = std::sqrt(dlx * dlx + dly * dly);
    const float rx = d * s.sx, ry = d * s.sy;
    const float bright = std::min(1.0f, 2.0f * d) * (b * 0.15f + 0.85f) * 0.5f * std::min(1.0f, b);
    // orientacao: o "-y" local aponta do objeto para o centro do flare
    const float psi = std::atan2((R.centerX - px) / R.aspectBase, py - R.centerY) + compRot;
    const float cP = std::cos(psi), sP = std::sin(psi);
    auto place = [&](Vtx& w, float x, float y) {
        const float xr = cP * x - sP * y, yr = sP * x + cP * y;
        w.x = xr * s.aspect + px;
        w.y = yr + py;
    };
    const bool compOn = comp < kPi;
    auto fadeAt = [&](float th) {
        if (!compOn) return 1.0f;
        const float a = std::fabs(wrapPi(th));
        if (a <= comp) return 1.0f;
        return std::max(0.0f, 1.0f - ((a - comp) / (kPi - comp)) / compFeather);
    };
    float col[3];
    if (band) {
        std::vector<Vtx> v(size_t(2 * n + 2));
        for (int k = 0; k < 2 * n + 2; k += 2) {
            const float t = (float(k) * 0.5f) / float(n);
            const float th = (2.0f * t - 1.0f) * kPi;
            const float f = fadeAt(th);
            const float bx = std::sin(th) * rx * radiusK;
            const float by = (std::cos(th) - 1.0f) * ry * radiusK;
            const float phi = std::atan2(float(R.W) * bx, float(R.H) * by);
            const float len = (1.0f - arr[size_t(k)]) * 0.5f * length;
            Vtx& w0 = v[size_t(k)];
            w0.a[0] = 0.0f;
            w0.a[1] = f;
            w0.a[2] = 0.0f;
            place(w0, bx, by);
            Vtx& w1 = v[size_t(k) + 1];
            w1.a[0] = 1.0f;
            w1.a[1] = (arr[size_t(k) + 1] * 2.0f + 0.8f) * f;
            place(w1, bx + std::sin(phi) * rx * len, by + std::cos(phi) * ry * len);
        }
        drawMesh(R, v, 1, [&](const float* a, float* p) {
            const float x = (a[0] - 0.5f) * 2.0f;
            const float val = (1.0f - x * x) * a[1] * bright;
            if (!(val > 0.0f)) return;
            shadeColor(s, a[0], col);
            addColor(p, col, val);
        });
        return;
    }
    std::vector<Vtx> v(size_t(6 * n));
    for (int i = 0; i < n; ++i) {
        const float t = float(i) / float(n);
        const float th = (2.0f * t - 1.0f) * kPi;
        const float f = fadeAt(th);
        const float bx = std::sin(th) * rx * radiusK;
        const float by = (std::cos(th) - 1.0f) * ry * radiusK;
        const float phi = std::atan2(float(R.W) * bx, float(R.H) * by);
        const float sp = std::sin(phi), cp = std::cos(phi);
        const float len = (1.0f - arr[size_t(2 * i)]) * 0.5f * length;
        const float off = 0.5f * arr[size_t(2 * i + 1)] * length;
        const float wx = lineThick * cp * 0.02f, wy = lineThick * sp * -0.02f;
        const float x0 = off * rx * sp - wx * 0.5f + bx, y0 = off * ry * cp - wy * 0.5f + by;
        const float x1 = rx * sp * len + x0, y1 = ry * cp * len + y0;
        struct P { float x, y, a0, a1, a3; } pts[4] = {
            {x0, y0, 1.4142135f, 1.4142135f, 0}, {x1, y1, -1.4142135f, 1.4142135f, 1},
            {x0 + wx, y0 + wy, 1.4142135f, -1.4142135f, 0}, {x1 + wx, y1 + wy, -1.4142135f, -1.4142135f, 1}};
        const int order[6] = {0, 1, 2, 2, 1, 3};
        for (int k = 0; k < 6; ++k) {
            const P& p = pts[order[k]];
            Vtx& w = v[size_t(6 * i + k)];
            place(w, p.x, p.y);
            w.a[0] = p.a0;
            w.a[1] = p.a1;
            w.a[2] = f;
            w.a[3] = p.a3;
        }
    }
    R.allowBack = true;
    drawMesh(R, v, 2, [&](const float* a, float* p) {
        const float r = std::sqrt(a[0] * a[0] + a[1] * a[1]);
        const float val = std::max(0.0f, (1.0f - r) * a[2]) * bright;
        if (!(val > 0.0f)) return;
        shadeColor(s, a[3], col);
        addColor(p, col, val);
    });
    R.allowBack = false;
}

// ================================================================ pos-processamento
void applyColorize(float k, const float C[3], float* lightBuf, float* out, size_t pixels)
{
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

struct LensLight {
    float x, y, bright;
};

void applyLensTexture(const Ctx& R, const std::vector<LensLight>& lights, float matte, float* buf)
{
    const Preset& P = *R.preset;
    const Param* tp = P.globals.find(19);
    if (!tp) return;
    const std::string name = tp->textureName();
    if (name.empty() || tp->i() == 0) return;
    const Texture* tex = findTexture(R.texRoot + "/Glass", name, tp->i());
    if (!tex) {
        if (R.stats) ++R.stats->texturesMissing;
        return;
    }
    const float radius = P.globals.getFloat(63, 100.0f) * R.depth * 0.01f;
    const float intensity = P.globals.getFloat(100, 50.0f) * 0.01f * matte;
    const float falloff = P.globals.getFloat(101, 0.5f);
    const float offX = P.globals.getFloat2(3, 0, 0.0f) * 0.01f - 0.5f;
    const float offY = P.globals.getFloat2(3, 1, 0.0f) * 0.01f - 0.5f;
    const float scX = P.globals.getFloat2(1, 0, 100.0f) * 0.01f;
    const float scY = P.globals.getFloat2(1, 1, 100.0f) * 0.01f;
    if (!(radius > 0.0f) || !(intensity > 0.0f) || !(scX > 0.0f) || !(scY > 0.0f)) return;
    const float invX = 1.0f / scX, invY = 1.0f / scY;
    const float expo = falloff * 3.0f + 0.2f;
    const float footprint = std::max(float(tex->width()) / (float(R.W) * scX), float(tex->height()) / (float(R.H) * scY));
    float tx[4];
    for (int j = 0; j < R.H; ++j) {
        const float fy = float(j) / float(R.H);
        const float v = (fy - 0.5f) * invY - offY;
        if (v < 0.0f || v > 1.0f) continue;
        for (int i = 0; i < R.W; ++i) {
            const float fx = float(i) / float(R.W);
            const float u = (fx - 0.5f) * invX - offX;
            if (u < 0.0f || u > 1.0f) continue;
            float sum = 0.0f;
            for (const LensLight& l : lights) {
                const float dx = l.x - fx, dy = l.y - fy;
                sum += std::max(0.0f, (1.0f - std::sqrt(dx * dx + dy * dy) / radius) * l.bright);
            }
            if (!(sum > 0.0f)) continue;
            const float k = std::pow(sum, expo) * (intensity / 255.0f);
            tex->sample(u, v, footprint, tx);
            float* p = buf + (size_t(j) * R.W + i) * 4;
            p[0] += tx[0] * k;
            p[1] += tx[1] * k;
            p[2] += tx[2] * k;
        }
    }
}

void sampleBilinear(const std::vector<float>& src, int W, int H, float x, float y, float out[3])
{
    const int x0 = int(std::floor(x)), y0 = int(std::floor(y));
    const float tx = x - float(x0), ty = y - float(y0);
    auto at = [&](int xx, int yy, int c) {
        xx = std::min(std::max(xx, 0), W - 1);
        yy = std::min(std::max(yy, 0), H - 1);
        return src[(size_t(yy) * W + xx) * 4 + c];
    };
    for (int c = 0; c < 3; ++c) {
        const float a = at(x0, y0, c) * (1 - tx) + at(x0 + 1, y0, c) * tx;
        const float b = at(x0, y0 + 1, c) * (1 - tx) + at(x0 + 1, y0 + 1, c) * tx;
        out[c] = a * (1 - ty) + b * ty;
    }
}

void applyAberration(const Ctx& R, float* buf)
{
    const Preset& P = *R.preset;
    const int type = P.globals.getInt(55, 0);
    const float intensity = P.globals.getFloat(51, 0.0f) * 0.01f;
    const float spread = P.globals.getFloat(84, 100.0f) * 0.01f;
    if (type == 0 || !(intensity > 0.0f) || !(spread > 0.0f)) return;
    const int W = R.W, H = R.H;
    std::vector<float> copy(buf, buf + size_t(W) * H * 4);
    const float k2 = intensity * 2.0f;
    const float hx = float(W) * 0.5f, hy = float(H) * 0.5f;
    const float sx = float(W) * 0.002f * spread, sy = float(H) * 0.002f * spread;
    float s[3];
    for (int j = 0; j < H; ++j) {
        const float ky = ((float(j) - hy) / hy) * sy;
        for (int i = 0; i < W; ++i) {
            const float kx = ((float(i) - hx) / hx) * sx;
            float* p = buf + (size_t(j) * W + i) * 4;
            const float* o = copy.data() + (size_t(j) * W + i) * 4;
            if (type == 2) {
                sampleBilinear(copy, W, H, float(i) - 2.0f * kx, float(j) - 2.0f * ky, s);
                p[2] = std::max(0.0f, (s[2] - o[2]) * k2 + s[2]);
                sampleBilinear(copy, W, H, float(i) - kx, float(j) - ky, s);
                p[1] = std::max(0.0f, (s[1] - o[1]) * k2 + s[1]);
            } else {
                sampleBilinear(copy, W, H, float(i) - kx, float(j) - ky, s);
                p[0] = std::max(0.0f, (s[0] - o[0]) * k2 + o[0]);
                p[2] = std::max(0.0f, (s[2] - o[2]) * k2 * 0.5f + o[2]);
            }
        }
    }
}

void applyColorCorrection(const Preset& preset, float* buf, size_t pixels)
{
    const float sat = preset.globals.getFloat(54, 0.0f) * 0.01f + 1.0f;
    const float con = preset.globals.getFloat(66, 0.0f) * 0.01f + 1.0f;
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
            const float a = 2.0f - con, e = con - 1.0f;
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
    const int W = st.width, H = st.height;
    rgba.assign(size_t(std::max(W, 0)) * size_t(std::max(H, 0)) * 4, 0.0f);
    if (W <= 0 || H <= 0 || preset.objects.empty()) return;
    const size_t pixels = size_t(W) * size_t(H);
    RenderStats local;

    Ctx R;
    R.W = W;
    R.H = H;
    R.clip[2] = W;
    R.clip[3] = H;
    R.preset = &preset;
    R.texRoot = st.textureRoot;
    R.stats = &local;
    R.aspectBase = (float(H) / float(W)) * st.aspectRatio;
    R.scaleOffFlag = st.scaleOffset ? 1.0f : 0.0f;
    R.rot = st.rotationDeg * kDeg;
    R.multiply = st.colorMode == 1;
    R.seed = int(preset.globals.getFloat(18, 5000.0f));
    R.matteShape = preset.globals.getInt(36, 0);
    R.matteStart = preset.globals.getFloat(37, 25.0f) * 0.01f;
    R.matteFade = preset.globals.getFloat(38, 25.0f) * 0.01f;
    R.evolution = st.evolution * 10.0f;
    R.g112 = preset.globals.getFloat(112, 100.0f) * 0.01f;
    R.g8 = preset.globals.getFloat(8, 1.0f);
    preset.globals.getColor(4, R.globalColor, 126.0f / 255.0f, 146.0f / 255.0f, 180.0f / 255.0f);

    bool anySolo = false;
    for (const FlareObject& o : preset.objects) anySolo = anySolo || o.solo;

    std::vector<float> lightBuf;
    std::vector<LensLight> lensLights;
    float lastMatte = 1.0f;

    for (const Light& light : lights) {
        R.lightX = light.x / float(W);
        R.lightY = 1.0f - light.y / float(H);
        R.centerX = st.centerX / float(W);
        R.centerY = 1.0f - st.centerY / float(H);
        float b = st.brightness * light.brightness;
        if (b > 1.0f) b = b * 0.7f + 0.3f;
        R.bright = (preset.globals.getFloat(0, 0.0f) * 0.01f + 1.0f) * b;
        R.scale = st.scale * light.scale;
        for (int k = 0; k < 3; ++k) R.lightColor[k] = std::min(1.0f, std::max(0.0f, light.color[k]));

        float colorize = 0.0f, colorizeColor[3] = {0, 0, 0};
        if (!R.multiply) {
            float h, l, s;
            rgbToHsl(R.lightColor, h, l, s);
            hslToRgb(h, 0.5f, std::min(1.0f, l * 2.0f) * s, colorizeColor);
            const float s1 = std::min(1.0f, s);
            float t = std::max(0.0f, l - s1 * 0.5f) / (1.0f - s1 * 0.5f);
            colorize = std::min(1.0f, 2.0f * (1.0f - std::min(1.0f, t)));
        }
        R.buf = rgba.data();
        if (colorize > 0.0f) {
            lightBuf.assign(pixels * 4, 0.0f);
            R.buf = lightBuf.data();
        }
        lensLights.push_back({R.lightX, R.lightY, R.bright});
        lastMatte = matteBox(R, 0.0f);

        for (size_t idx = 0; idx < preset.objects.size(); ++idx) {
            const FlareObject& o = preset.objects[idx];
            if (anySolo ? !o.solo : o.hidden) continue;
            if (st.soloFlareId >= 0 && int(idx) != st.soloFlareId) continue;
            bool drawn = true;
            switch (o.type) {
            case kGlow: drawGlow(R, o); break;
            case kStreak: drawStreak(R, o); break;
            case kMultiIris:
            case kLensOrbs:
            case kIris: drawIrisFamily(R, o); break;
            case kShimmer: drawShimmer(R, o); break;
            case kRing: drawRing(R, o); break;
            case kHoop: drawHoop(R, o); break;
            case kGlint: drawGlint(R, o); break;
            case kSparkle: drawSparkle(R, o); break;
            case kSpikeBall: drawSpikeBall(R, o); break;
            case kCaustic: drawCaustic(R, o); break;
            default: drawn = false; break;
            }
            if (drawn) ++local.objectsDrawn;
            else ++local.objectsSkipped;
        }
        if (colorize > 0.0f) applyColorize(colorize, colorizeColor, lightBuf.data(), rgba.data(), pixels);
    }

    // Blend Mode = Screen: curva logaritmica (0,6 * ln(2x + 1))
    if (preset.globals.getInt(9, 0) == 1)
        for (size_t n = 0; n < pixels * 4; ++n) {
            const float v = std::max(0.0f, rgba[n]);
            rgba[n] = 0.6f * std::log(2.0f * v + 1.0f);
        }
    R.buf = rgba.data();
    applyLensTexture(R, lensLights, lastMatte, rgba.data());
    applyAberration(R, rgba.data());
    applyColorCorrection(preset, rgba.data(), pixels);
    if (stats) *stats = local;
}

}  // namespace ofndk
