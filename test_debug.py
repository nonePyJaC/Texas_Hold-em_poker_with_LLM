import pygame
pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.SCALED, vsync=1)
from ui.renderer import Renderer
from engine.deck import Card

r = Renderer(screen)
cards = [Card(14,0), Card(13,0), Card(12,0), Card(11,0), Card(10,0)]

class P:
    name = 'Alice'
    folded = False
    hole_cards = [Card(2,1), Card(3,1)]
    total_bet = 500
    is_human = False

class E:
    name = 'test'

results = {
    'fold_win': False,
    'winners': [P()],
    'payouts': {0: 1500, 2: 0},
    'evaluations': {0: E(), 2: E()},
    'pot_won': 2000,
}
players = [P(), P(), P()]
players[1].folded = True

import traceback
try:
    r.draw_showdown_results(results, players, cards, hand_number=1, timer=1.5)
    print("OK")
except Exception as e:
    traceback.print_exc()
    print(f"Error: {e}")

pygame.quit()
