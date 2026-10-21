// OfpPreset.h - leitura dos presets .ofp e do estado salvo no knob renderOptions.
// Escrito do zero a partir de docs/02-formato-ofp.md.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace ofndk {

enum ParamType : int {
    kFloat = 0,
    kFloat2 = 1,
    kColor = 2,
    kEnum = 3,
    kBool = 4,
    kTexture = 5,
    kDivider = 6,
};

enum ObjectType : int {
    kGlow = 1,
    kStreak = 2,
    kMultiIris = 4,
    kShimmer = 5,
    kRing = 6,
    kHoop = 7,
    kGlint = 8,
    kSparkle = 9,
    kSpikeBall = 11,
    kCaustic = 12,
    kLensOrbs = 14,
    kIris = 15,
};

struct Param {
    int id = 0;
    int type = 0;
    uint8_t raw[32] = {};

    float f(int i = 0) const;
    int i() const;
    // cor empacotada (R nos 8 bits baixos) convertida para 0..1
    void rgb(float out[3]) const;
    std::string textureName() const;
};

struct ParamList {
    std::vector<Param> params;
    const Param* find(int id) const;
    float getFloat(int id, float def) const;
    float getFloat2(int id, int comp, float def) const;
    int getInt(int id, int def) const;
    bool getBool(int id, bool def) const;
    void getColor(int id, float out[3], float r, float g, float b) const;
};

struct FlareObject : ParamList {
    int type = 0;
    std::string name;
    bool hidden = false;
    bool solo = false;
};

struct Preset {
    ParamList globals;
    std::vector<FlareObject> objects;
    std::vector<std::string> warnings;
    bool empty() const { return objects.empty(); }
};

// Le o container binario (OFP\x03 + registros). Retorna false e preenche
// error se o arquivo nao for um preset valido.
bool parseOfp(const uint8_t* data, size_t size, Preset& out, std::string& error);
bool loadOfpFile(const std::string& path, std::vector<uint8_t>& bytes, std::string& error);

// Estado do knob renderOptions: "<N>;<2N digitos hex>".
std::string encodeState(const std::vector<uint8_t>& bytes);
bool decodeState(const std::string& text, std::vector<uint8_t>& bytes, std::string& error);

const char* objectTypeName(int type);

}  // namespace ofndk
