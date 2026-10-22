// FlareRenderer.h - renderizador em CPU dos elementos do flare.
// Comportamento descrito em docs/03-comportamento-render.md; codigo escrito do zero.
#pragma once

#include <string>
#include <vector>

#include "OfpPreset.h"

namespace ofndk {

// Uma fonte de luz, em pixels do formato (origem embaixo-esquerda, como no Nuke).
struct Light {
    float x = 0.0f;
    float y = 0.0f;
    float brightness = 1.0f;  // Brightness0..16 do no
    float scale = 1.0f;       // Scale0..16 do no
    float color[3] = {1.0f, 1.0f, 1.0f};
};

struct RenderSettings {
    int width = 0;
    int height = 0;
    float centerX = 0.0f;  // CenterPosition, pixels
    float centerY = 0.0f;
    float brightness = 1.0f;   // knob Brightness
    float scale = 1.0f;        // knob Scale
    float rotationDeg = 0.0f;  // knob RotationOffset
    bool scaleOffset = false;  // knob ScaleOffset
    float aspectRatio = 1.0f;  // knob AspectRatio
    int colorMode = 0;         // 0 Tint, 1 Multiply
    int soloFlareId = -1;      // knob SoloFlareID
    float evolution = 0.0f;    // knob AnimationEvolution
    // expoente aplicado no fim (o no usa 1/gamma = 2,2 para linearizar). 1 = sem mudanca.
    // Quando != 1, o canal alfa recebe min(1, maior componente) antes do expoente.
    float outputExponent = 1.0f;
    // pasta "Optical Flares Textures" (contem Elements/ e Glass/)
    std::string textureRoot;
};

struct RenderStats {
    int objectsDrawn = 0;
    int objectsSkipped = 0;
    int texturesMissing = 0;
};

// Buffer RGBA float de width*height pixels; linha 0 = topo da imagem
// (mesma orientacao do original). O valor esta em "espaco de display": o no
// eleva a 1/gamma (2,2 por padrao) antes de somar ao fundo.
class FlareRenderer {
public:
    void render(const Preset& preset, const RenderSettings& settings, const std::vector<Light>& lights,
                std::vector<float>& rgba, RenderStats* stats = nullptr) const;
};

}  // namespace ofndk
