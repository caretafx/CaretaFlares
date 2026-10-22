# -*- coding: utf-8 -*-
"""Rotulos, menus e unidades dos parametros dos presets (para o Editor da janela Options).

Nomes vindos do estudo do plugin original (docs/anexo-parametros.txt e a tabela de
rotulos do DLL). Escrito do zero; so descreve o que cada id significa.
"""

# ---- objetos
LABELS = {
    0: 'Brightness', 1: 'Scale', 85: 'Stretch', 2: 'Distance', 103: 'Distance', 5: 'Rotation',
    3: 'Offset', 6: 'Translation', 23: 'Custom Translation', 8: 'Aspect Ratio',
    7: 'Color Source', 4: 'Color 1', 102: 'Color 2', 92: 'Gradient Loops', 97: 'Gradient Offset',
    98: 'Reverse Gradient', 35: 'Color Random',
    29: 'Gamma', 41: 'Auto Rotate', 69: 'Length', 67: 'Thickness', 68: 'Core Intensity', 30: 'Symmetry',
    31: 'Fan Ends', 70: 'Fan Feathering', 32: 'Replicator Copies', 33: 'Replicator Angle',
    34: 'Scale Random', 65: 'Spacing Random', 18: 'Random Seed', 13: 'Spread', 61: 'Spread Random',
    14: 'Number of Objects', 15: 'Scale Random', 16: 'Brightness Random', 47: 'Rotation Random',
    48: 'Offset Random', 11: 'Shape Type', 19: 'Texture Image', 87: 'Shape Orientation',
    113: 'Orientation Random', 12: 'Polygon Sides', 42: 'Polygon Roundness', 43: 'Blade Notching',
    17: 'Smoothness', 25: 'Smoothness Random', 46: 'Outline Intensity', 44: 'Outline Thickness',
    45: 'Outline Feathering', 49: 'Completion', 50: 'Completion Feathering', 60: 'Completion Rotation',
    62: 'Rotation Random', 59: 'Auto Rotate Completion', 56: 'Thickness', 57: 'Inside Feathering',
    58: 'Outside Feathering', 93: 'Convex Roundness', 52: 'Complexity', 53: 'Detail', 104: 'Continuous',
    105: 'Line Thickness', 120: 'Line Spacing', 94: 'Length Random', 111: 'Thickness Random',
    95: 'Spread Random', 63: 'Illumination Radius', 64: 'Far Scale Offset',
    118: 'Ring Brightness', 119: 'Ring Outline', 114: 'Core Brightness', 115: 'Core Scale',
    116: 'Core Roundness', 117: 'Core Distortion',
    110: 'Enable', 108: 'Speed', 109: 'Amount',
    106: 'Enable Trigger', 75: 'Brightness Offset', 76: 'Scale Offset', 123: 'Stretch Offset',
    107: 'Rotation Offset', 78: 'Completion Offset', 86: 'Outline Intensity Offset', 96: 'Spread Offset',
    121: 'Thickness Offset', 83: 'Color Shift', 71: 'Trigger Type', 81: 'Trigger Mode',
    99: 'Invert Trigger', 77: 'Border Width', 72: 'Expansion', 80: 'Inner Falloff Range',
    73: 'Outer Falloff Range', 74: 'Falloff Type', 122: 'Trigger Stretch', 79: 'Preview Trigger',
    82: 'Offset Trigger Location', 88: '1-Way Brightness', 89: '1-Way Scale', 90: '1-Way Color',
    39: 'Start Range Offset', 40: 'Exclude From Matte Box', 10: 'Ignore 3D Perspective',
    26: 'Ignore Global Brightness', 27: 'Ignore Global Scale', 22: 'Ignore Global Rotation',
}
# rotulos que mudam conforme o tipo do objeto
TYPE_LABELS = {
    7: {67: 'Length'},   # Hoop
}

ENUMS = {
    6: ['Free', 'Horizontal', 'Vertical', 'None', 'Custom'],
    7: ['Global', 'Custom', 'Spectrum', 'Gradient'],
    41: ['None', 'To Light', 'To Center'],
    11: ['Polygon', 'Circle', 'Texture'],
    59: ['None', 'Object Rotation', 'To Light', 'To Center'],
    71: ['From Border', 'From Center', 'From Light'],
    81: ['Object Position', 'Light Position'],
    74: ['Linear', 'Smooth', 'Exponential'],
}

# ---- globais
GLOBAL_LABELS = {
    112: 'Scale', 8: 'Aspect Ratio', 9: 'Blend Mode', 4: 'Color', 18: 'Global Seed',
    36: 'Shape', 37: 'Start Range', 38: 'Fade Amount',
    19: 'Texture Image', 63: 'Illumination Radius', 101: 'Falloff', 100: 'Brightness', 1: 'Scale', 3: 'Offset',
    55: 'Aberration Type', 51: 'Intensity', 84: 'Spread',
    0: 'Brightness', 66: 'Contrast', 54: 'Saturation',
}
GLOBAL_ENUMS = {
    9: ['Add', 'Screen'],
    36: ['None', 'Box', 'Ellipse'],
    55: ['None', 'Purple Fringe', 'Red/Blue Shift'],
}
GLOBAL_SECTIONS = {112: 'Common Settings', 36: 'Matte Box Controls', 19: 'Lens Texture',
                   55: 'Chromatic Aberration', 0: 'Color Correction'}

# ---- secoes dos objetos: nome pelo primeiro parametro depois do divisor
SECTIONS = {0: 'Common Settings', 7: 'Colorize', 106: 'Dynamic Triggering', 39: 'Matte Box Controls',
            10: 'Advanced Settings', 110: 'Animation Controls', 11: 'Object Shape', 49: 'Circular Completion'}

# ---- unidades e passo do arrasto
DEGREES = {5, 87, 60, 107, 78, 49, 33}
INTEGERS = {18, 12, 14, 32, 52}
PLAIN = {29, 8, 92, 97, 63}  # sem unidade
GLOBAL_PLAIN = {8, 101}
GLOBAL_INTEGERS = {18}


def label(pid, otype=None, is_global=False):
    if is_global:
        return GLOBAL_LABELS.get(pid, 'Param %d' % pid)
    return TYPE_LABELS.get(otype, {}).get(pid) or LABELS.get(pid, 'Param %d' % pid)


def enum_options(pid, is_global=False):
    return (GLOBAL_ENUMS if is_global else ENUMS).get(pid)


def unit(pid, is_global=False):
    if is_global:
        if pid in GLOBAL_INTEGERS or pid in GLOBAL_PLAIN:
            return ''
        return '%'
    if pid in DEGREES:
        return u'°'
    if pid in INTEGERS or pid in PLAIN:
        return ''
    return '%'


def is_integer(pid, is_global=False):
    return pid in (GLOBAL_INTEGERS if is_global else INTEGERS)


def section_name(first_id, type_name, is_global=False):
    if is_global:
        return GLOBAL_SECTIONS.get(first_id, 'Settings')
    return SECTIONS.get(first_id, '%s Controls' % type_name)


def drag_step(pid, is_global=False):
    if is_integer(pid, is_global):
        return 1.0
    u = unit(pid, is_global)
    if u == u'°':
        return 1.0
    if u == '%':
        return 0.5
    return 0.01
