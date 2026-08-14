"""Exercises every boss and every attack pattern with an immortal player."""

import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
pygame.init()
from core.settings import *
from core.utils import *


class Keys:
	def __init__(self, k=()): self.d = {x: True for x in k}
	def __getitem__(self, k): return self.d.get(k, False)


screen = pygame.display.set_mode((W, H))
from core.audio import Audio
from game.world import World
from game.bosses import B, BOSS_ORDER
from game import ui

audio = Audio(); audio.muted = True
dt = 1.0 / 60.0

for bk in B:
	w = World(5, {'dmgnum': True, 'shake': 1.0, 'quality': 1.0}, audio)
	w.director.t = 200.0
	w.director.recalc()
	from game.enemies import spawn_boss
	e = spawn_boss(w, bk, 300, 0)
	w.director.boss_alive = True
	e.maxhp = e.hp = 1e9        # never dies: we want to see every pattern and both phase gates
	seen = set()
	keys = Keys()
	hurt = 0.0
	for i in range(60 * 40):
		if i == 60 * 13: e.hp = e.maxhp * 0.5      # force phase 1
		if i == 60 * 26: e.hp = e.maxhp * 0.2      # force phase 2
		w.player.hp = w.player.maxhp
		w.player.iframe = 0.0
		w.update(dt, keys)
		if e.boss_data['atk']: seen.add(e.boss_data['atk'])
		if i % 4 == 0:
			w.draw(screen)
			ui.draw_hud(w, screen)
	print('%-11s patterns=%-52s haz=%-3d eproj=%-4d phase=%d'
	      % (bk, ','.join(sorted(seen)), len(w.hazards), len(w.eprojs), e.boss_data['phase']))
	pygame.image.save(screen, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	                                       'shots', '06_boss_%s.png' % bk))

print('OK')
