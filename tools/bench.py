"""Worst-case performance probe: late-game arsenal, full enemy cap, everything on."""

import os, sys, math, time, random
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
from game.weapons import Process, E, O
from game import ui
from main import make_overlay

audio = Audio(); audio.muted = True
overlay = make_overlay()

for bloom in (True, False):
	w = World(3, {'dmgnum': True, 'shake': 1.0, 'quality': 1.0, 'bloom': bloom}, audio)
	w.director.t = 660.0
	w.director.biome = __import__('game.levels', fromlist=['x']).BIOMES[3]
	w.level = w.director.biome
	w.backdrop.set_biome(w.level)
	w.director.recalc()
	pl = w.player
	pl.dmg_mult = 6.0; pl.area_mult = 1.8; pl.cd_mult = 0.55; pl.amount = 2
	pl.maxhp = pl.hp = 400
	# a heavy, fully combinatorial arsenal
	build = [('bolt', {'pierce': 5, 'blast': 4, 'split': 3, 'crit': 3, 'multishot': 3}),
	         ('swarm', {'homing': 4, 'multishot': 4, 'recursion': 3, 'corrupt': 3, 'echo': 3}),
	         ('orbit', {'giant': 4, 'frost': 4, 'blast': 3, 'void': 3}),
	         ('aura', {'burn': 5, 'void': 4, 'drain': 3}),
	         ('beam', {'chain': 4, 'burn': 4, 'overclock': 4, 'giant': 3}),
	         ('spiral', {'orbitize': 4, 'split': 4, 'multishot': 3, 'bounce': 3})]
	w.arsenal.procs = []
	for emit, ops in build:
		p = Process(emit, 8, ops)
		w.arsenal.procs.append(p)
	w.arsenal.slots = 6

	from game.enemies import spawn
	for i in range(430):
		a = random.random() * TAU
		d = random.uniform(60, 900)
		spawn(w, random.choice(w.level['pool']), pl.x + math.cos(a) * d, pl.y + math.sin(a) * d,
		      elite=random.random() < 0.05)
	keys = Keys([pygame.K_d])
	dt = 1.0 / 60.0
	for i in range(90): w.update(dt, keys)      # warm up / settle
	tu = td = 0.0
	N = 420
	for i in range(N):
		t0 = time.perf_counter()
		w.update(dt, keys)
		t1 = time.perf_counter()
		w.draw(screen)
		screen.blit(overlay, (0, 0))
		ui.draw_hud(w, screen)
		t2 = time.perf_counter()
		tu += t1 - t0; td += t2 - t1
	tot = (tu + td) / N * 1000
	print('bloom=%-5s update %.2f ms   draw %.2f ms   total %.2f ms  -> %.0f fps  (e=%d p=%d ep=%d fx=%d)'
	      % (bloom, tu / N * 1000, td / N * 1000, tot, 1000.0 / tot,
	         len(w.enemies), len(w.projs), len(w.eprojs), len(w.fx.parts)))
	pygame.image.save(screen, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	                                       'shots', '07_stress_%s.png' % ('bloom' if bloom else 'plain')))
