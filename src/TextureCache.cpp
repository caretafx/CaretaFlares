// TextureCache.cpp - ver TextureCache.h.
#define WIN32_LEAN_AND_MEAN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "TextureCache.h"

#include <windows.h>
#include <wincodec.h>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <map>
#include <memory>

namespace fs = std::filesystem;

namespace ofndk {

namespace {

// SRWLOCK direto: nao depende da runtime C++ (o Nuke traz uma msvcp140 antiga).
SRWLOCK g_lock = SRWLOCK_INIT;

struct Folder {
    std::vector<std::pair<std::string, fs::path>> files;  // nome em minusculas, caminho
};

std::map<std::string, std::unique_ptr<Folder>>& folders()
{
    static std::map<std::string, std::unique_ptr<Folder>> m;
    return m;
}

std::map<std::string, std::unique_ptr<Texture>>& textures()
{
    static std::map<std::string, std::unique_ptr<Texture>> m;
    return m;
}

std::string lower(std::string s)
{
    for (char& c : s) c = char(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

Folder* scanFolder(const std::string& folder)
{
    auto& m = folders();
    auto it = m.find(folder);
    if (it != m.end()) return it->second.get();
    auto f = std::make_unique<Folder>();
    std::error_code ec;
    for (const auto& e : fs::directory_iterator(fs::u8path(folder), ec)) {
        if (!e.is_regular_file()) continue;
        const std::string ext = lower(e.path().extension().u8string());
        if (ext != ".png" && ext != ".jpg" && ext != ".tif" && ext != ".tiff" && ext != ".bmp") continue;
        f->files.emplace_back(lower(e.path().stem().u8string()), e.path());
    }
    std::sort(f->files.begin(), f->files.end());
    Folder* raw = f.get();
    m[folder] = std::move(f);
    return raw;
}

bool decodeWic(const fs::path& path, Texture::Level& out)
{
    const HRESULT init = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool mustUninit = SUCCEEDED(init);
    bool ok = false;
    IWICImagingFactory* factory = nullptr;
    IWICBitmapDecoder* decoder = nullptr;
    IWICBitmapFrameDecode* frame = nullptr;
    IWICFormatConverter* conv = nullptr;
    if (SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER,
                                   IID_PPV_ARGS(&factory))) &&
        SUCCEEDED(factory->CreateDecoderFromFilename(path.wstring().c_str(), nullptr, GENERIC_READ,
                                                     WICDecodeMetadataCacheOnDemand, &decoder)) &&
        SUCCEEDED(decoder->GetFrame(0, &frame)) && SUCCEEDED(factory->CreateFormatConverter(&conv)) &&
        SUCCEEDED(conv->Initialize(frame, GUID_WICPixelFormat32bppRGBA, WICBitmapDitherTypeNone, nullptr, 0.0,
                                   WICBitmapPaletteTypeCustom))) {
        UINT w = 0, h = 0;
        conv->GetSize(&w, &h);
        out.w = int(w);
        out.h = int(h);
        out.rgba.resize(size_t(w) * h * 4);
        ok = SUCCEEDED(conv->CopyPixels(nullptr, w * 4, UINT(out.rgba.size()), out.rgba.data())) && w && h;
    }
    if (conv) conv->Release();
    if (frame) frame->Release();
    if (decoder) decoder->Release();
    if (factory) factory->Release();
    if (mustUninit) CoUninitialize();
    return ok;
}

void buildMips(Texture& t)
{
    while (t.levels.back().w > 1 || t.levels.back().h > 1) {
        const Texture::Level& a = t.levels.back();
        Texture::Level b;
        b.w = std::max(1, a.w / 2);
        b.h = std::max(1, a.h / 2);
        b.rgba.resize(size_t(b.w) * b.h * 4);
        for (int y = 0; y < b.h; ++y)
            for (int x = 0; x < b.w; ++x)
                for (int c = 0; c < 4; ++c) {
                    int sum = 0, n = 0;
                    for (int dy = 0; dy < 2; ++dy)
                        for (int dx = 0; dx < 2; ++dx) {
                            const int sx = std::min(a.w - 1, 2 * x + dx);
                            const int sy = std::min(a.h - 1, 2 * y + dy);
                            sum += a.rgba[(size_t(sy) * a.w + sx) * 4 + c];
                            ++n;
                        }
                    b.rgba[(size_t(y) * b.w + x) * 4 + c] = uint8_t(sum / n);
                }
        t.levels.push_back(std::move(b));
    }
}

}  // namespace

void Texture::sample(float u, float v, float footprint, float out[4]) const
{
    out[0] = out[1] = out[2] = out[3] = 0.0f;
    if (levels.empty()) return;
    int li = 0;
    if (footprint > 1.0f) li = std::min(int(levels.size()) - 1, int(std::log2(footprint)));
    const Level& L = levels[size_t(li)];
    const float fx = u * float(L.w) - 0.5f;
    const float fy = v * float(L.h) - 0.5f;
    const int x0 = int(std::floor(fx));
    const int y0 = int(std::floor(fy));
    const float tx = fx - float(x0);
    const float ty = fy - float(y0);
    auto texel = [&](int x, int y, int c) -> float {
        x = std::min(std::max(x, 0), L.w - 1);
        y = std::min(std::max(y, 0), L.h - 1);
        return float(L.rgba[(size_t(y) * L.w + x) * 4 + c]);
    };
    for (int c = 0; c < 4; ++c) {
        const float a = texel(x0, y0, c) * (1 - tx) + texel(x0 + 1, y0, c) * tx;
        const float b = texel(x0, y0 + 1, c) * (1 - tx) + texel(x0 + 1, y0 + 1, c) * tx;
        out[c] = a * (1 - ty) + b * ty;
    }
}

const Texture* findTexture(const std::string& folder, const std::string& rawName, int index)
{
    std::string name = rawName;
    const std::string suffix = " (U)";
    if (name.size() > suffix.size() && name.compare(name.size() - suffix.size(), suffix.size(), suffix) == 0)
        name.resize(name.size() - suffix.size());
    name = lower(name);

    AcquireSRWLockExclusive(&g_lock);
    const Texture* result = nullptr;
    Folder* f = scanFolder(folder);
    const fs::path* path = nullptr;
    for (const auto& e : f->files)
        if (e.first == name) path = &e.second;
    // o indice gravado nos presets nao e confiavel (0 = "nenhuma" no original); so o nome conta
    (void)index;
    if (path) {
        const std::string key = path->u8string();
        auto& tm = textures();
        auto it = tm.find(key);
        if (it == tm.end()) {
            auto t = std::make_unique<Texture>();
            Texture::Level l0;
            if (decodeWic(*path, l0)) {
                t->levels.push_back(std::move(l0));
                buildMips(*t);
            }
            it = tm.emplace(key, std::move(t)).first;
        }
        if (!it->second->levels.empty()) result = it->second.get();
    }
    ReleaseSRWLockExclusive(&g_lock);
    return result;
}

}  // namespace ofndk
