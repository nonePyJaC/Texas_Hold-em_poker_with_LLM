"""德州扑克游戏 - 主入口"""
import sys
import os
import pygame

# PyInstaller frozen 模式下获取正确的根目录
if getattr(sys, 'frozen', False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_ROOT)
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE,
    DEFAULT_STARTING_CHIPS,
    MIN_PLAYERS, MAX_PLAYERS, BLIND_PRESETS,
    BETTING_NO_LIMIT,
    DECK_STANDARD, SHOWDOWN,
    DIFFICULTY_NORMAL,
)
from engine.action import Action, ActionType
from ui.renderer import Renderer
from ui.scenes import SceneRenderer, SceneEventHandler
from ui.scenes.replay_renderer import fix_blind_phases, normalize_action_order
from ui.components import Button, Dropdown, Panel, TextInput
from ui.animations import AnimationManager, DealCardAnimation, ChipAnimation, FlipCardAnimation, WinAnimation, TextPopupAnimation
from ui.audio import AudioEngine
from ui.font_util import get_font
from ai.personality import Personality
from ai.character_pool import CharacterPool
from ai.mcts_ai import MCTSAI, OpponentModel
from ai.advanced_ai import AdvancedAI
from ai.emotion import EVENT_LOSE_BIG, EVENT_WIN_POT, EVENT_BLUFFED, EVENT_SUCCESSFUL_BLUFF
from ai.memory import (
    EPISODE_BIG_WIN, EPISODE_BAD_BEAT, EPISODE_SUCCESSFUL_BLUFF,
    EPISODE_BLUFFED_BY, EPISODE_BIG_FOLD, EPISODE_ALL_IN_CALL,
    REL_EVENT_BEAT_THEM, REL_EVENT_LOST_TO_THEM,
    REL_EVENT_THEY_BLUFFED_ME, REL_EVENT_I_BLUFFED_THEM,
)
from ai.ai_controller import AIController
from engine.hand_evaluator import estimate_hand_strength
from data.save_manager import SaveManager
from chat import ChatController
from game_logic import HandEndController, GameSetup, GameCallbacks
from data.game_logger import GameLogger


class GameApp:
    def __init__(self):
        pygame.init()
        self._fullscreen = False
        self._window_flags = pygame.RESIZABLE
        self._window_size = (SCREEN_WIDTH, SCREEN_HEIGHT)
        # 直接在 display surface 上渲染，无虚拟屏幕无缩放
        self.display = pygame.display.set_mode(self._window_size, self._window_flags)
        self.screen = self.display
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.audio = AudioEngine()
        self.audio.init()
        self.animations = AnimationManager()
        self.save_manager = SaveManager()
        self.save_manager.load()
        self.game_logger = GameLogger()

        # 游戏状态
        self.game = None
        self.players = []
        self.human_player = None

        # UI 状态
        self.scene = "menu"  # menu, setup, playing, showdown, replay
        self.showdown_results = None
        self.showdown_timer = 0
        self.ai_thinking = False
        self.ai_think_timer = 0
        self.ai_action_delay = 1.0  # AI 思考延迟（秒）
        self.ai_speaking = False
        self.ai_speak_timer = 0.0
        self.ai_speak_min_time = 0.8  # 台词最少"读"多久再执行行动
        self.ai_speak_max_time = 2.5  # 台词最多读多久（兜底）
        self._pending_ai_action = None
        self.ai_dialogue = None     # 当前AI思考时的对话 (DialogueResult)
        self.ai_action_dialogue = None  # AI行动时的对话 (DialogueResult)
        self.ai_action_dialogue_timer = 0  # 行动对话显示计时器
        self.ai_action_dialogue_name = None  # 行动对话对应的玩家名
        self.ai_action_dialogue_revealed = ""  # 当前已逐字显示的文本
        self.ai_action_dialogue_reveal_timer = 0.0  # 逐字显示计时器
        self._pending_hand_end_results = None  # 摊牌后延迟处理的手尾
        self._hand_end_thread = None  # 后台执行 on_hand_end 的线程
        self.selected_player_index = None  # 点击弹出的玩家详情索引
        self.player_popup_close_btn = None  # 弹窗关闭按钮
        self.session_hand_history = []  # 本局对局内历史，仅在当前牌桌有效
        self._dealing_timer = 0.0  # 发牌动画计时器
        self._dealing_card_index = 0  # 当前已播放音效的牌索引
        self._dealing_total_cards = 0  # 本手需发的总牌数

        # 回放状态
        self.replay_state = None  # {hand_data, step, timer, paused, speed}
        self.replay_buttons = {}  # 回放控制按钮

        # 聊天系统
        self.chat_controller = ChatController(self)

        # AI 控制器
        self.ai_controller = AIController(self)

        # 手牌结束控制器
        self.hand_end_controller = HandEndController(self)

        # 游戏初始化
        self.game_setup = GameSetup(self)

        # 游戏回调
        self.game_callbacks = GameCallbacks(self)

        # 场景渲染器
        self.scene_renderer = SceneRenderer(self)

        # 场景事件处理器
        self.scene_event_handler = SceneEventHandler(self)

        # 设置参数
        self.setup_num_players = 4
        self.setup_blind_index = 1  # 10/20
        self.setup_betting_mode = BETTING_NO_LIMIT
        self.setup_deck_type = DECK_STANDARD
        self.setup_difficulty = DIFFICULTY_NORMAL
        self.setup_buy_in = DEFAULT_STARTING_CHIPS

        self._init_menu()
        self._init_setup()
        self._init_settings()
        self._init_bankruptcy()
        self._init_replay_buttons()

    def _init_menu(self):
        """初始化主菜单"""
        cx = SCREEN_WIDTH // 2
        self.menu_buttons = {
            "start": Button(cx - 100, 250, 200, 50, "开始游戏", color=(50, 120, 60)),
            "settings": Button(cx - 100, 320, 200, 50, "设置", color=(60, 80, 120)),
            "quit": Button(cx - 100, 390, 200, 50, "退出游戏", color=(120, 50, 50)),
            "bonus": Button(cx + 120, 250, 130, 36, "每日奖励", color=(160, 130, 50)),
            "loan": Button(cx + 120, 296, 130, 36, "申请贷款", color=(80, 80, 160)),
        }
        self.menu_buttons["start"].on_click = lambda: self._goto_scene("setup")
        self.menu_buttons["settings"].on_click = lambda: self._goto_scene("settings")
        self.menu_buttons["quit"].on_click = lambda: self._quit()
        self.menu_buttons["bonus"].on_click = self._handle_daily_bonus
        self.menu_buttons["loan"].on_click = self._handle_loan
        # 对战记录按钮（排行榜下方）
        self.history_button = Button(20, 0, 240, 36, "查看对战记录", color=(60, 80, 100))

    def _init_setup(self):
        """初始化设置界面"""
        cx = SCREEN_WIDTH // 2
        self.setup_components = {}

        # 玩家数量
        self.setup_components["num_players"] = Dropdown(
            cx - 100, 160, 200, 36,
            [f"{i}人" for i in range(MIN_PLAYERS, MAX_PLAYERS + 1)]
        )
        self.setup_components["num_players"].selected_index = 2  # 默认4人

        # 盲注
        self.setup_components["blinds"] = Dropdown(
            cx - 100, 240, 200, 36,
            [f"小盲{sb}/大盲{bb}" for sb, bb in BLIND_PRESETS]
        )

        # 下注模式
        self.setup_components["betting"] = Dropdown(
            cx - 100, 320, 200, 36,
            ["无限注 (No-Limit)", "底池限注 (Pot-Limit)", "限注 (Fixed-Limit)"]
        )

        # 牌组类型
        self.setup_components["deck"] = Dropdown(
            cx - 100, 400, 200, 36,
            ["标准牌组 (52张)", "短牌牌组 (36张, <5人)"]
        )

        # AI 难度
        self.setup_components["difficulty"] = Dropdown(
            cx - 100, 480, 200, 36,
            ["简单", "普通", "困难"]
        )
        self.setup_components["difficulty"].selected_index = 1  # 默认普通

        # 买入金额
        self.setup_components["buy_in"] = TextInput(
            cx - 100, 540, 200, 36, "输入买入金额", font_size=20,
            numeric_only=True, max_length=8
        )
        self.setup_components["buy_in"].text = str(DEFAULT_STARTING_CHIPS)

        # 开始/返回按钮
        self.setup_components["start_btn"] = Button(
            cx - 220, 610, 200, 50, "开始游戏", color=(50, 120, 60)
        )
        self.setup_components["back_btn"] = Button(
            cx + 20, 610, 200, 50, "返回", color=(80, 80, 80)
        )
        self.setup_components["start_btn"].on_click = self.game_setup.start_game
        self.setup_components["back_btn"].on_click = lambda: self._goto_scene("menu")

    def _init_settings(self):
        """初始化设置界面"""
        cx = SCREEN_WIDTH // 2
        self.settings_components = {}

        # === 音效设置 (左侧) ===
        # 音效开关
        self.settings_components["sound_toggle"] = Button(
            cx - 320, 160, 200, 40, "音效: 开", color=(50, 100, 80)
        )
        self.settings_components["sound_toggle"].on_click = self._toggle_sound

        # 音量滑块
        from ui.components import Slider
        self.settings_components["volume"] = Slider(
            cx - 320, 220, 200, 20, 0.0, 1.0, 0.5, show_value=False
        )

        # 全屏切换按钮
        self.settings_components["fullscreen_toggle"] = Button(
            cx - 320, 270, 200, 40, "全屏: 关", color=(60, 80, 120)
        )
        self.settings_components["fullscreen_toggle"].on_click = self._toggle_fullscreen_from_settings

        # 返回按钮
        self.settings_components["back_btn"] = Button(
            cx - 320, 610, 200, 50, "返回", color=(80, 80, 80)
        )
        self.settings_components["back_btn"].on_click = lambda: self._goto_scene("menu")

        # === LLM 对话配置 (右侧) ===
        panel_x = cx + 20
        panel_w = 380

        # 加载现有配置
        self._llm_cfg = self._read_llm_config()

        # API Key 输入
        self.settings_components["llm_api_key"] = TextInput(
            panel_x, 160, panel_w, 36, "输入 API Key", font_size=16, max_length=200
        )
        self.settings_components["llm_api_key"].text = self._llm_cfg.get("api_key", "")

        # API Base 输入
        self.settings_components["llm_api_base"] = TextInput(
            panel_x, 220, panel_w, 36, "API Base URL", font_size=16, max_length=200
        )
        self.settings_components["llm_api_base"].text = self._llm_cfg.get("api_base", "https://api.deepseek.com/v1")

        # 模型选择
        self.settings_components["llm_model"] = Dropdown(
            panel_x, 280, panel_w, 36,
            ["deepseek-v4-flash (快速·经济)", "deepseek-v4-pro (强力·推理)"],
            font_size=16
        )
        model = self._llm_cfg.get("model", "deepseek-v4-flash")
        if "pro" in model:
            self.settings_components["llm_model"].selected_index = 1

        # LLM 概率
        self.settings_components["llm_prob"] = Dropdown(
            panel_x, 340, panel_w, 36,
            ["10% 台词用 LLM", "30% 台词用 LLM", "50% 台词用 LLM", "80% 台词用 LLM", "全部用 LLM"],
            font_size=16
        )
        prob = self._llm_cfg.get("llm_probability", 0.3)
        prob_map = {0.1: 0, 0.3: 1, 0.5: 2, 0.8: 3, 1.0: 4}
        self.settings_components["llm_prob"].selected_index = prob_map.get(prob, 1)

        # 启用开关
        self.settings_components["llm_enabled"] = Dropdown(
            panel_x, 400, panel_w, 36,
            ["LLM 已关闭", "LLM 已开启"],
            font_size=16
        )
        self.settings_components["llm_enabled"].selected_index = 1 if self._llm_cfg.get("enabled") else 0

        # 测试/保存按钮
        self.settings_components["llm_test_btn"] = Button(
            panel_x, 460, 180, 40, "测试连接", color=(60, 100, 140)
        )
        self.settings_components["llm_save_btn"] = Button(
            panel_x + 200, 460, 180, 40, "保存配置", color=(50, 120, 60)
        )
        self.settings_components["llm_test_btn"].on_click = self._test_llm_connection
        self.settings_components["llm_save_btn"].on_click = self._save_llm_config

        # 测试结果显示
        self._llm_test_result = ""
        self._llm_test_result_color = (180, 180, 180)

    def _toggle_sound(self):
        self.audio.toggle()
        btn = self.settings_components["sound_toggle"]
        btn.text = "音效: 开" if self.audio.enabled else "音效: 关"
        btn.color = (50, 100, 80) if self.audio.enabled else (100, 50, 50)

    def _init_bankruptcy(self):
        """初始化破产/补充筹码界面"""
        cx = SCREEN_WIDTH // 2
        self.bankruptcy_buttons = {
            "rebuy": Button(cx - 220, 350, 200, 50, "从银行取出筹码", color=(50, 120, 60)),
            "quit": Button(cx + 20, 350, 200, 50, "离开并返回菜单", color=(120, 50, 50)),
            "loan": Button(cx - 220, 410, 200, 50, "申请贷款 5000", color=(80, 80, 160)),
            "bonus": Button(cx + 20, 410, 200, 50, "领取每日奖励", color=(160, 130, 50)),
        }
        self.bankruptcy_buttons["rebuy"].on_click = self._handle_rebuy
        self.bankruptcy_buttons["quit"].on_click = self._handle_bankruptcy_quit
        self.bankruptcy_buttons["loan"].on_click = self._handle_loan
        self.bankruptcy_buttons["bonus"].on_click = self._handle_daily_bonus

    def _init_replay_buttons(self):
        """初始化回放控制按钮"""
        cx = SCREEN_WIDTH // 2
        btn_y = SCREEN_HEIGHT - 50
        self.replay_buttons = {
            "replay_prev": Button(cx - 210, btn_y, 90, 36, "上一步", color=(60, 80, 120)),
            "replay_play": Button(cx - 100, btn_y, 90, 36, "播放", color=(50, 120, 60)),
            "replay_next": Button(cx + 10, btn_y, 90, 36, "下一步", color=(60, 80, 120)),
            "replay_back": Button(cx + 120, btn_y, 90, 36, "返回", color=(100, 50, 50)),
        }
        self.replay_buttons["replay_prev"].on_click = self._replay_prev
        self.replay_buttons["replay_play"].on_click = self._replay_toggle_play
        self.replay_buttons["replay_next"].on_click = self._replay_next
        self.replay_buttons["replay_back"].on_click = lambda: self._goto_scene("history")

    def _start_replay(self, hand_data):
        """开始回放指定手牌"""
        # 预处理动作数据：修复盲注阶段 + 按阶段排序（只做一次）
        actions = hand_data.get("actions", [])
        actions = fix_blind_phases(actions)
        actions = normalize_action_order(actions)
        hand_data = {**hand_data, "actions": actions}

        self.replay_state = {
            "hand_data": hand_data,
            "step": 0,
            "timer": 0.0,
            "paused": False,
            "speed": 1.0,
        }
        self.scene = "replay"

    def _replay_next(self):
        """回放前进一步"""
        if not self.replay_state:
            return
        actions = self.replay_state["hand_data"].get("actions", [])
        total = len(actions) + 1
        if self.replay_state["step"] < total:
            self.replay_state["step"] += 1
            self.replay_state["timer"] = 0.0

    def _replay_prev(self):
        """回放后退一步"""
        if not self.replay_state:
            return
        if self.replay_state["step"] > 0:
            self.replay_state["step"] -= 1
            self.replay_state["timer"] = 0.0

    def _replay_toggle_play(self):
        """切换回放播放/暂停"""
        if not self.replay_state:
            return
        self.replay_state["paused"] = not self.replay_state.get("paused", False)

    def _handle_rebuy(self):
        # 补充筹码
        rebuy_amount = getattr(self, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
        taken = self.save_manager.withdraw_from_bank(rebuy_amount)
        if taken > 0:
            self.human_player.chips = taken
            self.human_player_initial_chips = taken
            self.human_player.folded = False
            self.human_player.all_in = False

            # 重新开始一手，恢复背景音
            self.audio.play_background_music()
            self.scene = "playing"
            self._next_hand()
        else:
            # 银行真的没钱了，按钮变灰色禁用
            self.bankruptcy_buttons["rebuy"].enabled = False
            self.bankruptcy_buttons["rebuy"].text = "银行余额不足"

    def _handle_bankruptcy_quit(self):
        # 保存并退回主菜单
        self.audio.stop_all_sounds()
        self.save_manager.save(force=True)
        self.scene = "menu"

    def _handle_loan(self):
        """申请贷款5000筹码"""
        if self.save_manager.can_take_loan():
            self.save_manager.take_loan(5000)
            self.save_manager.save(force=True)

    def _handle_daily_bonus(self):
        """领取每日奖励2000筹码"""
        if self.save_manager.can_get_daily_bonus():
            self.save_manager.get_daily_bonus()
            self.save_manager.save(force=True)

    def _goto_scene(self, scene):
        self.scene = scene

    def _toggle_fullscreen(self):
        """切换全屏/窗口模式 — 全屏切换显示器分辨率到 1280x720，零缩放"""
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.display = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        else:
            self.display = pygame.display.set_mode(self._window_size, pygame.RESIZABLE)
        self.screen = self.display
        self.renderer.screen = self.display

    def _toggle_fullscreen_from_settings(self):
        """从设置界面切换全屏，并更新按钮文字"""
        self._toggle_fullscreen()
        btn = self.settings_components.get("fullscreen_toggle")
        if btn:
            btn.text = "全屏: 开" if self._fullscreen else "全屏: 关"
            btn.color = (40, 60, 100) if self._fullscreen else (60, 80, 120)

    def _map_mouse_pos(self, pos):
        """窗口和虚拟表面同为 1280x720，直接返回"""
        return pos

    def _present(self):
        """直接渲染到 display surface，无需 blit"""
        pass

    def _quit(self):
        pygame.quit()
        sys.exit()

    def _read_llm_config(self):
        """读取 LLM 配置文件"""
        import json

        config_path = os.path.join(APP_ROOT, "config", "llm_config.json")
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_llm_config(self):
        """从设置界面读取并保存 LLM 配置"""
        import json

        model_idx = self.settings_components["llm_model"].selected_index
        model = "deepseek-v4-pro" if model_idx == 1 else "deepseek-v4-flash"

        prob_idx = self.settings_components["llm_prob"].selected_index
        prob_values = [0.1, 0.3, 0.5, 0.8, 1.0]
        prob = prob_values[prob_idx]

        cfg = {
            "enabled": self.settings_components["llm_enabled"].selected_index == 1,
            "api_key": self.settings_components["llm_api_key"].text.strip(),
            "api_base": self.settings_components["llm_api_base"].text.strip() or "https://api.deepseek.com/v1",
            "model": model,
            "temperature": 0.8,
            "max_tokens": 100,
            "timeout": 5.0,
            "llm_probability": prob,
        }

        config_dir = os.path.join(APP_ROOT, "config")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "llm_config.json")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self._llm_test_result = "配置已保存!"
            self._llm_test_result_color = (80, 200, 80)
        except Exception as e:
            self._llm_test_result = f"保存失败: {e}"
            self._llm_test_result_color = (220, 80, 80)

    def _test_llm_connection(self):
        """测试 LLM API 连接"""
        api_key = self.settings_components["llm_api_key"].text.strip()
        api_base = self.settings_components["llm_api_base"].text.strip() or "https://api.deepseek.com/v1"
        model_idx = self.settings_components["llm_model"].selected_index
        model = "deepseek-v4-pro" if model_idx == 1 else "deepseek-v4-flash"

        if not api_key:
            self._llm_test_result = "请先输入 API Key"
            self._llm_test_result_color = (220, 180, 60)
            return

        self._llm_test_result = "测试中..."
        self._llm_test_result_color = (180, 180, 60)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=api_base)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "说一个字：好"}],
                max_tokens=10,
                temperature=0.5,
                timeout=10.0,
            )
            reply = response.choices[0].message.content.strip()
            self._llm_test_result = f"连接成功! 回复: {reply}"
            self._llm_test_result_color = (80, 200, 80)
        except Exception as e:
            err = str(e)[:80]
            self._llm_test_result = f"连接失败: {err}"
            self._llm_test_result_color = (220, 80, 80)

    def _load_llm_bridge(self):
        """加载 LLM 配置并创建 LLMBridge

        读取 config/llm_config.json，如果 enabled 且有 api_key 则创建 LLMBridge。
        失败时返回 (None, 0.3)，游戏正常使用模板台词。

        Returns: (llm_bridge, llm_probability)
        """
        cfg = self._read_llm_config()
        if not cfg:
            return None, 0.3

        llm_prob = cfg.get("llm_probability", 0.3)

        if not cfg.get("enabled") or not cfg.get("api_key"):
            return None, llm_prob

        try:
            from ai.dialogue_manager.providers.llm_bridge import LLMBridge, LLMConfig
            llm_config = LLMConfig(
                api_key=cfg["api_key"],
                api_base=cfg.get("api_base", "https://api.deepseek.com/v1"),
                model=cfg.get("model", "deepseek-v4-flash"),
                temperature=cfg.get("temperature", 0.8),
                max_tokens=cfg.get("max_tokens", 100),
                timeout=cfg.get("timeout", 5.0),
            )
            bridge = LLMBridge(config=llm_config)
            return bridge, llm_prob
        except Exception:
            return None, llm_prob

    # ==================== 游戏循环 ====================

    def _process_betting_round(self):
        """处理下注轮逻辑"""
        if self.game.phase == SHOWDOWN:
            return

        if self.game.is_betting_round_complete():
            self.game.end_betting_round()
            self.ai_controller.check_turn()
            return

        current = self.game.get_current_player()
        if not current or not current.can_act():
            self.game.advance_to_next_player()
            return

    def _advance_after_action(self):
        """玩家行动后推进游戏"""
        # 检查是否只剩一人
        if self.game.get_active_player_count() <= 1:
            self.game.go_to_showdown()
            return

        if self.game.is_betting_round_complete():
            self.game.end_betting_round()
        else:
            self.game.advance_to_next_player()

        self.ai_controller.check_turn()

    def _settle_ai_banks(self):
        """将 AI 玩家当前持有的筹码存回各自银行"""
        for player in self.players:
            if not player.is_human and hasattr(player, '_char_id') and player.chips > 0:
                char = self.character_pool.get_by_id(player._char_id)
                if char:
                    char.bank += player.chips
                    player.chips = 0
                    # 同步显示用的统计数据
                    if hasattr(player, '_char_stats'):
                        player._char_stats["bank"] = char.bank

    def _leave_game(self):
        """玩家主动离开对局，将剩余筹码存回银行"""
        # 停止所有音效和背景音乐
        self.audio.stop_all_sounds()
        # 等待后台 on_hand_end 线程完成
        if hasattr(self, '_hand_end_thread') and self._hand_end_thread:
            self._hand_end_thread.join(timeout=2.0)
            self._hand_end_thread = None
        if self.human_player:
            self.save_manager.deposit_to_bank(self.human_player.chips)
        # AI 玩家剩余筹码也存回银行
        self._settle_ai_banks()
        self.save_manager.save(force=True)
        # 清空聊天记录 (仅本局，不持久化)
        self.chat_controller.messages = []
        self.chat_controller.active = False
        if self.chat_controller.input:
            self.chat_controller.input.text = ""
            self.chat_controller.input.active = False
        self.scene = "menu"
        self.ai_thinking = False
        self.ai_speaking = False
        self._pending_ai_action = None
        self._pending_hand_end_results = None
        self.chat_controller.target = None
        self.animations.clear()

    def _next_hand(self):
        """开始下一手"""
        # 等待后台 on_hand_end 线程完成（通常用户看结算时已完成）
        if hasattr(self, '_hand_end_thread') and self._hand_end_thread:
            self._hand_end_thread.join(timeout=2.0)
            self._hand_end_thread = None
        self._pending_hand_end_results = None

        # 当前在场 AI 角色ID集合
        active_char_ids = set()
        for p in self.players:
            if not p.is_human and hasattr(p, '_char_id'):
                active_char_ids.add(p._char_id)

        # 1. 处理筹码为 0 的 AI 玩家：尝试从银行买入，买不起则换新玩家
        for p in self.players:
            if not p.is_human and p.chips == 0:
                char_id = getattr(p, '_char_id', None)
                if char_id:
                    char = self.character_pool.get_by_id(char_id)
                    if char and char.bank >= self.setup_buy_in:
                        # 从角色银行取钱重买入
                        char.bank -= self.setup_buy_in
                        p.chips = self.setup_buy_in
                    elif char and char.bank > 0:
                        # 银行不够买入，用剩余全部
                        p.chips = char.bank
                        char.bank = 0
                    else:
                        # 银行空了，尝试向排行榜前10富有角色借钱
                        borrow_result = self.character_pool.borrow_from_peer(
                            char_id, self.setup_buy_in
                        )
                        if borrow_result["success"]:
                            # 借钱成功，用借来的钱买入
                            borrowed = borrow_result["amount"]
                            char.bank = borrowed  # borrow_from_peer 已转入 char.bank
                            buy_amount = min(self.setup_buy_in, char.bank)
                            char.bank -= buy_amount
                            p.chips = buy_amount
                            # 聊天提示
                            self.chat_controller.messages.append({
                                "name": "系统",
                                "text": f"{char.name} 向 {borrow_result['lender_name']} 借了 {borrowed} 筹码",
                                "color": (255, 200, 100),
                            })
                        else:
                            # 借钱失败，角色离场，换新玩家
                            active_char_ids.discard(char_id)
                            new_chars = self.character_pool.pick_random_excluding(
                                1, active_char_ids
                            )
                            if new_chars:
                                new_char = new_chars[0]
                                active_char_ids.add(new_char.id)
                                # 基于原型生成一局随机性格
                                new_session_personality = Personality.randomized_from_archetype(new_char.archetype)
                                new_buy_in = min(self.setup_buy_in, new_char.bank)
                                new_char.bank -= new_buy_in
                                p.name = new_char.name
                                p.chips = new_buy_in
                                p.personality = new_session_personality
                                p._archetype = new_char.archetype
                                p._char_id = new_char.id
                                p._char_stats = {
                                    "hands_played": new_char.hands_played,
                                    "hands_won": new_char.hands_won,
                                    "total_profit": new_char.total_profit,
                                    "bank": new_char.bank,
                                }
                                # 重建 AI 大脑
                                num_players = len(self.players)
                                if num_players == 2:
                                    p.ai_brain = AdvancedAI(new_session_personality, difficulty=self.setup_difficulty)
                                else:
                                    p.ai_brain = MCTSAI(new_session_personality, difficulty=self.setup_difficulty)

                                # 加载持久化的对手记忆
                                for opp_key, mem_dict in new_char.opponent_memories.items():
                                    if isinstance(p.ai_brain, AdvancedAI):
                                        p.ai_brain.opponent_model = OpponentModel.from_dict(mem_dict)
                                    else:
                                        p.ai_brain.opponent_models[opp_key] = OpponentModel.from_dict(mem_dict)
                            else:
                                # 没有可用新角色，标记为弃牌
                                p.folded = True

        # 2. 检查人类玩家是否破产（输光了且 0 筹码）
        if self.human_player.chips == 0:
            # 按钮是否启用由银行余额决定
            rebuy_amount = getattr(self, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
            bank_balance = self.save_manager.player_data.bank
            self.bankruptcy_buttons["rebuy"].enabled = bank_balance >= rebuy_amount
            if bank_balance < rebuy_amount:
                self.bankruptcy_buttons["rebuy"].text = "银行余额不足"
            else:
                self.bankruptcy_buttons["rebuy"].text = f"从银行取出 {rebuy_amount}"
            self.audio.stop_background_music()
            self.audio.play_bankruptcy()
            self.scene = "bankruptcy"
            return

        # 3. 检查游戏是否结束 (除去可自动买入后，是否只剩一个玩家有筹码)
        if self.game.is_game_over():
            # 将人类玩家剩余筹码存回银行
            self.save_manager.deposit_to_bank(self.human_player.chips)
            # AI 玩家剩余筹码也存回银行
            self._settle_ai_banks()
            self.save_manager.save(force=True)
            self.audio.stop_background_music()
            # 清空聊天记录
            self.chat_controller.messages = []
            self.chat_controller.active = False
            if self.chat_controller.input:
                self.chat_controller.input.text = ""
                self.chat_controller.input.active = False
            self.scene = "menu"
            return

        # 移除淘汰玩家（标记但不从列表移除，保持座位）
        self.audio.play("shuffle")
        self.game.start_new_hand()
        self.showdown_results = None
        self.ai_thinking = False
        self.ai_speaking = False
        self._pending_ai_action = None
        self._pending_hand_end_results = None
        self.chat_controller.target = None
        # 重置每手初始筹码
        self.human_player_initial_chips = self.human_player.chips
        for p in self.players:
            p.initial_chips = p.chips
        # 启动发牌动画，动画结束后才进入 playing
        self._start_dealing_animation()

    def _start_dealing_animation(self):
        """创建逐张发牌动画，按小盲先发顺序"""
        from ui.animations import DealCardAnimation

        num_players = len(self.players)
        positions = self.renderer.get_seat_positions(self.players)
        # 牌堆位置：桌面中央偏上
        deck_x = SCREEN_WIDTH // 2
        deck_y = SCREEN_HEIGHT // 2 - 50

        # 发牌顺序：从小盲位开始，顺时针一圈，共两轮
        active_indices = [i for i, p in enumerate(self.players) if p.chips > 0]
        sb = self.game.small_blind_index
        # 以小盲为起点重排
        sb_pos = active_indices.index(sb) if sb in active_indices else 0
        deal_order = active_indices[sb_pos:] + active_indices[:sb_pos]

        self.animations.clear()
        card_delay = 0.12  # 每张牌间隔 0.12 秒
        card_duration = 0.25  # 每张牌飞行时间

        idx = 0
        for round_num in range(2):
            for seat_idx in deal_order:
                if seat_idx >= len(positions):
                    continue
                player = self.players[seat_idx]
                if not player.hole_cards or round_num >= len(player.hole_cards):
                    continue
                card = player.hole_cards[round_num] if round_num < len(player.hole_cards) else player.hole_cards[-1]
                end_pos = positions[seat_idx]
                # 牌飞到玩家位置上方（与静态底牌位置对齐）
                # 静态底牌顶部在 rect_y - 75 = (y-35) - 75 = y - 110
                # 动画卡片中心 y 需满足：y - 50 = y - 110 => y = y - 60
                end_y = end_pos[1] - 60
                face_up = player.is_human
                delay = idx * card_delay
                anim = DealCardAnimation(
                    (deck_x, deck_y), (end_pos[0], end_y),
                    card, duration=card_duration, face_up=face_up, delay=delay
                )
                self.animations.add(anim)
                idx += 1

        self._dealing_total_cards = idx
        self._dealing_card_index = 0
        self._dealing_timer = 0.0
        self.scene = "dealing"

    def update(self, dt):
        """每帧更新"""
        self.animations.update(dt)

        # 轮询 LLM 异步结果
        if hasattr(self, 'dialogue_manager') and self.dialogue_manager:
            llm_result = self.dialogue_manager.poll_llm_result()
            if llm_result:
                # LLM 回来了，替换当前行动对话
                self.ai_action_dialogue = llm_result
                self.ai_action_dialogue_timer = llm_result.duration
                self.ai_action_dialogue_name = llm_result.metadata.get("char_name", "")
                self.ai_action_dialogue_revealed = ""
                self.ai_action_dialogue_reveal_timer = 0.0
                # 同时更新聊天记录 (替换之前的模板消息)
                self.chat_controller.add_message(
                    llm_result.metadata.get("char_name", ""),
                    llm_result.text,
                    "llm",
                    replace_last_template=True,
                )

        # 轮询 AI 回复玩家聊天的结果
        if hasattr(self, 'dialogue_manager') and self.dialogue_manager:
            replies = self.dialogue_manager.poll_replies()
            for reply in replies:
                self.chat_controller.add_message(
                    reply.metadata.get("char_name", ""),
                    reply.text,
                    "llm"
                )

        # 情绪衰减
        if hasattr(self, 'players'):
            for p in self.players:
                if not p.is_human and hasattr(p, 'emotion_engine'):
                    p.emotion_engine.decay(dt)

        # 行动对话计时器
        if self.ai_action_dialogue_timer > 0:
            self.ai_action_dialogue_timer -= dt
            # 逐字显示效果：每个字约 0.08 秒
            if self.ai_action_dialogue:
                dialogue_text = self.ai_action_dialogue.text if hasattr(self.ai_action_dialogue, 'text') else str(self.ai_action_dialogue)
                self.ai_action_dialogue_reveal_timer += dt
                target_len = min(len(dialogue_text), int(self.ai_action_dialogue_reveal_timer / 0.08) + 1)
                if target_len > len(self.ai_action_dialogue_revealed):
                    self.ai_action_dialogue_revealed = dialogue_text[:target_len]
            if self.ai_action_dialogue_timer <= 0:
                self.ai_action_dialogue = None
                self.ai_action_dialogue_timer = 0
                self.ai_action_dialogue_revealed = ""

        if self.scene == "dealing":
            # 逐张播放发牌音效
            self._dealing_timer += dt
            card_delay = 0.12
            while self._dealing_card_index < self._dealing_total_cards:
                if self._dealing_timer >= self._dealing_card_index * card_delay:
                    self.audio.play("deal")
                    self._dealing_card_index += 1
                else:
                    break
            # 所有动画结束后进入 playing
            if not self.animations.is_busy:
                self.animations.clear()
                self.scene = "playing"
                self.ai_controller.check_turn()

        elif self.scene == "playing":
            if self.ai_thinking:
                self.ai_think_timer += dt
                # 思考延迟结束后启动后台 AI 决策
                if self.ai_think_timer >= self.ai_action_delay:
                    self.ai_controller.start_decision()
                # 轮询后台决策结果
                action = self.ai_controller.poll_decision()
                if action is not None:
                    self.ai_thinking = False
                    self.ai_speaking = True
                    self.ai_speak_timer = 0.0
                    self._pending_ai_action = action
            elif self.ai_speaking:
                self.ai_speak_timer += dt
                # 台词逐字显示完成，且过了最少读台词时间，才执行行动
                dialogue_text = ""
                if self.ai_action_dialogue:
                    dialogue_text = self.ai_action_dialogue.text if hasattr(self.ai_action_dialogue, 'text') else str(self.ai_action_dialogue)
                reveal_done = len(self.ai_action_dialogue_revealed) >= len(dialogue_text)
                min_done = self.ai_speak_timer >= self.ai_speak_min_time
                max_done = self.ai_speak_timer >= self.ai_speak_max_time
                if min_done and (reveal_done or max_done):
                    self.ai_speaking = False
                    self.ai_controller.execute_action(self._pending_ai_action)
                    self._pending_ai_action = None
                    self._advance_after_action()
            else:
                self._process_betting_round()

        elif self.scene == "showdown":
            self.showdown_timer += dt

        elif self.scene == "replay":
            if self.replay_state and not self.replay_state.get("paused", False):
                self.replay_state["timer"] += dt * self.replay_state.get("speed", 1.0)
                step_delay = 1.2  # 每步 1.2 秒
                if self.replay_state["timer"] >= step_delay:
                    self.replay_state["timer"] = 0.0
                    actions = self.replay_state["hand_data"].get("actions", [])
                    total = len(actions) + 1
                    if self.replay_state["step"] < total:
                        self.replay_state["step"] += 1
                    else:
                        self.replay_state["paused"] = True

    def handle_event(self, event):
        """处理事件"""
        self.scene_event_handler.handle_event(event)

    def _on_human_action(self, action_key):
        """人类玩家执行动作"""
        player = self.human_player
        player_index = self.game.players.index(player)
        legal = self.game.get_legal_actions(player_index)
        legal_types = set(legal)

        if action_key == "fold" and ActionType.FOLD in legal_types:
            self.game.execute_action(Action(player_index, ActionType.FOLD))
        elif action_key == "check" and ActionType.CHECK in legal_types:
            self.game.execute_action(Action(player_index, ActionType.CHECK))
        elif action_key == "call" and ActionType.CALL in legal_types:
            self.game.execute_action(Action(player_index, ActionType.CALL))
        elif action_key == "raise":
            # 确保从输入框同步最新数值到滑块
            ri = self.renderer.raise_input
            if ri.active and ri.int_value is not None:
                clamped = max(self.renderer.raise_slider.min_val,
                              min(self.renderer.raise_slider.max_val, ri.int_value))
                self.renderer.raise_slider.value = clamped
            raise_to = self.renderer.raise_slider.value
            if ActionType.RAISE in legal_types:
                self.game.execute_action(Action(player_index, ActionType.RAISE, raise_to))
            elif ActionType.BET in legal_types:
                self.game.execute_action(Action(player_index, ActionType.BET, raise_to))
        elif action_key == "all_in" and ActionType.ALL_IN in legal_types:
            self.game.execute_action(Action(player_index, ActionType.ALL_IN))
        else:
            return

        self.renderer.raise_input.active = False
        self._advance_after_action()

    def render(self):
        """渲染当前场景"""
        self.scene_renderer.render(self.scene)
        self._present()

    def run(self):
        """主循环"""
        import traceback as _tb
        while True:
            try:
                dt = self.clock.tick(FPS) / 1000.0

                for event in pygame.event.get():
                    self.handle_event(event)

                self.update(dt)
                self.render()

                pygame.display.flip()
            except Exception:
                _tb.print_exc()
                raise


def main():
    import traceback
    try:
        app = GameApp()
        app.run()
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
