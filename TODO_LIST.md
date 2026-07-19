# WORLD.md

# AI娱乐城计划（World 2.0）

> Version：2.0 Planning
> Status：Design
> Author：ChatGPT & Developer

---

# 一、项目定位

本项目不再是一个单纯的德州扑克游戏。

未来，它将演变成一个持续运行的 AI 娱乐城（AI Entertainment World）。

玩家不是进入一局德州扑克。

而是进入一个长期存在、持续演化的 AI 世界。

在这个世界中：

- AI 会一直生活
- AI 会不断参加各种游戏
- AI 会赢钱输钱
- AI 会建立关系
- AI 会聊天
- AI 会借贷
- AI 会参加锦标赛
- AI 会形成属于自己的故事

德州扑克只是这个世界中的第一个玩法。

未来可扩展：

- Blackjack（二十一点）
- Baccarat（百家乐）
- 梭哈
- AI酒吧
- 世界新闻
- 名人堂
- 世界排行榜
- 更多游戏...

---

# 二、开发原则

World 2.0 不追求功能数量。

而追求：

> 让玩家感觉自己真的进入了一座活着的娱乐城。

所有新增功能都必须符合世界观。

禁止为了功能而功能。

---

# 三、开发路线

---

# Phase 0

## 世界观设计（Design）

目标：

建立整个娱乐城世界。

完成：

- 世界背景
- 世界名称
- 城市布局
- AI存在方式
- 玩家身份
- 各区域规划

产出：

WORLD.md

---

# Phase 1

## 世界入口（Lobby）

目标：

不再直接进入德州扑克。

流程：

启动游戏

↓

欢迎来到 XXXX

↓

娱乐城大厅

↓

玩家选择区域

需要新增：

WelcomeScene

LobbyScene

TexasZoneScene

PokerTable 数据结构

WorldManager（空架构）

要求：

Poker Engine 不修改。

AI 不修改。

Tournament 不修改。

---

# Phase 2

## WorldManager

新增：

world/

WorldManager

职责：

管理整个娱乐城。

负责：

- 所有区域
- 所有桌子
- 所有排行榜
- 所有新闻
- 世界状态

目前只需要框架。

---

# Phase 3

## Texas Hold'em Club

大厅进入：

德州专区

展示：

8张牌桌。

每张桌子拥有：

- 名称
- 主题
- 买入
- 人数
- 当前状态

点击桌子

↓

进入 SetupScene

↓

开始游戏。

---

# Phase 4

## World Simulator

BackgroundSimulator

升级：

WorldSimulator

负责：

后台世界运行。

包括：

- AI自动组桌
- AI自动游戏
- AI借贷
- AI聊天
- AI关系变化
- AI参加赛事
- 世界新闻

World Tick：

统一驱动整个世界。

---

# Phase 5

## World News

新增：

NewsManager

负责：

生成世界新闻。

例如：

- XXX获得四条
- XXX赢得50000筹码
- XXX破产
- XXX向YYY借钱
- 财富榜更新
- 锦标赛开始

大厅实时滚动播报。

---

# Phase 6

## 世界排行榜

新增：

RankingManager

例如：

财富榜

胜率榜

冠军榜

诈唬榜

传奇榜

最富有AI

最佳玩家

等等。

---

# Phase 7

## AI人物图鉴

所有52位AI。

拥有：

头像

背景

关系

财富

历史

性格

最近新闻

聊天记录

玩家可以查看。

---

# Phase 8

## AI酒吧

未来开放。

AI可自由聊天。

讨论：

比赛

借贷

恩怨

玩家也可加入。

---

# Phase 9

## 更多游戏

娱乐城未来新增：

Blackjack

Baccarat

梭哈

斗地主

等等。

统一由 WorldManager 管理。

---

# 四、世界架构

Game

↓

World

↓

Zone

↓

Table

↓

Game Instance

即：

Main

↓

WorldManager

↓

娱乐城

↓

德州专区

↓

某张桌子

↓

PokerGame

---

# 五、开发原则

每完成一个 Phase：

必须保证：

✅ 游戏仍然可以正常启动。

✅ 玩家仍然可以打一局完整德州。

禁止：

完成所有重构以后再测试。

始终保持：

项目可运行。

---

# 六、性能目标

目前版本：

作为 Stable Version。

优化：

- CPU
- FPS
- 后台模拟
- SQLite
- 线程
- 内存

性能稳定以后：

正式进入 World 2.0。

---

# 七、未来世界（待讨论）

待确定：

## 1.

娱乐城名字

例如：

NEXUS

Legend Club

Starport

……

待讨论。

---

## 2.

德州专区名字

待讨论。

---

## 3.

八张桌子名字

待讨论。

---

## 4.

世界背景

为什么52位传奇人物会来到这里？

待讨论。

---

## 5.

玩家身份

玩家为什么来到娱乐城？

是普通会员？

还是新晋挑战者？

待讨论。

---

## 6.

世界时间

是否加入：

Day 1

Day 2

Season

年度赛事

待讨论。

---

## 7.

AI生活

未来：

AI是否会：

聊天

喝酒

观战

训练

消费

旅行

待讨论。

---

# 八、目前版本状态

当前版本：

World 1.x

特点：

- 德州扑克
- 52 AI
- Personality
- Emotion
- Memory
- Relationship
- SQLite
- Background Simulation
- Replay
- Tournament

下一阶段：

World 2.0

目标：

建立一个真正"活着"的 AI 娱乐城。