# 03 — Comportamento do nó e do renderizador

Descrição, com as nossas palavras, do que o `OpticalFlares.dll` 1.0.86 faz, obtida com o REA
(Ghidra) em 2026-10-21. Serve de especificação para o plugin novo. Onde há incerteza, está dito.

## 1. O nó no Nuke

**Classe** `OpticalFlares`, derivada de `Iop`. Quatro entradas, nesta ordem: `background` (0),
`matte` (1), `scene` (2, GeoOp, opcional com NullGeo padrão), `cam` (3, CameraOp, opcional com
câmera padrão). Ajuda do nó: "VideoCopilot.net - Optical Flares for Nuke".

**Knobs**, na ordem em que o original os cria (nome interno = rótulo sem espaços; botões usam o
rótulo com espaço). `F` = flare (estado global do preset), `op` = membro do nó.

| # | Tipo | Nome | Rótulo | Observações |
|---|---|---|---|---|
| 1 | Button | `Options` | Options | abre o editor (fora do escopo da v1) |
| 2 | Int | `` (vazio) | — | INVISIBLE; inteiro interno, zero |
| 3 | Format | `Format` | Format | formato de saída |
| 4 | Bool | `UseBackgroundFormat` | Use Background Format | |
| 5 | XY | `PositionXY` | Position XY | posição da luz principal, em pixels |
| 6 | XY | `CenterPosition` | Center Position | centro do flare (eixo dos fantasmas); STARTLINE; padrão 320,240 |
| 7 | Button | `Init Center` | Init Center | define Center Position = metade do formato |
| 8 | Enum | `SourceType` | Source Type | 2D, 3D (o menu do nó só tem essas duas; os outros rótulos existem na tabela de textos mas não são usados) |
| 9 | Grupo fechado | `Additional2DFlares` | Additional 2D Flares | |
| 10 | Int | `Count` | Count | 0..16 luzes extras |
| 11 | Float | `Brightness0` / `Scale0` | Brightness 0 / Scale 0 | da luz principal |
| 12 | XY/Float/Float ×16 | `PositionXY1..16`, `Brightness1..16`, `Scale1..16` | | só os ≤ Count ficam habilitados |
| 13 | Float | `Brightness` | Brightness | F; FORCE_RANGE, LOG_SLIDER; padrão 1 |
| 14 | Float | `Scale` | Scale | F; padrão 1 |
| 15 | Bool | `ScaleOffset` | Scale Offset | F |
| 16 | Float | `RotationOffset` | Rotation Offset | F, graus |
| 17 | Color | `Color` | Color | op, cor global (padrão branco) |
| 18 | Enum | `ColorMode` | Color Mode | Tint, Multiply |
| 19 | Float | `AnimationEvolution` | Animation Evolution | |
| 20 | Grupo fechado | `2DMatteOcclusion` | 2D Matte Occlusion | |
| 21 | Bool | `Enable2DOcclusion` | Enable 2D Occlusion | |
| 22 | Bool | `ShowForeground` | Show Foreground | mistura a entrada matte por cima |
| 23 | Enum | `SampleMethod` | Sample Method | Alpha, Alpha Invert, Luma, Luma Invert |
| 24 | Int | `LightRadius` | Light Radius | raio em pixels da amostragem, máx. 64 |
| 25 | Bool | `SampleColor` | Sample Color | tinge a luz com a cor amostrada |
| 26 | Grupo fechado | `Flicker` | Flicker | |
| 27 | Enum | `Type` | Type | Smooth, Sharp |
| 28 | Float | `Speed` / `Amount` | Speed / Amount | |
| 29 | Bool | `RandomizeMultipleFlares` | Randomize Multiple Flares | |
| 30 | Int | `RandomSeed` | Random Seed | |
| 31 | Float | `AspectRatio` | Aspect Ratio | padrão 1 |
| 32 | Enum | `RenderMode` | Render Mode | On Black, On Transparent, Over Original (padrão) |
| 33 | Enum | `Colorspace` | Colorspace | linear, Custom Gamma |
| 34 | Float | `CustomGamma` | Custom Gamma | padrão 0,4545 |
| 35 | Bool | `GPU` | GPU | padrão ligado |
| 36 | Custom | `renderOptions` | — | INVISIBLE, ALWAYS_SAVE; estado do flare (doc 02 §6) |
| 37 | Aba | `3D` | 3D | |
| 38 | Grupo fechado | `3DLights` | 3D Lights | `UseLightColor`, `UseLightIntensity`, `UseDepthScaling` |
| 39 | Grupo fechado | `3DDepthMatteOcclusion` | 3D Depth Matte Occlusion | `EnableOcclusion`, `NormalizeDepthData`, `OcclusionTestRadius` |
| 40 | Aba | `Misc` | Misc | |
| 41 | Float | `UIPreviewGamma` | UI Preview Gamma | padrão 2,2 |
| 42 | Int | `SoloFlareID` | Solo Flare ID | -1 = nenhum |

`knob_changed` só habilita/desabilita knobs (Count, modo 2D/3D, oclusão) e trata os dois botões.
O `Init Center` escreve metade da largura e da altura do formato em `CenterPosition`.

**Hash**: o nó acrescenta ao hash só o tempo (`outputContext().frame`) quando o flicker ou a
animação estão ativos; o estado do flare já entra pelo knob `renderOptions`.

## 2. Pipeline do nó

1. `_validate`: copia a info da entrada 0; se há background e `UseBackgroundFormat`, usa o formato
   dele, senão o knob `Format`. Canais: RGBA se Render Mode = On Transparent, senão RGB (+ canais
   do background).
2. `_request`: pede a entrada 0 inteira e, se existir, a matte inteira. Monta a lista de luzes
   (§3), amostra a matte em volta de cada luz (§8), e **renderiza o flare inteiro** num buffer
   RGBA float do tamanho do formato. O render é feito uma vez por request, não por linha.
3. `engine(y)`: para cada canal RGB pedido, `saída = base + flare^(1/gamma)`; alfa é somado sem
   gamma. `base` é o background quando Render Mode = Over Original, senão 0. Depois, se
   `ShowForeground` e há matte, faz `saída = f·matte + (1−f)·saída`, onde `f` = fator fixo
   (padrão 1) multiplicado pelo alfa da matte quando pedido.
   - `gamma` = 0,4545 no modo linear, ou `CustomGamma` no modo Custom Gamma. Ou seja: o flare é produzido em
     espaço de display e **linearizado com expoente 2,2** antes de somar ao fundo linear. Esse é
     um detalhe importante para igualar a aparência.
4. Sem licença válida o original salpica ruído aleatório em 10% dos pixels; o plugin novo não tem
   licenciamento, então nada disso existe.

## 3. Lista de luzes

Cada luz tem posição (x,y) em pixels, profundidade/escala z, cor RGB, brilho e escala.

- **2D**: luz 0 = `PositionXY`; luzes 1..Count = `PositionXY n`; cor = knob `Color`; brilho e
  escala = `Brightness n`, `Scale n`.
- **3D**: cada luz da cena é projetada pela câmera (`cam`): divide por w, z = w; usa a cor e a
  intensidade da luz 3D se `UseLightColor`/`UseLightIntensity`; luzes atrás da câmera são
  descartadas. `UseDepthScaling` escala o flare por `AspectRatio-ish / z`.
- Track Lights, Mask e Luminance existem como opções mas o código estudado só trata 2D e 3D no
  caminho principal; deixar para depois.

Coordenadas do renderizador: a posição da luz é normalizada para `lx = x / largura`,
`ly = 1 − y / altura` (origem no canto superior esquerdo); o centro do flare idem. Chamo de
**eixo** o segmento do centro até a luz.

## 4. Render de um flare (uma luz)

Para cada luz, em ordem:

1. Prepara o contexto: brilho global = `Brightness` (×100 no original, depois ×0,01) com
   compressão quando > 1 (`b = 0,7·b + 0,3`), multiplicado por (1 + 0,01·global 0); escala global
   = `Scale`; rotação = `RotationOffset` em radianos; aspect = `AspectRatio` × (altura/largura);
   seed global; solo; cor da luz (bytes 0..255 → 0..1).
2. "Colorize": se Color Mode = Tint e a cor da luz não é branca, calcula o fator de colorização a
   partir da luminância/saturação HSL da cor (0 para branco; cresce com a saturação).
3. Para cada objeto da pilha (na ordem do preset), se não está desligado (ou está em solo quando
   há solo) e se `SoloFlareID` não filtra, chama o desenhador do tipo (§6).
4. Finaliza: aplica colorização por pixel (mistura entre o pixel e a cor da luz pesada pela
   luminância), acumula o buffer da luz no buffer principal e zera o buffer da luz.

Depois de todas as luzes: pós-processamento (§7) e, se Blend Mode = Screen, uma curva de
compressão por pixel (aproximadamente `0,6·f(2x+1)`, ver "não verificado").

## 5. Preparação comum a todo objeto

Função compartilhada por todos os tipos. Produz, a partir dos parâmetros do objeto (ids do doc 02):

- **Posição no eixo**: `distância` (id 2, %) percorre da luz (0) ao centro (1); valores >1 passam
  do centro, <0 ficam atrás da luz. Translation (id 6): *Free* = ao longo do eixo; *Horizontal* = só o X
  acompanha a luz; *Vertical* = só o Y; *None* = fica na luz; *Custom* = pesos de Custom
  Translation (id 23). Depois soma Offset (id 3, % da tela) multiplicado pelo "scale offset"
  global. Isto é `pos = luz + (centro − luz)·d.x + offset`; nos modos que não são Free soma-se ainda
  `(centro − luz)·d.y` (segundo componente da distância).
- **Escala** = Scale global × Scale do objeto (id 1) × Stretch (id 85, xy) × (fator de escala
  por luz). `Ignore Global Scale` (id 27) e `Ignore 3D Perspective` (id 10) zeram os fatores
  correspondentes.
- **Brilho** = Brightness global × brilho da luz × Brightness do objeto (id 0); `Ignore Global
  Brightness` (id 26) remove o fator global.
- **Cor**: Color Source (id 7): *Global* = cor da luz; *Custom* = Color 1 (id 4); *Spectrum* =
  gradiente arco-íris; *Gradient* = Color 1 → Color 2 (id 102). Gradient Loops (92) e Gradient
  Offset (97, convertido para `(v+30)/360`) parametrizam; Reverse (98) inverte. No modo Multiply
  do nó, a cor do objeto é multiplicada pela cor da luz.
- **Aspect** = aspect global × aspect do objeto (id 8).
- **Trigger** (grupo Dynamic Triggering, id 106 liga): calcula um fator `t ∈ [0,1]` pela posição
  do objeto (ou da luz, Trigger Mode) relativa a uma borda (From Border, com Border Width e
  Expansion), ao centro ou à luz; `t` passa por Inner/Outer Falloff e pelo Falloff Type (Linear,
  Smooth = sigmoide `1,02/(1+e^(5−10t)) − 0,01`, Exponential = `t²`); Invert inverte. Com `t` em
  mãos: brilho += Brightness Offset·t, escala += Scale Offset·t, stretch, rotação (107, graus),
  completion, outline, spread, thickness e cor (Color Shift misturada por `t`). As opções 1-Way
  prendem o efeito a 1 quando o objeto está dentro da área.
- **Matte Box** (global 36/37/38): fator pela distância da luz à borda da tela em caixa ou
  elipse, com Start Range e Fade; `Exclude From Matte Box` (id 40) ignora.
- **Flicker/animação**: a semente aleatória do objeto é `Random Seed (id 18) + semente global
  (inteiro)`; para cada objeto o original chama `srand(seed)` e depois `rand()` em sequência fixa.
  Para reproduzir os presets **exatamente** (posições das cópias do Multi Iris, comprimento dos
  raios do Glint, etc.) é preciso o mesmo gerador: o `rand()` do CRT da Microsoft (LCG
  `x = x·214013 + 2531011`, retorna `(x >> 16) & 0x7fff`) e a mesma ordem de chamadas. O flicker
  usa `evolução = Amount·0,05·frame + Evolution` quando Enable (id 110) está ligado.

Auto Rotate (id 41): *None* usa só Rotation (id 5) + rotação global (que entra só se `Ignore
Global Rotation` (id 22) está desligado); *To Light* e *To Center* somam o ângulo `atan2` do
vetor objeto→luz ou objeto→centro (com o aspect aplicado ao eixo y).

## 6. Os elementos

Todos são desenhados como geometria 2D (quads ou leques de triângulos) rasterizada em CPU com um
"shader" por pixel, ou pela GPU com shaders GLSL equivalentes. Para o plugin novo basta a versão
CPU. Convenções: `r` = distância ao centro do elemento normalizada (1 na borda do quad), `c` = cor
do objeto (ou do gradiente/espectro no ponto), `b` = brilho final; o shader **soma** `c·b·forma`
no pixel (blend aditivo), RGBA.

**Espectro/gradiente por pixel.** Com Color Source = Gradient: `t = u·loops + offset`, cor =
mistura de Color 1 e Color 2 por `0,5 + 0,5·sin(2π·t)` (invertido se Reverse). Com Spectrum:
`t = frac(u·loops + offset)` e as três componentes são parábolas deslocadas de um terço:
`R = 1 − (2,5·frac(t−0,3) − 1)²`, `G = 1 − (2,5·t − 1)²`, `B = 1 − (2,5·frac(t+0,3) − 1)²`, cada uma
limitada em `[0, 1]`, onde `u` é a coordenada do elemento (raio para glow/círculo/iris, posição
ao longo do raio para streak e sparkle, ângulo para hoop).

**Glow (1).** Quad de lado 2·escala (×0,002 do Scale) centrado em `pos`, girado por rotação +
auto-rotate. Por pixel: `d = sqrt(u²+v²)`; `forma = (brilho / (d + 0,5))^gamma − 0,005`, com
`gamma = 1/(Gamma do objeto)`; soma se > 0. O brilho ≤ 1 é remapeado para `0,7b² + 0,3b` e o
tamanho do quad escala com `2·(b/0,005^(1/γ) − 0,5)` para cobrir a cauda (na prática o quad é
grande; pode-se usar um raio de corte).

**Streak (2).** Replicador: `Replicator Copies` (id 32) cópias espalhadas por `Replicator Angle`
(id 33, graus) a partir de Rotation + auto-rotate, com `Spacing Random` (id 65) e `Scale Random`
(id 34) por cópia (seed do objeto). Cada cópia é um leque de 8 vértices (centro + 7 pontos em
ângulos fixos 0, 45°, 90°, 135°, 180°, 225°, 270° a partir de `Symmetry`/`Fan Ends`): comprimento
= Length (id 69) × escala × 12 × 0,01; espessura = Thickness (id 67) × escala × 0,08 × 0,01.
Por pixel (coordenadas `x` ao longo, `y` transversal, `s` posição 0..1 na cópia):
`fan = (1 + (Fan Ends−1)·0,1·feather)` aplicado como `y' = y·((1,42−|x|)/1,42·fan + 1−fan)^5`;
`d = 10·sqrt(x² + y'²)`; `forma = 1/(d + CoreIntensity) − 0,09`, com um amaciamento quadrático
abaixo de 0,06. Core Intensity (68) entra como o termo somado a `d` (0,9/valor).

**Círculo (Ring 6, e Iris/Multi Iris com Shape = Circle).** Quad girado; por pixel `r` = raio;
`forma` = rampa linear de 1 no centro até 0 em `r = 1` suavizada por `Smoothness` (`(1−r)/smooth`
limitado a 1). O Ring usa Thickness (56) como raio interno (`1 − thickness`) e Inside/Outside
Feathering (57/58) como larguras de transição; Convex Roundness (93) deforma o quad
(`escala·(1 − |pos−0,5|·0,5·convex)` e um cisalhamento). Outline Intensity/Thickness/Feathering
(46/44/45) adicionam uma borda: rampa `1 − (1−r)/thick` dividida por feather, pesada por
intensity. Circular Completion (49/50/60): se Completion < 360°, pixels cujo ângulo polar
(relativo a Completion Rotation + auto-rotate completion) excede o setor são atenuados por
`1 − ((|a| − comp)/(2π − comp))/feather`.

**Iris polígono (15/4, Shape = Polygon).** Leque de `N·k + 2` vértices onde `N` = Polygon Sides
(12) e `k` = 10 ou 11 subdivisões por lado quando há Roundness (42) ou Notching (43), senão 1.
Cada vértice é interpolado entre os cantos do polígono e a circunferência por Roundness, com
recorte por Notching; a coordenada `v` do vértice é 1 na borda e 0 no centro, e o shader é o
mesmo do círculo (rampa por `v`, outline, completion). Shape Orientation (87) gira a forma antes
da rotação do objeto. Convex (93) e aspect idem ao círculo.

**Iris textura (Shape = Texture).** Quad com UV 0..1; por pixel amostra o PNG (bilinear, com
pré-escala quando o quad é menor que a textura), multiplica RGB da textura pelo alfa e pela cor
do objeto, brilho e completion.

**Multi Iris (4) e Lens Orbs (14).** Replicador: `Number of Objects` (14) cópias; para cada uma,
com o `rand()` do objeto: rotação aleatória (Rotation Random 47), distância no eixo = Spread (13)
× random + (1 − Spread) … (ou seja, espalha ao longo do eixo centro→luz), Offset Random (48)
perpendicular (multiplicado pelo comprimento do eixo), Scale Random (15), cor com Color Random
(35, gira a matiz em HSL), Smoothness Random (25), Brightness Random (16), Rotation Random (62)
da completion e Orientation Random (113). Cada cópia chama o desenhador de Iris. Lens Orbs usa o
mesmo laço com Spread = 0, cópias espalhadas pela tela inteira (offset aleatório em ±0,5 da
tela, com wrap) e brilho pesado por `1 − dist(cópia, luz)/Illumination Radius` (63).

**Shimmer (5).** Três leques de `Complexity` (52) raios cada (a 0°, 120° e 240° do ângulo base),
comprimento de cada raio = `1 − rand·v` onde `v` depende de Detail (53) e do flicker; shader
`SpikeShader`: `forma = 0,5/(0,3·s + 0,05)·(1 − s)·brilho` com `s` = posição ao longo do raio.
Brilho do objeto ×0,0002; escala ×0,01.

**Glint (8).** Um leque de `Complexity` raios com ângulos `2πi/N + orientação + rand·spread
(id 41)` e comprimento `1 − rand·LengthRandom`, Thickness (67) ×0,03; shader `GlintShader`
(mesma fórmula do Shimmer). Brilho ×0,00015, escala ×0,003.

**Sparkle (9).** `Complexity` raios, cada um um quad fino (6 vértices, 2 triângulos) com
comprimento `(1 − rand·LengthRandom)·Length·0,03`, espessura `(1 − rand·ThicknessRandom)·0,02`,
brilho por raio `1 − rand·BrightnessRandom`, espalhamento por Spread/Spread Random; shader
`SparkleShader`: `forma = max(0, 1 − r)·brilho·peso_do_raio`.

**Spike Ball (11).** `Complexity` raios como no Sparkle, com Thickness/Length/Brightness Random e
seed deslocada de +4; shader `SpikeBallShader`: `forma = (1 − |atan2(v,u)|·0,77)⁺ ·
(1 − r)⁺ · peso / (sqrt(5·(5u² + v²)) + 0,25)`.

**Hoop (7).** Semicírculo/anel pontilhado: `Complexity` segmentos ao longo de um arco de
Completion (49) graus, raio dado pela distância luz–centro × Scale, Line Thickness (105) e Line
Spacing (120), Length (67) do arco, Detail (53) dá o ruído por segmento (mesmo `sin(6,15·rand +
flicker)` do Shimmer); shader `HoopShader` (`forma = (1 − r)·v·brilho`) ou `HoopShaderSpectrum`
quando Color Source = Spectrum (cor pelo ângulo).

**Caustic (12).** Composto: um círculo grande (Ring Brightness 118, Ring Outline 119 como
outline), um segundo círculo menor e dois polígonos (Core Brightness 114, Core Roundness 116,
Core Distortion 117), todos atenuados pela distância da luz ao centro (`1 − d·0,4` na escala).

## 7. Pós-processamento (buffer inteiro, depois de todas as luzes)

1. **Lens Texture** (global 19 + 100 Brightness + 101 Falloff + 1 Scale + 3 Offset): se houver
   textura, ela é sobreposta multiplicando/somando com brilho pesado pela distância ao centro
   (falloff). Não lido em detalhe.
2. **Aberração cromática** (globais 55 tipo, 51 Intensity, 84 Spread): amostra o buffer em
   posições deslocadas radialmente (`±spread·0,002·largura` por canal); *Purple Fringe* desloca
   R e B contra G; *Red/Blue Shift* desloca R e B em sentidos opostos.
3. **Correção de cor** (global 54 Saturation, 66 Contrast, 0 Brightness): converte para HSL,
   multiplica S por `1 + 0,01·sat`, volta a RGB, e aplica contraste (`<1`: mistura com cinza 0,5;
   `>1`: curva em S); clampa em ≥ 0.
4. **Dynamic Trigger de preview** (global 79): desenha o gradiente do trigger por cima, só no
   editor.

## 8. Oclusão e amostragem da matte (entrada `matte`)

Para cada luz, antes de renderizar:

- **2D** (`Enable2DOcclusion`): copia um bloco de até 128×128 px da entrada matte em volta da luz;
  média de RGBA num raio `LightRadius` (máx. 64); `f` = alfa (ou luma = 0,3R + 0,59G + 0,11B, ou
  os invertidos, por Sample Method) × (1 − fator); brilho da luz ×= `1 − f` (Alpha) etc. Com
  `SampleColor`, a cor da luz vira `f·cor_amostrada + (1−f)·cor`.
- **3D** (`EnableOcclusion`): lê o canal Z (profundidade) da matte no mesmo bloco (1/z a menos
  que `NormalizeDepthData`); fração dos pixels com profundidade menor que a da luz, com
  transição linear de largura `OcclusionTestRadius`; brilho ×= `1 − fração`.

## 9. GPU vs CPU no original

O original usa OpenGL (FBOs, shaders GLSL com os mesmos nomes de uniforms: `glowPos`, `glowScale`,
`circleSmooth`, `irisSides`, `streakAngles`…) quando `GPU` está ligado e a variável
`OPTICAL_FLARES_NO_GPU` não está definida; senão rasteriza em CPU com os mesmos vértices e um
shader por pixel por tipo (`GlowShader`, `StreakShader`, `CircleShader`, `IrisShader`,
`CustomShader`, `SpikeShader`, `GlintShader`, `SparkleShader`, `HoopShader`,
`HoopShaderSpectrum`, `SpikeBallShader`). O rasterizador CPU é um scanline simples por triângulo
(leque, tira ou lista), interpolando 4 atributos por vértice, sem antialiasing e **sem
multithreading** (um frame inteiro por request). O plugin novo pode paralelizar por linhas sem
mudar o resultado, porque cada pixel é independente.

## 10. Plano de implementação sugerido

1. Parser `.ofp` em C++ (espelho do `ofp_dump.py`) + tabela de definições por tipo (ids, tipos,
   defaults) para criar objetos completos a partir de arquivos parciais.
2. Nó com os knobs da §1 e o knob `renderOptions` (string hex) para compatibilidade de script.
3. Buffer RGBA float do formato; luzes 2D; preparação comum (§5) sem trigger/flicker.
4. Elementos em ordem de frequência: Multi Iris/Iris (círculo e polígono) → Glow → Streak →
   Ring → Shimmer → Hoop → Glint → Spike Ball → Sparkle → Lens Orbs → Iris textura → Caustic.
5. Colorize, blend Screen, gamma 2,2 na saída, Render Mode.
6. Trigger, flicker, matte box, oclusão 2D, aberração, correção de cor, lens texture.
7. 3D (câmera e luzes da cena) por último.

## 11. Não verificado / incerto

- A curva exata do Blend Mode = Screen (`FUN_1800780c0`, não lida).
- Detalhes do Lens Texture (sobreposição) e da aberração (ordem R/B).
- O quad do Glow usa cantos em ±√2 girados; o fator `2·(b/0,005^(1/γ) − 0,5)` é a minha leitura
  do cálculo do tamanho e precisa de teste visual.
- Constantes empíricas (0,002, 0,08, 12, 0,0002, 0,03…) foram lidas do código e podem ter
  arredondamento na decompilação; conferir com renders.
- Modos Track Lights, Mask e Luminance do Source Type.

## 12. Estado da implementação (2026-10-21)

Implementado em `src/FlareRenderer.cpp` (renderizador em CPU) e `src/OpticalFlares.cpp` (nó):

- Os 12 tipos de elemento, preparação comum (posição, escala, cor, gradiente/espectro), Dynamic
  Triggering, Matte Box, Colorize por luz, Blend Mode = Screen, Lens Texture (Glass), aberração
  cromática, saturação/contraste. Texturas lidas com o WIC do Windows, com mipmaps.
- Flicker por elemento: `fase = Animation Evolution · 10` quando Enable (id 110) está ligado. O
  termo `Speed (id 108) · 0,05 · tempo` do original recebe tempo 0 no Nuke, então só a Animation
  Evolution anima.
- Oclusão 2D: média num quadrado de ±`LightRadius` (máx. 64 px) em volta da luz; alfa médio `a` e
  cor média pré-multiplicada. Fator: Alpha `1 − a`, Alpha Invert `a`, Luma `1 − a·luma`,
  Luma Invert `a·luma` (luma = 0,3R + 0,59G + 0,11B). Brilho da luz ×= fator; Sample Color mistura a
  cor da luz com a amostrada pelo mesmo fator.
- Show Foreground: `saída = k·matte + (1 − k)·saída`, `k` = alfa da matte quando o alfa é pedido,
  senão 1.
- Rasterização: o original cobre a linha `r` quando `r + 0,25` cai dentro do triângulo; a largura da
  linha é medida nesse mesmo ponto (medir em `r` deixava buraco em raios exatamente horizontais).

Reconstruído ou incerto (confere visualmente, sem render de referência):

- Hoop: orientação do arco e as duas variantes (tira com espectro e quads) foram montadas a partir
  do desenho dos vértices; o original usa a variante tira em 128 de 142 presets.
- Argumentos dos shaders do Sparkle e do Spike Ball (quais atributos entram em cada termo).
- Orientação da textura no Iris com textura.
- Grupo Flicker do nó (Type, Speed, Amount, Randomize, Random Seed): o nó original preenche vetores
  de brilho/cor por luz que não achei sendo calculados na versão Nuke; aqui os knobs existem mas não
  alteram o render.
- 3D (luzes da cena e câmera, oclusão por profundidade): ainda não implementado.
- Texturas citadas por presets antigos que não existem na pasta Elements ("Sharp Disc",
  "Textured Circle", "Grainy Lens", "Crecent Moon", "Pentagon", "Specks"): o elemento é pulado.

### Desempenho e browser (2026-10-21, segunda rodada)

- O render divide o quadro em faixas de 16 linhas e usa todos os núcleos menos um (threads do
  Windows; `OFNDK_THREADS` força outro número). Cada faixa refaz a geometria e desenha só nas suas
  linhas, então o resultado é idêntico ao de um núcleo (conferido byte a byte nos 243 presets). A
  aberração lê vizinhos e roda numa segunda passada. Em 2048×1556: 3 a 10 vezes mais rápido.
- O knob `GPU` do original continua salvo no script, mas fica escondido: não há caminho de GPU.
- O botão `Options` (mesmo nome do original) abre `ofndk_browser.py`, um browser em PySide
  (PySide2 no Nuke 15, PySide6 no 17). As miniaturas vêm do `ofthumb.dll`, que usa o mesmo
  renderizador sem depender do Nuke, e ficam em `%LOCALAPPDATA%/OpticalFlaresNDK/thumbs`. O
  preview grande usa a posição da luz e do centro do nó. Aplicar grava `renderOptions`,
  `ofpPresetName` e `ofpPresetFile` num único undo.
