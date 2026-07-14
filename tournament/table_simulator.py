"""后台桌模拟器 — 纯 AI 对局，无渲染/LLM/音效

用于锦标赛阶段1的其他7桌（玩家不在的桌），快速模拟对局。
"""
import random
import logging

from engine.game import PokerGame
from engine.player import Player
from engine.action import Action, ActionType
from ai.mcts_ai import MCTSAI, OpponentModel
from ai.advanced_ai import AdvancedAI
from ai.personality import Personality
from ai.emotion import EmotionEngine
from config import (
    DECK_SHORT, DECK_STANDARD,
    BETTING_NO_LIMIT,
    DIFFICULTY_NORMAL,
    PREFLOP, SHOWDOWN,
)

logger = logging.getLogger(__name__)


class TableSimulator:
    """单桌模拟器：纯 AI 对局，快速结算"""

    def __init__(self, table_info, small_blind, big_blind,
                 deck_type=DECK_SHORT, max_hands=30, difficulty=DIFFICULTY_NORMAL):
        """Args:
            table_info: TableInfo 对象
            small_blind, big_blind: 盲注
            deck_type: 牌组类型
            max_hands: 最多局数
            difficulty: AI 难度
        """
        self.table_info = table_info
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.deck_type = deck_type
        self.max_hands = max_hands
        self.difficulty = difficulty
        self.game = None
        self.players = []

    def _create_players(self):
        """从 TableInfo 创建 Player 对象"""
        self.players = []
        for i, tp in enumerate(self.table_info.players):
            p = Player(tp.name, tp.chips, is_human=False, seat_index=i)
            p._char_id = tp.char_id
            p._archetype = tp.archetype

            # 重建性格
            if tp.personality_dict:
                personality = Personality.from_dict(tp.personality_dict)
            else:
                personality = Personality.from_archetype(tp.archetype)
            p.personality = personality

            # 重建 AI 大脑
            if len(self.table_info.players) == 2:
                p.ai_brain = AdvancedAI(personality, difficulty=self.difficulty)
            else:
                p.ai_brain = MCTSAI(personality, difficulty=self.difficulty)

            # 加载对手记忆
            for opp_key, mem_dict in tp.opponent_memories.items():
                if isinstance(p.ai_brain, AdvancedAI):
                    p.ai_brain.opponent_model = OpponentModel.from_dict(mem_dict)
                else:
                    p.ai_brain.opponent_models[opp_key] = OpponentModel.from_dict(mem_dict)

            p.emotion_engine = EmotionEngine(personality)
            self.players.append(p)

    def _is_player_eliminated(self, p: Player) -> bool:
        """玩家是否被淘汰：筹码为0或出不起小盲"""
        return p.chips == 0 or p.chips < self.small_blind

    def _get_active_count(self) -> int:
        """有筹码的玩家数"""
        return sum(1 for p in self.players if p.chips > 0)

    def _play_one_hand(self):
        """模拟一手牌"""
        # 过滤出有筹码的玩家参与
        active_players = [p for p in self.players if p.chips > 0]
        if len(active_players) <= 1:
            return

        # 创建临时游戏（只含有筹码的玩家）
        self.game = PokerGame(
            active_players,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            betting_mode=BETTING_NO_LIMIT,
            deck_type=self.deck_type,
        )
        self.game.start_new_hand()

        # 快速推进游戏
        while self.game.phase != SHOWDOWN:
            current = self.game.get_current_player()
            if not current or not current.can_act():
                # 检查下注轮是否结束
                if self.game.is_betting_round_complete():
                    self.game.end_betting_round()
                else:
                    self.game.advance_to_next_player()
                continue

            # 检查是否只剩一人
            if self.game.get_active_player_count() <= 1:
                self.game.go_to_showdown()
                break

            # AI 决策
            player_index = self.game.players.index(current)
            try:
                action = current.ai_brain.decide(self.game, player_index)
            except Exception:
                legal = self.game.get_legal_actions(player_index)
                if legal:
                    action = Action(player_index, legal[0].action_type)
                else:
                    action = Action(player_index, ActionType.FOLD)

            self.game.execute_action(action)

            # 检查是否只剩一人
            if self.game.get_active_player_count() <= 1:
                self.game.go_to_showdown()
                break

            # 检查下注轮
            if self.game.is_betting_round_complete():
                self.game.end_betting_round()

        # 摊牌结算
        if self.game.phase == SHOWDOWN:
            self.game._do_showdown()

    def run(self):
        """运行整桌直到决出胜者或达到最大局数"""
        self._create_players()

        while self.table_info.hand_count < self.max_hands:
            # 检查是否只剩一人有筹码
            active = [p for p in self.players if p.chips > 0]
            if len(active) <= 1:
                break

            # 检查是否有玩家出不起小盲（也算淘汰）
            can_play = [p for p in active if p.chips >= self.small_blind]
            if len(can_play) <= 1:
                # 把出不起小盲的标记为淘汰
                for p in active:
                    if p.chips < self.small_blind:
                        p.chips = 0
                break

            self._play_one_hand()
            self.table_info.hand_count += 1

        # 确定胜者：筹码最高者
        active = [p for p in self.players if p.chips > 0]
        if active:
            winner = max(active, key=lambda p: p.chips)
            self.table_info.winner_id = winner._char_id
        else:
            # 所有人都没筹码了（极端情况），取第一个
            self.table_info.winner_id = self.players[0]._char_id

        self.table_info.finished = True

        # 同步筹码回 TableInfo
        for tp, p in zip(self.table_info.players, self.players):
            tp.chips = p.chips

        logger.info(f"桌 {self.table_info.table_id} 完成，{self.table_info.hand_count} 局，"
                     f"胜者: {winner.name if active else 'N/A'}")
