r"""音效模块 - 使用 pygame.mixer 播放音效

优先从外部加载高品质音效（sounds 目录）。
如果没有外部音频文件，使用程序化生成音效（合成音）进行无缝备选。
"""
import os
import math
import struct
import pygame
from config import SOUND_ENABLED, SOUND_VOLUME

# 游戏自定义音效目录（相对路径，兼容 PyInstaller 打包）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(_PROJECT_ROOT, "sounds")

# 新增音效文件映射（文件路径、音量系数）
SOUND_FILES = {
    "deal": ("787405__realsquink__card-deal.wav", 0.7),
    "shuffle": ("217503__vkproduktion__shuffling-cards-riffle-03.wav", 0.8),
    "bet": ("201809__fartheststar__poker_chips5.wav", 0.7),
    "call": ("201809__fartheststar__poker_chips5.wav", 0.6),
    "raise": ("201809__fartheststar__poker_chips5.wav", 0.75),
    "allin": ("201809__fartheststar__poker_chips5.wav", 0.9),
    "fold": ("201809__fartheststar__poker_chips5.wav", 0.4),
    "check": ("787405__realsquink__card-deal.wav", 0.4),
    "bankruptcy": ("685456__danlucaz__sad-loop-3.wav", 0.6),
    "cheer": ("651646__krizin__crowd-cheer-5.wav", 0.7),
}

# 背景音乐文件（循环播放，音量独立控制）
BACKGROUND_MUSIC = "425771__airborne80__casino-background-sounds.mp3"
BACKGROUND_VOLUME_RATIO = 0.25  # 背景音相对于主音量的比例


class AudioEngine:
    """音效引擎"""
    def __init__(self):
        self.enabled = SOUND_ENABLED
        self.volume = SOUND_VOLUME
        self.initialized = False
        self.sounds = {}
        self._temp_files = []
        self._bgm_loaded = False

    def init(self):
        """初始化音频系统"""
        if not self.enabled:
            return
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            pygame.mixer.music.set_volume(self.volume * BACKGROUND_VOLUME_RATIO)
            self.initialized = True
            self._load_sounds()
            self._load_background_music()
        except Exception:
            self.enabled = False

    def _load_sounds(self):
        """加载外部音效，失败时使用合成音备用"""
        # 基础合成音参数（备用）
        fallback = {
            "deal": (0.08, 800, 0.3, "click"),
            "flip": (0.1, 900, 0.3, "click"),
            "fold": (0.1, 300, 0.3, "swoosh"),
            "check": (0.08, 400, 0.25, "click"),
            "bet": (0.15, 600, 0.4, "chip"),
            "call": (0.12, 500, 0.35, "chip"),
            "raise": (0.2, 700, 0.5, "chip"),
            "allin": (0.3, 1000, 0.6, "impact"),
            "win": (0.5, 523, 0.6, "fanfare"),
            "lose": (0.4, 200, 0.5, "descending"),
            "shuffle": (0.5, 300, 0.5, "swoosh"),
            "bankruptcy": (0.5, 200, 0.5, "descending"),
            "cheer": (0.8, 600, 0.7, "fanfare"),
        }

        for name, params in fallback.items():
            duration, freq, volume, style = params
            sound_loaded = False

            if name in SOUND_FILES:
                ext_file, vol_ratio = SOUND_FILES[name]
                filepath = os.path.join(SOUNDS_DIR, ext_file)
                if os.path.exists(filepath):
                    try:
                        snd = pygame.mixer.Sound(filepath)
                        snd.set_volume(vol_ratio)
                        self.sounds[name] = snd
                        sound_loaded = True
                    except Exception:
                        pass

            if not sound_loaded:
                self.sounds[name] = self._make_sound(duration, freq, volume, style)

    def _make_sound(self, duration, freq, volume, style="click"):
        """合成一个简短的音效"""
        if not self.initialized:
            return None
        try:
            sample_rate = 22050
            num_samples = int(sample_rate * duration)
            samples = []

            for i in range(num_samples):
                t = i / sample_rate
                env = 1.0 - (t / duration)  # 线性衰减

                if style == "click":
                    val = int(32767 * volume * env * math.sin(2 * math.pi * freq * t))
                elif style == "chip":
                    # 筹码声：高频 + 低频混合
                    val = int(32767 * volume * env * (
                        0.6 * math.sin(2 * math.pi * freq * t) +
                        0.4 * math.sin(2 * math.pi * freq * 2 * t))
                    )
                elif style == "swoosh":
                    # 弃牌声：频率下降
                    f = freq * (1 - t / duration)
                    val = int(32767 * volume * env * math.sin(2 * math.pi * f * t))
                elif style == "fanfare":
                    # 获胜声：上升音阶
                    f = freq * (1 + t / duration * 0.5)
                    val = int(32767 * volume * env * (
                        0.5 * math.sin(2 * math.pi * f * t) +
                        0.3 * math.sin(2 * math.pi * f * 1.5 * t) +
                        0.2 * math.sin(2 * math.pi * f * 2 * t))
                    )
                elif style == "descending":
                    # 失败声：下降音阶
                    f = freq * (1 - t / duration * 0.5)
                    val = int(32767 * volume * env * math.sin(2 * math.pi * f * t))
                elif style == "impact":
                    # 全押声：重击
                    val = int(32767 * volume * env * (
                        0.7 * math.sin(2 * math.pi * freq * t) +
                        0.3 * math.sin(2 * math.pi * freq * 0.5 * t))
                    )
                else:
                    val = int(32767 * volume * env * math.sin(2 * math.pi * freq * t))

                samples.append(struct.pack('<h', val))

            # 转为 stereo (16-bit)
            stereo_samples = []
            for s in samples:
                stereo_samples.append(s)
                stereo_samples.append(s)
            raw = b''.join(stereo_samples)

            snd = pygame.mixer.Sound(buffer=raw)
            snd._synthetic = True
            return snd
        except Exception:
            return None

    def _load_background_music(self):
        """加载环境背景音"""
        if not self.initialized:
            return
        try:
            bgm_path = os.path.join(SOUNDS_DIR, BACKGROUND_MUSIC)
            if os.path.exists(bgm_path):
                pygame.mixer.music.load(bgm_path)
                self._bgm_loaded = True
        except Exception:
            self._bgm_loaded = False

    def play_background_music(self):
        """循环播放环境背景音（音量已单独设置）"""
        if not self.enabled or not self.initialized or not self._bgm_loaded:
            return
        try:
            if pygame.mixer.music.get_busy():
                return
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    def stop_background_music(self):
        """停止背景音"""
        if not self.initialized:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    def stop_all_sounds(self):
        """停止所有音效（含背景音）"""
        if not self.initialized:
            return
        try:
            pygame.mixer.music.stop()
            pygame.mixer.stop()
        except Exception:
            pass

    def play(self, name):
        """播放音效"""
        if not self.enabled or not self.initialized:
            return
        snd = self.sounds.get(name)
        if snd:
            try:
                # 外部文件已在加载时设置相对音量；合成音再乘全局音量
                if getattr(snd, "_synthetic", False):
                    snd.set_volume(self.volume)
                snd.play()
            except Exception:
                pass

    def play_cheer(self):
        """播放欢呼音效"""
        self.play("cheer")

    def play_bankruptcy(self):
        """播放破产音效"""
        self.play("bankruptcy")

    def set_volume(self, vol):
        self.volume = max(0.0, min(1.0, vol))
        if self.initialized:
            # 背景音乐音量独立控制，保持较低
            try:
                pygame.mixer.music.set_volume(self.volume * BACKGROUND_VOLUME_RATIO)
            except Exception:
                pass
            # 合成音更新音量；外部文件保持自己的相对音量
            for name, snd in self.sounds.items():
                if snd and getattr(snd, "_synthetic", False):
                    try:
                        snd.set_volume(self.volume)
                    except Exception:
                        pass

    def toggle(self):
        self.enabled = not self.enabled
        if self.enabled and not self.initialized:
            self.init()

    def cleanup(self):
        """清理临时文件"""
        for f in self._temp_files:
            try:
                os.remove(f)
            except Exception:
                pass
        self._temp_files.clear()
