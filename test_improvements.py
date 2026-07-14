"""自测脚本：验证 V1.2 三个高优先级改进

1. 动态 temperature 逻辑
2. 牌桌信息渲染（函数签名 + 常量）
3. 摊牌动画阶段逻辑
"""
import sys
import os

# PyInstaller frozen 模式下获取正确的根目录
if getattr(sys, 'frozen', False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_ROOT)

import pygame
pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.SCALED, vsync=1)

from ai.emotion import EmotionState
from ai.dialogue_manager.context import DialogueContext
from ai.dialogue_manager.providers.llm_bridge import LLMBridge, LLMConfig
from ui.renderer import Renderer, PHASE_NAMES
from config import PREFLOP, FLOP, TURN, RIVER, SHOWDOWN
from engine.deck import Card

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name}  {detail}")
        failed += 1


print("=" * 60)
print("测试 1: 动态 Temperature")
print("=" * 60)

config = LLMConfig(api_key="test", temperature=0.8)
bridge = LLMBridge(config=config)

# 场景 A: 平静状态 → 基础 temperature
ctx_calm = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.0, confidence=0.5, excitement=0.0))
temp_calm = bridge._get_dynamic_temperature(ctx_calm)
check("平静状态 temperature = 0.8", abs(temp_calm - 0.8) < 0.01, f"got {temp_calm}")

# 场景 B: 高 tilt → +0.2
ctx_tilt = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.6, confidence=0.5, excitement=0.0))
temp_tilt = bridge._get_dynamic_temperature(ctx_tilt)
check("高 tilt (0.6) → temperature = 1.0", abs(temp_tilt - 1.0) < 0.01, f"got {temp_tilt}")

# 场景 C: 高 confidence → -0.2
ctx_conf = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.0, confidence=0.8, excitement=0.0))
temp_conf = bridge._get_dynamic_temperature(ctx_conf)
check("高 confidence (0.8) → temperature = 0.6", abs(temp_conf - 0.6) < 0.01, f"got {temp_conf}")

# 场景 D: 高 excitement → +0.1
ctx_exc = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.0, confidence=0.5, excitement=0.7))
temp_exc = bridge._get_dynamic_temperature(ctx_exc)
check("高 excitement (0.7) → temperature = 0.9", abs(temp_exc - 0.9) < 0.01, f"got {temp_exc}")

# 场景 E: tilt + excitement + confidence 组合
ctx_combo = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.4, confidence=0.6, excitement=0.6))
temp_combo = bridge._get_dynamic_temperature(ctx_combo)
# tilt 0.4 > 0.3 → +0.1, confidence 0.6 > 0.5 → -0.1, excitement 0.6 > 0.5 → +0.1
# 0.8 + 0.1 - 0.1 + 0.1 = 0.9
check("组合 (tilt=0.4, conf=0.6, exc=0.6) → 0.9", abs(temp_combo - 0.9) < 0.01, f"got {temp_combo}")

# 场景 F: 极端 tilt → clamp 到 1.2
ctx_extreme = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=1.0, confidence=0.0, excitement=1.0))
temp_extreme = bridge._get_dynamic_temperature(ctx_extreme)
# 0.8 + 0.2 + 0.1 = 1.1, confidence 0.0 < 0.5 so no change
check("极端状态 → clamp ≤ 1.2", temp_extreme <= 1.2, f"got {temp_extreme}")

# 场景 G: 无情绪状态 → 返回基础 temperature
ctx_no_emo = DialogueContext(char_name="Test", emotion_state=None)
temp_no_emo = bridge._get_dynamic_temperature(ctx_no_emo)
check("无情绪状态 → temperature = 0.8", abs(temp_no_emo - 0.8) < 0.01, f"got {temp_no_emo}")

# 场景 H: 低 temperature config + 高 confidence → clamp 到 0.3
config_low = LLMConfig(api_key="test", temperature=0.4)
bridge_low = LLMBridge(config=config_low)
ctx_low = DialogueContext(char_name="Test", emotion_state=EmotionState(tilt=0.0, confidence=0.9, excitement=0.0))
temp_low = bridge_low._get_dynamic_temperature(ctx_low)
# 0.4 - 0.2 = 0.2 → clamp to 0.3
check("低 base + 高 confidence → clamp ≥ 0.3", temp_low >= 0.3, f"got {temp_low}")


print()
print("=" * 60)
print("测试 2: 牌桌信息渲染")
print("=" * 60)

renderer = Renderer(screen)

# 检查 draw_pot 存在且可调用
check("draw_pot 方法存在", hasattr(renderer, 'draw_pot'))
check("draw_phase_info 方法存在", hasattr(renderer, 'draw_phase_info'))
check("draw_betting_info 方法存在", hasattr(renderer, 'draw_betting_info'))

# 实际渲染测试 - 不崩溃即通过
try:
    renderer.draw_pot(1500)
    check("draw_pot(1500) 渲染无异常", True)
except Exception as e:
    check("draw_pot(1500) 渲染无异常", False, str(e))

try:
    renderer.draw_phase_info(FLOP, 42)
    check("draw_phase_info(FLOP, 42) 渲染无异常", True)
except Exception as e:
    check("draw_phase_info(FLOP, 42) 渲染无异常", False, str(e))

try:
    renderer.draw_phase_info(SHOWDOWN, 99)
    check("draw_phase_info(SHOWDOWN, 99) 渲染无异常", True)
except Exception as e:
    check("draw_phase_info(SHOWDOWN, 99) 渲染无异常", False, str(e))

try:
    renderer.draw_betting_info(500, 1000)
    check("draw_betting_info(500, 1000) 渲染无异常", True)
except Exception as e:
    check("draw_betting_info(500, 1000) 渲染无异常", False, str(e))

try:
    renderer.draw_betting_info(0, 0)
    check("draw_betting_info(0, 0) 空下注无异常", True)
except Exception as e:
    check("draw_betting_info(0, 0) 空下注无异常", False, str(e))

# 检查阶段配色覆盖所有阶段
phase_colors_keys = {PREFLOP, FLOP, TURN, RIVER, SHOWDOWN}
check("PHASE_NAMES 覆盖所有阶段", all(p in PHASE_NAMES for p in phase_colors_keys))


print()
print("=" * 60)
print("测试 3: 摊牌动画")
print("=" * 60)

# 构造测试数据
test_cards = [Card(14, 's'), Card(13, 's'), Card(12, 's'), Card(11, 's'), Card(10, 's')]

# 模拟玩家
class FakePlayer:
    def __init__(self, name, folded=False, hole_cards=None, total_bet=500, is_human=False):
        self.name = name
        self.folded = folded
        self.hole_cards = hole_cards or [Card(2, 'h'), Card(3, 'h')]
        self.total_bet = total_bet
        self.is_human = is_human

test_players = [
    FakePlayer("Alice", folded=False, hole_cards=[Card(14, 's'), Card(13, 's')]),
    FakePlayer("Bob", folded=True),
    FakePlayer("Charlie", folded=False, hole_cards=[Card(10, 'h'), Card(9, 'h')]),
]

class FakeEval:
    def __init__(self, name):
        self.name = name

test_results = {
    'fold_win': False,
    'winners': [test_players[0]],
    'payouts': {0: 1500, 2: 0},
    'evaluations': {0: FakeEval("皇家同花顺"), 2: FakeEval("一对")},
    'pot_won': 2000,
}

# Phase 0: 悬念阶段 (timer=0.2)
try:
    renderer.draw_showdown_results(test_results, test_players, test_cards, hand_number=1, timer=0.2)
    check("Phase 0 (timer=0.2) 悬念阶段无异常", True)
except Exception as e:
    check("Phase 0 (timer=0.2) 悬念阶段无异常", False, str(e))

# Phase 1: 滑入阶段 (timer=0.6)
try:
    renderer.draw_showdown_results(test_results, test_players, test_cards, hand_number=1, timer=0.6)
    check("Phase 1 (timer=0.6) 滑入阶段无异常", True)
except Exception as e:
    check("Phase 1 (timer=0.6) 滑入阶段无异常", False, str(e))

# Phase 2: 完整显示 + 脉冲 (timer=1.5)
try:
    renderer.draw_showdown_results(test_results, test_players, test_cards, hand_number=1, timer=1.5)
    check("Phase 2 (timer=1.5) 完整显示无异常", True)
except Exception as e:
    check("Phase 2 (timer=1.5) 完整显示无异常", False, str(e))

# Phase 2: 长时间后 (timer=5.0)
try:
    renderer.draw_showdown_results(test_results, test_players, test_cards, hand_number=1, timer=5.0)
    check("Phase 2 (timer=5.0) 长时间无异常", True)
except Exception as e:
    check("Phase 2 (timer=5.0) 长时间无异常", False, str(e))

# 弃牌获胜场景
fold_results = {
    'fold_win': True,
    'winners': [test_players[0]],
    'payouts': {0: 1000},
    'evaluations': {},
    'pot_won': 1000,
}
try:
    renderer.draw_showdown_results(fold_results, test_players, test_cards, hand_number=1, timer=1.5)
    check("弃牌获胜场景无异常", True)
except Exception as e:
    check("弃牌获胜场景无异常", False, str(e))

# 空公共牌场景
try:
    renderer.draw_showdown_results(test_results, test_players, None, hand_number=1, timer=1.5)
    check("空公共牌场景无异常", True)
except Exception as e:
    check("空公共牌场景无异常", False, str(e))


print()
print("=" * 60)
print(f"测试结果: {passed} 通过, {failed} 失败")
print("=" * 60)

pygame.quit()
sys.exit(0 if failed == 0 else 1)
