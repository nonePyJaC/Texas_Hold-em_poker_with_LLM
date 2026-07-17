# 德州扑克 - Texas Hold'em with LLM (V1.5)

一个基于 Python + Pygame 开发的德州扑克游戏，集成 LLM（大语言模型）驱动的 AI 对手对话系统。

## ✨ 特性

- **完整德州扑克玩法**：支持 2-8 人对局，无限注/底池限/固定注模式，盲注可调
- **AI 对手**：基于 MCTS 蒙特卡洛树搜索 + 性格模型的 AI 决策系统
- **LLM 对话**：接入 DeepSeek API，AI 角色会说出台词，支持诈唬、嘲讽、互动
- **情绪系统**：AI 角色有情绪引擎，赢/输/被诈唬会影响后续行为
- **记忆系统**：AI 角色会记住与你的对局历史，影响关系和策略
- **AI 借贷系统**：AI 角色破产时可向富有角色借钱，基于交手关系决定信任度，赢钱后自动还款
- **AI 补筹码与换人**：AI 筹码归零时自动从银行补买入或替换为新角色，对局不中断
- **主菜单 AI 借款**：返回主菜单时银行不足的 AI 自动向富友借款，保持角色池经济活力
- **中文输入法支持**：支持 IME 候选框（TEXTEDITING 事件 + per-frame 输入框定位）
- **角色池**：52 个预设角色，各有独特性格、背景和对话风格
- **聊天系统**：可在游戏中与 AI 角色实时聊天
- **发牌动画**：卡牌从牌堆飞向玩家的动画效果
- **筹码可视化**：按面值分摞展示底池筹码
- **存档系统**：自动保存进度，支持银行系统管理筹码
- **对局日志**：详细记录每手牌的过程和结果

## 🎮 截图

> 游戏主界面：8 人德州扑克牌桌，含 AI 对手、底池、公共牌区

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Pygame 2.6+
- OpenAI SDK（用于 LLM 对话功能，可选）

### 安装依赖

```bash
pip install pygame openai
```

### 运行

```bash
python main.py
```

### LLM 配置（可选）

1. 复制配置模板：
```bash
cp config/llm_config.example.json config/llm_config.json
```

2. 编辑 `config/llm_config.json`，填入你的 API Key：
```json
{
  "enabled": true,
  "api_key": "your-api-key-here",
  "api_base": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-flash",
  "temperature": 0.8,
  "max_tokens": 60,
  "timeout": 5.0,
  "llm_probability": 0.3
}
```

> 也可以在游戏内「设置 → LLM 配置」界面直接填写。

> 不配置 LLM 也能正常游戏，AI 会使用模板台词。

### 打包为 EXE

```bash
pip install pyinstaller
python -m PyInstaller dezhou.spec --noconfirm
```

生成的 EXE 位于 `dist/德州扑克.exe`。

## 📁 项目结构

```
.
├── main.py                 # 主入口
├── config.py               # 全局配置（窗口、颜色、游戏参数）
├── engine/                 # 游戏引擎
│   ├── action.py           # 动作定义
│   ├── deck.py             # 牌组
│   ├── game.py             # 游戏流程
│   ├── hand_evaluator.py   # 手牌评估
│   ├── player.py           # 玩家
│   └── pot.py              # 底池
├── ai/                     # AI 系统
│   ├── advanced_ai.py      # AI 决策
│   ├── mcts_ai.py          # MCTS 搜索
│   ├── ai_controller.py    # AI 控制器
│   ├── emotion.py          # 情绪引擎
│   ├── personality.py      # 性格模型
│   ├── character_pool.py   # 角色池
│   ├── character_descriptions.py  # 角色描述
│   ├── dialogue.py         # 对话系统
│   └── memory/             # 记忆系统
│       ├── manager.py      # 记忆管理器
│       ├── models.py       # 数据模型
│       ├── storage.py      # SQLite 存储
│       ├── player_memory.py
│       ├── statistics_memory.py
│       ├── relationship_memory.py
│       └── episode_memory.py
├── chat/                   # 聊天系统
│   └── chat_controller.py
├── game_logic/             # 游戏流程控制
│   ├── hand_end_controller.py  # 手尾处理
│   ├── game_setup.py       # 游戏初始化
│   ├── game_flow.py        # 对局流程（离场、AI补筹码、AI借款）
│   ├── background_simulator.py  # 后台AI对局模拟器
│   └── game_callbacks.py   # 回调绑定
├── ui/                     # UI 渲染
│   ├── renderer.py         # 主渲染器
│   ├── assets.py           # 素材加载（卡牌、筹码）
│   ├── audio.py            # 音效引擎
│   ├── font_util.py        # 字体工具
│   ├── animations.py       # 动画系统
│   ├── broadcast_bar.py    # 滚动播报栏（大牌播报）
│   ├── scenes/             # 场景渲染
│   └── components/         # UI 组件
├── data/                   # 数据层
│   ├── save_manager.py     # 存档管理
│   ├── game_logger.py      # 对局日志
│   ├── characters.json     # 角色数据
│   └── memory/             # AI 记忆数据库（运行时生成）
├── sounds/                 # 音效文件
├── kenney_boardgame-pack/  # 卡牌图片素材
├── config/                 # 配置
│   ├── llm_config.example.json  # LLM 配置模板
│   └── llm_config.json     # LLM 配置（不提交，含 API Key）
└── tests/                  # 测试
```

## 🎯 游戏操作

| 按键 | 功能 |
|------|------|
| 鼠标点击 | 选择按钮、操作菜单 |
| Enter | 发送聊天消息 |
| ESC | 返回/退出 |
| F1 | 调试信息（开发用） |

## 🧠 AI 系统说明

- **决策**：MCTS 蒙特卡洛树搜索 + 性格参数（松紧度、激进度、诈唬倾向）
- **情绪**：赢/输/被诈唬会改变 AI 的激进度和诈唬概率
- **记忆**：SQLite 存储对局历史，AI 会记住与你的交手记录
- **对话**：LLM 生成角色台词，支持诈唬（声称有好牌但实际没有），不会暴露真实底牌

## 📜 许可

- 代码：MIT
- 卡牌素材：[Kenney Boardgame Pack](https://kenney.nl) (CC0)
- 音效：各音效作者（见文件名），CC0/CC-BY

## 🤝 致谢

- [Kenney](https://kenney.nl) — 卡牌素材
- [Pygame](https://pygame.org) — 游戏框架
- [DeepSeek](https://deepseek.com) — LLM API
