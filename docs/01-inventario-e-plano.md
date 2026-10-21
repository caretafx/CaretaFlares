# 01 — Inventário e plano

Data: 2026-10-21. Primeira entrega: o que existe na máquina, o que isso implica, e um plano curto.

## 1. O instalador (`OpticalFlares_Nuke_1.0.86.zip`, 690 MB, 800 arquivos)

| Item | Conteúdo |
|---|---|
| `OpticalFlares_Nuke_12.0_Node-Locked_1.0.86.zip` | `plugin/Windows/OpticalFlares.dll`, `plugin/Linux/OpticalFlares.so`, `plugin/Mac/OpticalFlares.dylib`, `Menu/menu.py` |
| `OpticalFlares_Nuke_12.1_...zip`, `12.2_...zip` | só `plugin/OpticalFlares.dll` (Windows) + `Menu/menu.py` |
| `OpticalFlares_Nuke_13.0_Node-Locked_1.0.86.zip` | Windows/Linux/Mac + `Menu/menu.py`. O DLL é **byte a byte igual** ao instalado em `~/.nuke/OpticalFlares/plugin` (md5 `26031bfb…`) |
| `Program Files/Nuke12.0v8/Optical Flares Presets` e `Textures` | presets e texturas de fábrica (os mesmos que estão instalados) |
| `Pro_Presets.zip` (1,5 MB) e `Pro_Presets_2.zip` (125 MB) | pacotes extras de presets |
| `OpticalFlaresLicense.lic` (47 KB) | licença node-locked (não foi lida; fica fora do projeto) |
| `menu.py add to end with notepad.txt`, `Users/YOURUSERNAME/.nuke/menu.py` | as 3 linhas do toolbar, iguais às do seu `menu.py` |

**Não há** documentação, SDK, código-fonte, builds para 13.1+ nem para 14/15/16/17.
Existe um build por versão *minor* do Nuke (12.0, 12.1, 12.2, 13.0). Isso já diz que o
NDK não é compatível entre minors, confirmado abaixo.

## 2. A instalação atual (`C:\Users\Mauricio\.nuke\OpticalFlares`, só leitura)

- `plugin/OpticalFlares.dll` (1,73 MB) e cópia `OpticalFlares_orig_13.0.dll`, idênticos.
- `Optical Flares Presets/`: 243 `.ofp` no total: 100 na raiz, 50 em `Custom Objects/`,
  o resto em `Lens Flares/{Conspiracy, Light, Motion Graphics, Natural Flares, Nuclear, _Custom Presets}`.
- `Optical Flares Textures/`: `Elements/` (74 png) e `Glass/` (27 png). Total 103 png (2 são ícones).
- `OpticalFlaresLicense.lic`, `icons/`.
- `init.py` define `OPTICAL_FLARES_PATH`, `_LICENSE_PATH`, `_PRESET_PATH`, `_TEXTURE_PATH` e adiciona
  `plugin/` ao pluginPath. `menu.py` cria o nó pela toolbar "VideoCopilot".

## 3. O DLL 1.0.86 (olhada superficial, sem REA ainda)

| Fato | Evidência |
|---|---|
| Compilado em 2021-04-09 com **MSVC 14.16 (VS 2017 15.9)** | cabeçalho PE; caminho do pdb `C:\customers\VC\ofnuke\ofnuke\Win\x64\13.0-Release\OpticalFlares.pdb` |
| Importa **225 símbolos** de `DDImage.dll` (Op, Iop, Knob, virtuais) | tabela de imports (anexo `anexo-imports-ddimage-1.0.86.txt`) |
| Exige o marcador de ABI `DD::Image::Op::DDImage_ABI_13_0_1` | import; o Nuke 13.2 exporta `DDImage_ABI_13_2_1`, o 15.2 `15_2_1`, o 17.0 `17_0_1` |
| Fora o marcador de ABI, **só 1 símbolo some** no Nuke 17 (`Op::Description` ganhou um parâmetro `License*`) e **nenhum** no 15.2 | comparação de exports |
| Usa **OpenGL** (41 funções de `OPENGL32.dll`, pbuffer/FBO/shaders) com fallback por `OPTICAL_FLARES_NO_GPU` | strings e imports |
| O editor de flares é uma **janela Win32 própria** (user32, gdiplus, `CreateWindowExA`), não Qt | imports |
| O código é compartilhado com a versão After Effects (strings de suites `AEGP …`) | strings |
| Mensagens: `*OF* No License found`, `Hardware ID`, caminhos `%s/Optical Flares Textures`, `%s/Lens Flares/_Custom Presets/`, `%s/OpticalFlaresPref.dat` | strings |
| Preset `.ofp`: assinatura `OFP` + versão 3, depois blocos *tag/tamanho/dados* (TLV); o primeiro bloco traz o nome do elemento (`Glow`) | hexdump de `Custom Objects/Hot Glow.ofp` |

### 3.1 Consequência: o plugin antigo não carrega em NENHUM Nuke desta máquina

O Nuke checa o marcador `DDImage_ABI_<major>_<minor>_1` na carga. O 13.2 não exporta
`13_0_1`, então o `OpticalFlares.dll` de 13.0 é recusado no 13.2 do mesmo jeito que no 15 e no 17.
Isso tira a referência de imagens do caminho que você imaginou (comparar preset a preset com o
plugin antigo). Alternativas, a decidir com você:

1. **Instalar um Nuke 13.0vX** (Foundry ainda disponibiliza releases antigos; a sua licença de Nuke
   normalmente cobre). É a única forma de ter renders de referência e de extrair a lista exata de
   knobs com `writeKnobs` sem engenharia reversa. **Recomendo.**
2. Sem referência: validar "no olho" contra as miniaturas dos presets e o comportamento conhecido do
   OF no After Effects (se você tiver o OF para AE instalado em algum lugar, ele serve de referência
   parcial: mesmo motor).

Importante: o fato de só 1–2 símbolos faltarem **não** significa que dá para "remendar" o DLL antigo
para carregar no 15/17. Os símbolos existem, mas o layout das classes (vtables de `Op`/`Iop`/`Knob`)
muda entre versões; forçar a carga daria crash. E a recomendação de não mexer no binário/licença
continua valendo. O caminho é mesmo o plugin novo.

## 4. Toolchain

| Item | Estado |
|---|---|
| Visual Studio 2022 **Build Tools** 17.14, MSVC **14.44.35207**, `cl.exe` x64 | instalado |
| CMake e Ninja (embutidos no Build Tools, `Common7/IDE/CommonExtensions/Microsoft/CMake`) | instalados, fora do PATH |
| Windows SDK 10.0.26100 | instalado |
| Nuke 13.2v9, 15.2v9, 17.0v2 em `C:\Program Files`, cada um com `include/DDImage`, `DDImage.lib`, `CMake/NukeConfig.cmake` | instalados |
| `DDImage.dll` do 15.2 e do 17.0: linkados com **MSVC 14.35 (VS 2022)** | cabeçalho PE |
| Python 3.14 | instalado |

MSVC 14.44 é da mesma família de ABI que 14.35, então **o Build Tools que você já tem compila para
o 15.2 e para o 17.0** sem instalar toolset extra. Nuke 13.0 não está instalado.

## 5. Plano proposto (curto)

**Viabilidade.** Plugin novo em C++/NDK é viável e é o único caminho; o NDK dá conta de um Iop 2D
que lê arquivos e desenha procedural. Proposta de arquitetura:

- **Render em CPU** dentro de um `Iop` (ou `PlanarIop`), determinístico e testável sem GPU. Cada
  elemento do flare (glow, streak, ring, iris, ghost, caustic, textura…) vira uma função que
  desenha em um buffer linear, somado aditivamente; depois a oclusão pelo alfa da entrada.
  GPU (BlinkScript) só numa fase posterior, se o CPU ficar lento para você.
- **Sem o editor de flares na v1.** O editor original é uma aplicação Win32/OpenGL inteira; refazer
  isso é um projeto à parte. Na v1 o nó carrega `.ofp` por um knob de arquivo (com navegador nos
  diretórios de presets) e expõe os knobs do nó original, para os scripts antigos abrirem.
  Um painel Python de browser de presets pode vir na v2.
- **Compatibilidade de script:** mesmo nome de classe `OpticalFlares` e mesmos nomes de knob, para
  `.nk` antigos abrirem sem erro. Os knobs que a v1 ainda não implementar existem mas são inertes.

**Etapas.**

1. *(você decide)* Instalar Nuke 13.0 para referência; eu preparo o script que exporta a lista de
   knobs e renderiza cada preset em condições fixas (eu não abro o Nuke; você roda).
2. **Estudo com o REA** (próxima entrega): `knobs()` do nó (nomes, tipos, defaults), parser do
   `.ofp` (tags, elementos, parâmetros, curvas, texturas embutidas), e a matemática de cada
   elemento. Sai `docs/02-formato-ofp.md` e `docs/03-comportamento-render.md`, em palavras nossas,
   mais um `tools/ofp_dump.py` escrito do zero para validar o entendimento do formato contra os 243
   presets.
3. **Esqueleto do plugin:** CMake com dois targets (15.2, 17.0), nó `OpticalFlares` com a lista de
   knobs, carregando um preset e desenhando só o *glow*. Você testa no Nuke 15.2.
4. **Elementos um a um**, na ordem de frequência nos presets, cada um comparado com a referência
   (se houver) ou com as miniaturas.
5. **Testes:** render dos 243 presets em lote (`nuke -t`, combinado com você) e comparação de
   imagens.

**Riscos.** (a) Paridade pixel a pixel é improvável; a meta é equivalência visual. (b) Presets
grandes (100–270 KB) sugerem texturas/curvas embutidas: o formato pode ser mais complexo do que o
cabeçalho indica. (c) Sem Nuke 13.0, a lista de knobs e os defaults saem só do REA, com mais chance
de erro. (d) Eventuais regras de licença nos presets (`Hardware ID`): o plugin novo não lê a
licença; se um preset vier cifrado, paramos e conversamos.
