# 更新日志 / Changelog

## V1.5.1 (2026-07-17)

### 新功能
- **中文 IME 候选框修复**：`main.py` 在 `import pygame` 前设置 `SDL_IME_SHOW_UI=1` 环境变量，并通过 `ctypes` 显式调用 `SDL_SetHint`，启用 Windows 原生 IME 候选窗口显示
  - `ui/components.py` 的 `TextInput.draw()` 每帧同步 `set_text_input_rect` 到光标位置，确保候选框跟随输入框
- **场所状态横向展示栏**：`ui/scenes/scene_renderer.py` 的 `_draw_background_info` 改为屏幕最顶部居中横向条，9 格（"我" + 1-8 号桌）一字排开，不再遮挡右侧排行榜

### Bug 修复
- **播报栏位置重叠**：`ui/broadcast_bar.py` 的 y 坐标从 8 调整到 42，避免与顶部场所栏重叠
- **离开游戏卡顿**：`game_logic/background_simulator.py` 的 `stop()` 线程 join 超时从 10s 降到 2s；`game_logic/game_flow.py` 的 `leave_game()` 中 `_hand_end_thread` join 超时从 2s 降到 0.5s

### 优化
- 后台模拟器 8 桌固定场所模型：桌子固定 1-8 号，玩家随机进入，凑够 2-8 人开局
- 模拟节奏放慢：手间间隔 5-12s，桌间间隔 10-25s，轮间间隔 15-40s
- 播报栏滚动速度调整为 60px/s

---

## V1.5 (2026-07-17)

### 新功能
- **后台 AI 模拟系统**：`game_logic/background_simulator.py` 后台线程模拟 8 桌场所，AI 随机上桌打牌
  - 随机牌型（标准/短牌）、盲注、买入金额
  - 每桌 3-8 手，手间/桌间/轮间有真实节奏间隔
  - 结算写回角色 bank，统计在线桌数和人数
- **大牌播报系统**：`ui/broadcast_bar.py` 横向滚动播报栏，展示后台桌同花及以上大牌
  - 不同牌型不同颜色高亮
  - 平滑滚动 + 渐入渐出动画
- **场所状态展示**：游戏界面顶部横向展示当前开桌数、在线人数、今日累计桌数
- **锦标赛模式**：完整的多人锦标赛系统
  - `tournament/` 模块：`tournament_state.py`（数据模型）、`table_simulator.py`（后台AI桌模拟器）、`tournament_controller.py`（主控制器）、`tournament_flow.py`（流程委托）
  - 三阶段赛制：分组赛 → 决赛 → 终极对决，每阶段自动推进
  - 后台 AI 桌快速模拟（MCTS 快速模式 200 次模拟 / 0.3s 超时）
  - AI 角色新增 `tournament_wins` 字段，排行榜显示 🏆 冠军标记
  - 锦标赛场景 UI：报名页 / 等待页 / 进行中 / 结果页
  - 锦标赛存档支持
- **AI 慢打策略 + 台词伪装**：AI 概率性进入慢打模式
  - 新增 `slow_play_frequency` 性格特质，强牌时概率性慢打而非激进加注
  - 台词系统在慢打时伪装弱牌强度，诱导对手加注
  - 角色台词去除暴露性内容，新增 `dialogue_context_builder.py`
- **AI 补筹码与换人**：AI 筹码归零时，若银行余额 >= 买入金额则自动补筹码，否则替换为新角色
- **主菜单 AI 借款系统**：返回主菜单时银行不足的 AI 自动向富有角色借款，保持角色池经济活力
- **LLM 配置管理器**：新增 `llm_config_manager.py`，支持游戏内配置 LLM 参数
- **场景系统重构**：`main.py` 拆分为独立场景模块
  - `ui/scenes/` 下新增 `base_scene.py`、`menu_scene.py`、`setup_scene.py`、`settings_scene.py`、`playing_scene.py`、`dealing_scene.py`、`showdown_scene.py`、`bankruptcy_scene.py`、`replay_scene.py`、`history_scene.py` 等
  - `ui/ui_factory.py` 统一管理 UI 组件初始化
  - `game_logic/game_flow.py` 抽离对局流程逻辑（离场、AI 补筹码、AI 借款）

### Bug 修复
- **修复离开游戏闪退**：`game_flow.py` 缺少 `import pygame`，调用 `pygame.key.stop_text_input()` 时 `NameError`
- **修复聊天渲染崩溃**：系统消息缺少 `source` 字段导致 `KeyError`，渲染改用 `.get()` 安全访问
- **修复 LLM 调用超时参数**：`LLMBridge._call_api_with_system()` 不支持 `timeout` 关键字参数
- **修复破产场景筹码丢失**：破产退出时人类玩家剩余筹码未存回银行
- **修复破产音乐不停**：破产界面点击贷款/每日奖励时不停止背景音乐
- **修复 AI 破产卡住**：`character_pool` 未初始化 + 盲注分配不跳过 0 筹码玩家 + 淘汰 AI 未标记 `all_in`
- **修复离开不结算**：破产离开时 AI 筹码未结算回银行 + 点 X 退出不保存
- **修复摊牌结果为空**：`ui/renderer.py` 用列表索引而非 `seat_index` 查找 evaluations/payouts
- **修复回放与赢家信息为空**：`game_logger.py` 和 `hand_end_controller.py` 中 payouts/evaluations 查找使用 `seat_index` 映射
- **修复存档被覆盖**：诊断脚本意外将玩家银行余额覆盖为 100000，已恢复

### 优化
- 买入金额阈值从硬编码 1000 改为动态 `app.setup_buy_in`
- 系统消息统一添加 `source` 字段
- 破产场景退出时触发 AI 借款处理
- AI 角色池从 40 扩展到 52 个（V1.3 起已生效，文档补记）

---

## V1.4 (2026-07-14)

### Bug 修复
- **修复 IndexError: list index out of range**：`game_callbacks.py` 中 `action.player_index` 越界崩溃
  - 根因：`engine/player.py` 的 `fold()`/`check()`/`call()`/`bet()`/`raise_to()`/`all_in_bet()` 方法内部用 `self.seat_index`（物理座位号 0-7）创建 `last_action`，而回调函数用 `action.player_index`（列表索引）访问 `game.players` 列表，两者不一致导致越界
  - 修复：移除 Player 方法内的 `last_action` 赋值，统一在 `engine/game.py` 的 `execute_action` 中用正确的列表索引创建 `last_action`
- **修复 `game_callbacks.py:102`**：ALL_IN 感知逻辑中 `p.seat_index != action.player_index` 混用座位号与列表索引，改为对象身份比较 `p is not actor`
- **修复 `engine/game.py:590`**：`_calculate_side_pots` 中 `payouts.keys()` 返回 `seat_index` 值，却用于索引 `self.players` 列表，改为通过 `seat_index -> player` 映射查找
- **修复 `engine/game.py` get_legal_actions**：玩家筹码不够跟注时始终包含 FOLD 选项

### 优化
- **牌桌背景渲染**：`draw_table` 先填充黑色背景再 blit 桌面图，消除透明通道导致的噪点
- **LLM Prompt 约束**：添加明确规则禁止 AI 在诈唬时做出与牌力矛盾的陈述
- 清理 `_calculate_side_pots` 中的无用代码

---

## V1.3 (2026-07-13)

### 新功能
- **SQLite 存储迁移**：AI 角色数据和手牌历史从 JSON 迁移到 SQLite
  - `CharacterDB` 管理角色数据，支持 JSON 自动迁移
  - `HandHistoryDB` 存储完整手牌日志（玩家、动作、摊牌结果）
  - 性能更好，存储量更大，自动清理超过 50 手的旧记录
- **手牌历史回放**：可在对战记录页面回放最近 50 手完整牌局
  - 逐步回放每个动作，显示玩家信息、底牌、公共牌、底池
  - 控制按钮：播放/暂停、上一步/下一步、返回
  - 键盘快捷键：SPACE（播放/暂停）、←/→（步进）、ESC（返回）
  - `Action.phase` 字段记录每个动作的游戏阶段，回放更准确
- **跨手对话记忆**：AI 对话上下文扩展至跨手维度
  - `recent_hand_results`：最近 5 手结果（如 "弃牌 → 输了-200 → 赢了+500"）
  - `session_summary`：本局会话摘要（如 "已打15手，近3手赢1输1弃1，连胜2手"）
  - 聊天历史 Token 优化：超过 5 条自动压缩，仅保留最近 5 条
- **AI 性格动态演化**：角色基础性格基于累积经验自动微调
  - 每 10 手触发一次，根据胜率、盈亏趋势调整 5 个性格维度
  - 适应性（adaptivity）高的角色变化更快
  - 调整幅度极小（0.01-0.03），多局累积后产生明显风格变化
  - 性格值始终限制在 [0.05, 0.95] 范围内

### 优化
- AI 角色池从 40 扩展到 52 个，覆盖全部预设名字
- 手牌日志每手都记录到 SQLite（原来每 3 手记录一次）
- Prompt Token 优化：完整 prompt 约 467 tokens，重负载约 601 tokens

---

## V1.2 (2026-07-13)

### 新功能
- **LLM 对话上下文增强**：所有 LLM 回复现在携带更丰富的上下文
  - AI 自己的底牌（可据此诈唬，但 prompt 明确禁止暴露具体牌面）
  - 当前公共牌
  - 上一小局自己的结果（赢/输/弃牌及盈亏）
  - 本小局 LLM 生成的聊天记录作为对话上下文（最近10条，过滤本地预制消息）
- **行动台词路径补全**：AI 决策后说话现在也能引用自己的底牌和公共牌
- **聊天回复路径补全**：AI 回复玩家@消息时现在也能引用上一局结果和聊天历史

### 优化
- 统一两条 LLM 调用路径的上下文信息，消除信息不对称
- LLM 最大输出从 60 tokens 提升到 100 tokens（约50个中文字），台词更丰富
- 对话气泡最大宽度从 280px 扩大到 360px，多行显示更美观
- 聊天历史上下文仅传 LLM 生成的消息，避免本地预制台词占用 token
- **动态 temperature**：LLM temperature 根据情绪状态动态调整（tilt 高 +0.2，confidence 高 -0.2，excitement 高 +0.1），让台词风格更贴合情绪
- **牌桌信息密度提升**：底池移至中央公共牌上方带半透明背景，阶段信息改为胶囊式徽章带阶段配色，下注信息带背景条醒目显示
- **摊牌动画**：新增悬念延迟（0.4s 渐暗 + "摊牌中..." 脉冲文字）→ 面板滑入（0.4s ease-out）→ 赢家行金色脉冲光效

---

## V1.1 (2026-07-12)

### 新功能
- **AI 借贷系统**：AI 角色银行破产时，可向排行榜前 10 富有角色借钱继续游戏
  - 基于交手历史计算信任度，决定借出金额
  - 关系好的 AI 更愿意借钱，关系差的可能被拒
  - AI 赢钱后自动偿还利润的 50% 给债主
  - 借款和还款事件在聊天框显示系统消息
  - 债务数据持久化到 `characters.json`

### 优化
- 修复 AI 角色银行全部耗尽时游戏无法继续的问题
- 聊天消息支持多行换行显示，不再截断

### 打包
- 所有素材路径改为相对路径，支持 PyInstaller 打包
- 提供 `dezhou.spec` 打包配置文件

---

## V1.0 (2026-07-10)

### 初始版本
- 完整德州扑克玩法（无限注/底池限/固定注）
- MCTS 蒙特卡洛树搜索 AI 决策系统
- LLM 驱动的 AI 角色对话系统（DeepSeek API）
- 40 个预设角色，各有独特性格和背景
- 情绪引擎、记忆系统、关系系统
- 发牌动画、筹码可视化、聊天系统
- 存档系统、银行系统、对局日志
