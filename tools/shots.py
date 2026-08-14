"""Render screenshots of every screen for visual review.

	python tools/shots.py [--at 30,180,600] [--out DIR]
"""

import os, sys, math, random, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
pygame.init()

from core.settings import *
from core.utils import *


class FakeKeys:
	def __init__(self, keys=()): self.d = {k: True for k in keys}
	def __getitem__(self, k): return self.d.get(k, False)


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('--at', default='45,240,700')
	ap.add_argument('--out', default=None)
	ap.add_argument('--seed', type=int, default=11)
	a = ap.parse_args()
	out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shots')
	os.makedirs(out, exist_ok=True)

	screen = pygame.display.set_mode((W, H))
	from core.audio import Audio
	from game.world import World
	from game.offers import build_offers
	from game import ui
	from main import make_overlay

	audio = Audio(); audio.muted = True
	overlay = make_overlay()
	rng = random.Random(a.seed)

	# ---- title
	ui.draw_title(screen, 3.4, 0, ['START RUN', 'CODEX', 'QUIT'],
	              {'time': '14:22', 'level': 41, 'kills': 8210})
	pygame.image.save(screen, os.path.join(out, '00_title.png'))

	for p in range(4):
		ui.draw_codex(screen, p, 0)
		pygame.image.save(screen, os.path.join(out, '01_codex_%d.png' % p))

	w = World(a.seed, {'dmgnum': True, 'shake': 1.0, 'quality': 1.0, 'bloom': True}, audio)
	keys = FakeKeys()
	dt = 1.0 / 60.0
	marks = sorted(float(x) for x in a.at.split(','))
	dirs = [(pygame.K_w,), (pygame.K_d,), (pygame.K_s,), (pygame.K_a,), (pygame.K_w, pygame.K_d)]
	cur = FakeKeys(dirs[0])
	i = 0
	shot = 0
	maxt = marks[-1] + 1
	while w.t < maxt:
		i += 1
		if i % 30 == 0:
			px, py = w.player.x, w.player.y
			bx = by = 0.0
			for e in w.enemies[:150]:
				dx = px - e.x; dy = py - e.y
				d2 = dx * dx + dy * dy
				if 1 < d2 < 90000: bx += dx / d2; by += dy / d2
			ang_ = math.atan2(by, bx) if (bx or by) else rng.random() * TAU
			k = []
			if math.cos(ang_) > 0.38: k.append(pygame.K_d)
			if math.cos(ang_) < -0.38: k.append(pygame.K_a)
			if math.sin(ang_) > 0.38: k.append(pygame.K_s)
			if math.sin(ang_) < -0.38: k.append(pygame.K_w)
			cur = FakeKeys(k or rng.choice(dirs))
		w.update(dt, cur)
		if w.player.dead:
			w.player.dead = False; w.player.hp = w.player.maxhp
		if w.player.banked > 0:
			while w.player.banked > 0:
				offs = build_offers(w)
				# prefer meaningful picks so the build actually comes together
				offs.sort(key=lambda o: (0 if o.note and 'EVOLVES' in o.note else
				                         (1 if o.note else 2), rng.random()))
				offs[0].apply()
				w.player.banked -= 1

		if shot < len(marks) and w.t >= marks[shot]:
			w.draw(screen)
			screen.blit(overlay, (0, 0))
			ui.draw_hud(w, screen)
			pygame.image.save(screen, os.path.join(out, '02_play_%03ds.png' % int(marks[shot])))
			# level-up screen at this point
			offs = build_offers(w)
			lu = ui.LevelUp(w, offs)
			lu.snapshot(screen)
			lu.t = 1.0
			lu.draw(screen, w)
			pygame.image.save(screen, os.path.join(out, '03_levelup_%03ds.png' % int(marks[shot])))
			w.draw(screen)
			ui.draw_hud(w, screen)
			ui.draw_pause(w, screen)
			pygame.image.save(screen, os.path.join(out, '04_pause_%03ds.png' % int(marks[shot])))
			shot += 1
			print('shot at %s  lv%d  enemies %d  procs %d' % (w.director.time_str(),
			      w.player.level, len(w.enemies), len(w.arsenal.procs)))

	w.draw(screen)
	ui.draw_hud(w, screen)
	ui.draw_end(w, screen, 1.0, False)
	pygame.image.save(screen, os.path.join(out, '05_end.png'))
	print('saved to', out)
	for p in w.arsenal.procs:
		print('  ', p.name, '|', ','.join('%s%d' % (k, v) for k, v in p.ops.items()), '|', ','.join(p.syn))
	print('evos:', w.evo_log)


main()
