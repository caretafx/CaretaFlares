// TextureCache.h - texturas PNG da instalacao (Elements, Glass), lidas com o WIC
// do Windows e guardadas com mipmaps para amostragem bilinear.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace ofndk {

struct Texture {
    struct Level {
        int w = 0, h = 0;
        std::vector<uint8_t> rgba;  // RGBA 8 bits, alfa nao pre-multiplicado
    };
    std::vector<Level> levels;
    int width() const { return levels.empty() ? 0 : levels[0].w; }
    int height() const { return levels.empty() ? 0 : levels[0].h; }

    // u, v em 0..1; footprint = quantos texels por pixel de saida (escolhe o mip).
    // Saida em 0..255 (r, g, b, a).
    void sample(float u, float v, float footprint, float out[4]) const;
};

// Procura "nome" (sem extensao, sem diferenciar maiusculas, ignorando " (U)")
// na pasta. Nome vazio ou inexistente = sem textura.
const Texture* findTexture(const std::string& folder, const std::string& name, int index);

}  // namespace ofndk
