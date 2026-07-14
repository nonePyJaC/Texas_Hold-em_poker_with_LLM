"""跨手对话记忆 + Token 优化自测脚本"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.chdir(PROJECT_ROOT)


def check(label, condition, detail=""):
    status = "[PASS]" if condition else "[FAIL]"
    line = f"  {status} {label}"
    if detail and not condition:
        line += f"  {detail}"
    print(line)
    return condition


def main():
    passed = 0
    failed = 0

    print("=" * 60)
    print("测试 1: DialogueContext 新字段")
    print("=" * 60)

    from ai.dialogue_manager.context import DialogueContext
    from ai.personality import Personality
    from ai.emotion import EmotionState

    ctx = DialogueContext(
        char_id=1,
        char_name="柯南",
        personality=Personality.from_archetype("tag"),
        emotion_state=EmotionState(),
        last_hand_result="赢了+500筹码",
        recent_hand_results=("弃牌", "输了-200筹码", "赢了+500筹码"),
        session_summary="已打15手，近3手赢1输1弃1",
        chat_history=("柯南: 哈哈", "玩家: 你运气真好"),
    )

    if check("recent_hand_results 有 3 条", len(ctx.recent_hand_results) == 3):
        passed += 1
    else:
        failed += 1
    if check("session_summary 非空", ctx.session_summary != ""):
        passed += 1
    else:
        failed += 1
    if check("last_hand_result 保留", ctx.last_hand_result == "赢了+500筹码"):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 60)
    print("测试 2: PromptBuilder 上下文构建")
    print("=" * 60)

    from ai.dialogue_manager.prompt_builder import PromptBuilder
    pb = PromptBuilder()

    # 测试有 recent_hand_results 的情况
    prompt = pb.build_context_prompt(ctx)
    if check("prompt 包含近期手牌", "近期手牌" in prompt):
        passed += 1
    else:
        failed += 1
    if check("prompt 包含会话概况", "本局概况" in prompt):
        passed += 1
    else:
        failed += 1
    if check("prompt 包含手牌结果箭头连接", "→" in prompt):
        passed += 1
    else:
        failed += 1

    # 测试只有 last_hand_result 的情况（向后兼容）
    ctx_old = DialogueContext(
        char_name="柯南",
        personality=Personality.from_archetype("tag"),
        emotion_state=EmotionState(),
        last_hand_result="弃牌",
    )
    prompt_old = pb.build_context_prompt(ctx_old)
    if check("旧格式 prompt 包含上一局结果", "上一局结果" in prompt_old):
        passed += 1
    else:
        failed += 1
    if check("旧格式不含近期手牌数据", "近期手牌:" not in prompt_old and "近期手牌 " not in prompt_old):
        passed += 1
    else:
        failed += 1

    # 测试聊天历史压缩
    long_chat = tuple(f"玩家{i}: 消息{i}" for i in range(12))
    ctx_long_chat = DialogueContext(
        char_name="柯南",
        personality=Personality.from_archetype("tag"),
        emotion_state=EmotionState(),
        chat_history=long_chat,
    )
    prompt_long = pb.build_context_prompt(ctx_long_chat)
    if check("长聊天历史有压缩提示", "已省略" in prompt_long):
        passed += 1
    else:
        failed += 1
    # 验证只保留最近 5 条
    msg_count = prompt_long.count("消息")
    if check("长聊天历史只保留最近 5 条", msg_count <= 5):
        passed += 1
    else:
        failed += 1

    # 测试短聊天历史不压缩
    short_chat = tuple(f"玩家{i}: 消息{i}" for i in range(3))
    ctx_short_chat = DialogueContext(
        char_name="柯南",
        personality=Personality.from_archetype("tag"),
        emotion_state=EmotionState(),
        chat_history=short_chat,
    )
    prompt_short = pb.build_context_prompt(ctx_short_chat)
    if check("短聊天历史无压缩", "已省略" not in prompt_short):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 60)
    print("测试 3: 回复路径 Prompt 构建")
    print("=" * 60)

    system, user = pb.build_reply_prompt(ctx, "你好啊")
    if check("reply user 包含会话概况", "本局概况" in user):
        passed += 1
    else:
        failed += 1
    if check("reply user 包含近期手牌", "近期手牌" in user):
        passed += 1
    else:
        failed += 1

    # 测试回复路径的聊天压缩
    system2, user2 = pb.build_reply_prompt(ctx_long_chat, "你好")
    if check("reply 长聊天有压缩", "最近" in user2 or "已省略" in user2):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 60)
    print("测试 4: 完整 Prompt Token 估算")
    print("=" * 60)

    full_prompt = pb.build_prompt(ctx, "confident", 0.7)
    # 粗略估算 token 数（中文约 1.5 字/token）
    char_count = len(full_prompt)
    est_tokens = int(char_count / 1.5)
    print(f"  完整 prompt 字符数: {char_count}")
    print(f"  估算 token 数: {est_tokens}")
    if check("完整 prompt 在合理范围 (< 2000 tokens)", est_tokens < 2000):
        passed += 1
    else:
        failed += 1

    # 测试大量聊天历史时的 token 控制
    ctx_heavy = DialogueContext(
        char_name="柯南",
        char_description="一个高中生侦探，聪明冷静",
        personality=Personality.from_archetype("tag"),
        emotion_state=EmotionState(tilt=0.8, confidence=0.3),
        last_hand_result="输了-1000筹码",
        recent_hand_results=("赢了+500", "输了-200", "弃牌", "输了-1000"),
        session_summary="已打20手，近4手赢1输2弃1，连败2手",
        chat_history=tuple(f"玩家{i}: 这是一条比较长的聊天消息内容用于测试token控制{i}" for i in range(15)),
    )
    heavy_prompt = pb.build_prompt(ctx_heavy, "tilt", 0.9)
    heavy_chars = len(heavy_prompt)
    heavy_tokens = int(heavy_chars / 1.5)
    print(f"  重负载 prompt 字符数: {heavy_chars}")
    print(f"  估算 token 数: {heavy_tokens}")
    if check("重负载 prompt 在合理范围 (< 2500 tokens)", heavy_tokens < 2500):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
