"""聊天控制器：负责玩家输入、AI 回复和聊天框渲染"""
import time
import random
import pygame

from config import SCREEN_HEIGHT
from ui.components import TextInput
from ai.dialogue_manager.context import DialogueContext
from ai.character_descriptions import get_description as get_char_description
from ai.character_pool import HUMAN_OPPONENT_KEY


class ChatController:
    """管理牌桌聊天：人类输入、AI 回复、渲染"""

    def __init__(self, game_app):
        """Args:
            game_app: GameApp 实例，用于读取游戏状态
        """
        self.app = game_app
        self.messages = []  # [{name, text, source, timestamp}]
        self.input = None
        self.active = False
        self.scroll = 0
        self.target = None  # 右键艾特的目标 AI 玩家名

    def init_input(self):
        """初始化聊天输入框"""
        chat_w = 360
        chat_h = 32
        chat_x = 10
        chat_y = SCREEN_HEIGHT - chat_h - 10
        self.input = TextInput(chat_x, chat_y, chat_w, chat_h, max_length=80)

    def reset(self):
        """重置聊天状态"""
        self.messages = []
        self.active = False
        self.scroll = 0
        self.target = None
        if self.input:
            self.input.text = ""
            self.input.active = False

    def add_message(self, name, text, source="template", replace_last_template=False):
        """添加一条聊天消息"""
        if not text:
            return
        if replace_last_template and self.messages:
            last = self.messages[-1]
            if last["name"] == name and last["source"] == "template":
                last["text"] = text
                last["source"] = source
                return
        self.messages.append({
            "name": name,
            "text": text,
            "source": source,
            "timestamp": time.time(),
        })
        if len(self.messages) > 50:
            self.messages = self.messages[-50:]

    def handle_event(self, event):
        """处理聊天相关事件；返回 True 表示事件已被消费"""
        if not self.active or not self.input:
            return False

        if event.type == pygame.TEXTINPUT:
            self.input.handle_event(event)
            return True
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.send_message()
                return True
            elif event.key == pygame.K_ESCAPE:
                self.input.text = ""
                self.input.active = False
                self.active = False
                self.target = None
                return True
            else:
                self.input.handle_event(event)
                return True
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.input.rect.collidepoint(event.pos):
                self.input.active = False
                self.active = False
                self.target = None
            else:
                self.input.handle_event(event)
            return True
        return False

    def activate_with_target(self, player_name):
        """右键艾特 AI：激活输入框并预填 @名字"""
        self.target = player_name
        self.active = True
        if self.input is None:
            self.init_input()
        self.input.active = True
        self.input.text = f"@{player_name} "
        if hasattr(self.input, 'cursor_pos'):
            self.input.cursor_pos = len(self.input.text)

    def send_message(self):
        """发送人类玩家的聊天消息"""
        if not self.input or not self.input.text.strip():
            return
        msg = self.input.text.strip()
        target = self._parse_target(msg)
        human_player = self.app.human_player
        self.add_message(human_player.name if human_player else "我", msg, "human")
        self.input.text = ""
        self.input.active = False
        self.active = False
        self.target = None
        self.trigger_ai_replies(msg, target=target)

    def _parse_target(self, msg):
        """解析消息开头的 @名字"""
        if not msg.startswith("@"):
            return None
        parts = msg[1:].split(" ", 1)
        name = parts[0].rstrip("：")
        for p in self.app.players:
            if not p.is_human and p.name == name:
                return p
        return None

    def trigger_ai_replies(self, human_message, target=None):
        """触发 AI 回复玩家消息；支持 target 指定艾特对象"""
        dialogue_manager = getattr(self.app, 'dialogue_manager', None)
        if not dialogue_manager:
            print("[Chat] dialogue_manager 不可用，跳过AI回复")
            return
        if not self.app.game:
            print("[Chat] game 不存在，跳过AI回复")
            return

        if target and not target.is_human and target in self.app.players:
            print(f"[Chat] 艾特回复: {target.name}")
            ctx = self._build_reply_context(target, human_message)
            dialogue_manager.submit_reply(ctx, human_message)
            return

        ai_players = [p for p in self.app.players if not p.is_human and not p.folded]
        if not ai_players:
            ai_players = [p for p in self.app.players if not p.is_human]
        if not ai_players:
            print("[Chat] 没有AI玩家，跳过回复")
            return

        num_replies = random.randint(1, min(2, len(ai_players)))
        repliers = random.sample(ai_players, num_replies)
        print(f"[Chat] 触发 {num_replies} 个AI回复: {[p.name for p in repliers]}")

        for ai_player in repliers:
            ctx = self._build_reply_context(ai_player, human_message)
            dialogue_manager.submit_reply(ctx, human_message)

    def _build_reply_context(self, ai_player, human_message):
        """为 AI 回复人类消息构建上下文"""
        char_id = getattr(ai_player, '_char_id', 0)
        opponent_id = HUMAN_OPPONENT_KEY
        rel = None
        memory_manager = getattr(self.app, 'memory_manager', None)
        if memory_manager:
            rel = memory_manager.get_relationship(char_id, opponent_id)
        recent_episodes = ()
        self_summary = ""
        if memory_manager:
            dctx = memory_manager.getDialogueContext(char_id, opponent_id=opponent_id)
            recent_episodes = tuple(dctx.recent_episodes[:3])
            self_summary = dctx.self_summary
        emotion_state = None
        if hasattr(ai_player, 'emotion_engine'):
            emotion_state = ai_player.emotion_engine.get_state()
        return DialogueContext(
            char_id=char_id,
            char_name=ai_player.name,
            char_description=get_char_description(ai_player.name),
            archetype=getattr(ai_player, '_archetype', ''),
            personality=ai_player.personality,
            trigger="reply",
            hand_strength=0.0,
            emotion_state=emotion_state,
            relationship=rel,
            opponent_name=self.app.human_player.name or "你",
            recent_episodes=recent_episodes,
            self_summary=self_summary,
            pot_size=self.app.game.pot,
            phase=self.app.game.phase,
            is_all_in=any(p.all_in and not p.folded for p in self.app.players),
            hand_number=self.app.game.hand_number,
            hole_cards=tuple(ai_player.hole_cards) if ai_player.hole_cards else (),
            community_cards=tuple(self.app.game.community_cards) if self.app.game.community_cards else (),
            last_hand_result=getattr(ai_player, '_last_hand_result', ''),
            chat_history=tuple(
                f"{m['name']}: {m['text']}"
                for m in self.messages[-10:]
            ) if self.messages else (),
        )

    def render(self, screen, renderer):
        """渲染左下角聊天框"""
        if not self.app.game:
            return

        chat_w = 380
        chat_x = 10
        chat_y = SCREEN_HEIGHT - 320  # 再上移，减少遮挡
        chat_h = 180
        input_h = 32

        # 几乎透明的背景，仅帮助文字可读
        chat_bg = pygame.Surface((chat_w, chat_h + input_h + 10), pygame.SRCALPHA)
        chat_bg.fill((15, 15, 20, 55))
        screen.blit(chat_bg, (chat_x, chat_y))

        # 标题（弱化，不抢注意力）
        title_surf = renderer.font_tiny.render("牌桌聊天", True, (120, 120, 140))
        screen.blit(title_surf, (chat_x + 8, chat_y + 4))

        # 消息区域
        msg_y = chat_y + 20
        msg_h = chat_h - 25
        msg_area = pygame.Rect(chat_x + 4, msg_y, chat_w - 8, msg_h)

        prev_clip = screen.get_clip()
        screen.set_clip(msg_area)

        # 最新消息在底部，向上滚动，长消息自动折行
        visible_messages = list(reversed(self.messages))
        line_h = 18
        y = msg_y + msg_h - line_h
        name_x = chat_x + 40

        for msg in visible_messages:
            if msg["source"] == "llm":
                tag_text = "LLM"
                tag_color = (100, 200, 255)
            elif msg["source"] == "template":
                tag_text = "本地"
                tag_color = (180, 180, 140)
            else:
                tag_text = "我"
                tag_color = (100, 255, 150)

            name_surf = renderer.font_tiny.render(msg["name"], True, (200, 200, 200))
            text_x = name_x + name_surf.get_width() + 6
            avail_w = chat_w - (text_x - chat_x) - 12
            lines = renderer._wrap_text(msg["text"], renderer.font_tiny, avail_w)

            # 检查是否还有足够空间显示这则消息
            if y - (len(lines) - 1) * line_h < msg_y:
                break

            tag_surf = renderer.font_tiny.render(tag_text, True, tag_color)

            # 标签和人名放在消息底行
            screen.blit(tag_surf, (chat_x + 8, y + 2))
            screen.blit(name_surf, (name_x, y + 2))

            # 从底行向上逐行绘制文本
            for line in reversed(lines):
                text_surf = renderer.font_tiny.render(line, True, (240, 240, 240))
                screen.blit(text_surf, (text_x, y + 2))
                y -= line_h

        screen.set_clip(prev_clip)

        # 输入框位置跟随聊天框上移
        if self.input is None:
            self.init_input()
        self.input.rect.x = chat_x
        self.input.rect.y = chat_y + chat_h + 4
        self.input.draw(screen)

        # 提示文字
        if not self.active and not self.input.text:
            hint = renderer.font_tiny.render("按 Enter 发送消息", True, (100, 100, 120))
            screen.blit(hint, (self.input.rect.x + 8, self.input.rect.y + 9))
        elif self.active and self.target:
            hint = renderer.font_tiny.render(f"对 {self.target} 说:", True, (100, 200, 255))
            screen.blit(hint, (self.input.rect.x + 8, self.input.rect.y - 12))
