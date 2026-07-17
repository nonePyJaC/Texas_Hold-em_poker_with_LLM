"""锦标赛流程控制：从 GameApp 中抽离的锦标赛业务逻辑。

包含：开始/继续锦标赛、设置锦标赛桌、每手结束后推进、
自动模拟（人类淘汰后）、离开锦标赛等。
"""


class TournamentFlow:
    """锦标赛流程控制器，持有 GameApp 引用，操作其状态。"""

    def __init__(self, app):
        self.app = app

    @property
    def controller(self):
        return self.app.tournament_controller

    @property
    def state(self):
        return self.controller.state if self.controller else None

    # ==================== 按钮初始化 ====================

    def init_buttons(self):
        """初始化锦标赛设置界面按钮"""
        from ui.components import Button
        from config import SCREEN_WIDTH
        cx = SCREEN_WIDTH // 2
        app = self.app
        app.tournament_buttons = {
            "start": Button(cx - 100, 480, 200, 50, "开始锦标赛", color=(140, 80, 160)),
            "continue": Button(cx - 100, 480, 200, 50, "继续锦标赛", color=(50, 120, 60)),
            "back": Button(cx - 100, 540, 200, 40, "返回菜单", color=(80, 80, 80)),
        }
        app.tournament_buttons["start"].on_click = self.start_tournament
        app.tournament_buttons["continue"].on_click = self.continue_tournament
        app.tournament_buttons["back"].on_click = lambda: app.switch_scene("menu")

    def goto_setup(self):
        """进入锦标赛设置页面"""
        self.init_buttons()
        self.app.switch_scene("tournament_setup")

    # ==================== 开始/继续 ====================

    def start_tournament(self):
        """开始新锦标赛"""
        if self.controller.start_tournament():
            self.setup_table("group")
        else:
            pass

    def continue_tournament(self):
        """继续已保存的锦标赛"""
        if self.controller.load_saved_tournament():
            state = self.state
            if state.phase.value == "group":
                self.setup_table("group")
            elif state.phase.value == "final":
                self.setup_table("final")
            elif state.phase.value == "ultimate":
                self.setup_table("ultimate")
            elif state.phase.value == "finished":
                self.app.switch_scene("tournament_result")

    # ==================== 设置锦标赛桌 ====================

    def setup_table(self, phase):
        """统一设置锦标赛桌（阶段1/2/3共用）

        Args:
            phase: "group" | "final" | "ultimate"
        """
        app = self.app
        state = self.state
        if not state:
            return
        if phase == "group":
            human = state.human_player
            if not human:
                return
            table = state.get_table(human.table_id)
        else:
            table = state.tables[0]
        if not table:
            return

        from engine.player import Player as EnginePlayer
        from ai.mcts_ai import MCTSAI, OpponentModel
        from ai.advanced_ai import AdvancedAI
        from ai.personality import Personality
        from ai.emotion import EmotionEngine
        from ai.memory import MemoryManager
        from ai.dialogue_manager import DialogueManager
        from ai.strategy_adapter import StrategyAdapter
        from engine.game import PokerGame
        from game_logic import GameCallbacks
        from config import DECK_SHORT, DECK_STANDARD, BETTING_NO_LIMIT, DIFFICULTY_HARD, DIFFICULTY_EXPERT

        # 按阶段确定参数
        if phase == "group":
            small_blind = state.GROUP_SMALL_BLIND
            big_blind = state.GROUP_BIG_BLIND
            deck_type = DECK_SHORT
            use_advanced = True  # 3人桌
            difficulty = DIFFICULTY_HARD  # 阶段1: 困难
        elif phase == "final":
            small_blind = state.FINAL_SMALL_BLIND
            big_blind = state.FINAL_BIG_BLIND
            deck_type = DECK_STANDARD
            use_advanced = False  # 8人桌用MCTS
            difficulty = DIFFICULTY_EXPERT  # 阶段2: 专家
        else:  # ultimate
            small_blind = state.ULTIMATE_SMALL_BLIND
            big_blind = state.ULTIMATE_BIG_BLIND
            deck_type = DECK_SHORT
            use_advanced = True  # ≤3人桌
            difficulty = DIFFICULTY_EXPERT  # 阶段3: 专家

        app.players = []
        for i, tp in enumerate(table.players):
            p = EnginePlayer(tp.name, tp.chips, is_human=tp.is_human, seat_index=i)
            if tp.is_human:
                app.human_player = p
            else:
                if tp.personality_dict:
                    personality = Personality.from_dict(tp.personality_dict)
                else:
                    personality = Personality.from_archetype(tp.archetype)
                p.personality = personality
                p._archetype = tp.archetype
                p._char_id = tp.char_id
                if use_advanced:
                    p.ai_brain = AdvancedAI(personality, difficulty=difficulty)
                    for opp_key, mem_dict in tp.opponent_memories.items():
                        p.ai_brain.opponent_model = OpponentModel.from_dict(mem_dict)
                else:
                    p.ai_brain = MCTSAI(personality, difficulty=difficulty)
                    for opp_key, mem_dict in tp.opponent_memories.items():
                        p.ai_brain.opponent_models[opp_key] = OpponentModel.from_dict(mem_dict)
                p.emotion_engine = EmotionEngine(personality)
            app.players.append(p)

        app.game = PokerGame(
            app.players,
            small_blind=small_blind,
            big_blind=big_blind,
            betting_mode=BETTING_NO_LIMIT,
            deck_type=deck_type,
        )

        app.game_callbacks.bind(app.game)
        app.game.on_showdown = app.hand_end_controller.on_showdown
        app.game.on_hand_end = self.on_hand_end

        app.memory_manager = MemoryManager()
        llm_bridge, llm_prob = app._load_llm_bridge()
        app.dialogue_manager = DialogueManager(llm_bridge=llm_bridge, llm_probability=llm_prob)
        app.dialogue_manager.reset_all_cooldowns()
        app.strategy_adapter = StrategyAdapter()
        app.chat_controller.reset()
        app.chat_controller.init_input()

        app.audio.play_background_music()
        app.audio.play("shuffle")
        app.game.start_new_hand()
        app.human_player_initial_chips = app.human_player.chips
        for p in app.players:
            p.initial_chips = p.chips
        app.ai_thinking = False
        app.showdown_results = None
        app.session_hand_history = []

        app.switch_scene("tournament")
        app._start_dealing_animation()

    # ==================== 每手结束回调 ====================

    def on_hand_end(self, results):
        """锦标赛中每手牌结束后的回调"""
        state = self.state
        if not state:
            return

        app = self.app
        # 同步筹码回 TournamentPlayer
        for p in app.players:
            tp = state.get_player_by_id(getattr(p, '_char_id', -1) if not p.is_human else -1)
            if tp:
                tp.chips = p.chips

        # 更新桌局数
        if state.phase.value == "group":
            table = state.get_table(state.current_table_id)
            if table:
                table.hand_count += 1
        elif state.phase.value == "final":
            state.final_hand_count += 1
        elif state.phase.value == "ultimate":
            state.ultimate_hand_count += 1

        state.save()

    # ==================== 推进锦标赛 ====================

    def advance(self):
        """锦标赛中一手牌结束后推进到下一手或下一阶段"""
        app = self.app
        state = self.state
        if not state:
            return

        # 同步筹码 + 更新桌局数（on_hand_end 不会被引擎调用，在此补偿）
        self.on_hand_end(app.showdown_results)

        # 检查人类玩家是否被淘汰（筹码为0）
        human = state.human_player
        if human and human.chips == 0 and not human.eliminated:
            human.eliminated = True
            state.save()

        if state.phase.value == "group":
            self._advance_group(state, human)
        elif state.phase.value == "final":
            self._advance_final(state, human)
        elif state.phase.value == "ultimate":
            self._advance_ultimate(state, human)

    def _start_next_hand(self):
        """开始下一手牌的公共逻辑"""
        app = self.app
        app.audio.play("shuffle")
        app.game.start_new_hand()
        app.showdown_results = None
        app.ai_thinking = False
        app._pending_hand_end_results = None
        app.human_player_initial_chips = app.human_player.chips
        for p in app.players:
            p.initial_chips = p.chips
        app._start_dealing_animation()

    def _advance_group(self, state, human):
        """小组赛阶段推进"""
        app = self.app
        table = state.get_table(state.current_table_id)
        if not table:
            return

        # 检查桌上是否只剩1人
        active = [p for p in app.players if p.chips > 0]
        if len(active) <= 1 or table.hand_count >= state.GROUP_MAX_HANDS:
            # 玩家桌结束
            if active:
                winner = max(active, key=lambda p: p.chips)
                table.winner_id = getattr(winner, '_char_id', -1) if not winner.is_human else -1
            table.finished = True
            state.save()

            # 检查所有桌是否完成
            if self.check_all_tables_done():
                # 进入决赛圈
                self.controller.advance_to_final_stage()
                self.setup_table("final")
            else:
                # 等待其他桌
                app.switch_scene("tournament_waiting")
        else:
            if human and human.eliminated:
                # 人类被淘汰，自动模拟玩家桌剩余牌局
                from tournament.table_simulator import TableSimulator
                from config import DECK_SHORT
                sim = TableSimulator(
                    table,
                    small_blind=state.GROUP_SMALL_BLIND,
                    big_blind=state.GROUP_BIG_BLIND,
                    deck_type=DECK_SHORT,
                    max_hands=state.GROUP_MAX_HANDS,
                )
                sim.run()
                state.save()
                if self.check_all_tables_done():
                    self.controller.advance_to_final_stage()
                    self.auto_simulate_final_and_ultimate()
                else:
                    app.switch_scene("tournament_waiting")
            else:
                # 继续下一手
                self._start_next_hand()

    def _advance_final(self, state, human):
        """决赛圈阶段推进"""
        app = self.app
        if human and human.chips == 0 and not human.eliminated:
            human.eliminated = True
            state.save()
        if human and human.eliminated:
            # 人类已淘汰，自动模拟决赛圈剩余牌局
            self.auto_simulate_final_and_ultimate()
        elif self.controller.check_final_stage_complete():
            self.controller.advance_to_ultimate_stage()
            if human and not human.eliminated:
                self.setup_table("ultimate")
            else:
                self.auto_simulate_ultimate()
        else:
            self._start_next_hand()

    def _advance_ultimate(self, state, human):
        """最终局阶段推进"""
        app = self.app
        if human and human.chips == 0 and not human.eliminated:
            human.eliminated = True
            state.save()
        if human and human.eliminated:
            self.auto_simulate_ultimate()
        elif self.controller.check_ultimate_stage_complete():
            self.controller.finish_tournament()
            app.audio.stop_background_music()
            app.switch_scene("tournament_result")
        else:
            self._start_next_hand()

    # ==================== 工具方法 ====================

    def check_all_tables_done(self) -> bool:
        """检查所有桌是否都已完成"""
        state = self.state
        if not state:
            return False
        for table in state.tables:
            if not table.finished:
                return False
        return True

    def auto_simulate_ultimate(self):
        """人类淘汰后自动模拟最终局到结束（后台线程）"""
        app = self.app
        state = self.state
        if not state:
            return
        table = state.tables[0]
        if not table:
            return

        app.switch_scene("tournament_waiting")
        import threading

        def _run():
            from tournament.table_simulator import TableSimulator
            from config import DECK_SHORT, DIFFICULTY_FAST
            sim = TableSimulator(
                table,
                small_blind=state.ULTIMATE_SMALL_BLIND,
                big_blind=state.ULTIMATE_BIG_BLIND,
                deck_type=DECK_SHORT,
                max_hands=state.ULTIMATE_MAX_HANDS,
                difficulty=DIFFICULTY_FAST,
            )
            sim.run()

            for tp in table.players:
                if tp.chips == 0:
                    tp.eliminated = True

            self.controller.finish_tournament()
            app.switch_scene("tournament_result")

        thread = threading.Thread(target=_run, daemon=True, name="auto-ultimate")
        thread.start()

    def auto_simulate_final_and_ultimate(self):
        """人类淘汰后自动模拟决赛圈+最终局到结束（后台线程）"""
        app = self.app
        state = self.state
        if not state:
            return

        app.switch_scene("tournament_waiting")
        import threading

        def _run():
            # 模拟决赛圈剩余牌局
            table = state.tables[0]
            if table and not self.controller.check_final_stage_complete():
                from tournament.table_simulator import TableSimulator
                from config import DECK_STANDARD, DIFFICULTY_FAST
                sim = TableSimulator(
                    table,
                    small_blind=state.FINAL_SMALL_BLIND,
                    big_blind=state.FINAL_BIG_BLIND,
                    deck_type=DECK_STANDARD,
                    max_hands=state.FINAL_MAX_HANDS,
                    difficulty=DIFFICULTY_FAST,
                )
                sim.run()

            # 进入最终局
            self.controller.advance_to_ultimate_stage()

            # 模拟最终局
            ultimate_table = state.tables[0]
            if ultimate_table:
                from tournament.table_simulator import TableSimulator
                from config import DECK_SHORT, DIFFICULTY_FAST
                sim = TableSimulator(
                    ultimate_table,
                    small_blind=state.ULTIMATE_SMALL_BLIND,
                    big_blind=state.ULTIMATE_BIG_BLIND,
                    deck_type=DECK_SHORT,
                    max_hands=state.ULTIMATE_MAX_HANDS,
                    difficulty=DIFFICULTY_FAST,
                )
                sim.run()

                for tp in ultimate_table.players:
                    if tp.chips == 0:
                        tp.eliminated = True

            self.controller.finish_tournament()
            app.switch_scene("tournament_result")

        thread = threading.Thread(target=_run, daemon=True, name="auto-final-ultimate")
        thread.start()

    def leave(self):
        """离开锦标赛（存档）"""
        app = self.app
        app.audio.stop_all_sounds()
        if hasattr(app, '_hand_end_thread') and app._hand_end_thread:
            app._hand_end_thread.join(timeout=2.0)
            app._hand_end_thread = None
        # 保存锦标赛状态
        if self.controller:
            state = self.state
            if state:
                for p in app.players:
                    tp = state.get_player_by_id(getattr(p, '_char_id', -1) if not p.is_human else -1)
                    if tp:
                        tp.chips = p.chips
                state.save()
        # 清空游戏状态
        app.game = None
        app.players = []
        app.human_player = None
        app.chat_controller.messages = []
        app.chat_controller.active = False
        if app.chat_controller.input:
            app.chat_controller.input.text = ""
            app.chat_controller.input.active = False
        app.switch_scene("menu")
