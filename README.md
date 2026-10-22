# CaretaFlares

Plugin de lens flares para Nuke, escrito do zero no NDK (C++) com a janela Options em
Python/PySide. Nó `CaretaFlares`; também responde pelo nome antigo `OpticalFlares`, então
scripts feitos com o Optical Flares da Video Copilot (1.0.86, só até o Nuke 13.0) abrem nele
com os mesmos knobs.
Alvos: Nuke 15.2v9 e Nuke 17.0v2, Windows x64.

O plugin lê os presets (.ofp) e texturas da instalação do usuário em tempo de execução.
Nenhum arquivo da Video Copilot (código, presets, texturas, licença) entra neste repositório.
Uso pessoal; nada é publicado.

Documentos em `docs/`, na ordem numérica. Ferramentas auxiliares em `tools/`.

## Estado (2026-10-21)

- `docs/01-inventario-e-plano.md`: inventário e plano.
- `docs/02-formato-ofp.md`: formato dos presets e do estado salvo no `.nk`.
- `docs/03-comportamento-render.md`: knobs, pipeline e matemática de cada elemento.
- `tools/ofp_dump.py`: leitor/validador de `.ofp` (lê os 243 presets instalados sem erro).
- `tools/peinfo.py`, `tools/exports.py`: inspeção de PE usada no inventário.

## Compilar e testar (branch feat/esqueleto-plugin)

- `tools\build_low.cmd` compila em prioridade baixa para Nuke 15.2v9 e 17.0v2
  (saída em `build\Nuke15.2v9` e `build\Nuke17.0v2`, log em `build\build.log`).
- `build\Nuke15.2v9\oftool.exe scan <pasta de presets>` valida o parser;
  `oftool render <preset> W H X Y saida.ppm` renderiza sem o Nuke.
- `tools\nuke_test.py` carrega o DLL novo no Nuke sem mexer no `~/.nuke`.
- `python tools\make_dist.py` monta `dist\CaretaFlares` (pasta-plugin completa: DLLs por
  versão, janela Options, ícone, presets e texturas), no formato das pastas do `_AutoInstaller`.

Estado: nó completo em knobs (nomes do original), estado `renderOptions` compatível,
carregamento de `.ofp` e o elemento Glow desenhado. Os demais elementos são ignorados.
