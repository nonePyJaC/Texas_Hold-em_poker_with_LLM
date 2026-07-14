"""字体工具模块 - 绕过 pygame SysFont 在 Windows 上的 bug

pygame 2.6.1 在某些 Windows 配置下，initsysfonts_win32() 会因
注册表返回 int 类型而非 str 导致 TypeError。
此模块通过 monkey-patch 绕过该问题，直接加载 TTF 文件。
"""
import os
import pygame

_font_cache = {}
_patched = False

# Windows 中文字体路径
_FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑 (完整中文 + 符号 glyph)
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/Deng.ttf",       # 等线
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
]

_default_font_path = None


def _patch_sysfont():
    """Monkey-patch pygame.font.initsysfonts 使其不触发有 bug 的 Win32 注册表扫描"""
    global _patched
    if _patched:
        return
    _patched = True
    try:
        pygame.font.init()
    except Exception:
        pass

    try:
        import pygame.sysfont as sf
        original = sf.initsysfonts
        def safe_init():
            try:
                return original()
            except Exception:
                return {}
        sf.initsysfonts = safe_init
        if hasattr(pygame.font, 'initsysfonts'):
            pygame.font.initsysfonts = safe_init
    except Exception:
        pass


def _find_font():
    """找到第一个可用的中文字体文件"""
    global _default_font_path
    if _default_font_path:
        return _default_font_path
    for path in _FONT_PATHS:
        if os.path.exists(path):
            _default_font_path = path
            return path
    return None


def get_font(size, bold=False):
    """获取字体，支持中文。绕过 pygame SysFont bug。"""
    _patch_sysfont()

    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]

    font_path = _find_font()
    if font_path:
        try:
            font = pygame.font.Font(font_path, size)
            font.set_bold(bold)
        except Exception:
            font = pygame.font.Font(None, size)
            font.set_bold(bold)
    else:
        try:
            font = pygame.font.Font(None, size)
            font.set_bold(bold)
        except Exception:
            font = pygame.font.Font(None, size)

    _font_cache[key] = font
    return font
