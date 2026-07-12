"""字体工具模块 - 绕过 pygame SysFont 在 Windows 上的 bug

pygame 2.6.1 在某些 Windows 配置下，initsysfonts_win32() 会因
注册表返回 int 类型而非 str 导致 TypeError。
此模块通过 monkey-patch 绕过该问题，直接加载 TTF 文件。
"""
import os
from collections import OrderedDict
import pygame

_font_cache = {}
_patched = False

# 文字渲染 surface 缓存（按字体、文本、颜色、背景键控）
_TEXT_SURFACE_CACHE = OrderedDict()
_MAX_TEXT_CACHE = 200


def _font_render_key(font, text, antialias, color, background=None):
    color_key = tuple(color) if isinstance(color, (list, tuple)) else color
    bg_key = tuple(background) if isinstance(background, (list, tuple)) else background
    if not isinstance(text, str):
        text = str(text)
    return (id(font), text, antialias, color_key, bg_key)


class CachedFont:
    """包装 pygame.font.Font，对 render 结果做 LRU 缓存"""

    def __init__(self, font):
        self._font = font

    def __getattr__(self, name):
        return getattr(self._font, name)

    def render(self, text, antialias, color, background=None):
        key = _font_render_key(self._font, text, antialias, color, background)
        if key in _TEXT_SURFACE_CACHE:
            _TEXT_SURFACE_CACHE.move_to_end(key)
            return _TEXT_SURFACE_CACHE[key]
        surf = self._font.render(text, antialias, color, background)
        _TEXT_SURFACE_CACHE[key] = surf
        if len(_TEXT_SURFACE_CACHE) > _MAX_TEXT_CACHE:
            _TEXT_SURFACE_CACHE.popitem(last=False)
        return surf

# Windows 中文字体路径
_FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑 Bold
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
    "C:/Windows/Fonts/Deng.ttf",       # 等线
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
        actual_path = font_path
        if bold:
            bold_path = "C:/Windows/Fonts/msyhbd.ttc"
            if os.path.exists(bold_path):
                actual_path = bold_path
        try:
            font = pygame.font.Font(actual_path, size)
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

    cached_font = CachedFont(font)
    _font_cache[key] = cached_font
    return cached_font
