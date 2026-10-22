// OfpPreset.cpp - ver OfpPreset.h e docs/02-formato-ofp.md.
#include "OfpPreset.h"

#include <cstdio>
#include <cstring>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace ofndk {

namespace {

enum Tag : uint16_t {
    kTagObjType = 1,
    kTagObjName = 2,
    kTagObjHidden = 3,
    kTagObjSolo = 4,
    kTagParamId = 50,
    kTagParamType = 51,
    kTagParamValue = 52,
    kTagObjEnd = 1000,
    kTagParamEnd = 2000,
    kTagGlobalsBegin = 3000,
    kTagGlobalsEnd = 4000,
};

uint16_t readU16(const uint8_t* p) { return uint16_t(p[0] | (p[1] << 8)); }
int32_t readI32(const uint8_t* p)
{
    uint32_t v = uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
    int32_t r;
    std::memcpy(&r, &v, 4);
    return r;
}

int hexValue(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

}  // namespace

float Param::f(int i) const
{
    float v;
    std::memcpy(&v, raw + 4 * i, 4);
    return v;
}

int Param::i() const { return readI32(raw); }

void Param::rgb(float out[3]) const
{
    const uint32_t v = uint32_t(readI32(raw));
    out[0] = float(v & 0xff) / 255.0f;
    out[1] = float((v >> 8) & 0xff) / 255.0f;
    out[2] = float((v >> 16) & 0xff) / 255.0f;
}

std::string Param::textureName() const
{
    const char* s = reinterpret_cast<const char*>(raw + 4);
    size_t n = 0;
    while (n < 28 && s[n]) ++n;
    return std::string(s, n);
}

const Param* ParamList::find(int id) const
{
    for (const Param& p : params)
        if (p.id == id) return &p;
    return nullptr;
}

float ParamList::getFloat(int id, float def) const
{
    const Param* p = find(id);
    if (!p) return def;
    if (p->type == kEnum || p->type == kBool) return float(p->i());
    return p->f(0);
}

float ParamList::getFloat2(int id, int comp, float def) const
{
    const Param* p = find(id);
    return p ? p->f(comp) : def;
}

int ParamList::getInt(int id, int def) const
{
    const Param* p = find(id);
    if (!p) return def;
    if (p->type == kFloat || p->type == kFloat2) return int(p->f(0));
    return p->i();
}

bool ParamList::getBool(int id, bool def) const { return getInt(id, def ? 1 : 0) != 0; }

void ParamList::getColor(int id, float out[3], float r, float g, float b) const
{
    const Param* p = find(id);
    if (p && p->type == kColor) {
        p->rgb(out);
    } else {
        out[0] = r;
        out[1] = g;
        out[2] = b;
    }
}

bool parseOfp(const uint8_t* data, size_t size, Preset& out, std::string& error)
{
    out = Preset();
    if (size < 4 || data[0] != 'O' || data[1] != 'F' || data[2] != 'P') {
        error = "assinatura OFP ausente";
        return false;
    }
    if (data[3] != 3) {
        error = "versao de preset nao suportada";
        return false;
    }

    ParamList* target = nullptr;
    FlareObject* obj = nullptr;
    int pid = -1;
    int ptype = -1;
    bool havePid = false;
    bool haveType = false;

    size_t pos = 4;
    while (pos < size) {
        if (pos + 4 > size) {
            error = "registro truncado";
            return false;
        }
        const uint16_t tag = readU16(data + pos);
        const uint16_t len = readU16(data + pos + 2);
        const uint8_t* payload = data + pos + 4;
        if (pos + 4 + len > size) {
            error = "payload truncado";
            return false;
        }
        pos += 4 + size_t(len);

        switch (tag) {
        case kTagGlobalsBegin:
            target = &out.globals;
            break;
        case kTagGlobalsEnd:
            target = nullptr;
            break;
        case kTagObjType:
            if (len < 4) break;
            out.objects.emplace_back();
            obj = &out.objects.back();
            obj->type = readI32(payload);
            target = obj;
            break;
        case kTagObjName:
            if (obj) {
                size_t n = 0;
                while (n < len && payload[n]) ++n;
                obj->name.assign(reinterpret_cast<const char*>(payload), n);
            }
            break;
        case kTagObjHidden:
            if (obj && len >= 1) obj->hidden = payload[0] != 0;
            break;
        case kTagObjSolo:
            if (obj && len >= 1) obj->solo = payload[0] != 0;
            break;
        case kTagObjEnd:
            obj = nullptr;
            target = nullptr;
            break;
        case kTagParamId:
            if (len >= 4) {
                pid = readI32(payload);
                // o plugin original trata o id 91 como 7 (Color Source)
                if (pid == 91) pid = 7;
                havePid = true;
            }
            break;
        case kTagParamType:
            if (len >= 4) {
                ptype = readI32(payload);
                haveType = true;
            }
            break;
        case kTagParamValue:
            if (!havePid || !haveType) {
                out.warnings.push_back("valor sem id/tipo");
            } else if (!target) {
                out.warnings.push_back("parametro fora de contexto");
            } else {
                // presets gravam todos os parametros do objeto; se um id aparecer
                // duas vezes, o ultimo vence (mesma semantica de "sobrescrever")
                Param* dst = nullptr;
                for (Param& p : target->params)
                    if (p.id == pid) dst = &p;
                if (!dst || pid == 24) {  // 24 = divisor, pode repetir
                    target->params.emplace_back();
                    dst = &target->params.back();
                }
                dst->id = pid;
                dst->type = ptype;
                std::memset(dst->raw, 0, sizeof(dst->raw));
                std::memcpy(dst->raw, payload, len < 32 ? len : 32);
            }
            break;
        case kTagParamEnd:
            havePid = haveType = false;
            break;
        default:
            out.warnings.push_back("tag desconhecida " + std::to_string(tag));
            break;
        }
    }
    return true;
}

bool loadOfpFile(const std::string& path, std::vector<uint8_t>& bytes, std::string& error)
{
    bytes.clear();
#ifdef _WIN32
    // caminho em UTF-8 (Nuke e Python): abre pela API larga do Windows
    std::wstring wpath;
    if (const int len = MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, nullptr, 0); len > 0) {
        wpath.resize(size_t(len));
        MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, &wpath[0], len);
        wpath.resize(size_t(len) - 1);
    }
    FILE* fh = wpath.empty() ? nullptr : _wfopen(wpath.c_str(), L"rb");
    if (!fh) fh = std::fopen(path.c_str(), "rb");  // caminho ANSI antigo
#else
    FILE* fh = std::fopen(path.c_str(), "rb");
#endif
    if (!fh) {
        error = "nao foi possivel abrir " + path;
        return false;
    }
    uint8_t buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), fh)) > 0) bytes.insert(bytes.end(), buf, buf + n);
    std::fclose(fh);
    if (bytes.size() > (1u << 20)) {
        error = "preset maior que 1 MB";
        return false;
    }
    return true;
}

std::string encodeState(const std::vector<uint8_t>& bytes)
{
    static const char kHex[] = "0123456789abcdef";
    std::string s = std::to_string(bytes.size()) + ";";
    s.reserve(s.size() + bytes.size() * 2);
    for (uint8_t b : bytes) {
        s.push_back(kHex[b >> 4]);
        s.push_back(kHex[b & 15]);
    }
    return s;
}

bool decodeState(const std::string& text, std::vector<uint8_t>& bytes, std::string& error)
{
    bytes.clear();
    const size_t semi = text.find(';');
    if (semi == std::string::npos || semi == 0) {
        error = "estado sem ';'";
        return false;
    }
    size_t n = 0;
    for (size_t i = 0; i < semi; ++i) {
        if (text[i] < '0' || text[i] > '9') {
            error = "tamanho invalido";
            return false;
        }
        n = n * 10 + size_t(text[i] - '0');
    }
    const size_t digits = text.size() - semi - 1;
    if (digits / 2 != n) {
        error = "dados corrompidos (" + std::to_string(digits / 2) + " != " + std::to_string(n) + ")";
        return false;
    }
    bytes.resize(n);
    for (size_t i = 0; i < n; ++i) {
        const int hi = hexValue(text[semi + 1 + 2 * i]);
        const int lo = hexValue(text[semi + 2 + 2 * i]);
        if (hi < 0 || lo < 0) {
            error = "digito hex invalido";
            bytes.clear();
            return false;
        }
        bytes[i] = uint8_t(hi * 16 + lo);
    }
    return true;
}

const char* objectTypeName(int type)
{
    switch (type) {
    case kGlow: return "Glow";
    case kStreak: return "Streak";
    case kMultiIris: return "Multi Iris";
    case kShimmer: return "Shimmer";
    case kRing: return "Ring";
    case kHoop: return "Hoop";
    case kGlint: return "Glint";
    case kSparkle: return "Sparkle";
    case kSpikeBall: return "Spike Ball";
    case kCaustic: return "Caustic";
    case kLensOrbs: return "Lens Orbs";
    case kIris: return "Iris";
    default: return "?";
    }
}

}  // namespace ofndk
