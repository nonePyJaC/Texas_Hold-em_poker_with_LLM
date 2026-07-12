"""GameSetup：负责从设置界面创建并初始化一局游戏"""
from config import (
    DEFAULT_STARTING_CHIPS,
    MIN_PLAYERS,
    BLIND_PRESETS,
    BETTING_NO_LIMIT, BETTING_POT_LIMIT, BETTING_FIXED_LIMIT,
    DECK_STANDARD, DECK_SHORT,
    DIFFICULTY_EASY, DIFFICULTY_NORMAL, DIFFICULTY_HARD,
)
from engine.game import PokerGame
from engine.player import Player
from ai.mcts_ai import MCTSAI, OpponentModel
from ai.advanced_ai import AdvancedAI
from ai.personality import Personality
from ai.emotion import EmotionEngine
from ai.memory import MemoryManager
from ai.dialogue_manager import DialogueManager
from ai.strategy_adapter import StrategyAdapter


class GameSetup:
    """管理游戏初始化：解析设置、创建玩家、AI 大脑、情绪引擎、游戏实例"""

    def __init__(self, game_app):
        self.app = game_app

    def start_game(self):
        """从设置界面开始游戏"""
        app = self.app

        # 解析设置
        num_players = MIN_PLAYERS + app.setup_components["num_players"].selected_index
        sb, bb = BLIND_PRESETS[app.setup_components["blinds"].selected_index]
        betting_modes = [BETTING_NO_LIMIT, BETTING_POT_LIMIT, BETTING_FIXED_LIMIT]
        betting_mode = betting_modes[app.setup_components["betting"].selected_index]
        deck_types = [DECK_STANDARD, DECK_SHORT]
        deck_type = deck_types[app.setup_components["deck"].selected_index]

        try:
            buy_in = int(app.setup_components["buy_in"].text)
            if buy_in < 1:
                buy_in = DEFAULT_STARTING_CHIPS
        except (ValueError, TypeError):
            buy_in = DEFAULT_STARTING_CHIPS
        app.setup_buy_in = buy_in

        difficulty_map = [DIFFICULTY_EASY, DIFFICULTY_NORMAL, DIFFICULTY_HARD]
        app.setup_difficulty = difficulty_map[app.setup_components["difficulty"].selected_index]

        # 短牌仅 <5 人时可用
        if num_players >= 5 and deck_type == DECK_SHORT:
            deck_type = DECK_STANDARD

        # 使用 SaveManager 的角色池
        app.character_pool = app.save_manager.character_pool

        # 创建记忆管理器
        app.memory_manager = MemoryManager()

        # 创建对话管理器 (注入 LLM Bridge)
        llm_bridge, llm_prob = app._load_llm_bridge()
        app.dialogue_manager = DialogueManager(
            llm_bridge=llm_bridge,
            llm_probability=llm_prob,
        )
        app.dialogue_manager.reset_all_cooldowns()

        # 初始化聊天
        app.chat_controller.reset()
        app.chat_controller.init_input()

        # 创建策略适配器
        app.strategy_adapter = StrategyAdapter()

        # 检查银行余额
        if app.save_manager.player_data.bank < buy_in:
            return

        # 从角色池随机选取 AI 角色
        ai_chars = app.character_pool.pick_random(num_players - 1)

        # 人类玩家从银行取筹码
        human_buy_in = app.save_manager.withdraw_from_bank(buy_in)
        app.players = []
        app.human_player = Player("你", human_buy_in, is_human=True, seat_index=0)
        app.players.append(app.human_player)

        for i, char in enumerate(ai_chars):
            session_personality = Personality.randomized_from_archetype(char.archetype)
            ai_buy_in = min(buy_in, char.bank)
            char.bank -= ai_buy_in
            p = Player(char.name, ai_buy_in, is_human=False, seat_index=i + 1)
            p.personality = session_personality
            p._archetype = char.archetype
            if num_players == 2:
                p.ai_brain = AdvancedAI(session_personality, difficulty=app.setup_difficulty)
            else:
                p.ai_brain = MCTSAI(session_personality, difficulty=app.setup_difficulty)

            for opp_key, mem_dict in char.opponent_memories.items():
                if isinstance(p.ai_brain, AdvancedAI):
                    p.ai_brain.opponent_model = OpponentModel.from_dict(mem_dict)
                else:
                    p.ai_brain.opponent_models[opp_key] = OpponentModel.from_dict(mem_dict)

            p._char_id = char.id
            p._char_stats = {
                "hands_played": char.hands_played,
                "hands_won": char.hands_won,
                "total_profit": char.total_profit,
                "bank": char.bank,
            }
            p.emotion_engine = EmotionEngine(session_personality)
            app.players.append(p)

        # 创建游戏
        app.game = PokerGame(
            app.players,
            small_blind=sb,
            big_blind=bb,
            betting_mode=betting_mode,
            deck_type=deck_type,
        )

        # 设置回调
        app.game_callbacks.bind(app.game)
        app.game.on_showdown = app.hand_end_controller.on_showdown
        app.game.on_hand_end = app.hand_end_controller.on_hand_end

        # 重置本局内历史
        app.session_hand_history = []

        # 开始第一手
        app.audio.play_background_music()
        app.audio.play("shuffle")
        app.game.start_new_hand()
        app.human_player_initial_chips = app.human_player.chips
        for p in app.players:
            p.initial_chips = p.chips
        app.ai_thinking = False
        app.showdown_results = None

        # 启动发牌动画，动画结束后才进入 playing
        app._start_dealing_animation()
