"""UI 组件工厂：从 GameApp 中抽离的 _init_* 方法。

各方法在 GameApp 实例上创建 UI 组件（按钮、下拉菜单等），
供 SceneRenderer 渲染和 Scene 事件处理使用。
"""

from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    MIN_PLAYERS, MAX_PLAYERS,
    BLIND_PRESETS, BETTING_NO_LIMIT,
    DECK_STANDARD, DIFFICULTY_NORMAL,
    DEFAULT_STARTING_CHIPS,
)
from ui.components import Button, Dropdown, TextInput


class UIFactory:
    """创建各场景的 UI 组件，挂载到 GameApp 实例上。"""

    def __init__(self, app):
        self.app = app

    def init_menu(self):
        """初始化主菜单"""
        app = self.app
        cx = SCREEN_WIDTH // 2
        app.menu_buttons = {
            "start": Button(cx - 100, 250, 200, 50, "开始游戏", color=(50, 120, 60)),
            "tournament": Button(cx - 100, 310, 200, 50, "锦标赛", color=(140, 80, 160)),
            "settings": Button(cx - 100, 370, 200, 50, "设置", color=(60, 80, 120)),
            "quit": Button(cx - 100, 430, 200, 50, "退出游戏", color=(120, 50, 50)),
            "bonus": Button(cx + 120, 250, 130, 36, "每日奖励", color=(160, 130, 50)),
            "loan": Button(cx + 120, 296, 130, 36, "申请贷款", color=(80, 80, 160)),
        }
        app.menu_buttons["start"].on_click = lambda: app.switch_scene("setup")
        app.menu_buttons["tournament"].on_click = app._goto_tournament_setup
        app.menu_buttons["settings"].on_click = lambda: app.switch_scene("settings")
        app.menu_buttons["quit"].on_click = app._quit
        app.menu_buttons["bonus"].on_click = app._scene_map["bankruptcy"].handle_daily_bonus
        app.menu_buttons["loan"].on_click = app._scene_map["bankruptcy"].handle_loan
        app.history_button = Button(20, 0, 240, 36, "查看对战记录", color=(60, 80, 100))

    def init_setup(self):
        """初始化设置界面"""
        app = self.app
        cx = SCREEN_WIDTH // 2
        app.setup_components = {}

        app.setup_components["num_players"] = Dropdown(
            cx - 100, 160, 200, 36,
            [f"{i}人" for i in range(MIN_PLAYERS, MAX_PLAYERS + 1)]
        )
        app.setup_components["num_players"].selected_index = 2  # 默认4人

        app.setup_components["blinds"] = Dropdown(
            cx - 100, 240, 200, 36,
            [f"小盲{sb}/大盲{bb}" for sb, bb in BLIND_PRESETS]
        )

        app.setup_components["betting"] = Dropdown(
            cx - 100, 320, 200, 36,
            ["无限注 (No-Limit)", "底池限注 (Pot-Limit)", "限注 (Fixed-Limit)"]
        )

        app.setup_components["deck"] = Dropdown(
            cx - 100, 400, 200, 36,
            ["标准牌组 (52张)", "短牌牌组 (36张, <5人)"]
        )

        app.setup_components["difficulty"] = Dropdown(
            cx - 100, 480, 200, 36,
            ["简单", "普通", "困难"]
        )
        app.setup_components["difficulty"].selected_index = 1  # 默认普通

        app.setup_components["buy_in"] = TextInput(
            cx - 100, 540, 200, 36, "输入买入金额", font_size=20,
            numeric_only=True, max_length=8
        )
        app.setup_components["buy_in"].text = str(DEFAULT_STARTING_CHIPS)

        app.setup_components["start_btn"] = Button(
            cx - 220, 610, 200, 50, "开始游戏", color=(50, 120, 60)
        )
        app.setup_components["back_btn"] = Button(
            cx + 20, 610, 200, 50, "返回", color=(80, 80, 80)
        )
        app.setup_components["start_btn"].on_click = app.game_setup.start_game
        app.setup_components["back_btn"].on_click = lambda: app.switch_scene("menu")

    def init_settings(self):
        """初始化设置界面"""
        app = self.app
        cx = SCREEN_WIDTH // 2
        app.settings_components = {}

        # === 音效设置 (左侧) ===
        app.settings_components["sound_toggle"] = Button(
            cx - 320, 160, 200, 40, "音效: 开", color=(50, 100, 80)
        )
        app.settings_components["sound_toggle"].on_click = app._toggle_sound

        from ui.components import Slider
        app.settings_components["volume"] = Slider(
            cx - 320, 220, 200, 20, 0.0, 1.0, 0.5, show_value=False
        )

        app.settings_components["fullscreen_toggle"] = Button(
            cx - 320, 270, 200, 40, "全屏: 关", color=(60, 80, 120)
        )
        app.settings_components["fullscreen_toggle"].on_click = app._toggle_fullscreen_from_settings

        app.settings_components["back_btn"] = Button(
            cx - 320, 610, 200, 50, "返回", color=(80, 80, 80)
        )
        app.settings_components["back_btn"].on_click = lambda: app.switch_scene("menu")

        # === LLM 对话配置 (右侧) ===
        panel_x = cx + 20
        panel_w = 380

        app._llm_cfg = app._read_llm_config()

        app.settings_components["llm_api_key"] = TextInput(
            panel_x, 160, panel_w, 36, "输入 API Key", font_size=16, max_length=200
        )
        app.settings_components["llm_api_key"].text = app._llm_cfg.get("api_key", "")

        app.settings_components["llm_api_base"] = TextInput(
            panel_x, 220, panel_w, 36, "API Base URL", font_size=16, max_length=200
        )
        app.settings_components["llm_api_base"].text = app._llm_cfg.get("api_base", "https://api.deepseek.com/v1")

        app.settings_components["llm_model"] = Dropdown(
            panel_x, 280, panel_w, 36,
            ["deepseek-v4-flash (快速·经济)", "deepseek-v4-pro (强力·推理)"],
            font_size=16
        )
        model = app._llm_cfg.get("model", "deepseek-v4-flash")
        if "pro" in model:
            app.settings_components["llm_model"].selected_index = 1

        app.settings_components["llm_prob"] = Dropdown(
            panel_x, 340, panel_w, 36,
            ["10% 台词用 LLM", "30% 台词用 LLM", "50% 台词用 LLM", "80% 台词用 LLM", "全部用 LLM"],
            font_size=16
        )
        prob = app._llm_cfg.get("llm_probability", 0.3)
        prob_map = {0.1: 0, 0.3: 1, 0.5: 2, 0.8: 3, 1.0: 4}
        app.settings_components["llm_prob"].selected_index = prob_map.get(prob, 1)

        app.settings_components["llm_enabled"] = Dropdown(
            panel_x, 400, panel_w, 36,
            ["LLM 已关闭", "LLM 已开启"],
            font_size=16
        )
        app.settings_components["llm_enabled"].selected_index = 1 if app._llm_cfg.get("enabled") else 0

        app.settings_components["llm_test_btn"] = Button(
            panel_x, 460, 180, 40, "测试连接", color=(60, 100, 140)
        )
        app.settings_components["llm_save_btn"] = Button(
            panel_x + 200, 460, 180, 40, "保存配置", color=(50, 120, 60)
        )
        app.settings_components["llm_test_btn"].on_click = app._test_llm_connection
        app.settings_components["llm_save_btn"].on_click = app._save_llm_config

        app._llm_test_result = ""
        app._llm_test_result_color = (180, 180, 180)

    def init_bankruptcy(self):
        """初始化破产/补充筹码界面"""
        app = self.app
        cx = SCREEN_WIDTH // 2
        app.bankruptcy_buttons = {
            "rebuy": Button(cx - 220, 350, 200, 50, "从银行取出筹码", color=(50, 120, 60)),
            "quit": Button(cx + 20, 350, 200, 50, "离开并返回菜单", color=(120, 50, 50)),
            "loan": Button(cx - 220, 410, 200, 50, "申请贷款 5000", color=(80, 80, 160)),
            "bonus": Button(cx + 20, 410, 200, 50, "领取每日奖励", color=(160, 130, 50)),
        }
        app.bankruptcy_buttons["rebuy"].on_click = app._scene_map["bankruptcy"].handle_rebuy
        app.bankruptcy_buttons["quit"].on_click = app._scene_map["bankruptcy"].handle_quit
        app.bankruptcy_buttons["loan"].on_click = app._scene_map["bankruptcy"].handle_loan
        app.bankruptcy_buttons["bonus"].on_click = app._scene_map["bankruptcy"].handle_daily_bonus

    def init_replay_buttons(self):
        """初始化回放控制按钮"""
        app = self.app
        cx = SCREEN_WIDTH // 2
        btn_y = SCREEN_HEIGHT - 50
        app.replay_buttons = {
            "replay_prev": Button(cx - 210, btn_y, 90, 36, "上一步", color=(60, 80, 120)),
            "replay_play": Button(cx - 100, btn_y, 90, 36, "播放", color=(50, 120, 60)),
            "replay_next": Button(cx + 10, btn_y, 90, 36, "下一步", color=(60, 80, 120)),
            "replay_back": Button(cx + 120, btn_y, 90, 36, "返回", color=(100, 50, 50)),
        }
        app.replay_buttons["replay_prev"].on_click = app._scene_map["replay"].replay_prev
        app.replay_buttons["replay_play"].on_click = app._scene_map["replay"].replay_toggle_play
        app.replay_buttons["replay_next"].on_click = app._scene_map["replay"].replay_next
        app.replay_buttons["replay_back"].on_click = lambda: app.switch_scene("history")
