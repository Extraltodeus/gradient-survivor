"""Drops: experience tokens, integrity, caches and screen-clearing artefacts."""

import math
import pygame
from core.settings import *
from core.utils import *

XP_TIERS = ((1, (110, 210, 255)), (5, (120, 255, 190)), (25, (200, 140, 255)), (100, GOLD))


class Pickup:
	__slots__ = ('kind', 'x', 'y', 'vx', 'vy', 'val', 'col', 'r', 't', 'pull', 'dead', 'seed')
	def __init__(self): self.dead = True


CHEST_GAP = 11.0        # minimum seconds between two caches entering the world


def drop(w, kind, x, y, val=1, force=False):
	if kind == 'chest' and not force:
		# Caches feed power, power feeds kills, kills feed caches. Rate-limit the
		# loop or it runs away: without this it compounds into hundreds per minute.
		if w.t - w.last_chest < CHEST_GAP:
			kind = 'xp'; val = 20 + int(w.director.tier * 6)
		else:
			w.last_chest = w.t
	elif kind == 'chest':
		w.last_chest = w.t
	p = w.pick_pool.pop() if w.pick_pool else Pickup()
	p.kind = kind; p.x = x; p.y = y; p.val = val
	a = w.rng.random() * TAU
	sp = w.rng.uniform(20, 90)
	p.vx = math.cos(a) * sp; p.vy = math.sin(a) * sp
	p.t = 0.0; p.pull = False; p.dead = False
	p.seed = w.rng.random() * 10.0
	if kind == 'xp':
		c = XP_TIERS[0][1]
		for th, cc in XP_TIERS:
			if val >= th: c = cc
		p.col = c; p.r = 5.0 + min(5.0, val * 0.08)
	elif kind == 'hp':   p.col = HP_COL; p.r = 8.0
	elif kind == 'chest':p.col = GOLD; p.r = 12.0; p.vx = p.vy = 0.0
	elif kind == 'bomb': p.col = ORANGE; p.r = 9.0
	elif kind == 'magnet': p.col = (150, 200, 255); p.r = 9.0
	elif kind == 'clock': p.col = (200, 180, 255); p.r = 9.0
	else: p.col = INK; p.r = 7.0
	w.pickups.append(p)
	return p


def update_pickups(w, dt):
	pl = w.player
	mag = pl.magnet
	mag2 = mag * mag
	alive = []
	for p in w.pickups:
		if p.dead:
			if len(w.pick_pool) < 400: w.pick_pool.append(p)
			continue
		p.t += dt
		dx = pl.x - p.x; dy = pl.y - p.y
		d2 = dx * dx + dy * dy
		if not p.pull and (d2 < mag2 or (p.kind != 'xp' and d2 < mag2 * 2.2) or p.t > 5.5):
			p.pull = True
		if p.pull:
			d = math.sqrt(d2) or 1.0
			acc = (900.0 if d2 < mag2 * 2.5 else 300.0) + 2200.0 / max(30.0, d)
			p.vx += dx / d * acc * dt; p.vy += dy / d * acc * dt
			p.vx *= (1.0 - 1.5 * dt); p.vy *= (1.0 - 1.5 * dt)
		else:
			p.vx *= (1.0 - 3.0 * dt); p.vy *= (1.0 - 3.0 * dt)
		p.x += p.vx * dt; p.y += p.vy * dt

		rr = (P_RADIUS + P_PICKUP + p.r)
		if d2 < rr * rr:
			collect(w, p)
			if len(w.pick_pool) < 400: w.pick_pool.append(p)
			continue
		if d2 > 1900 ** 2:
			if len(w.pick_pool) < 400: w.pick_pool.append(p)
			continue
		alive.append(p)
	w.pickups = alive
	if len(alive) > 150 and (w.frame & 31) == 0:
		_condense(w, alive)


def _condense(w, alive):
	"""Too many loose tokens: merge the far ones into fewer, fatter ones."""
	pl = w.player
	far = [p for p in alive if p.kind == 'xp' and not p.pull]
	if len(far) < 40: return
	far.sort(key=lambda p: -dist2(p.x, p.y, pl.x, pl.y))
	chunk = far[:len(far) // 2]
	val = 0; sx = sy = 0.0
	for p in chunk:
		val += p.val; sx += p.x; sy += p.y
		p.dead = True
	n = len(chunk)
	w.pickups = [p for p in alive if not p.dead]
	for i in range(max(1, n // 8)):
		a = w.rng.random() * TAU
		d = w.rng.uniform(0, 90)
		drop(w, 'xp', sx / n + math.cos(a) * d, sy / n + math.sin(a) * d,
		     max(1, val // max(1, n // 8)))


def collect(w, p):
	pl = w.player
	k = p.kind
	if k == 'xp':
		pl.add_xp(p.val)
		w.stats['xp'] += p.val
		w.audio.play('pickup', 0.30, 0.035)
		w.fx.part('dot', p.x, p.y, 0, -40, 0.3, 4.0, p.col, 1.0)
	elif k == 'hp':
		pl.heal(p.val)
		w.audio.play('heal', 0.8)
		w.fx.wave(pl.x, pl.y, 6, 44, 0.35, HP_COL, 3)
	elif k == 'chest':
		# Caches install themselves. They used to queue up level-up screens, which
		# meant packs of caches buried the player in menus instead of gameplay.
		n = 1 + (1 if w.rng.random() < 0.30 + pl.luck * 0.6 else 0)
		w.audio.play('evolve', 0.8)
		w.fx.wave(pl.x, pl.y, 8, 130, 0.6, GOLD, 5)
		w.fx.burst(pl.x, pl.y, 30, GOLD, 300, 0.8, 3.4)
		w.auto_upgrade(n)
	elif k == 'bomb':
		w.audio.play('bossdie', 0.9)
		w.fx.screen_flash(ORANGE, 0.5)
		w.fx.shake(0.6)
		w.fx.wave(pl.x, pl.y, 20, 900, 0.8, ORANGE, 10)
		w.explode_friendly(pl.x, pl.y, 900.0, 260.0 * pl.dmg_mult)
	elif k == 'magnet':
		w.audio.play('gem', 0.9)
		for q in w.pickups:
			if q.kind == 'xp': q.pull = True
		w.fx.wave(pl.x, pl.y, 10, 700, 0.7, (150, 200, 255), 4)
	elif k == 'clock':
		w.freeze_t = 4.0
		w.audio.play('evolve', 0.6)
		w.fx.screen_flash((120, 160, 255), 0.4)
		w.banner('TIME DILATION', 'the field slows to a crawl', (150, 200, 255))


def draw_pickups(w, s, camx, camy):
	ADD = pygame.BLEND_ADD
	sw, sh = s.get_size()
	t = w.t
	for p in w.pickups:
		x = p.x - camx; y = p.y - camy
		if x < -30 or y < -30 or x > sw + 30 or y > sh + 30: continue
		k = p.kind
		if k == 'xp':
			pl = 0.75 + 0.25 * math.sin(t * 5.0 + p.seed)
			blit_glow(s, x, y, p.r * 2.6 * pl, p.col, 0.75)
			r = p.r * 0.6
			pygame.draw.polygon(s, WHITE, [(x, y - r), (x + r, y), (x, y + r), (x - r, y)])
		else:
			pl = 0.7 + 0.3 * math.sin(t * 4.0 + p.seed)
			blit_glow(s, x, y, p.r * 3.2 * pl, p.col, 0.95)
			g = ngon(6 if k != 'chest' else 4, int(p.r), p.col, 2, t * 1.1 + p.seed)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
			ch = {'hp': '+', 'chest': '$', 'bomb': '*', 'magnet': 'M', 'clock': 'T'}.get(k, '?')
			g = text(ch, 13, WHITE, True)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
