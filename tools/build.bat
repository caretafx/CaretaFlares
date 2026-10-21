@echo off
rem Compila o plugin para Nuke 15.2 e 17.0 e a ferramenta de teste.
rem Use tools\build_low.cmd para rodar em prioridade baixa.
setlocal
set ROOT=%~dp0..
set VS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
set CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe
set NINJA=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe

for %%V in (15.2v9 17.0v2) do (
    echo ==== Nuke%%V
    "%CMAKE%" -S "%ROOT%" -B "%ROOT%\build\Nuke%%V" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="C:/Program Files/Nuke%%V" || exit /b 1
    "%CMAKE%" --build "%ROOT%\build\Nuke%%V" -j 2 || exit /b 1
)
echo BUILD OK
