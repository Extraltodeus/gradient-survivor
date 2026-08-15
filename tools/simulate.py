"""Headless soak test: runs the simulation with a scripted player and reports timings.

	python tools/simulate.py [minutes] [--draw] [--seed N]
"""

import os, sys, math, time, random, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
pygame.init()

from core.settings import *
from core.utils import *


class FakeKeys:
	def __init__(self): self.d = {}
	def __getitem__(self, k): return self.d.get(k, False)
	def set(self, keys):
		self.d = {}
		for k in keys: self.d[k] = True


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('minutes', nargs='?', type=float, default=3.0)
	ap.add_argument('--seed', type=int, default=7)
	ap.add_argument('--draw', action='store_true')
	ap.add_argument('--profile', action='store_true')
	ap.add_argument('--pace', default='slow', help='slow | normal | fast | insanity')
	a = ap.parse_args()

	screen = pygame.display.set_mode((W, H))
	from core.audio import Audio
	from core.pace import get as get_pace
	from game.world import World
	from game.offers import build_offers
	from game import ui

	audio = Audio(); audio.muted = True
	w = World(a.seed, {'dmgnum': True, 'shake': 1.0, 'quality': 1.0, 'bloom': True}, audio,
	          None, get_pace(a.pace))
	w.banned = set()
	keys = FakeKeys()
	rng = random.Random(a.seed)

	dt = 1.0 / 60.0
	steps = int(a.minutes * 60 * 60)
	t0 = time.time()
	worst = 0.0
	worst_at = 0.0
	lv = 0
	acc_upd = acc_draw = 0.0
	hist = []
	picks = {}

	dirs = [(pygame.K_w,), (pygame.K_s,), (pygame.K_a,), (pygame.K_d,),
	        (pygame.K_w, pygame.K_a), (pygame.K_w, pygame.K_d),
	        (pygame.K_s, pygame.K_a), (pygame.K_s, pygame.K_d)]
	cur = dirs[0]

	for i in range(steps):
		if i % 24 == 0:
			# steer away from the densest nearby cluster (crude but keeps it alive)
			px, py = w.player.x, w.player.y
			bx = by = 0.0
			for e in w.enemies[:160]:
				dx = px - e.x; dy = py - e.y
				d2 = dx * dx + dy * dy
				if d2 < 90000 and d2 > 1:
					bx += dx / d2; by += dy / d2
			if bx or by:
				ang_ = math.atan2(by, bx)
				k = []
				if math.cos(ang_) > 0.38: k.append(pygame.K_d)
				if math.cos(ang_) < -0.38: k.append(pygame.K_a)
				if math.sin(ang_) > 0.38: k.append(pygame.K_s)
				if math.sin(ang_) < -0.38: k.append(pygame.K_w)
				cur = tuple(k) if k else rng.choice(dirs)
			else:
				cur = rng.choice(dirs)
		keys.set(cur)

		t1 = time.time()
		w.update(dt, keys)
		acc_upd += time.time() - t1

		if w.player.banked > 0:
			while w.player.banked > 0:
				offs = build_offers(w)
				o = offs[rng.randrange(len(offs))]
				picks[o.kind] = picks.get(o.kind, 0) + 1
				o.apply()
				w.player.banked -= 1
			lv = w.player.level
		if w.player.dead:
			print('DIED at %s (level %d)' % (w.director.time_str(), w.player.level))
			w.player.dead = False
			w.player.hp = w.player.maxhp

		if a.draw:
			t1 = time.time()
			w.draw(screen)
			ui.draw_hud(w, screen)
			acc_draw += time.time() - t1

		fr = time.time() - t1
		if fr > worst: worst = fr; worst_at = w.t
		if i % 600 == 0 and i:
			pw = w.arsenal.total_power(w.player)
			hist.append((w.director.time_str(), w.player.level, len(w.enemies), len(w.projs),
			             int(w.stats['kills']), int(pw), int(w.director.hp_mult)))

	el = time.time() - t0
	print('sim %.1f min in %.1fs  (%.1fx realtime)' % (a.minutes, el, a.minutes * 60 / el))
	print('avg update %.2f ms   avg draw %.2f ms   worst frame %.1f ms @%.0fs'
	      % (acc_upd / steps * 1000, acc_draw / steps * 1000, worst * 1000, worst_at))
	print('%-7s %-5s %-6s %-6s %-8s %-9s %s' % ('time', 'lv', 'enemy', 'proj', 'kills', 'power', 'hpmult'))
	for h in hist: print('%-7s %-5d %-6d %-6d %-8d %-9d %d' % h)
	print('picks:', picks)
	print('procs:')
	for p in w.arsenal.procs:
		print('   %-46s rank %-3d ops %s  syn %s' % (p.name, p.rank,
		      ','.join('%s%d' % (k, v) for k, v in p.ops.items()), ','.join(p.syn)))
	print('evolutions:', w.evo_log)
	print('stats:', {k: int(v) for k, v in w.stats.items()})


main()
