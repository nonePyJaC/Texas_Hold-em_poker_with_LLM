"""对局日志模块 - 记录每手牌的详细信息，按周自动清理"""
import os
import json
from datetime import datetime, timedelta

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_RETENTION_DAYS = 7


class GameLogger:
    """对局日志记录器"""

    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self._cleanup_old_logs()

    def _get_log_filename(self, dt=None):
        """获取给定日期的日志文件名（按天分文件）"""
        if dt is None:
            dt = datetime.now()
        return os.path.join(LOG_DIR, f"game_{dt.strftime('%Y%m%d')}.log")

    def _cleanup_old_logs(self):
        """清理超过保留天数的日志文件"""
        cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        try:
            for filename in os.listdir(LOG_DIR):
                if not filename.startswith("game_") or not filename.endswith(".log"):
                    continue
                date_str = filename[5:13]  # game_YYYYMMDD.log
                try:
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff:
                        filepath = os.path.join(LOG_DIR, filename)
                        os.remove(filepath)
                except ValueError:
                    continue
        except Exception:
            pass

    def log_hand(self, hand_number, players, community_cards, action_history,
                 results, payouts, evaluations):
        """记录一手牌的完整日志

        Args:
            hand_number: 手牌编号
            players: 玩家列表
            community_cards: 公共牌列表
            action_history: 动作历史列表
            results: 摊牌结果字典
            payouts: 派彩字典 {seat_index: amount}
            evaluations: 牌型评估字典 {seat_index: HandEvaluation}
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 玩家信息
        player_infos = []
        for p in players:
            hole_str = ""
            if p.hole_cards:
                hole_str = " ".join(
                    f"{c.rank_name}{c.suit_symbol}" for c in p.hole_cards
                )
            player_infos.append({
                "seat": p.seat_index,
                "name": p.name,
                "is_human": p.is_human,
                "hole_cards": hole_str,
                "total_bet": p.total_bet,
                "chips_before_hand": p.chips + p.total_bet,
                "chips_after_hand": p.chips,
                "folded": p.folded,
                "all_in": p.all_in,
            })

        # 公共牌
        comm_str = ""
        if community_cards:
            comm_str = " ".join(
                f"{c.rank_name}{c.suit_symbol}" for c in community_cards
            )

        # 动作历史
        actions = []
        for act in action_history:
            player = players[act.player_index] if act.player_index < len(players) else None
            name = player.name if player else f"Seat{act.player_index}"
            phase = self._guess_phase(actions, len(community_cards))
            actions.append({
                "phase": phase,
                "player": name,
                "action": act.action_type.value,
                "amount": act.amount,
            })

        # 摊牌结果
        showdown = []
        if results.get('fold_win'):
            for w in results.get('winners', []):
                net = results.get('pot_won', 0) - w.total_bet
                showdown.append({
                    "seat": w.seat_index,
                    "name": w.name,
                    "hand_type": "弃牌获胜",
                    "payout": results.get('pot_won', 0),
                    "total_bet": w.total_bet,
                    "net_profit": net,
                })
        else:
            for idx, amount in payouts.items():
                if idx < len(players):
                    p = players[idx]
                    ev = evaluations.get(idx)
                    net = amount - p.total_bet
                    showdown.append({
                        "seat": idx,
                        "name": p.name,
                        "hand_type": ev.name if ev else "未知",
                        "payout": amount,
                        "total_bet": p.total_bet,
                        "net_profit": net,
                    })

        # 所有未弃牌玩家的牌型（包括输家）
        all_evals = {}
        for idx, ev in evaluations.items():
            if idx < len(players):
                all_evals[players[idx].name] = ev.name if ev else "未知"

        entry = {
            "timestamp": timestamp,
            "hand_number": hand_number,
            "community_cards": comm_str,
            "players": player_infos,
            "actions": actions,
            "showdown": showdown,
            "all_evaluations": all_evals,
            "pot_total": sum(p.total_bet for p in players),
        }

        line = json.dumps(entry, ensure_ascii=False) + "\n"
        filepath = self._get_log_filename()
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _guess_phase(self, actions_so_far, comm_count):
        """根据公共牌数量推断当前阶段"""
        if comm_count == 0:
            return "preflop"
        elif comm_count == 3:
            return "flop"
        elif comm_count == 4:
            return "turn"
        elif comm_count >= 5:
            return "river"
        return "unknown"

    def get_hand_log(self, hand_number):
        """查询指定手牌编号的日志

        Args:
            hand_number: 手牌编号

        Returns:
            dict or None: 该手牌的日志记录
        """
        try:
            for filename in sorted(os.listdir(LOG_DIR), reverse=True):
                if not filename.startswith("game_") or not filename.endswith(".log"):
                    continue
                filepath = os.path.join(LOG_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("hand_number") == hand_number:
                                return entry
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass
        return None

    def get_recent_hands(self, count=10):
        """获取最近几手牌的日志摘要

        Args:
            count: 返回条数

        Returns:
            list of dict: 最近几手牌的摘要
        """
        results = []
        try:
            for filename in sorted(os.listdir(LOG_DIR), reverse=True):
                if not filename.startswith("game_") or not filename.endswith(".log"):
                    continue
                filepath = os.path.join(LOG_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        results.append({
                            "hand_number": entry.get("hand_number"),
                            "timestamp": entry.get("timestamp"),
                            "community_cards": entry.get("community_cards"),
                            "showdown": entry.get("showdown"),
                        })
                        if len(results) >= count:
                            return results
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return results
