"""Projectile entities and the hit-resolution pipeline where ops interact."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.combat import (damage_enemy, explode, chain_arc, enemies_in, nearest_n,
                         nearest_enemy, apply_burn, apply_frost, apply_shock, apply_corrupt, apply_mark)

MAX_GEN = 3

_bolt_cache = {}

def bolt_surf(r, col):
	"""Glow + hot core baked into one additive blit. Returns (surface, half extent)."""
	ri = int(r)
	if ri < 2: ri = 2
	if ri > 14: ri = (ri // 2) * 2
	key = (ri, col[0] >> 3, col[1] >> 3, col[2] >> 3)
	e = _bolt_cache.get(key)
	if e is None:
		g = glow(ri * 3.0, col, 0.85)
		s = g.copy()
		c = s.get_width() * 0.5
		pygame.draw.circle(s, WHITE if ri > 4 else col, (int(c), int(c)), max(1, int(ri * 0.55)))
		e = (s, c)
		_bolt_cache[key] = e
	return e


class Proj:
	__slots__ = ('kind', 'x', 'y', 'px', 'py', 'vx', 'vy', 'r', 'dr', 'dmg', 'col', 'ttl', 'life0',
	             'pierce', 'bounce', 'hits', 'proc', 'ops', 'gen', 'dead', 'angle', 'spin',
	             'a0', 'a1', 'f0', 'f1', 'f2', 'ref', 'flags', 'crit_c', 'crit_m', 'dist',
	             'follow', 'split_used', 'owner', 'tint2', 'trail_t', 'seed', 'impact_t')

	def __init__(self): self.dead = True


def new_proj(w, kind, x, y, vx, vy, dmg, col, proc, r=6.0, ttl=2.0, gen=0, **kw):
	if len(w.projs) >= MAX_PROJ:
		# hard cap: retire the oldest live transient, or refuse the shot outright
		killed = False
		for q in w.projs:
			if not q.dead and not q.follow:
				q.dead = True; killed = True
				break
		if not killed: return None
	p = w.proj_pool.pop() if w.proj_pool else Proj()
	p.kind = kind; p.x = x; p.y = y; p.px = x; p.py = y
	p.impact_t = 0.0
	p.vx = vx; p.vy = vy; p.dmg = dmg; p.col = col
	p.r = r; p.dr = kw.get('dr', r)
	p.ttl = ttl; p.life0 = ttl
	p.proc = proc
	p.ops = proc.ops if proc is not None else {}
	p.gen = gen; p.dead = False
	p.angle = math.atan2(vy, vx) if (vx or vy) else 0.0
	p.spin = kw.get('spin', 0.0)
	p.a0 = kw.get('a0', 0.0); p.a1 = kw.get('a1', 0.0)
	p.f0 = kw.get('f0', 0.0); p.f1 = kw.get('f1', 0.0); p.f2 = kw.get('f2', 0.0)
	p.ref = kw.get('ref', None)
	p.flags = kw.get('flags', 0)
	p.follow = kw.get('follow', False)
	p.dist = 0.0
	p.split_used = False
	p.trail_t = 0.0
	p.seed = w.rng.random() * 100.0
	p.owner = kw.get('owner', None)
	p.tint2 = kw.get('tint2', None)

	ops = p.ops
	p.pierce = kw.get('pierce', 0) + ops.get('pierce', 0) + (2 if 'JUGGERNAUT' in _syn(p) else 0)
	p.bounce = ops.get('bounce', 0)
	p.hits = {} if (p.pierce or p.follow or kind in ('orb', 'blade', 'beam', 'field', 'wave')) else None
	p.crit_c = kw.get('crit_c', 0.0)
	p.crit_m = kw.get('crit_m', 2.0)
	w.projs.append(p)
	return p


def _syn(p):
	return p.proc.syn if p.proc is not None else ()


# --------------------------------------------------------------------- update
def update_projs(w, dt):
	player = w.player
	alive = []
	pool = w.proj_pool
	for p in w.projs:
		if p.dead:
			if len(pool) < 400: pool.append(p)
			continue
		k = p.kind
		p.px = p.x; p.py = p.y

		if k == 'shot':
			_upd_shot(w, p, dt)
		elif k == 'orb':
			_upd_orb(w, p, dt, player)
		elif k == 'field':
			_upd_field(w, p, dt, player)
		elif k == 'beam':
			_upd_beam(w, p, dt, player)
		elif k == 'wave':
			_upd_wave(w, p, dt)
		elif k == 'mine':
			_upd_mine(w, p, dt)
		elif k == 'blade':
			_upd_blade(w, p, dt, player)
		elif k == 'turret':
			_upd_turret(w, p, dt)

		if p.dead:
			if len(pool) < 400: pool.append(p)
			continue
		p.ttl -= dt
		if p.ttl <= 0.0:
			_expire(w, p)
			if p.dead:
				if len(pool) < 400: pool.append(p)
				continue
		alive.append(p)
	w.projs = alive


def _upd_shot(w, p, dt):
	ops = p.ops
	sp = math.hypot(p.vx, p.vy)

	hm = ops.get('homing', 0)
	if hm:
		tgt = p.ref
		if tgt is None or tgt.dead or p.f2 <= 0.0:
			tgt = nearest_enemy(w, p.x, p.y, 460.0)
			p.ref = tgt; p.f2 = 0.22
		p.f2 -= dt
		if tgt is not None and not tgt.dead:
			want = math.atan2(tgt.y - p.y, tgt.x - p.x)
			cur = math.atan2(p.vy, p.vx)
			turn = (2.2 + 1.5 * hm) * dt
			d = shortest_angle(cur, want)
			cur += clamp(d, -turn, turn)
			p.vx = math.cos(cur) * sp; p.vy = math.sin(cur) * sp

	ob = ops.get('orbitize', 0) + p.a1
	if ob:
		a = math.atan2(p.vy, p.vx) + (1.4 + 0.62 * ob) * dt * (1 if (p.seed % 2 < 1) else -1)
		p.vx = math.cos(a) * sp; p.vy = math.sin(a) * sp

	mo = ops.get('momentum', 0)
	if mo and sp > 1.0:
		acc = 1.0 + (0.42 + 0.10 * mo) * dt
		p.vx *= acc; p.vy *= acc

	p.x += p.vx * dt; p.y += p.vy * dt
	p.dist += sp * dt
	p.angle = math.atan2(p.vy, p.vx)
	_collide_point(w, p)


def _upd_orb(w, p, dt, player):
	p.a0 += p.f1 * dt
	cx, cy = (player.x, player.y) if p.follow else (p.f2, p.a1)
	r = p.f0
	p.x = cx + math.cos(p.a0) * r
	p.y = cy + math.sin(p.a0) * r
	p.vx = (p.x - p.px) / max(dt, 1e-5); p.vy = (p.y - p.py) / max(dt, 1e-5)
	_collide_persist(w, p, 0.30)


def _upd_field(w, p, dt, player):
	p.x = player.x; p.y = player.y
	p.a0 += dt
	p.f1 -= dt
	if p.f1 <= 0.0:
		p.f1 = p.f2                       # tick interval
		hit = enemies_in(w, p.x, p.y, p.r)
		if hit:
			for e in hit:
				dx, dy = norm(e.x - p.x, e.y - p.y)
				_apply(w, p, e, p.dmg, dx, dy, spawn_fx=False)
			w.audio.play('fire_beam', 0.22, 0.18)


def _upd_beam(w, p, dt, player):
	p.x = player.x; p.y = player.y
	p.a0 += p.f1 * dt
	p.f2 -= dt
	if p.f2 <= 0.0:
		p.f2 = 0.13
		ex = p.x + math.cos(p.a0) * p.f0
		ey = p.y + math.sin(p.a0) * p.f0
		dx = ex - p.x; dy = ey - p.y
		L2 = dx * dx + dy * dy
		mx = (p.x + ex) * 0.5; my = (p.y + ey) * 0.5
		for e in w.grid.query(mx, my, p.f0 * 0.5 + 60):
			if e.dead: continue
			t = ((e.x - p.x) * dx + (e.y - p.y) * dy) / L2
			if t < 0.0 or t > 1.0: continue
			qx = p.x + dx * t; qy = p.y + dy * t
			rr = e.r + p.r
			if (e.x - qx) ** 2 + (e.y - qy) ** 2 <= rr * rr:
				nx, ny = norm(math.cos(p.a0), math.sin(p.a0))
				_apply(w, p, e, p.dmg, nx, ny, spawn_fx=False)


def _upd_wave(w, p, dt):
	if p.follow and p.owner is not None:
		p.x = p.owner.x; p.y = p.owner.y
	t = 1.0 - p.ttl / p.life0
	p.r = p.f0 + (p.f1 - p.f0) * ease_out(t)
	for e in w.grid.query(p.x, p.y, p.r + 30):
		if e.dead or e.uid in p.hits: continue
		d = math.hypot(e.x - p.x, e.y - p.y)
		if d <= p.r + e.r:
			p.hits[e.uid] = 1
			dx, dy = norm(e.x - p.x, e.y - p.y)
			_apply(w, p, e, p.dmg, dx, dy, knock=260.0)


def _upd_mine(w, p, dt):
	p.vx *= (1.0 - 4.0 * dt); p.vy *= (1.0 - 4.0 * dt)
	p.x += p.vx * dt; p.y += p.vy * dt
	p.f0 -= dt
	if p.f0 > 0.0: return
	for e in w.grid.query(p.x, p.y, p.r + 26):
		if e.dead: continue
		if (e.x - p.x) ** 2 + (e.y - p.y) ** 2 <= (p.r + e.r) ** 2:
			_detonate_mine(w, p)
			return


def _detonate_mine(w, p):
	"""A mine never touches _hit, so every op it advertises has to be spent here."""
	if p.dead: return
	p.dead = True
	ops = p.ops
	syn = _syn(p)
	bl = ops.get('blast', 0)
	rad = p.f1 * (1.0 + 0.16 * bl)
	dmg = p.dmg * (1.0 + (0.42 + 0.14 * bl if bl else 0.0))
	vd = ops.get('void', 0)
	if vd: _void_pull(w, p.x, p.y, rad * 1.45, vd)
	explode(w, p.x, p.y, rad, dmg, p.col, p.proc, 260.0, 0.14, status=True)
	sp = ops.get('split', 0)
	if sp and p.gen < MAX_GEN and len(w.projs) < MAX_PROJ * 0.82:
		_do_split(w, p, sp, syn)
	ch = ops.get('chain', 0)
	if ch and p.gen < MAX_GEN:
		from game.combat import chain_arc, nearest_n
		tg = nearest_n(w, p.x, p.y, 1, 190.0 + 22.0 * ch, set())
		if tg:
			chain_arc(w, p.x, p.y, tg[0], p.dmg * (0.45 + 0.08 * ch),
			          p.tint2 or (170, 220, 255), p.proc, ch - 1, 190.0 + 22.0 * ch)
	_post_hit_extras(w, p, None)


def _upd_blade(w, p, dt, player):
	# PIERCE and BOUNCE are consumed in _hit, which a blade never reaches: it
	# re-hits on a cooldown instead. So they buy what they would have bought --
	# more contacts, and a longer outward arc.
	p.f0 -= dt
	if p.f0 > 0.0:
		p.vx *= (1.0 - 1.55 * dt); p.vy *= (1.0 - 1.55 * dt)
	else:
		dx, dy = norm(player.x - p.x, player.y - p.y)
		acc = 1700.0 * dt
		p.vx += dx * acc; p.vy += dy * acc
		m = math.hypot(p.vx, p.vy)
		mx = 900.0
		if m > mx: p.vx *= mx / m; p.vy *= mx / m
		if dist2(p.x, p.y, player.x, player.y) < 400.0:
			p.dead = True
			w.fx.burst(p.x, p.y, 6, p.col, 130, 0.25, 2.4)
			return
	p.x += p.vx * dt; p.y += p.vy * dt
	p.angle += p.spin * dt
	_collide_persist(w, p, 0.34 / (1.0 + 0.34 * p.ops.get('pierce', 0)))


def _upd_turret(w, p, dt):
	p.a0 += dt
	p.f0 -= dt
	if p.f0 <= 0.0:
		p.f0 = p.f1
		tgt = nearest_enemy(w, p.x, p.y, 420.0)
		if tgt is not None:
			a = math.atan2(tgt.y - p.y, tgt.x - p.x)
			sp = 560.0
			np_ = new_proj(w, 'shot', p.x + math.cos(a) * 12, p.y + math.sin(a) * 12,
			               math.cos(a) * sp, math.sin(a) * sp, p.dmg, p.col, p.proc,
			               r=p.f2, ttl=1.4, gen=min(MAX_GEN, p.gen + 1),
			               crit_c=p.crit_c, crit_m=p.crit_m, tint2=p.tint2)
			w.audio.play('fire_turret', 0.20, 0.06)


# ------------------------------------------------------------------ collision
def _collide_point(w, p):
	r = p.r
	hits = p.hits
	for e in w.grid.query(p.x, p.y, r + 34):
		if e.dead: continue
		if hits is not None and e.uid in hits: continue
		rr = r + e.r
		dx = e.x - p.x; dy = e.y - p.y
		if dx * dx + dy * dy > rr * rr:
			# swept test for fast projectiles
			sx = p.x - p.px; sy = p.y - p.py
			L2 = sx * sx + sy * sy
			if L2 < 64.0: continue
			t = ((e.x - p.px) * sx + (e.y - p.py) * sy) / L2
			if t < 0.0 or t > 1.0: continue
			qx = p.px + sx * t; qy = p.py + sy * t
			if (e.x - qx) ** 2 + (e.y - qy) ** 2 > rr * rr: continue
			p.x = qx; p.y = qy
		_hit(w, p, e)
		if p.dead: return


def _collide_persist(w, p, recd):
	"""Persistent shapes (orbs, blades): per-enemy re-hit cooldown."""
	hits = p.hits
	t = w.t
	for e in w.grid.query(p.x, p.y, p.r + 34):
		if e.dead: continue
		last = hits.get(e.uid)
		if last is not None and t - last < recd: continue
		rr = p.r + e.r
		if (e.x - p.x) ** 2 + (e.y - p.y) ** 2 > rr * rr: continue
		hits[e.uid] = t
		dx, dy = norm(e.x - p.x, e.y - p.y)
		_apply(w, p, e, p.dmg, dx, dy, knock=170.0)
		if p.dead: return
	if len(hits) > 40:
		for k in [k for k, v in hits.items() if t - v > 1.2]: del hits[k]


# ------------------------------------------------------------------ hit logic
def _apply(w, p, e, dmg, nx, ny, knock=140.0, spawn_fx=True):
	"""Damage + status + on-hit op effects, without consuming pierce."""
	crit = p.crit_c > 0.0 and w.rng.random() < p.crit_c
	d = dmg * (p.crit_m if crit else 1.0)
	ops = p.ops
	syn = _syn(p)

	if 'PENETRATOR' in syn and p.dist > 180.0:
		d *= 1.0 + min(0.6, p.dist / 900.0)

	proc = p.proc
	if proc is not None and proc.heat > 0.0:
		d *= 1.0 + proc.heat * proc.heat_dmg

	dealt = damage_enemy(w, e, d, p.col, proc, crit, knock, nx, ny)

	bn = ops.get('burn', 0)
	if bn:
		apply_burn(w, e, (2.6 + 2.2 * bn) * w.player.dmg_mult * (1.5 if 'WILDFIRE' in syn else 1.0),
		           2.2 + 0.5 * bn, bn)
		if 'LEECH' in syn: e.burn_leech = True
	fr = ops.get('frost', 0)
	if fr:
		apply_frost(w, e, 0.16 + 0.09 * fr, 1.6 + 0.35 * fr)
	sh = ops.get('shock', 0)
	if sh and w.rng.random() < 0.10 + 0.06 * sh:
		apply_shock(w, e, 0.35 + 0.13 * sh)
		w.fx.burst(e.x, e.y, 5, (200, 230, 255), 210, 0.28, 2.4)
		if 'SUPERCONDUCT' in syn and e.frost > 0.0:
			for o in enemies_in(w, e.x, e.y, 90.0):
				if o is not e:
					damage_enemy(w, o, d * 0.45, (170, 220, 255), proc)
					apply_shock(w, o, 0.2)
	cr = ops.get('corrupt', 0)
	if cr: apply_corrupt(w, e, cr, 2.0 if 'CONTAGION' in syn else 1.0)

	# BLAST, VOID and CHAIN live in _hit, which orbs, fields, waves, beams and
	# blades never reach -- so an ATTENTION RING could carry BLAST III and feel
	# nothing, while SINGULARITY RING asked for exactly that. They act here too,
	# on a per-shape cooldown, because a field ticking over twenty bodies must
	# not become twenty explosions.
	if p.kind != 'shot' and w.t >= p.impact_t:
		bl = ops.get('blast', 0); vd = ops.get('void', 0); ch = ops.get('chain', 0)
		if bl or vd or ch:
			p.impact_t = w.t + 0.26
			if vd: _void_pull(w, e.x, e.y, 62.0 + 20.0 * vd, vd)
			if bl:
				explode(w, e.x, e.y, (30.0 + 11.0 * bl) * w.player.area_mult,
				        dmg * (0.35 + 0.12 * bl), p.tint2 or p.col, proc, 170.0, 0.03, e)
			if ch and p.gen < MAX_GEN:
				seen = {e.uid}
				tg = nearest_n(w, e.x, e.y, 1, 170.0 + 22.0 * ch, seen)
				if tg:
					chain_arc(w, e.x, e.y, tg[0], dmg * (0.40 + 0.07 * ch),
					          p.tint2 or (170, 220, 255), proc, ch - 1, 170.0 + 22.0 * ch, seen)
	if crit:
		w.fx.burst(e.x, e.y, 7, GOLD, 260, 0.4, 3.0)
		w.fx.shake(0.045)
		if 'AVALANCHE' in syn and p.gen < MAX_GEN:
			w.spawn_recursion(e.x, e.y, proc)

	if spawn_fx:
		w.audio.play('hit', 0.5, 0.03)
	return dealt


def _hit(w, p, e):
	ops = p.ops
	syn = _syn(p)
	nx, ny = norm(p.vx, p.vy)
	_apply(w, p, e, p.dmg, nx, ny)

	if p.hits is not None: p.hits[e.uid] = w.t

	bl = ops.get('blast', 0)
	if bl:
		vd = ops.get('void', 0)
		rad = (38.0 + 13.0 * bl) * w.player.area_mult
		mult = 0.42 + 0.14 * bl
		if 'IMPLOSION' in syn:
			_void_pull(w, p.x, p.y, rad * 1.7, vd)
			rad *= 1.25; mult *= 1.45
		if p.pierce > 0 and 'CASCADE' in syn:
			rad *= 0.72; mult *= 0.62      # cascade: smaller pops on every pierce
		elif p.pierce > 0:
			rad *= 0.0                      # no cascade synergy: only the final hit blows up
		if rad > 4.0:
			explode(w, p.x, p.y, rad, p.dmg * mult, p.tint2 or p.col, p.proc, 200.0, 0.05, e)

	ch = ops.get('chain', 0)
	if ch and p.gen < MAX_GEN:
		seen = {e.uid}
		tg = nearest_n(w, e.x, e.y, 1, 190.0 + 22.0 * ch, seen)
		if tg:
			chain_arc(w, e.x, e.y, tg[0], p.dmg * (0.45 + 0.08 * ch), p.tint2 or (170, 220, 255),
			          p.proc, ch - 1, 190.0 + 22.0 * ch, seen)

	sp = ops.get('split', 0)
	if sp and not p.split_used and p.gen < MAX_GEN and len(w.projs) < MAX_PROJ * 0.82:
		p.split_used = True
		_do_split(w, p, sp, syn)

	vd = ops.get('void', 0)
	if vd and 'IMPLOSION' not in syn:
		_void_pull(w, p.x, p.y, 70.0 + 22.0 * vd, vd)

	if p.pierce > 0:
		p.pierce -= 1
		if 'JUGGERNAUT' not in syn:
			p.vx *= 0.94; p.vy *= 0.94
		return
	if p.bounce > 0:
		p.bounce -= 1
		p.hits = p.hits if p.hits is not None else {}
		p.hits[e.uid] = w.t
		nx2, ny2 = norm(p.x - e.x, p.y - e.y)
		sp2 = math.hypot(p.vx, p.vy)
		if 'STALKER' in syn:
			tg = nearest_n(w, p.x, p.y, 1, 520.0, set(p.hits.keys()))
			if tg:
				a = math.atan2(tg[0].y - p.y, tg[0].x - p.x)
				p.vx = math.cos(a) * sp2; p.vy = math.sin(a) * sp2
				p.ttl = max(p.ttl, p.life0 * 0.65)
				return
		a = math.atan2(ny2, nx2) + w.rng.uniform(-0.5, 0.5)
		p.vx = math.cos(a) * sp2; p.vy = math.sin(a) * sp2
		p.ttl = max(p.ttl, 0.5)
		return

	p.dead = True
	_post_hit_extras(w, p, e)


def _expire(w, p):
	if p.kind == 'mine':
		_detonate_mine(w, p)
		return
	if p.kind in ('shot',):
		ops = p.ops
		if ops.get('blast', 0) and ops.get('split', 0) == 0 and w.rng.random() < 0.5:
			pass
		w.fx.burst(p.x, p.y, 2, p.col, 60, 0.2, 1.8)
	p.dead = True


def _post_hit_extras(w, p, e):
	w.fx.burst(p.x, p.y, 3, p.col, 120, 0.24, 2.2)


def _do_split(w, p, rank, syn):
	n = 1 + rank
	base = math.atan2(p.vy, p.vx)
	sp = math.hypot(p.vx, p.vy) * 0.86
	hydra = 'HYDRA' in syn
	frac = 'FRACTAL' in syn or hydra
	gen = p.gen + 1
	dmg = p.dmg * ((0.78 if hydra else 0.46) + 0.05 * rank)
	spread = 1.5
	for i in range(n):
		a = base + (i - (n - 1) * 0.5) * (spread / max(1, n)) + w.rng.uniform(-0.12, 0.12)
		q = new_proj(w, 'shot', p.x, p.y, math.cos(a) * sp, math.sin(a) * sp, dmg,
		             p.tint2 or p.col, p.proc, r=p.r * 0.72, ttl=p.life0 * 0.62, gen=gen,
		             crit_c=p.crit_c, crit_m=p.crit_m, tint2=p.tint2)
		q.pierce = min(q.pierce, 1)
		if not frac: q.split_used = True
	w.fx.burst(p.x, p.y, 5, p.col, 170, 0.28, 2.4)


def _void_pull(w, x, y, radius, rank):
	f = 300.0 + 130.0 * rank
	for e in enemies_in(w, x, y, radius):
		if e.boss: continue
		dx, dy = norm(x - e.x, y - e.y)
		m = e.knock_res * (0.5 + 0.5 * rank / 5.0)
		e.vx += dx * f * m; e.vy += dy * f * m
	w.fx.wave(x, y, radius, radius * 0.15, 0.26, VIOLET, 3)


# ---------------------------------------------------------------------- draw
def draw_projs(w, s, camx, camy):
	ADD = pygame.BLEND_ADD
	sw, sh = s.get_size()
	t = w.t
	batch = []
	add = batch.append
	line = pygame.draw.line
	for p in w.projs:
		x = p.x - camx; y = p.y - camy
		k = p.kind
		if k == 'shot':
			if x < -40 or y < -40 or x > sw + 40 or y > sh + 40: continue
			r = p.dr
			dx = p.x - p.px; dy = p.y - p.py
			if dx * dx + dy * dy > r * r * 4.0:
				line(s, shade(p.col, 0.5), (x - dx, y - dy), (x, y), max(1, int(r * 0.8)))
			g, hw = bolt_surf(r, p.col)
			add((g, (x - hw, y - hw), None, ADD))
		elif k == 'orb':
			if x < -60 or y < -60 or x > sw + 60 or y > sh + 60: continue
			pl = 1.0 + 0.12 * math.sin(t * 7.0 + p.seed)
			blit_glow(s, x, y, p.dr * 3.2 * pl, p.col, 0.9)
			pygame.draw.circle(s, WHITE, (int(x), int(y)), max(1, int(p.dr * 0.45)))
			pygame.draw.circle(s, p.col, (int(x), int(y)), int(p.dr * 1.05), 2)
		elif k == 'field':
			# rim-lit, empty centre: the agent has to stay readable standing inside it
			r = int(p.r)
			a = 1.0 - max(0.0, p.f1 / max(0.001, p.f2))
			g = hollow_glow(r, p.col, 0.42 + 0.26 * (1.0 - a))
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
			pygame.draw.circle(s, shade(p.col, 0.9), (int(x), int(y)), r, 2)
			pygame.draw.circle(s, shade(p.col, 0.22 + 0.35 * (1.0 - a)), (int(x), int(y)), int(r * 0.66), 1)
			for i in range(8):
				aa = t * 1.3 + i * TAU / 8 + p.seed
				px = x + math.cos(aa) * r * 0.94; py = y + math.sin(aa) * r * 0.94
				blit_glow(s, px, py, 8, p.col, 0.8)
		elif k == 'beam':
			ex = x + math.cos(p.a0) * p.f0; ey = y + math.sin(p.a0) * p.f0
			pygame.draw.line(s, shade(p.col, 0.45), (x, y), (ex, ey), int(p.r * 2.2))
			pygame.draw.line(s, p.col, (x, y), (ex, ey), max(2, int(p.r * 1.1)))
			pygame.draw.line(s, WHITE, (x, y), (ex, ey), max(1, int(p.r * 0.4)))
			blit_glow(s, ex, ey, p.r * 4.0, p.col, 0.9)
		elif k == 'wave':
			r = int(p.r)
			if r > 2:
				tt = p.ttl / p.life0
				pygame.draw.circle(s, shade(p.col, tt), (int(x), int(y)), r, max(2, int(6 * tt)))
				pygame.draw.circle(s, shade(WHITE, tt * 0.8), (int(x), int(y)), r, max(1, int(2 * tt)))
		elif k == 'mine':
			armed = p.f0 <= 0.0
			pl = 0.6 + 0.4 * math.sin(t * (12.0 if armed else 5.0) + p.seed)
			blit_glow(s, x, y, p.dr * 2.6 * pl, p.col, 0.8)
			pygame.draw.circle(s, p.col, (int(x), int(y)), int(p.dr), 2)
			if armed:
				pygame.draw.circle(s, WHITE, (int(x), int(y)), max(1, int(p.dr * 0.3)))
		elif k == 'blade':
			g = ngon(3, int(p.dr * 1.6), p.col, 0, p.angle)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
			blit_glow(s, x, y, p.dr * 2.4, p.col, 0.7)
		elif k == 'turret':
			pl = 0.7 + 0.3 * math.sin(t * 5.0 + p.seed)
			blit_glow(s, x, y, 22 * pl, p.col, 0.8)
			g = ngon(4, 9, p.col, 2, p.a0 * 1.6)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
			pygame.draw.circle(s, WHITE, (int(x), int(y)), 3)
			lt = p.ttl / p.life0
			pygame.draw.arc(s, shade(p.col, 0.8), pygame.Rect(int(x - 14), int(y - 14), 28, 28),
			                -math.pi * 0.5, -math.pi * 0.5 + TAU * lt, 2)
	if batch: s.blits(batch, False)
