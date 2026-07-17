"""德州扑克游戏 - 主入口"""
import sys
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['SDL_IME_SHOW_UI'] = '1'
import pygame

# 显式设置 SDL hint 启用 IME 候选窗口（环境变量方式可能不生效）
try:
    import ctypes
    ctypes.CDLL('SDL2.dll').SDL_SetHint(b'SDL_IME_SHOW_UI', b'1')
except Exception:
    pass

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
    DECK_STANDARD,
    DIFFICULTY_NORMAL,
)
from ui.renderer import Renderer
from ui.scenes import SceneRenderer, SceneEventHandler
from ui.ui_factory import UIFactory
from ui.scenes.base_scene import BaseScene
from ui.scenes.legacy_scene import LegacyScene
from ui.scenes.menu_scene import MenuScene
from ui.scenes.setup_scene import SetupScene
from ui.scenes.settings_scene import SettingsScene
from ui.scenes.bankruptcy_scene import BankruptcyScene
from ui.scenes.showdown_scene import ShowdownScene
from ui.scenes.dealing_scene import DealingScene
from ui.scenes.replay_scene import ReplayScene
from ui.scenes.history_scene import HistoryScene
from ui.scenes.playing_scene import PlayingScene
from ui.scenes.tournament_scene import TournamentScene
from ui.scenes.tournament_setup_scene import TournamentSetupScene
from ui.scenes.tournament_waiting_scene import TournamentWaitingScene
from ui.scenes.tournament_result_scene import TournamentResultScene
from ui.animations import AnimationManager
from ui.audio import AudioEngine
from ai.ai_controller import AIController
from data.save_manager import SaveManager
from chat import ChatController
from game_logic import HandEndController, GameSetup, GameCallbacks
from game_logic.game_flow import GameFlow
from data.game_logger import GameLogger
from tournament.tournament_controller import TournamentController
from tournament.tournament_flow import TournamentFlow
from ai.llm_config_manager import LLMConfigManager
from game_logic.background_simulator import BackgroundSimulator, BroadcastMessage
from ui.broadcast_bar import BroadcastBar


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
        self.character_pool = self.save_manager.character_pool
        self.game_logger = GameLogger()
        self.tournament_controller = TournamentController(self)
        self.tournament_flow = TournamentFlow(self)
        self.llm_config_manager = LLMConfigManager(self)

        # 游戏状态
        self.game = None
        self.players = []
        self.human_player = None

        # UI 状态
        self.scene = "menu"  # 保留字符串用于向后兼容（update 内部分支）
        self._scene_map = {}  # 独立场景注册表，后续逐步填充
        self._register_scenes()
        self.current_scene = self._scene_map.get("menu", LegacyScene(self, "menu"))
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
        self.game_flow = GameFlow(self)

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

        self._ui_factory = UIFactory(self)
        self._ui_factory.init_menu()
        self._ui_factory.init_setup()
        self._ui_factory.init_settings()
        self._ui_factory.init_bankruptcy()
        self._ui_factory.init_replay_buttons()

        # 滚动播报栏
        self.broadcast_bar = BroadcastBar(SCREEN_WIDTH)

        # 后台 AI 模拟器
        self._bg_simulator = BackgroundSimulator(
            character_pool=self.character_pool,
            active_char_ids_provider=self._get_active_char_ids,
            broadcast_callback=self._on_background_broadcast,
        )

    def _toggle_sound(self):
        self.audio.toggle()
        btn = self.settings_components["sound_toggle"]
        btn.text = "音效: 开" if self.audio.enabled else "音效: 关"
        btn.color = (50, 100, 80) if self.audio.enabled else (100, 50, 50)

    # ==================== 锦标赛（委托 TournamentFlow）====================

    def _goto_tournament_setup(self):
        self.tournament_flow.goto_setup()

    def _start_tournament(self):
        self.tournament_flow.start_tournament()

    def _continue_tournament(self):
        self.tournament_flow.continue_tournament()

    def _setup_tournament_table(self, phase):
        self.tournament_flow.setup_table(phase)

    def _on_tournament_hand_end(self, results):
        self.tournament_flow.on_hand_end(results)

    def _advance_tournament(self):
        self.tournament_flow.advance()

    def _check_all_tables_done(self) -> bool:
        return self.tournament_flow.check_all_tables_done()

    def _auto_simulate_ultimate(self):
        self.tournament_flow.auto_simulate_ultimate()

    def _auto_simulate_final_and_ultimate(self):
        self.tournament_flow.auto_simulate_final_and_ultimate()

    def _leave_tournament(self):
        self.tournament_flow.leave()

    def _start_replay(self, hand_data):
        self._scene_map["replay"].start_replay(hand_data)

    def _replay_next(self):
        self._scene_map["replay"].replay_next()

    def _replay_prev(self):
        self._scene_map["replay"].replay_prev()

    def _replay_toggle_play(self):
        self._scene_map["replay"].replay_toggle_play()

    def _handle_rebuy(self):
        self._scene_map["bankruptcy"].handle_rebuy()

    def _handle_bankruptcy_quit(self):
        self._scene_map["bankruptcy"].handle_quit()

    def _handle_loan(self):
        self._scene_map["bankruptcy"].handle_loan()

    def _handle_daily_bonus(self):
        self._scene_map["bankruptcy"].handle_daily_bonus()

    def _register_scenes(self):
        """注册独立场景到 _scene_map。后续拆分时在此添加。"""
        self._scene_map["menu"] = MenuScene(self)
        self._scene_map["setup"] = SetupScene(self)
        self._scene_map["settings"] = SettingsScene(self)
        self._scene_map["bankruptcy"] = BankruptcyScene(self)
        self._scene_map["showdown"] = ShowdownScene(self)
        self._scene_map["dealing"] = DealingScene(self)
        self._scene_map["replay"] = ReplayScene(self)
        self._scene_map["history"] = HistoryScene(self)
        self._scene_map["playing"] = PlayingScene(self)
        self._scene_map["tournament"] = TournamentScene(self)
        self._scene_map["tournament_setup"] = TournamentSetupScene(self)
        self._scene_map["tournament_waiting"] = TournamentWaitingScene(self)
        self._scene_map["tournament_result"] = TournamentResultScene(self)

    def switch_scene(self, name: str):
        """切换场景。

        优先使用 _scene_map 中注册的独立 Scene；
        否则回退到 LegacyScene（委托旧逻辑）。

        Args:
            name: 场景名称字符串（如 "menu", "playing", "tournament" 等）
        """
        self.scene = name  # 向后兼容：update() 内部仍用 self.scene 分支
        if name in self._scene_map:
            self.current_scene.on_exit()
            self.current_scene = self._scene_map[name]
            self.current_scene.on_enter()
        else:
            # LegacyScene 只更新内部名称，不重新创建
            if isinstance(self.current_scene, LegacyScene):
                self.current_scene._scene_name = name
            else:
                self.current_scene = LegacyScene(self, name)

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
        # 锦标赛模式：showdown/dealing 也属于锦标赛
        if self.scene in ("tournament", "tournament_waiting"):
            self._leave_tournament()
            pygame.quit()
            sys.exit()
        # 锦标赛 showdown/dealing：检查是否锦标赛进行中
        if self.scene in ("showdown", "dealing") and self.game and self.game.on_hand_end == self._on_tournament_hand_end:
            self._leave_tournament()
            pygame.quit()
            sys.exit()
        # 如果在游戏中，先结算保存
        if self.scene in ("playing", "showdown", "dealing", "bankruptcy"):
            self._stop_background_simulator()
            if self.human_player:
                self.save_manager.deposit_to_bank(self.human_player.chips)
            self._settle_ai_banks()
            self.game_flow._process_ai_menu_loans()
            self.save_manager.save(force=True)
            if self.chat_controller.input:
                self.chat_controller.input.text = ""
                self.chat_controller.input.active = False
                pygame.key.stop_text_input()
        pygame.quit()
        sys.exit()

    # ==================== LLM 配置（委托 LLMConfigManager）====================

    def _read_llm_config(self):
        return self.llm_config_manager.read()

    def _save_llm_config(self):
        self.llm_config_manager.save()

    def _test_llm_connection(self):
        self.llm_config_manager.test_connection()

    def _load_llm_bridge(self):
        return self.llm_config_manager.load_bridge()

    # ==================== 游戏流程（委托 GameFlow）====================

    def _process_betting_round(self):
        self.game_flow.process_betting_round()

    def _advance_after_action(self):
        self.game_flow.advance_after_action()

    def _settle_ai_banks(self):
        self.game_flow.settle_ai_banks()

    def _get_active_char_ids(self):
        """返回当前上桌的 AI 角色ID集合"""
        ids = set()
        if self.players:
            for p in self.players:
                if not p.is_human and hasattr(p, '_char_id'):
                    ids.add(p._char_id)
        return ids

    def _on_background_broadcast(self, msg: BroadcastMessage):
        """后台模拟器播报回调（线程安全：只加入队列，主线程渲染）"""
        self.broadcast_bar.add(msg)

    def _start_background_simulator(self):
        self._bg_simulator.start()

    def _stop_background_simulator(self):
        self._bg_simulator.stop()

    def _leave_game(self):
        self.game_flow.leave_game()

    def _next_hand(self):
        self.game_flow.next_hand()

    def _start_dealing_animation(self):
        self.game_flow.start_dealing_animation()

    def _on_human_action(self, action_key):
        self.game_flow.on_human_action(action_key)

    def handle_event(self, event):
        """处理事件 — 委托给当前场景"""
        self.current_scene.handle_event(event)

    def update(self, dt):
        """更新当前场景 — 委托给当前场景"""
        self.current_scene.update(dt)
        self.broadcast_bar.update(dt)

    def render(self):
        """渲染当前场景 — 委托给当前场景"""
        self.current_scene.render(self.screen)
        # 滚动播报栏始终在最顶层
        self.broadcast_bar.draw(self.screen)

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
