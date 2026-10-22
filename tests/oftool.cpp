// oftool - testes do nucleo sem o Nuke.
//
//   oftool scan PASTA
//       le todos os .ofp, confere o parser e o ida-e-volta do estado hex.
//   oftool render PRESET.ofp LARGURA ALTURA LUZ_X LUZ_Y SAIDA.ppm [CENTRO_X CENTRO_Y]
//       renderiza o flare num PPM 8 bits,
//       em espaco de display (o mesmo que o viewer mostraria com gama 2,2).
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

#include "FlareRenderer.h"
#include "OfpPreset.h"

namespace fs = std::filesystem;
using namespace ofndk;

static int scan(const char* folder)
{
    int total = 0, ok = 0, objects = 0;
    for (const auto& e : fs::recursive_directory_iterator(folder)) {
        if (!e.is_regular_file() || e.path().extension() != ".ofp") continue;
        ++total;
        std::vector<uint8_t> bytes;
        std::string err;
        Preset p;
        if (!loadOfpFile(e.path().string(), bytes, err) || !parseOfp(bytes.data(), bytes.size(), p, err)) {
            std::printf("FALHA %s: %s\n", e.path().string().c_str(), err.c_str());
            continue;
        }
        std::vector<uint8_t> back;
        if (!decodeState(encodeState(bytes), back, err) || back != bytes) {
            std::printf("FALHA estado hex %s\n", e.path().string().c_str());
            continue;
        }
        for (const std::string& w : p.warnings) std::printf("AVISO %s: %s\n", e.path().string().c_str(), w.c_str());
        objects += int(p.objects.size());
        ++ok;
    }
    std::printf("%d arquivos, %d ok, %d objetos\n", total, ok, objects);
    return ok == total ? 0 : 1;
}

static int render(int argc, char** argv)
{
    if (argc < 8) {
        std::printf("uso: oftool render PRESET W H LX LY SAIDA.ppm [CX CY]\n");
        return 2;
    }
    std::vector<uint8_t> bytes;
    std::string err;
    Preset p;
    if (!loadOfpFile(argv[2], bytes, err) || !parseOfp(bytes.data(), bytes.size(), p, err)) {
        std::printf("erro: %s\n", err.c_str());
        return 1;
    }
    RenderSettings st;
    st.width = std::atoi(argv[3]);
    st.height = std::atoi(argv[4]);
    st.centerX = argc > 9 ? float(std::atof(argv[8])) : st.width * 0.5f;
    st.centerY = argc > 9 ? float(std::atof(argv[9])) : st.height * 0.5f;
    {
        const char* t = std::getenv("OPTICAL_FLARES_TEXTURE_PATH");
        const char* h = std::getenv("USERPROFILE");
        st.textureRoot = t ? std::string(t) : std::string(h ? h : "") + "/.nuke/OpticalFlares/Optical Flares Textures";
    }
    if (const char* solo = std::getenv("OF_SOLO")) st.soloFlareId = std::atoi(solo);
    Light l;
    l.x = float(std::atof(argv[5]));
    l.y = float(std::atof(argv[6]));
    std::vector<float> rgba;
    RenderStats stats;
    FlareRenderer().render(p, st, {l}, rgba, &stats);

    FILE* fh = std::fopen(argv[7], "wb");
    if (!fh) return 1;
    std::fprintf(fh, "P6\n%d %d\n255\n", st.width, st.height);
    for (size_t i = 0; i < size_t(st.width) * st.height; ++i)
        for (int c = 0; c < 3; ++c) {
            float v = rgba[i * 4 + c];
            v = v < 0 ? 0 : (v > 1 ? 1 : v);
            std::fputc(int(v * 255.0f + 0.5f), fh);
        }
    std::fclose(fh);
    std::printf("%d objetos desenhados, %d ignorados, %d texturas faltando\n", stats.objectsDrawn,
                stats.objectsSkipped, stats.texturesMissing);
    return 0;
}

// oftool bench PRESET W H [REPETICOES]: tempo do render inteiro e de cada objeto (solo)
static int bench(int argc, char** argv)
{
    if (argc < 5) return 2;
    std::vector<uint8_t> bytes;
    std::string err;
    Preset p;
    if (!loadOfpFile(argv[2], bytes, err) || !parseOfp(bytes.data(), bytes.size(), p, err)) {
        std::printf("erro: %s\n", err.c_str());
        return 1;
    }
    const int reps = argc > 5 ? std::atoi(argv[5]) : 3;
    RenderSettings st;
    st.width = std::atoi(argv[3]);
    st.height = std::atoi(argv[4]);
    st.centerX = st.width * 0.5f;
    st.centerY = st.height * 0.5f;
    const char* h = std::getenv("USERPROFILE");
    st.textureRoot = std::string(h ? h : "") + "/.nuke/OpticalFlares/Optical Flares Textures";
    Light l;
    l.x = st.width * 0.3f;
    l.y = st.height * 0.6f;
    std::vector<float> rgba;
    auto timeIt = [&]() {
        double best = 1e30;
        for (int r = 0; r < reps; ++r) {
            const auto t0 = std::chrono::steady_clock::now();
            FlareRenderer().render(p, st, {l}, rgba, nullptr);
            const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            best = std::min(best, ms);
        }
        return best;
    };
    std::printf("total %.1f ms\n", timeIt());
    for (size_t i = 0; i < p.objects.size(); ++i) {
        st.soloFlareId = int(i);
        std::printf("  %2zu %-12s %7.2f ms  %s\n", i, objectTypeName(p.objects[i].type), timeIt(),
                    p.objects[i].name.c_str());
    }
    return 0;
}

int main(int argc, char** argv)
{
    if (argc >= 2 && std::string(argv[1]) == "bench") return bench(argc, argv);
    if (argc >= 3 && std::string(argv[1]) == "scan") return scan(argv[2]);
    if (argc >= 2 && std::string(argv[1]) == "render") return render(argc, argv);
    std::printf("uso: oftool scan PASTA | oftool render ...\n");
    return 2;
}
