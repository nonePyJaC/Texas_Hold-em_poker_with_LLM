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
import gc
import threading
from collections import deque, defaultdict

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

        # 帧尖峰检测
        self._spike_thresholds = [
            (0.500, "CRITICAL"),  # >500ms
            (0.100, "SEVERE"),    # >100ms
            (0.033, "WARNING"),   # >33ms
        ]
        self._spike_last_log = {}  # threshold -> last log time
        self._spike_cooldown = 10.0  # 同一档位尖峰日志冷却秒数

        # 上下文追踪
        self._recent_scene_changes = deque(maxlen=3)  # (timestamp, old_scene, new_scene)
        self._recent_events = deque(maxlen=3)  # (timestamp, event_desc)

        # 端到端任务耗时统计 (P1-02.3)
        self._task_stats = defaultdict(lambda: {
            "count": 0, "total_ms": 0.0, "max_ms": 0.0,
            "failures": 0,
        })
        self._task_thresholds = {
            "ai_decision": 2000.0,    # ms
            "llm_request": 5000.0,
            "table_sim": 3000.0,
            "tournament_sim": 5000.0,
            "save": 1000.0,
            "audit_write": 500.0,
        }

    def set_stats_provider(self, provider):
        """设置外部统计提供者，返回 dict 包含后台模拟/AI/队列等指标"""
        self._stats_provider = provider

    def record_frame(self, fps, total_dt):
        self._fps_history.append(fps)
        self._frame_times.append(total_dt)
        self._frame_count += 1

        now = time.perf_counter()

        # 帧尖峰检测
        self._check_spike(total_dt, now)

        if now - self._last_log >= self.log_interval:
            self._dump_log()
            self._last_log = now

    def _check_spike(self, total_dt, now):
        """检测帧尖峰并记录事件日志"""
        for threshold, level in self._spike_thresholds:
            if total_dt > threshold:
                last = self._spike_last_log.get(threshold, 0.0)
                if now - last < self._spike_cooldown:
                    return
                self._spike_last_log[threshold] = now
                self._log_spike(total_dt, level, now)
                return

    def _log_spike(self, total_dt, level, now):
        """输出一条帧尖峰事件日志"""
        dt_ms = total_dt * 1000

        # 收集上下文
        thread_count = 0
        if self._process:
            try:
                thread_count = self._process.num_threads()
            except Exception:
                pass

        bg_tables = 0
        bg_players = 0
        active_ai = 0
        dialogue_queue = 0
        chat_messages = 0
        if self._stats_provider:
            try:
                stats = self._stats_provider()
                bg_tables = stats.get("bg_tables", 0)
                bg_players = stats.get("bg_players", 0)
                active_ai = stats.get("active_ai", 0)
                dialogue_queue = stats.get("dialogue_queue", 0)
                chat_messages = stats.get("chat_messages", 0)
            except Exception:
                pass

        lines = []
        lines.append(f"[SPIKE] {level} 帧尖峰 {dt_ms:.0f}ms (scene={self._scene})")
        lines.append(f"  Threads              {thread_count}")
        lines.append(f"  BG Tables            {bg_tables}")
        lines.append(f"  BG Players           {bg_players}")
        lines.append(f"  Active AI Total      {active_ai}")
        lines.append(f"  Dialogue Queue       {dialogue_queue}")
        lines.append(f"  Chat Messages        {chat_messages}")

        # 近期场景切换
        if self._recent_scene_changes:
            recent = []
            for ts, old_s, new_s in self._recent_scene_changes:
                ago = now - ts
                if ago < 30.0:
                    recent.append(f"{old_s}->{new_s}({ago:.1f}s ago)")
            if recent:
                lines.append(f"  Recent Scenes        {'; '.join(recent)}")

        # 近期事件
        if self._recent_events:
            recent_ev = []
            for ts, desc in self._recent_events:
                ago = now - ts
                if ago < 30.0:
                    recent_ev.append(f"{desc}({ago:.1f}s ago)")
            if recent_ev:
                lines.append(f"  Recent Events        {'; '.join(recent_ev)}")

        logger.info("\n".join(lines))

        # 清理过期上下文
        cutoff = now - 30.0
        while self._recent_scene_changes and self._recent_scene_changes[0][0] < cutoff:
            self._recent_scene_changes.popleft()
        while self._recent_events and self._recent_events[0][0] < cutoff:
            self._recent_events.popleft()

    def record_phase(self, phase, elapsed):
        if phase in self._phase_totals:
            self._phase_totals[phase] += elapsed
            self._phase_counts[phase] += 1

    def set_scene(self, scene_name):
        if scene_name != self._scene:
            old = self._scene
            self._scene = scene_name
            self._recent_scene_changes.append((time.perf_counter(), old, scene_name))
            logger.info(f"[PERF] 场景切换 -> {scene_name}")

    def record_event(self, desc):
        """记录近期事件（存档、结算等）用于尖峰日志上下文"""
        self._recent_events.append((time.perf_counter(), desc))

    def record_task(self, task_type, elapsed_ms, failed=False):
        """记录端到端任务耗时（P1-02.3）

        Args:
            task_type: "ai_decision"/"llm_request"/"table_sim"/"tournament_sim"/"save"/"audit_write"
            elapsed_ms: 耗时（毫秒）
            failed: 是否失败
        """
        s = self._task_stats[task_type]
        s["count"] += 1
        s["total_ms"] += elapsed_ms
        if elapsed_ms > s["max_ms"]:
            s["max_ms"] = elapsed_ms
        if failed:
            s["failures"] += 1

        # 阈值告警
        threshold = self._task_thresholds.get(task_type, 0)
        if threshold > 0 and elapsed_ms > threshold:
            logger.warning(
                f"[TASK-SLOW] {task_type} 耗时 {elapsed_ms:.0f}ms "
                f"(阈值 {threshold:.0f}ms, scene={self._scene})"
            )

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
        # 资源快照 (P1-02.2)
        animations_count = 0
        broadcast_count = 0
        card_cache_size = 0
        avatar_cache_size = 0
        text_cache_size = 0
        hand_history_count = 0
        llm_pending = 0

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
                animations_count = stats.get("animations", 0)
                broadcast_count = stats.get("broadcast_msgs", 0)
                card_cache_size = stats.get("card_cache", 0)
                avatar_cache_size = stats.get("avatar_cache", 0)
                text_cache_size = stats.get("text_cache", 0)
                hand_history_count = stats.get("hand_history", 0)
                llm_pending = stats.get("llm_pending", 0)
            except Exception as e:
                logger.warning(f"[PERF] 统计采样异常: {e}")

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
        # GC 计数
        gc_counts = gc.get_count()
        lines.append(f"  GC gen0/1/2          {gc_counts[0]}/{gc_counts[1]}/{gc_counts[2]}")
        lines.append("Queues:")
        lines.append(f"  Dialogue             {dialogue_queue}")
        lines.append(f"  Chat Messages        {chat_messages}")
        lines.append(f"  LLM Pending          {llm_pending}")
        lines.append("Caches:")
        lines.append(f"  Card Cache           {card_cache_size}")
        lines.append(f"  Avatar Cache         {avatar_cache_size}")
        lines.append(f"  Text Cache           {text_cache_size}")
        lines.append(f"  Animations           {animations_count}")
        lines.append(f"  Broadcast Msgs       {broadcast_count}")
        lines.append(f"  Hand History         {hand_history_count}")

        # 端到端任务耗时 (P1-02.3)
        task_lines = []
        for task_type in ["ai_decision", "llm_request", "table_sim", "tournament_sim", "save", "audit_write"]:
            s = self._task_stats.get(task_type)
            if s and s["count"] > 0:
                avg_ms = s["total_ms"] / s["count"]
                task_lines.append(
                    f"  {task_type:<20} n={s['count']} avg={avg_ms:.0f}ms "
                    f"max={s['max_ms']:.0f}ms fail={s['failures']}"
                )
        if task_lines:
            lines.append("Tasks:")
            lines.extend(task_lines)

        logger.info("\n".join(lines))

        # 重置累计
        for k in self._phase_totals:
            self._phase_totals[k] = 0.0
            self._phase_counts[k] = 0
        self._frame_count = 0
        for s in self._task_stats.values():
            s["count"] = 0
            s["total_ms"] = 0.0
            s["max_ms"] = 0.0
            s["failures"] = 0


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
