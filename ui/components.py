"""UI 组件：按钮、滑块、文本框等"""
import pygame
from config import (
    COLOR_WHITE, COLOR_BLACK, COLOR_GOLD, COLOR_PANEL_BG, COLOR_PANEL_BORDER,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER, COLOR_BUTTON_DISABLED,
    COLOR_FOLD, COLOR_CALL, COLOR_RAISE, COLOR_TEXT_DIM,
)
from ui.font_util import get_font


class Button:
    def __init__(self, x, y, w, h, text, color=None, text_color=COLOR_WHITE, font_size=20):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color or COLOR_BUTTON_BG
        self.text_color = text_color
        self.font = get_font(font_size)
        self.hovered = False
        self.enabled = True
        self.on_click = None

    def update(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.enabled and self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface):
        color = self.color
        if not self.enabled:
            color = COLOR_BUTTON_DISABLED
        elif self.hovered:
            color = COLOR_BUTTON_HOVER

        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, COLOR_PANEL_BORDER, self.rect, 2, border_radius=8)

        text_surf = self.font.render(self.text, True, self.text_color if self.enabled else COLOR_TEXT_DIM)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)


class Slider:
    def __init__(self, x, y, w, h, min_val, max_val, value=None, show_value=True):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_val = min_val
        self.max_val = max_val
        self.value = value if value is not None else min_val
        self.dragging = False
        self.enabled = True
        self.show_value = show_value
        self.font = get_font(16)

    @property
    def ratio(self):
        if self.max_val == self.min_val:
            return 0
        return (self.value - self.min_val) / (self.max_val - self.min_val)

    def _get_handle_x(self):
        return self.rect.x + int(self.ratio * self.rect.w)

    def handle_event(self, event):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            handle_x = self._get_handle_x()
            handle_rect = pygame.Rect(handle_x - 10, self.rect.y - 5, 20, self.rect.h + 10)
            if handle_rect.collidepoint(event.pos) or self.rect.collidepoint(event.pos):
                self.dragging = True
                self._update_from_pos(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_from_pos(event.pos[0])
            return True
        return False

    def _update_from_pos(self, x):
        ratio = (x - self.rect.x) / self.rect.w
        ratio = max(0, min(1, ratio))
        raw = self.min_val + ratio * (self.max_val - self.min_val)
        # 整数滑块保持整数；浮点滑块（如音量 0~1）保留两位小数
        if isinstance(self.min_val, int) and isinstance(self.max_val, int):
            self.value = int(round(raw))
        else:
            self.value = round(raw, 2)

    def draw(self, surface):
        # 轨道
        track_rect = pygame.Rect(self.rect.x, self.rect.centery - 3, self.rect.w, 6)
        pygame.draw.rect(surface, COLOR_PANEL_BORDER, track_rect, border_radius=3)

        # 已填充部分
        fill_w = int(self.ratio * self.rect.w)
        if fill_w > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.centery - 3, fill_w, 6)
            pygame.draw.rect(surface, COLOR_GOLD, fill_rect, border_radius=3)

        # 手柄
        handle_x = self._get_handle_x()
        pygame.draw.circle(surface, COLOR_GOLD, (handle_x, self.rect.centery), 10)
        pygame.draw.circle(surface, COLOR_WHITE, (handle_x, self.rect.centery), 10, 2)

        # 数值
        if self.show_value:
            val_text = self.font.render(str(self.value), True, COLOR_WHITE)
            surface.blit(val_text, (self.rect.right + 10, self.rect.centery - val_text.get_height() // 2))


class Panel:
    def __init__(self, x, y, w, h, bg_color=COLOR_PANEL_BG, border_color=COLOR_PANEL_BORDER):
        self.rect = pygame.Rect(x, y, w, h)
        self.bg_color = bg_color
        self.border_color = border_color

    def draw(self, surface):
        pygame.draw.rect(surface, self.bg_color, self.rect, border_radius=10)
        pygame.draw.rect(surface, self.border_color, self.rect, 2, border_radius=10)


class TextInput:
    def __init__(self, x, y, w, h, placeholder="", font_size=20, numeric_only=False, max_length=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.font = get_font(font_size)
        self.numeric_only = numeric_only
        self.max_length = max_length

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.TEXTINPUT and self.active:
            text = event.text
            if self.numeric_only:
                text = ''.join(c for c in text if c.isdigit())
                if not text:
                    return self.active
            if self.max_length and len(self.text) + len(text) > self.max_length:
                text = text[:self.max_length - len(self.text)]
                if not text:
                    return self.active
            self.text += text
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            elif event.key == pygame.K_ESCAPE:
                self.active = False
            elif event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                pasted = self._get_clipboard_text()
                if pasted:
                    if self.max_length:
                        remaining = self.max_length - len(self.text)
                        pasted = pasted[:remaining]
                    if self.numeric_only:
                        pasted = ''.join(c for c in pasted if c.isdigit())
                    self.text += pasted
        return self.active

    @staticmethod
    def _get_clipboard_text():
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return text
        except Exception:
            return ""

    @property
    def int_value(self):
        try:
            return int(self.text)
        except (ValueError, TypeError):
            return None

    def draw(self, surface):
        color = COLOR_GOLD if self.active else COLOR_PANEL_BORDER
        pygame.draw.rect(surface, COLOR_PANEL_BG, self.rect, border_radius=6)
        pygame.draw.rect(surface, color, self.rect, 2, border_radius=6)

        display_text = self.text if self.text else self.placeholder
        text_color = COLOR_WHITE if self.text else COLOR_TEXT_DIM
        text_surf = self.font.render(display_text, True, text_color)
        # Clip text to fit within the input box
        max_w = self.rect.w - 20
        if text_surf.get_width() > max_w:
            # Show rightmost portion
            text_surf = text_surf.subsurface((text_surf.get_width() - max_w, 0, max_w, text_surf.get_height()))
        surface.blit(text_surf, (self.rect.x + 10, self.rect.centery - text_surf.get_height() // 2))

        # Cursor blink when active
        if self.active:
            import pygame as _pg
            blink = (_pg.time.get_ticks() // 500) % 2 == 0
            if blink:
                cursor_x = self.rect.x + 10 + text_surf.get_width() + 2
                cursor_y = self.rect.y + 6
                pygame.draw.line(surface, COLOR_WHITE, (cursor_x, cursor_y), (cursor_x, cursor_y + self.rect.h - 12), 2)


class Dropdown:
    def __init__(self, x, y, w, h, options, font_size=18):
        self.rect = pygame.Rect(x, y, w, h)
        self.options = options
        self.selected_index = 0
        self.expanded = False
        self.font = get_font(font_size)
        self.hovered_index = -1

    @property
    def selected(self):
        return self.options[self.selected_index] if self.options else None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.expanded = not self.expanded
                return True
            elif self.expanded:
                for i in range(len(self.options)):
                    opt_rect = pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.h,
                                          self.rect.w, self.rect.h)
                    if opt_rect.collidepoint(event.pos):
                        self.selected_index = i
                        self.expanded = False
                        return True
                self.expanded = False
        return False

    def update(self, mouse_pos):
        self.hovered_index = -1
        if self.expanded:
            for i in range(len(self.options)):
                opt_rect = pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.h,
                                      self.rect.w, self.rect.h)
                if opt_rect.collidepoint(mouse_pos):
                    self.hovered_index = i
                    break

    def draw(self, surface):
        pygame.draw.rect(surface, COLOR_PANEL_BG, self.rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_PANEL_BORDER, self.rect, 2, border_radius=6)

        text = str(self.selected) if self.selected else ""
        text_surf = self.font.render(text, True, COLOR_WHITE)
        surface.blit(text_surf, (self.rect.x + 10, self.rect.centery - text_surf.get_height() // 2))

        arrow = "▼" if self.expanded else "▶"
        arrow_surf = self.font.render(arrow, True, COLOR_TEXT_DIM)
        surface.blit(arrow_surf, (self.rect.right - 25, self.rect.centery - arrow_surf.get_height() // 2))

        if self.expanded:
            for i, opt in enumerate(self.options):
                opt_rect = pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.h,
                                      self.rect.w, self.rect.h)
                bg = COLOR_BUTTON_HOVER if i == self.hovered_index else COLOR_PANEL_BG
                pygame.draw.rect(surface, bg, opt_rect)
                pygame.draw.rect(surface, COLOR_PANEL_BORDER, opt_rect, 1)

                opt_surf = self.font.render(str(opt), True, COLOR_WHITE)
                surface.blit(opt_surf, (opt_rect.x + 10, opt_rect.centery - opt_surf.get_height() // 2))
