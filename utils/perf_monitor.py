"""性能监控模块 — 定期记录帧率、各阶段耗时、系统指标到日志文件

日志格式示例:
=== World Tick ===
Time: 18:25:31
Scene: playing
FPS: avg=60.0 min=58.2 max=60.0
Frame Time: avg=16.7ms max=21.3ms
CPU:
  Game Thread          1.40ms
  Render               2.10ms
  Flip                 3.20ms
  AI Decision          0.80ms
Background:
  Tables Running       3
  Active AI Players    24
  Hands/sec            5.2
  Active AI Total      52
Memory:
  RSS                  156MB
  Threads              8
Queues:
  Dialogue             2
  Chat Messages        5
"""
import time
import os
import logging
from collections import deque

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

logger = logging.getLogger("perf")

_perf_monitor = None


class PerfMonitor:
    """单例性能监控器，每 N 秒输出一次汇总日志"""

    def __init__(self, log_interval=10.0, fps_window=120):
        self.log_interval = log_interval
        self._fps_history = deque(maxlen=fps_window)
        self._frame_times = deque(maxlen=fps_window)
        self._last_log = time.perf_counter()

        # 各阶段累计耗时
        self._phase_totals = {
            "event": 0.0,
            "update": 0.0,
            "render": 0.0,
            "flip": 0.0,
            "ai_decision": 0.0,
        }
        self._phase_counts = {
            "event": 0,
            "update": 0,
            "render": 0,
            "flip": 0,
            "ai_decision": 0,
        }
        self._frame_count = 0

        # 场景
        self._scene = "unknown"

        # 外部指标提供者（每帧调用获取最新值）
        self._stats_provider = None  # callable -> dict

        # 累计外部计数器（用于计算速率）
        self._prev_hands_played = 0
        self._prev_log_time = time.perf_counter()

        # 进程信息
        self._pid = os.getpid()
        self._process = psutil.Process(self._pid) if _HAS_PSUTIL else None

    def set_stats_provider(self, provider):
        """设置外部统计提供者，返回 dict 包含后台模拟/AI/队列等指标"""
        self._stats_provider = provider

    def record_frame(self, fps, total_dt):
        self._fps_history.append(fps)
        self._frame_times.append(total_dt)
        self._frame_count += 1

        now = time.perf_counter()
        if now - self._last_log >= self.log_interval:
            self._dump_log()
            self._last_log = now

    def record_phase(self, phase, elapsed):
        if phase in self._phase_totals:
            self._phase_totals[phase] += elapsed
            self._phase_counts[phase] += 1

    def set_scene(self, scene_name):
        if scene_name != self._scene:
            self._scene = scene_name
            logger.info(f"[PERF] 场景切换 -> {scene_name}")

    def _avg_phase(self, phase):
        n = max(self._phase_counts.get(phase, 1), 1)
        return self._phase_totals.get(phase, 0.0) / n * 1000  # ms

    def _dump_log(self):
        if not self._fps_history:
            return

        now = time.perf_counter()
        elapsed = now - self._prev_log_time

        # FPS
        fps_list = list(self._fps_history)
        avg_fps = sum(fps_list) / len(fps_list)
        min_fps = min(fps_list)
        max_fps = max(fps_list)

        # Frame time
        ft_list = list(self._frame_times)
        avg_ft = sum(ft_list) / len(ft_list) * 1000  # ms
        max_ft = max(ft_list) * 1000

        # CPU phases
        avg_event = self._avg_phase("event")
        avg_update = self._avg_phase("update")
        avg_render = self._avg_phase("render")
        avg_flip = self._avg_phase("flip")
        avg_ai = self._avg_phase("ai_decision")
        game_thread = avg_event + avg_update

        # 进程信息
        mem_mb = 0
        thread_count = 0
        if self._process:
            try:
                mem_info = self._process.memory_info()
                mem_mb = mem_info.rss / 1024 / 1024
                thread_count = self._process.num_threads()
            except Exception:
                pass

        # 外部统计
        bg_tables = 0
        bg_players = 0
        bg_hands_total = 0
        active_ai = 0
        dialogue_queue = 0
        chat_messages = 0
        hands_per_sec = 0.0
        game_players = 0
        game_buy_in = 0
        game_deck_type = "standard"
        game_betting = "no_limit"
        game_blind = "0"
        is_tournament = False
        table_name = ""

        if self._stats_provider:
            try:
                stats = self._stats_provider()
                bg_tables = stats.get("bg_tables", 0)
                bg_players = stats.get("bg_players", 0)
                bg_hands_total = stats.get("bg_hands_total", 0)
                active_ai = stats.get("active_ai", 0)
                dialogue_queue = stats.get("dialogue_queue", 0)
                chat_messages = stats.get("chat_messages", 0)
                game_players = stats.get("game_players", 0)
                game_buy_in = stats.get("game_buy_in", 0)
                game_deck_type = stats.get("game_deck_type", "standard")
                game_betting = stats.get("game_betting", "no_limit")
                game_blind = stats.get("game_blind", "0")
                is_tournament = stats.get("is_tournament", False)
                table_name = stats.get("table_name", "")
            except Exception:
                pass

        # 计算 hands/sec
        hands_delta = bg_hands_total - self._prev_hands_played
        if elapsed > 0:
            hands_per_sec = hands_delta / elapsed
        self._prev_hands_played = bg_hands_total
        self._prev_log_time = now

        # 多行格式输出
        lines = []
        lines.append("=== World Tick ===")
        lines.append(f"Time: {time.strftime('%H:%M:%S')}")
        lines.append(f"Scene: {self._scene}")
        if game_players > 0 or is_tournament:
            mode = "锦标赛" if is_tournament else "普通对局"
            lines.append(f"Game Context:")
            lines.append(f"  Mode                 {mode}")
            lines.append(f"  Table                {table_name}")
            lines.append(f"  Players              {game_players}")
            lines.append(f"  Buy-in               {game_buy_in:,}")
            lines.append(f"  Deck                 {game_deck_type}")
            lines.append(f"  Betting              {game_betting}")
            lines.append(f"  Blind Index          {game_blind}")
        lines.append(f"FPS: avg={avg_fps:.1f} min={min_fps:.1f} max={max_fps:.1f}")
        lines.append(f"Frame Time: avg={avg_ft:.1f}ms max={max_ft:.1f}ms")
        lines.append("CPU:")
        lines.append(f"  Game Thread          {game_thread:.2f}ms")
        lines.append(f"  Render               {avg_render:.2f}ms")
        lines.append(f"  Flip                 {avg_flip:.2f}ms")
        lines.append(f"  AI Decision          {avg_ai:.2f}ms")
        lines.append("Background:")
        lines.append(f"  Tables Running       {bg_tables}")
        lines.append(f"  Active AI Players    {bg_players}")
        lines.append(f"  Hands/sec            {hands_per_sec:.1f}")
        lines.append(f"  Active AI Total      {active_ai}")
        lines.append("Memory:")
        lines.append(f"  RSS                  {mem_mb:.0f}MB")
        lines.append(f"  Threads              {thread_count}")
        lines.append("Queues:")
        lines.append(f"  Dialogue             {dialogue_queue}")
        lines.append(f"  Chat Messages        {chat_messages}")

        logger.info("\n".join(lines))

        # 重置累计
        for k in self._phase_totals:
            self._phase_totals[k] = 0.0
            self._phase_counts[k] = 0
        self._frame_count = 0


def get_monitor():
    global _perf_monitor
    if _perf_monitor is None:
        _perf_monitor = PerfMonitor()
    return _perf_monitor


def init_logging(log_dir=None):
    """初始化性能日志文件"""
    if log_dir is None:
        log_dir = os.getcwd()
    log_path = os.path.join(log_dir, "perf.log")

    handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))

    perf_logger = logging.getLogger("perf")
    perf_logger.setLevel(logging.INFO)
    perf_logger.handlers.clear()
    perf_logger.addHandler(handler)
    perf_logger.propagate = False

    logger.info("[PERF] 性能监控已启动，日志文件: " + log_path)
    return log_path
