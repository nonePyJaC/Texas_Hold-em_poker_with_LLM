"""破产场景：筹码归零后的补充筹码/退出界面"""
import pygame
from .base_scene import BaseScene
from config import DEFAULT_STARTING_CHIPS


class BankruptcyScene(BaseScene):
    """破产/补充筹码场景"""

    @property
    def name(self) -> str:
        return "bankruptcy"

    def handle_rebuy(self):
        app = self.app
        rebuy_amount = getattr(app, 'setup_buy_in', DEFAULT_STARTING_CHIPS)
        taken = app.save_manager.withdraw_from_bank(rebuy_amount)
        if taken > 0:
            app.human_player.chips = taken
            app.human_player_initial_chips = taken
            app.human_player.folded = False
            app.human_player.all_in = False
            app.audio.play_background_music()
            app.switch_scene("playing")
            app._next_hand()
        else:
            app.bankruptcy_buttons["rebuy"].enabled = False
            app.bankruptcy_buttons["rebuy"].text = "银行余额不足"

    def handle_quit(self):
        app = self.app
        app._stop_background_simulator()
        # 破产退出时先把剩余筹码存回银行
        if app.human_player:
            app.save_manager.deposit_to_bank(app.human_player.chips)
        app._settle_ai_banks()
        app.game_flow._process_ai_menu_loans()
        app.audio.stop_all_sounds()
        app.save_manager.save(force=True)
        app.chat_controller.messages = []
        app.chat_controller.active = False
        if app.chat_controller.input:
            app.chat_controller.input.text = ""
            app.chat_controller.input.active = False
            pygame.key.stop_text_input()
        app.switch_scene("menu")

    def handle_loan(self):
        """申请贷款5000筹码"""
        app = self.app
        app.audio.stop_all_sounds()
        if app.save_manager.can_take_loan():
            app.save_manager.take_loan(5000)
            app.save_manager.save(force=True)

    def handle_daily_bonus(self):
        """领取每日奖励2000筹码"""
        app = self.app
        app.audio.stop_all_sounds()
        if app.save_manager.can_get_daily_bonus():
            app.save_manager.get_daily_bonus()
            app.save_manager.save(force=True)

    def handle_event(self, event):
        app = self.app
        if hasattr(event, 'pos'):
            event.pos = app._map_mouse_pos(event.pos)

        if event.type == pygame.QUIT:
            app._quit()
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            app._stop_background_simulator()
            if app.human_player:
                app.save_manager.deposit_to_bank(app.human_player.chips)
            app._settle_ai_banks()
            app.game_flow._process_ai_menu_loans()
            app.save_manager.save(force=True)
            app.switch_scene("menu")
            return

        for btn in app.bankruptcy_buttons.values():
            btn.handle_event(event)

    def update(self, dt: float):
        self.app.animations.update(dt)

    def render(self, screen):
        app = self.app
        app.scene_renderer._render_bankruptcy()
        app._present()
