cmake_minimum_required(VERSION 3.20)
project(OpticalFlaresNDK LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# Nucleo sem dependencia do Nuke: parser .ofp e renderizador.
add_library(ofcore STATIC
    src/OfpPreset.cpp
    src/FlareRenderer.cpp
    src/TextureCache.cpp
)
target_include_directories(ofcore PUBLIC src)
# texturas lidas com o WIC do Windows
target_link_libraries(ofcore PUBLIC windowscodecs ole32)
if(MSVC)
    target_compile_definitions(ofcore PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
if(MSVC)
    target_compile_options(ofcore PRIVATE /W4 /fp:fast)
endif()

# Ferramenta de teste (roda sem o Nuke).
add_executable(oftool tests/oftool.cpp)
target_link_libraries(oftool PRIVATE ofcore)

# Plugin do Nuke. Passe -DCMAKE_PREFIX_PATH="C:/Program Files/NukeXX.Xvn".
option(OF_BUILD_PLUGIN "Compila o plugin do Nuke" ON)
if(OF_BUILD_PLUGIN)
    find_package(Nuke REQUIRED)
    add_nuke_plugin(OpticalFlares src/OpticalFlares.cpp)
    target_link_libraries(OpticalFlares PRIVATE ofcore)
    if(MSVC)
        target_compile_options(OpticalFlares PRIVATE /W3)
    endif()
endif()
