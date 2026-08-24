"""Shared combat primitives: targeting, damage application, status effects, explosions.

Deliberately dependency-free w.r.t. the entity modules (duck-typed) so that
projectiles, enemies and weapons can all lean on it without import cycles.
"""

import math, random
import pygame
from core.settings import *
from core.utils import *

RINGS = (160.0, 340.0, 700.0, 1400.0)


def nearest_enemy(w, x, y, maxr=1400.0, exclude=None, pred=None):
	grid = w.grid
	for r in RINGS:
		if r > maxr * 1.35: r = maxr
		best = None; bd = r * r
		for e in grid.query(x, y, r):
			if e.dead or e is exclude: continue
			if pred is not None and not pred(e): continue
			dx = e.x - x; dy = e.y - y
			d = dx * dx + dy * dy
			if d < bd: bd = d; best = e
		if best is not None: return best
		if r >= maxr: break
	return None


def nearest_n(w, x, y, n, radius, exclude_uids=None, exclude=None):
	out = []
	for e in w.grid.query(x, y, radius):
		if e.dead or e is exclude: continue
		if exclude_uids is not None and e.uid in exclude_uids: continue
		dx = e.x - x; dy = e.y - y
		d = dx * dx + dy * dy
		if d <= radius * radius: out.append((d, e))
	out.sort(key=lambda t: t[0])
	return [e for _, e in out[:n]]


def enemies_in(w, x, y, radius):
	rr = radius * radius
	return [e for e in w.grid.query(x, y, radius)
	        if not e.dead and (e.x - x) ** 2 + (e.y - y) ** 2 <= rr + e.r * e.r]


def random_enemy(w, near_x, near_y, radius=620.0):
	c = [e for e in w.grid.query(near_x, near_y, radius) if not e.dead]
	return w.rng.choice(c) if c else None


# ------------------------------------------------------------------ status
def apply_burn(w, e, dps, dur, rank=1):
	if e.burn_t < dur: e.burn_t = dur
	e.burn_dps = max(e.burn_dps, dps)
	e.burn_rank = max(e.burn_rank, rank)

def apply_frost(w, e, amount, dur):
	e.frost = max(e.frost, min(0.78, amount))
	e.frost_t = max(e.frost_t, dur)

def apply_shock(w, e, dur):
	if e.boss: dur *= 0.28
	e.stun_t = max(e.stun_t, dur)

def apply_mark(w, e, amount, dur):
	e.mark = max(e.mark, amount)
	e.mark_t = max(e.mark_t, dur)

def apply_corrupt(w, e, rank, power=1.0):
	e.corrupt = max(e.corrupt, rank)
	e.corrupt_x = max(e.corrupt_x, power)
	e.corrupt_t = 4.0


# ------------------------------------------------------------------ damage
EXPLODE_SCALE = True    # turned off only by tools/, to price the fireworks


def apply_status(w, e, proc, dmg):
	"""The element ops, applied from a path that never built a projectile.

	explode() and chain_arc() reach enemies directly, so the on-hit block in
	projectiles._apply never runs for mines, rain, novas-by-blast or arcs. Every
	emitter whose affinity list mentions an element has to honour it."""
	if proc is None: return
	ops = proc.ops
	syn = proc.syn
	bn = ops.get('burn', 0)
	if bn:
		apply_burn(w, e, (2.6 + 2.2 * bn) * w.player.dmg_mult * (1.5 if 'WILDFIRE' in syn else 1.0),
		           2.2 + 0.5 * bn, bn)
		if 'LEECH' in syn: e.burn_leech = True
	fr = ops.get('frost', 0)
	if fr: apply_frost(w, e, 0.16 + 0.09 * fr, 1.6 + 0.35 * fr)
	sh = ops.get('shock', 0)
	if sh and w.rng.random() < 0.10 + 0.06 * sh:
		apply_shock(w, e, 0.35 + 0.13 * sh)
	cr = ops.get('corrupt', 0)
	if cr: apply_corrupt(w, e, cr, 2.0 if 'CONTAGION' in syn else 1.0)


def damage_enemy(w, e, dmg, col=None, proc=None, crit=False, knock=0.0, kx=0.0, ky=0.0,
                 silent=False, is_dot=False, lifesteal_ok=True):
	if e.dead or dmg <= 0.0: return 0.0

	if e.mark > 0.0: dmg *= (1.0 + e.mark)
	if e.frost > 0.0: dmg *= (1.0 + e.frost * 0.35)      # brittle: chilled targets take more
	if e.shield > 0.0:
		absorbed = min(e.shield, dmg * 0.72)
		e.shield -= absorbed
		dmg -= absorbed
		if e.shield <= 0.0:
			w.fx.burst(e.x, e.y, 10, (150, 220, 255), 220, 0.3, 2.5)
			w.audio.play('shatter', 0.5, 0.05)
	dmg = max(0.0, dmg - e.armor)
	if dmg <= 0.0: return 0.0

	e.hp -= dmg
	e.flash = 1.0
	if knock and not e.boss:
		m = knock * e.knock_res
		e.vx += kx * m; e.vy += ky * m

	if not silent:
		w.stats['dmg'] += dmg
		c = col or INK
		if crit:
			w.fx.dmg(e.x, e.y - e.r, str(int(dmg)), GOLD, True, 20)
		elif not is_dot:
			if dmg >= 1.0 and (w.opts['dmgnum'] and (len(w.fx.nums) < 46)):
				w.fx.dmg(e.x, e.y - e.r, str(int(dmg)) if dmg >= 10 else ('%.0f' % dmg), c, False, 14)
		if not is_dot:
			w.fx.part('spark', e.x + w.rng.uniform(-4, 4), e.y + w.rng.uniform(-4, 4),
			          kx * 90, ky * 90, 0.2, 2.4, c)

	if proc is not None and lifesteal_ok:
		dr = proc.ops.get('drain', 0)
		if dr and w.rng.random() < 0.10 + 0.045 * dr:
			w.player.heal(0.5 + 0.55 * dr)

	if e.hp <= 0.0:
		kill_enemy(w, e, proc, col)
	return dmg


def kill_enemy(w, e, proc=None, col=None):
	if e.dead: return
	e.dead = True
	w.stats['kills'] += 1
	c = col or e.col
	fx = w.fx

	if e.boss:
		fx.shake(0.85); fx.stop(0.30); fx.screen_flash((255, 240, 220), 0.5)
		fx.burst(e.x, e.y, 90, e.col, 520, 1.1, 6.0)
		fx.shards(e.x, e.y, 34, e.col, 380, 1.4)
		fx.glyphs(e.x, e.y, 26, WHITE, 200, 1.6)
		fx.wave(e.x, e.y, 20, 460, 1.0, WHITE, 9)
		fx.wave(e.x, e.y, 10, 300, 0.7, e.col, 6)
		w.audio.play('bossdie', 1.0)
	elif e.elite:
		fx.shake(0.16); fx.burst(e.x, e.y, 26, e.col, 300, 0.6, 4.0)
		fx.shards(e.x, e.y, 12, e.col, 260, 0.8)
		fx.wave(e.x, e.y, 6, 90, 0.4, e.col, 4)
		w.audio.play('kill', 0.8, 0.02)
	else:
		n = 8 if fx.quality > 0.6 else 4
		fx.burst(e.x, e.y, n, c, 210, 0.4, 3.0)
		if w.rng.random() < 0.32: fx.glyphs(e.x, e.y, 1, shade(e.col, 1.2), 120, 0.7)
		w.audio.play('kill', 0.34, 0.035)

	# on-kill weapon effects
	if proc is not None:
		ops = proc.ops
		fb = ops.get('feedback', 0)
		if fb: proc.t = max(0.0, proc.t - (0.05 + 0.035 * fb))
		rc = ops.get('recursion', 0)
		if rc and w.rng.random() < 0.16 + 0.11 * rc:
			w.spawn_recursion(e.x, e.y, proc)
		oc = ops.get('overclock', 0)
		if oc: proc.heat = min(proc.heat_max, proc.heat + 1.0)

	if e.corrupt > 0:
		_corrupt_burst(w, e)

	w.on_enemy_death(e)


def _corrupt_burst(w, e):
	rank = e.corrupt
	fx = w.fx
	fx.burst(e.x, e.y, 12, VIOLET, 250, 0.5, 3.2)
	fx.wave(e.x, e.y, 4, 40 + 16 * rank, 0.35, VIOLET, 3)
	n = int((2 + rank) * e.corrupt_x)
	dmg = (4.0 + 3.0 * rank) * w.player.dmg_mult * (1.0 + 0.3 * (e.corrupt_x - 1.0))
	for i in range(n):
		a = (i / n) * TAU + w.rng.random()
		w.spawn_corrupt_shot(e.x, e.y, a, dmg, rank)


def explode(w, x, y, radius, dmg, col=ORANGE, proc=None, knock=180.0, shake=0.10,
            source=None, crit=False, shatter=True, status=False):
	fx = w.fx
	# The ring is the readable part -- it IS the blast radius -- so it always draws,
	# and fx.wave decides for itself whether the screen still has room for it. The
	# sparks and the smoke are the ones there are hundreds of: those get cut.
	busy = len(fx.waves) if EXPLODE_SCALE else 0
	fx.wave(x, y, radius * 0.22, radius, 0.34, col, max(3, int(radius * 0.09)))
	q = fx.quality * (1.0 if busy < 18 else 0.45)
	fx.burst(x, y, int((6 + radius * 0.12) * q), col, radius * 3.0, 0.38, 3.4)
	if q > 0.6:
		fx.smoke(x, y, int(2 + radius * 0.035), shade(col, 0.55), 60, 0.7, radius * 0.24)
	if shake: fx.shake(shake)
	w.audio.play('explode', min(0.85, 0.28 + radius / 420.0), 0.045)

	frost_bonus = 0.0
	if proc is not None and shatter and 'SHATTER' in proc.syn:
		frost_bonus = 0.55 + 0.25 * proc.ops.get('frost', 0)

	for e in enemies_in(w, x, y, radius):
		if e is source: continue
		dx = e.x - x; dy = e.y - y
		d = math.hypot(dx, dy) or 1.0
		fall = 1.0 - 0.35 * min(1.0, d / radius)
		dd = dmg * fall
		if frost_bonus and e.frost > 0.0:
			dd *= (1.0 + frost_bonus)
			fx.burst(e.x, e.y, 5, (170, 230, 255), 200, 0.35, 2.6)
		damage_enemy(w, e, dd, col, proc, crit, knock, dx / d, dy / d)
		if status: apply_status(w, e, proc, dd)


def chain_arc(w, x0, y0, target, dmg, col, proc, jumps, radius=210.0, seen=None, falloff=0.86):
	"""Recursive lightning: each jump draws a jagged arc and can carry op effects."""
	if seen is None: seen = set()
	cur = target
	cx, cy = x0, y0
	blast = proc.ops.get('blast', 0) if proc else 0
	burn = proc.ops.get('burn', 0) if proc else 0
	d = dmg
	for _ in range(jumps + 1):
		if cur is None or cur.dead: break
		seen.add(cur.uid)
		w.fx_arc(cx, cy, cur.x, cur.y, col)
		damage_enemy(w, cur, d, col, proc, False, 90.0, *norm(cur.x - cx, cur.y - cy))
		apply_status(w, cur, proc, d)
		if blast:
			explode(w, cur.x, cur.y, 42 + 12 * blast, d * (0.32 + 0.09 * blast), col, proc,
			        120.0, 0.03, cur)
		cx, cy = cur.x, cur.y
		d *= falloff
		nxt = nearest_n(w, cx, cy, 1, radius, seen)
		cur = nxt[0] if nxt else None
	w.audio.play('zap', 0.4, 0.04)


def damage_player(w, amount, src=None):
	w.player.hurt(w, amount, src)
