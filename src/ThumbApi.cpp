// ThumbApi.cpp - ofthumb.dll: renderiza miniaturas de presets para o browser
// (Python/ctypes). Nao depende do Nuke, entao tambem roda fora dele nos testes.
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

#include "FlareRenderer.h"
#include "OfpPreset.h"

using namespace ofndk;

extern "C" {

// Renderiza o preset em RGB 8 bits (linha 0 = topo), em espaco de display.
// lightX/lightY e centerX/centerY em fracao do quadro (0..1, origem embaixo-esquerda,
// como no Nuke). Retorna o numero de objetos desenhados, ou -1 se o preset nao abre.
__declspec(dllexport) int ofthumb_render(const char* ofpPath, const char* textureRoot, int width, int height,
                                         float lightX, float lightY, float centerX, float centerY,
                                         unsigned char* rgbOut)
{
    if (!ofpPath || !rgbOut || width <= 0 || height <= 0) return -1;
    std::vector<uint8_t> bytes;
    std::string err;
    Preset preset;
    if (!loadOfpFile(ofpPath, bytes, err) || !parseOfp(bytes.data(), bytes.size(), preset, err)) return -1;

    RenderSettings st;
    st.width = width;
    st.height = height;
    st.centerX = centerX * float(width);
    st.centerY = centerY * float(height);
    st.textureRoot = textureRoot ? textureRoot : "";
    Light light;
    light.x = lightX * float(width);
    light.y = lightY * float(height);

    std::vector<float> rgba;
    RenderStats stats;
    FlareRenderer().render(preset, st, {light}, rgba, &stats);
    const size_t n = size_t(width) * size_t(height);
    for (size_t i = 0; i < n; ++i)
        for (int c = 0; c < 3; ++c) {
            const float v = std::min(1.0f, std::max(0.0f, rgba[i * 4 + c]));
            rgbOut[i * 3 + c] = static_cast<unsigned char>(v * 255.0f + 0.5f);
        }
    return stats.objectsDrawn;
}

// Igual a ofthumb_render, mas com o preset ja em memoria (editor ao vivo).
// solo >= 0 desenha so aquele objeto; brightness/scale sao os do preview (1 = 100%).
__declspec(dllexport) int ofthumb_render_mem(const unsigned char* data, int size, const char* textureRoot,
                                             int width, int height, float lightX, float lightY, float centerX,
                                             float centerY, int solo, float brightness, float scale,
                                             unsigned char* rgbOut)
{
    if (!data || size <= 0 || !rgbOut || width <= 0 || height <= 0) return -1;
    std::string err;
    Preset preset;
    if (!parseOfp(data, size_t(size), preset, err)) return -1;
    RenderSettings st;
    st.width = width;
    st.height = height;
    st.centerX = centerX * float(width);
    st.centerY = centerY * float(height);
    st.textureRoot = textureRoot ? textureRoot : "";
    st.soloFlareId = solo;
    st.brightness = brightness;
    st.scale = scale;
    Light light;
    light.x = lightX * float(width);
    light.y = lightY * float(height);
    std::vector<float> rgba;
    RenderStats stats;
    FlareRenderer().render(preset, st, {light}, rgba, &stats);
    const size_t n = size_t(width) * size_t(height);
    for (size_t i = 0; i < n; ++i)
        for (int c = 0; c < 3; ++c) {
            const float v = std::min(1.0f, std::max(0.0f, rgba[i * 4 + c]));
            rgbOut[i * 3 + c] = static_cast<unsigned char>(v * 255.0f + 0.5f);
        }
    return stats.objectsDrawn;
}

// Quantos objetos o preset tem (para mostrar no browser); -1 se nao abre.
__declspec(dllexport) int ofthumb_count(const char* ofpPath)
{
    std::vector<uint8_t> bytes;
    std::string err;
    Preset preset;
    if (!ofpPath || !loadOfpFile(ofpPath, bytes, err) || !parseOfp(bytes.data(), bytes.size(), preset, err))
        return -1;
    return int(preset.objects.size());
}

}  // extern "C"
