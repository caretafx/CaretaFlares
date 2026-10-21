# 02 — Formato dos presets `.ofp` e do estado salvo no `.nk`

Resultado do estudo com o REA (Ghidra) sobre o `OpticalFlares.dll` 1.0.86, em 2026-10-21.
Tudo aqui está descrito com as nossas palavras; nenhum trecho de código ou dado da Video Copilot
foi copiado. O leitor `tools/ofp_dump.py` foi escrito a partir desta descrição e lê os 243 presets
da instalação sem erro nem aviso.

## 1. Container

| Campo | Conteúdo |
|---|---|
| bytes 0..2 | assinatura ASCII `OFP` |
| byte 3 | versão, sempre `3` (o plugin recusa qualquer outra) |
| resto | sequência de registros `tag (u16 LE) + tamanho (u16 LE) + payload` até o fim do arquivo |

Não há checksum, cifra nem compressão. Os presets de fábrica, os "Custom Objects" e o estado
gravado dentro do script do Nuke usam exatamente o mesmo corpo de registros.

## 2. Registros

| Tag | Payload | Significado |
|---|---|---|
| 3000 | 1 byte (0) | começa o bloco de parâmetros globais do flare |
| 4000 | 1 byte (0) | termina o bloco global |
| 1 | int32 | abre um objeto do tipo N (tabela §4); cria o objeto com todos os parâmetros do tipo nos valores de fábrica |
| 2 | 64 bytes | nome do objeto, terminado em NUL (os bytes após o NUL são lixo de memória do gravador; ignorar) |
| 3 | 1 byte | objeto desligado (1 = não renderiza, a menos que esteja em solo) |
| 4 | 1 byte | solo (1 = quando qualquer objeto está em solo, só os em solo renderizam) |
| 1000 | 1 byte (0) | fecha o objeto |
| 50 | int32 | id do parâmetro seguinte (o id 91 é tratado como 7 ao carregar) |
| 51 | int32 | tipo do parâmetro (tabela §3); se não bater com a definição do tipo, o valor é ignorado, exceto que float (0) e float2 (1) são intercambiáveis |
| 52 | 32 bytes | valor do parâmetro, copiado sobre o valor atual |
| 2000 | 1 byte (0) | fecha o parâmetro |

Regras de leitura observadas:

- Um parâmetro só é aplicado se o **objeto corrente** (ou o bloco global) tiver um parâmetro
  com aquele id. Ids desconhecidos são ignorados em silêncio; o formato é tolerante a versões.
- Floats (tipo 0) são limitados ao intervalo `[min, max]` da definição quando `min < max`.
- Texturas (tipo 5) são resolvidas **na carga**: o nome gravado é comparado, sem diferenciar
  maiúsculas, com os nomes dos arquivos da pasta de texturas; o resultado é um índice. Se o nome
  terminar em ` (U)`, o sufixo é removido antes de comparar (textura do usuário).
- O gravador escreve primeiro os globais e depois os objetos, na ordem em que estão na pilha do
  editor. A ordem dos objetos é a ordem de desenho.

Tamanhos fixos usados pelo gravador, úteis para conferir arquivos: cada parâmetro ocupa 57 bytes
(4+4, 4+4, 4+32, 4+1); cada objeto ocupa 86 bytes de cabeçalho (tipo, nome, 2 flags) mais os
parâmetros mais 5 bytes do fechamento.

## 3. Tipos de parâmetro e layout dos 32 bytes

| Tipo | Nome | Conteúdo dos 32 bytes |
|---|---|---|
| 0 | float | `float[0]` é o valor; o resto é zero |
| 1 | float2 | `float[0]`, `float[1]` (ex.: Scale X/Y, Offset X/Y, Stretch) |
| 2 | color | `uint32` em `float[0]`: R nos 8 bits baixos, G nos 8 seguintes, B nos 8 seguintes (0..255) |
| 3 | enum | `int32` com o índice da opção |
| 4 | bool | `int32` 0/1 |
| 5 | texture | `int32` índice (resolvido na carga) + nome do arquivo sem extensão nos 28 bytes restantes |
| 6 | divider | sem valor; é só um título de seção no editor (id 24, repetido várias vezes) |

Unidades: quase tudo é gravado em **percentual** (100 = 1.0) ou em **graus**. O renderizador
multiplica por 0,01 ou por π/180 ao usar. As exceções estão anotadas na tabela de parâmetros.

## 4. Tipos de objeto

| Tipo | Nome no editor | Observação |
|---|---|---|
| 1 | Glow | |
| 2 | Streak | com replicador (cópias em leque) |
| 4 | Multi Iris | compartilha a definição de parâmetros com o Iris (15) |
| 5 | Shimmer | |
| 6 | Ring | |
| 7 | Hoop | |
| 8 | Glint | |
| 9 | Sparkle | |
| 11 | Spike Ball | |
| 12 | Caustic | desenhado como 2 círculos + 2 polígonos derivados |
| 14 | Lens Orbs | usa o replicador do Multi Iris com parâmetros próprios |
| 15 | Iris | forma: polígono, círculo ou textura |
| 3, 10, 13 | — | o renderizador ignora; não aparecem em nenhum preset da instalação |

Contagem nos 243 presets instalados: Multi Iris 1224, Iris 670, Glow 483, Streak 475, Ring 213,
Shimmer 168, Hoop 142, Glint 112, Spike Ball 102, Sparkle 100, Lens Orbs 52, Caustic 14.

## 5. Parâmetros

A lista completa (id, tipo, rótulo do editor, valor de fábrica, limites quando recuperados) está
em `docs/anexo-parametros.txt`, extraída da função que monta os objetos. Resumo da estrutura:

**Grupos comuns** (adicionados a quase todos os tipos, nesta ordem):

- *Common Settings*: 0 Brightness (%), 1 Scale (%), 85 Stretch (xy %), 2 Distance (xy %),
  103 Distance (float), 3 Offset (xy %), 6 Translation (enum Free|Horizontal|Vertical|None|Custom),
  23 Custom Translation (xy %), 8 Aspect Ratio.
- *Colorize*: 7 Color Source (enum Global|Custom|Spectrum|Gradient), 4 Color 1, 102 Color 2,
  92 Gradient Loops, 97 Gradient Offset, 98 Reverse Gradient.
- *Advanced Settings*: 10 Ignore 3D Perspective, 26 Ignore Global Brightness, 27, 28, 29 …
- *Matte Box Controls*: 39 Start Range Offset (e 40 Exclude From Matte Box).
- *Dynamic Triggering*: 106 Enable Trigger, 75 Brightness Offset, 76 Scale Offset,
  123 Stretch Offset, 107 Rotation Offset, 78 Completion Offset, 86 Outline Intensity Offset,
  96 Spread Offset, 121 Thickness Offset, 83 Color Shift, 71 Trigger Type
  (From Border|From Center|From Light), 81 Trigger Mode (Object Position|Light Position),
  99 Invert Trigger, 77 Border Width, 72 Expansion, 80 Inner Falloff Range, 73 Outer Falloff
  Range, 74 Falloff Type (Linear|Smooth|Exponential), 122 Trigger Stretch, 79 Preview Trigger,
  82 Offset Trigger Location, 88/89/90 1-Way Brightness/Scale/Color.
- *Animation Controls* (Flicker): 110 Enable, 108 Speed, 109 Amount.

**Por tipo** (além dos grupos): 5 Rotation (graus), 41 Auto Rotate (None|To Light|To Center),
22 Ignore Global Rotation; e os controles próprios: Streak 69 Length, 67 Thickness, 68 Core
Intensity, 30 Symmetry, 31 Fan Ends, 70 Fan Feathering, 32 Replicator Copies, 33 Replicator
Angle, 34 Scale Random, 65 Spacing Random, 18 Random Seed; Iris/Multi Iris 35 Color Random,
13 Spread, 61 Spread Random, 14 Number of Objects, 15 Scale Random, 16 Brightness Random,
47 Rotation Random, 48 Offset Random, 18 Random Seed, 11 Shape Type (Polygon|Circle|Texture),
19 Texture Image, 87 Shape Orientation, 113 Orientation Random, 12 Polygon Sides,
42 Polygon Roundness, 43 Blade Notching, 17 Smoothness, 25 Smoothness Random, 46 Outline
Intensity, 44 Outline Thickness, 45 Outline Feathering, 49 Completion, 50 Completion Feathering,
60 Completion Rotation, 62 Rotation Random, 59 Auto Rotate Completion; Shimmer 52 Complexity,
53 Detail; Ring 56 Thickness, 57 Inside Feathering, 58 Outside Feathering, 93 Convex Roundness;
Hoop 52 Complexity, 53 Detail, 67 Length, 105 Line Thickness, 120 Line Spacing; Glint/Sparkle/
Spike Ball 52 Complexity, 69 Length, 94 Length Random, 67 Thickness, 111 Thickness Random,
16 Brightness Random, 13 Spread, 95 Spread Random, 65 Spacing Random; Caustic 118 Ring
Brightness, 119 Ring Outline, 114 Core Brightness, 116 Core Roundness, 117 Core Distortion;
Lens Orbs 14 Number of Objects, 63 Illumination Radius, mais a forma do Iris.

**Globais** (bloco 3000…4000; ids no mesmo espaço): 112 Scale (%), 8 Aspect Ratio, 9 Blend
Mode (Add|Screen), 4 Color (global), 18 Global Seed, 36 Matte Box Shape (None|Box|Ellipse),
37 Start Range, 38 Fade Amount, 19 Lens Texture (textura da pasta Glass), 63 Illumination
Radius, 101 Falloff, 100 Brightness (da lens texture), 1 Scale (xy), 3 Offset (xy),
55 Aberration Type (None|Purple Fringe|Red/Blue Shift), 51 Intensity, 84 Spread, 0 Brightness
(correção de cor), 66 Contrast, 54 Saturation. Os ids 124 e 125 aparecem no preset padrão
embutido no DLL (valores 100 e 0) e não foram mapeados.

## 6. Estado dentro do script do Nuke (`renderOptions`)

O nó tem um knob custom invisível chamado `renderOptions` (flags INVISIBLE | ALWAYS_SAVE). O que
ele grava no `.nk` é uma string de texto:

```
<N>;<2N caracteres hexadecimais minúsculos>
```

onde `N` é o tamanho em bytes do corpo binário (o mesmo container `OFP\x03` + registros, gerado
pelo mesmo gravador dos presets, limitado a 1 MB) e cada byte é escrito com dois dígitos hex.
Na leitura o plugin lê o inteiro até o `;`, confere que a quantidade de dígitos dividida por dois é
igual a `N` (senão avisa "unable to restore state, data is corrupted" e mantém o estado atual) e
devolve os bytes ao mesmo parser dos presets.

Consequências para o plugin novo: basta implementar um knob de string com esse nome, com o
mesmo formato, para que scripts antigos reabram com o flare inteiro, inclusive flares editados
que nunca foram salvos como `.ofp`. O preset padrão (quando o knob está vazio) é um flare
embutido no DLL com 27 objetos (6 Glow, 6 Iris, 9 Multi Iris, 3 Ring, 1 Shimmer, 2 Streak), todos
desligados; o plugin novo pode usar qualquer `.ofp` da instalação como padrão.

## 7. Texturas

- Pasta `Optical Flares Textures/Elements/`: PNGs usados pelo Iris com Shape Type = Texture
  (parâmetro 19 dos objetos). O renderizador lê todos os arquivos da pasta na inicialização,
  decodifica com libpng para RGBA 8 bits e indexa pelo nome do arquivo sem extensão.
- Pasta `Optical Flares Textures/Glass/` (ou a variável de ambiente
  `OPTICAL_FLARES_CUSTOM_LAYER_PATH`): "custom layers", usadas pelo parâmetro global 19 (Lens
  Texture) e pelo recurso de camadas personalizadas do editor.
- A lista de texturas é global ao processo; os presets guardam só o nome.

## 8. O que ainda não foi verificado

- O significado dos ids globais 124 e 125.
- Os limites (`min/max`) de alguns parâmetros construídos de forma inline (marcados com `?` no
  anexo). Para o plugin novo eles só importam se quisermos clampear como o original.
- Se existe diferença entre os `.ofp` dos pacotes `Pro_Presets*.zip` e os instalados (os zips
  não foram extraídos; o formato é o mesmo).
