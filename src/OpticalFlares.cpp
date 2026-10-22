// OpticalFlares.cpp - no do Nuke compativel em nome e knobs com o Optical Flares
// 1.0.86 (docs/03-comportamento-render.md §1). Escrito do zero.
//
// v1: le o estado do flare do knob renderOptions (mesmo formato do original,
// para scripts antigos abrirem) ou de um .ofp escolhido no knob "ofpPresetFile",
// e desenha os objetos ja implementados (por enquanto so o Glow).

#include <cmath>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "DDImage/CameraOp.h"
#include "DDImage/Format.h"
#include "DDImage/GeoOp.h"
#include "DDImage/Iop.h"
#include "DDImage/Knobs.h"
#include "DDImage/Row.h"
#include "DDImage/Thread.h"

#include "FlareRenderer.h"
#include "OfpPreset.h"

using namespace DD::Image;

namespace {

const char* const kClass = "OpticalFlares";
const char* const kHelp =
    "Optical Flares (reimplementacao independente para Nuke 15/17).\n"
    "Le os presets .ofp e as texturas da instalacao do usuario. "
    "Versao em desenvolvimento: so o elemento Glow e desenhado.";

const int kMaxExtraLights = 16;

const char* const kSourceType[] = {"2D", "3D", nullptr};
const char* const kColorMode[] = {"Tint", "Multiply", nullptr};
const char* const kSampleMethod[] = {"Alpha", "Alpha Invert", "Luma", "Luma Invert", nullptr};
const char* const kFlickerType[] = {"Smooth", "Sharp", nullptr};
const char* const kRenderMode[] = {"On Black", "On Transparent", "Over Original", nullptr};
const char* const kColorspace[] = {"linear", "Custom Gamma", nullptr};

enum RenderMode { kOnBlack = 0, kOnTransparent = 1, kOverOriginal = 2 };

}  // namespace

class OpticalFlares : public Iop {
public:
    explicit OpticalFlares(Node* node)
        : Iop(node)
    {
        inputs(4);
        for (int i = 0; i < 2; ++i) positionXY_[i] = 0.0f;
        centerPosition_[0] = 320.0f;
        centerPosition_[1] = 240.0f;
        color_[0] = color_[1] = color_[2] = 1.0f;
        for (int i = 0; i <= kMaxExtraLights; ++i) {
            lightBrightness_[i] = 1.0f;
            lightScale_[i] = 1.0f;
        }
        for (auto& p : extraPositions_) p[0] = p[1] = 0.0f;
    }

    const char* Class() const override { return kClass; }
    const char* node_help() const override { return kHelp; }

    int minimum_inputs() const override { return 4; }
    int maximum_inputs() const override { return 4; }
    int optional_input() const override { return 1; }

    bool test_input(int n, Op* op) const override
    {
        if (n < 2) return dynamic_cast<Iop*>(op) != nullptr;
        if (n == 2) return dynamic_cast<GeoOp*>(op) != nullptr;
        return dynamic_cast<CameraOp*>(op) != nullptr;
    }

    Op* default_input(int n) const override
    {
        if (n < 2) return Iop::default_input(n);
        return nullptr;
    }

    const char* input_label(int n, char*) const override
    {
        switch (n) {
        case 0: return "background";
        case 1: return "matte";
        case 2: return "scene";
        case 3: return "cam";
        default: return nullptr;
        }
    }

    void knobs(Knob_Callback f) override;
    int knob_changed(Knob* k) override;
    void _validate(bool forReal) override;
    void _request(int x, int y, int r, int t, ChannelMask channels, int count) override;
    void engine(int y, int x, int r, ChannelMask channels, Row& out) override;

    static const Op::Description description;

private:
    bool inputConnected(int n);
    void loadPresetFile();
    void updateEnabledKnobs();
    void ensureRendered();

    // knobs do original -----------------------------------------------------
    FormatPair format_;
    bool useBackgroundFormat_ = false;
    float positionXY_[2];
    float centerPosition_[2];
    int sourceType_ = 0;
    int count_ = 0;
    float lightBrightness_[kMaxExtraLights + 1];
    float lightScale_[kMaxExtraLights + 1];
    float extraPositions_[kMaxExtraLights][2];
    double brightness_ = 1.0;
    double scale_ = 1.0;
    bool scaleOffset_ = false;
    double rotationOffset_ = 0.0;
    float color_[3];
    int colorMode_ = 0;
    double animationEvolution_ = 0.0;
    bool enable2DOcclusion_ = false;
    bool showForeground_ = false;
    int sampleMethod_ = 0;
    int lightRadius_ = 10;
    bool sampleColor_ = false;
    int flickerType_ = 0;
    double flickerSpeed_ = 0.0;
    double flickerAmount_ = 0.0;
    bool randomizeMultipleFlares_ = false;
    int randomSeed_ = 0;
    float aspectRatio_ = 1.0f;
    int renderMode_ = kOverOriginal;
    int colorspace_ = 0;
    float customGamma_ = 0.4545f;
    bool gpu_ = true;
    std::string renderOptions_;
    bool useLightColor_ = false;
    bool useLightIntensity_ = false;
    bool useDepthScaling_ = false;
    bool enableOcclusion_ = false;
    bool normalizeDepthData_ = false;
    int occlusionTestRadius_ = 0;
    float uiPreviewGamma_ = 2.2f;
    int soloFlareId_ = -1;

    // knobs novos -----------------------------------------------------------
    const char* presetFile_ = nullptr;

    // estado ----------------------------------------------------------------
    std::shared_ptr<const ofndk::Preset> preset_;
    std::string parsedState_;
    bool stateError_ = false;

    // DD::Image::Lock em vez de std::mutex: o Nuke traz a runtime C++ 14.36, e o
    // std::mutex do MSVC 14.40+ pode falhar nela.
    Lock renderLock_;
    Hash renderedHash_;
    bool rendered_ = false;
    std::vector<float> flare_;
    int flareX_ = 0, flareY_ = 0, flareW_ = 0, flareH_ = 0;
};

static Op* build(Node* node) { return new OpticalFlares(node); }
const Op::Description OpticalFlares::description(kClass, build);

void OpticalFlares::knobs(Knob_Callback f)
{
    Button(f, "Options", "Options");
    Tooltip(f, "Abre o editor de flares no plugin original. Ainda nao existe nesta versao; "
               "use o knob 'Preset (.ofp)'.");

    File_knob(f, &presetFile_, "ofpPresetFile", "Preset (.ofp)");
    SetFlags(f, Knob::KNOB_CHANGED_ALWAYS);
    Tooltip(f, "Carrega um preset .ofp da instalacao (por exemplo "
               "~/.nuke/OpticalFlares/Optical Flares Presets). O conteudo e copiado para o "
               "script, como no plugin original.");
    Button(f, "ofpLoadPreset", "Recarregar");
    Divider(f);

    Format_knob(f, &format_, "Format", "Format");
    Bool_knob(f, &useBackgroundFormat_, "UseBackgroundFormat", "Use Background Format");
    XY_knob(f, positionXY_, "PositionXY", "Position XY");
    XY_knob(f, centerPosition_, "CenterPosition", "Center Position");
    SetFlags(f, Knob::STARTLINE);
    Button(f, "InitCenter", "Init Center");
    Enumeration_knob(f, &sourceType_, kSourceType, "SourceType", "Source Type");

    BeginClosedGroup(f, "Additional2DFlares", "Additional 2D Flares");
    Int_knob(f, &count_, "Count", "Count");
    SetFlags(f, Knob::STARTLINE);
    SetRange(f, 0, kMaxExtraLights);
    Float_knob(f, &lightBrightness_[0], "Brightness0", "Brightness 0");
    Float_knob(f, &lightScale_[0], "Scale0", "Scale 0");
    for (int i = 0; i < kMaxExtraLights; ++i) {
        static std::string names[kMaxExtraLights][6];
        std::string* n = names[i];
        if (n[0].empty()) {
            n[0] = "PositionXY" + std::to_string(i + 1);
            n[1] = "Position XY " + std::to_string(i + 1);
            n[2] = "Brightness" + std::to_string(i + 1);
            n[3] = "Brightness " + std::to_string(i + 1);
            n[4] = "Scale" + std::to_string(i + 1);
            n[5] = "Scale " + std::to_string(i + 1);
        }
        XY_knob(f, extraPositions_[i], n[0].c_str(), n[1].c_str());
        Float_knob(f, &lightBrightness_[i + 1], n[2].c_str(), n[3].c_str());
        Float_knob(f, &lightScale_[i + 1], n[4].c_str(), n[5].c_str());
    }
    EndGroup(f);

    Float_knob(f, &brightness_, "Brightness", "Brightness");
    SetFlags(f, Knob::STARTLINE);
    Float_knob(f, &scale_, "Scale", "Scale");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &scaleOffset_, "ScaleOffset", "Scale Offset");
    Float_knob(f, &rotationOffset_, "RotationOffset", "Rotation Offset");
    SetFlags(f, Knob::STARTLINE);
    SetRange(f, -180, 180);
    Color_knob(f, color_, "Color", "Color");
    SetFlags(f, Knob::STARTLINE);
    Enumeration_knob(f, &colorMode_, kColorMode, "ColorMode", "Color Mode");
    SetFlags(f, Knob::STARTLINE);
    Float_knob(f, &animationEvolution_, "AnimationEvolution", "Animation Evolution");
    SetFlags(f, Knob::STARTLINE);

    BeginClosedGroup(f, "2DMatteOcclusion", "2D Matte Occlusion");
    Bool_knob(f, &enable2DOcclusion_, "Enable2DOcclusion", "Enable 2D Occlusion");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &showForeground_, "ShowForeground", "Show Foreground");
    SetFlags(f, Knob::STARTLINE);
    Enumeration_knob(f, &sampleMethod_, kSampleMethod, "SampleMethod", "Sample Method");
    SetFlags(f, Knob::STARTLINE);
    Int_knob(f, &lightRadius_, "LightRadius", "Light Radius");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &sampleColor_, "SampleColor", "Sample Color");
    SetFlags(f, Knob::STARTLINE);
    EndGroup(f);

    BeginClosedGroup(f, "Flicker", "Flicker");
    Enumeration_knob(f, &flickerType_, kFlickerType, "Type", "Type");
    Float_knob(f, &flickerSpeed_, "Speed", "Speed");
    SetFlags(f, Knob::STARTLINE);
    Float_knob(f, &flickerAmount_, "Amount", "Amount");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &randomizeMultipleFlares_, "RandomizeMultipleFlares", "Randomize Multiple Flares");
    SetFlags(f, Knob::STARTLINE);
    Int_knob(f, &randomSeed_, "RandomSeed", "Random Seed");
    SetFlags(f, Knob::STARTLINE);
    EndGroup(f);

    Float_knob(f, &aspectRatio_, "AspectRatio", "Aspect Ratio");
    SetFlags(f, Knob::STARTLINE);
    Enumeration_knob(f, &renderMode_, kRenderMode, "RenderMode", "Render Mode");
    SetFlags(f, Knob::STARTLINE);
    Enumeration_knob(f, &colorspace_, kColorspace, "Colorspace", "Colorspace");
    SetFlags(f, Knob::STARTLINE);
    Float_knob(f, &customGamma_, "CustomGamma", "Custom Gamma");
    Bool_knob(f, &gpu_, "GPU", "GPU");
    SetFlags(f, Knob::STARTLINE);
    Tooltip(f, "Mantido por compatibilidade; esta versao sempre renderiza em CPU.");

    String_knob(f, &renderOptions_, "renderOptions");
    SetFlags(f, Knob::INVISIBLE | Knob::ALWAYS_SAVE);

    Tab_knob(f, "3D");
    BeginClosedGroup(f, "3DLights", "3D Lights");
    Bool_knob(f, &useLightColor_, "UseLightColor", "Use Light Color");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &useLightIntensity_, "UseLightIntensity", "Use Light Intensity");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &useDepthScaling_, "UseDepthScaling", "Use Depth Scaling");
    SetFlags(f, Knob::STARTLINE);
    EndGroup(f);
    BeginClosedGroup(f, "3DDepthMatteOcclusion", "3D Depth Matte Occlusion");
    Bool_knob(f, &enableOcclusion_, "EnableOcclusion", "Enable Occlusion");
    SetFlags(f, Knob::STARTLINE);
    Bool_knob(f, &normalizeDepthData_, "NormalizeDepthData", "Normalize Depth Data");
    SetFlags(f, Knob::STARTLINE);
    Int_knob(f, &occlusionTestRadius_, "OcclusionTestRadius", "Occlusion Test Radius");
    SetFlags(f, Knob::STARTLINE);
    EndGroup(f);

    Tab_knob(f, "Misc");
    Float_knob(f, &uiPreviewGamma_, "UIPreviewGamma", "UI Preview Gamma");
    Int_knob(f, &soloFlareId_, "SoloFlareID", "Solo Flare ID");
    SetFlags(f, Knob::STARTLINE);
}

int OpticalFlares::knob_changed(Knob* k)
{
    if (k == &Knob::showPanel || k->is("Count")) {
        updateEnabledKnobs();
        return 1;
    }
    if (k->is("ofpPresetFile") || k->is("ofpLoadPreset")) {
        loadPresetFile();
        return 1;
    }
    if (k->is("InitCenter")) {
        const Format& fmt = format_.format() ? *format_.format() : input0().format();
        if (Knob* c = knob("CenterPosition")) {
            c->set_value(fmt.width() * 0.5, 0);
            c->set_value(fmt.height() * 0.5, 1);
        }
        return 1;
    }
    if (k->is("Options")) {
        critical("O editor de flares ainda nao existe nesta versao.\n"
                "Escolha um preset no knob 'Preset (.ofp)'.");
        return 1;
    }
    return Iop::knob_changed(k);
}

void OpticalFlares::updateEnabledKnobs()
{
    for (int i = 0; i < kMaxExtraLights; ++i) {
        const bool on = i < count_;
        const std::string idx = std::to_string(i + 1);
        for (const std::string& name : {"PositionXY" + idx, "Brightness" + idx, "Scale" + idx})
            if (Knob* kk = knob(name.c_str())) kk->enable(on);
    }
}

void OpticalFlares::loadPresetFile()
{
    if (!presetFile_ || !*presetFile_) return;
    std::vector<uint8_t> bytes;
    std::string err;
    if (!ofndk::loadOfpFile(presetFile_, bytes, err)) {
        critical("Optical Flares: %s", err.c_str());
        return;
    }
    ofndk::Preset test;
    if (!ofndk::parseOfp(bytes.data(), bytes.size(), test, err)) {
        critical("Optical Flares: preset invalido (%s)", err.c_str());
        return;
    }
    if (Knob* k = knob("renderOptions")) k->set_text(ofndk::encodeState(bytes).c_str());
}

bool OpticalFlares::inputConnected(int n)
{
    Iop* in = dynamic_cast<Iop*>(Op::input(n));
    if (!in) return false;
    // a entrada padrao (preto) tem bbox de 1x1, como o original assume
    const Box& b = in->info();
    return !(b.r() - b.x() == 1 && b.t() - b.y() == 1);
}

void OpticalFlares::_validate(bool forReal)
{
    input0().validate(forReal);
    if (Iop* matte = dynamic_cast<Iop*>(Op::input(1))) matte->validate(forReal);

    // estado do flare
    if (renderOptions_ != parsedState_) {
        parsedState_ = renderOptions_;
        stateError_ = false;
        auto preset = std::make_shared<ofndk::Preset>();
        if (!renderOptions_.empty()) {
            std::vector<uint8_t> bytes;
            std::string err;
            if (!ofndk::decodeState(renderOptions_, bytes, err) ||
                !ofndk::parseOfp(bytes.data(), bytes.size(), *preset, err)) {
                stateError_ = true;
                preset = std::make_shared<ofndk::Preset>();
            }
        }
        preset_ = preset;
    }

    copy_info(0);
    const bool bgConnected = inputConnected(0);
    const Format* fmt = format_.format();
    const Format* full = format_.fullSizeFormat();
    if ((useBackgroundFormat_ && bgConnected) || !fmt) {
        fmt = &input0().format();
        full = &input0().full_size_format();
    }
    info_.format(*fmt);
    info_.full_size_format(full ? *full : *fmt);
    info_.set(fmt->x(), fmt->y(), fmt->r(), fmt->t());
    ChannelSet out = input0().channels();
    out += Mask_RGBA;
    info_.channels(out);
    set_out_channels(Mask_All);

    if (stateError_) warning("renderOptions corrompido; o flare foi ignorado.");
    else if (!preset_ || preset_->empty()) warning("Nenhum preset carregado (knob 'Preset (.ofp)').");
}

void OpticalFlares::_request(int x, int y, int r, int t, ChannelMask channels, int count)
{
    input0().request(x, y, r, t, channels, count);
}

void OpticalFlares::ensureRendered()
{
    Guard guard(renderLock_);
    if (rendered_ && renderedHash_ == hash()) return;

    const Format& fmt = info_.format();
    flareX_ = fmt.x();
    flareY_ = fmt.y();
    flareW_ = fmt.width();
    flareH_ = fmt.height();

    ofndk::RenderSettings st;
    st.width = flareW_;
    st.height = flareH_;
    st.centerX = centerPosition_[0] - flareX_;
    st.centerY = centerPosition_[1] - flareY_;
    st.brightness = float(brightness_);
    st.scale = float(scale_);
    st.rotationDeg = float(rotationOffset_);
    st.scaleOffset = scaleOffset_;
    st.aspectRatio = aspectRatio_;
    st.colorMode = colorMode_;
    st.soloFlareId = soloFlareId_;

    std::vector<ofndk::Light> lights;
    const int n = std::max(0, std::min(count_, kMaxExtraLights));
    for (int i = 0; i <= n; ++i) {
        ofndk::Light l;
        const float* p = (i == 0) ? positionXY_ : extraPositions_[i - 1];
        l.x = p[0] - flareX_;
        l.y = p[1] - flareY_;
        l.brightness = lightBrightness_[i];
        l.scale = lightScale_[i];
        for (int c = 0; c < 3; ++c) l.color[c] = color_[c];
        lights.push_back(l);
    }

    ofndk::FlareRenderer renderer;
    if (preset_) renderer.render(*preset_, st, lights, flare_);
    else flare_.assign(size_t(flareW_) * size_t(flareH_) * 4, 0.0f);

    renderedHash_ = hash();
    rendered_ = true;
}

void OpticalFlares::engine(int y, int x, int r, ChannelMask channels, Row& out)
{
    ensureRendered();

    Row in(x, r);
    in.get(input0(), y, x, r, channels);
    if (aborted()) return;

    const float gamma = (colorspace_ == 1 && customGamma_ > 0.0f) ? customGamma_ : 0.4545f;
    const float expo = 1.0f / gamma;
    const int row = flareH_ - 1 - (y - flareY_);
    const bool rowInside = row >= 0 && row < flareH_;
    const float* frow = rowInside ? flare_.data() + size_t(row) * size_t(flareW_) * 4 : nullptr;

    foreach (z, channels) {
        const float* src = in[z];
        float* dst = out.writable(z);
        const bool isRGBA = z == Chan_Red || z == Chan_Green || z == Chan_Blue || z == Chan_Alpha;
        if (!isRGBA) {
            for (int X = x; X < r; ++X) dst[X] = src ? src[X] : 0.0f;
            continue;
        }
        const int comp = (z == Chan_Red) ? 0 : (z == Chan_Green) ? 1 : (z == Chan_Blue) ? 2 : 3;
        for (int X = x; X < r; ++X) {
            const float base = (renderMode_ == kOverOriginal && src) ? src[X] : 0.0f;
            float v = 0.0f;
            const int col = X - flareX_;
            if (frow && col >= 0 && col < flareW_) {
                const float* p = frow + size_t(col) * 4;
                if (comp < 3) {
                    v = std::pow(std::max(0.0f, p[comp]), expo);
                } else if (renderMode_ == kOnTransparent) {
                    // alfa = maior componente, limitado a 1 (aproximacao; ver doc 03 §2)
                    v = std::min(1.0f, std::max(std::max(p[0], p[1]), p[2]));
                }
            }
            dst[X] = base + v;
        }
    }
}
