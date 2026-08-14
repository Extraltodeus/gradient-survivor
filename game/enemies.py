"""Enemy archetypes, their AI, bosses and enemy projectiles."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.combat import damage_enemy, kill_enemy, explode, apply_shock

# ---------------------------------------------------------------- archetypes
A = {}

def _a(k, **kw):
	kw['id'] = k
	kw.setdefault('sides', 4)
	kw.setdefault('ai', 'chase')
	kw.setdefault('xp', 1)
	kw.setdefault('knock', 1.0)
	kw.setdefault('armor', 0.0)
	kw.setdefault('cost', 1.0)
	kw.setdefault('touch', 8.0)
	A[k] = kw

_a('null',    name='NULL',        hp=13,  spd=52,  r=13, col=(110, 150, 210), sides=4, xp=1, cost=1.0)
_a('bug',     name='BUG',         hp=9,  spd=98,  r=10, col=(255, 120, 120), sides=3, ai='zigzag', xp=1, cost=1.1)
_a('mite',    name='NOISE',       hp=5,   spd=136, r=7,  col=(200, 200, 255), sides=3, ai='swarm', xp=1, cost=0.7, touch=5.0)
_a('crawler', name='CRAWLER',     hp=34,  spd=66,  r=15, col=(160, 120, 255), sides=6, xp=2, cost=1.7)
_a('spam',    name='SPAM BOT',    hp=11,  spd=88,  r=9,  col=(255, 190, 80),  sides=4, ai='swarm', xp=1, cost=0.9)
_a('daemon',  name='DAEMON',      hp=120, spd=42,  r=24, col=(210, 90, 120),  sides=8, xp=5, cost=4.2, knock=0.35, armor=1.0, touch=12.0)
_a('phantom', name='HALLUCINATION',hp=28, spd=78,  r=14, col=(190, 160, 255), sides=5, ai='phase', xp=3, cost=2.4)
_a('splitter',name='FORK BOMB',   hp=40,  spd=58,  r=17, col=(120, 240, 190), sides=6, xp=2, cost=2.2)
_a('charger', name='GRADIENT WOLF',hp=46, spd=74,  r=15, col=(255, 150, 60),  sides=3, ai='charge', xp=3, cost=2.6)
_a('sentry',  name='SENTRY',      hp=60,  spd=0,   r=16, col=(120, 220, 255), sides=4, ai='turret', xp=3, cost=2.6, knock=0.0)
_a('orbiter', name='ATTENTION HEAD',hp=52,spd=104, r=14, col=(255, 110, 200), sides=5, ai='orbit', xp=3, cost=2.8)
_a('bloat',   name='OVERFIT',     hp=120, spd=38,  r=26, col=(180, 220, 90),  sides=7, ai='bloat', xp=4, cost=3.4, knock=0.4, touch=11.0)
_a('weaver',  name='WEAVER',      hp=70,  spd=92,  r=13, col=(255, 90, 160),  sides=4, ai='weave', xp=3, cost=3.0)
_a('mimic',   name='MIMIC',       hp=90,  spd=120, r=14, col=(150, 255, 220), sides=5, ai='mimic', xp=4, cost=3.2)

ELITE_AFFIX = ('shielded', 'hasted', 'volatile', 'magnetic', 'regenerating')


class Enemy:
	__slots__ = ('kind', 'a', 'x', 'y', 'vx', 'vy', 'hp', 'maxhp', 'r', 'col', 'spd', 'dead',
	             'uid', 'flash', 'burn_t', 'burn_dps', 'burn_rank', 'burn_leech', 'frost', 'frost_t',
	             'stun_t', 'mark', 'mark_t', 'corrupt', 'corrupt_t', 'corrupt_x', 'shield', 'shield_max',
	             'armor', 'knock_res', 'boss', 'elite', 'affix', 'xp', 'touch', 'ai', 'sides',
	             't', 'seed', 'st', 'f0', 'f1', 'f2', 'phase', 'ang', 'target', 'boss_data', 'name',
	             'tele', 'hitpl')

	def __init__(self): self.dead = True


_uid = [0]

def spawn(w, kind, x, y, elite=False, mult=None):
	a = A[kind]
	e = w.enemy_pool.pop() if w.enemy_pool else Enemy()
	_uid[0] += 1
	d = w.director
	hpm = d.hp_mult if mult is None else mult
	e.kind = kind; e.a = a; e.uid = _uid[0]
	e.x = x; e.y = y; e.vx = 0.0; e.vy = 0.0
	e.maxhp = e.hp = a['hp'] * hpm
	e.r = a['r']; e.col = a['col']; e.spd = a['spd'] * d.spd_mult
	e.dead = False; e.flash = 0.0
	e.burn_t = 0.0; e.burn_dps = 0.0; e.burn_rank = 0; e.burn_leech = False
	e.frost = 0.0; e.frost_t = 0.0; e.stun_t = 0.0
	e.mark = 0.0; e.mark_t = 0.0
	e.corrupt = 0; e.corrupt_t = 0.0; e.corrupt_x = 1.0
	e.shield = 0.0; e.shield_max = 0.0
	e.armor = a['armor'] * (1.0 + 0.5 * d.tier)
	e.knock_res = a['knock']
	e.boss = False; e.elite = False; e.affix = None
	e.xp = a['xp']; e.touch = a['touch'] * d.dmg_mult
	e.ai = a['ai']; e.sides = a['sides']; e.name = a['name']
	e.t = 0.0; e.seed = w.rng.random() * 10.0; e.st = 0
	e.f0 = 0.0; e.f1 = 0.0; e.f2 = 0.0; e.phase = w.rng.random() * TAU
	e.ang = 0.0; e.target = None; e.boss_data = None; e.tele = 0.0; e.hitpl = 0.0

	if elite:
		e.elite = True
		e.affix = w.rng.choice(ELITE_AFFIX)
		e.maxhp = e.hp = e.hp * 5.2
		e.r = int(e.r * 1.42)
		e.xp = e.xp * 5 + 3
		e.knock_res *= 0.45
		e.touch *= 1.35
		e.col = mix(e.col, GOLD, 0.35)
		if e.affix == 'shielded':
			e.shield_max = e.shield = e.maxhp * 0.55
		elif e.affix == 'hasted':
			e.spd *= 1.55
		elif e.affix == 'magnetic':
			e.spd *= 1.12
	w.enemies.append(e)
	return e


def spawn_boss(w, bkind, x, y):
	from game.bosses import make_boss
	return make_boss(w, bkind, x, y)


# ------------------------------------------------------------------ enemy shot
class EProj:
	__slots__ = ('x', 'y', 'vx', 'vy', 'r', 'dmg', 'col', 'ttl', 'dead', 'kind', 'seed', 'life0',
	             'a0', 'f0', 'owner')
	def __init__(self): self.dead = True


def eshot(w, x, y, vx, vy, dmg, col, r=6.0, ttl=4.0, kind='dot', **kw):
	if len(w.eprojs) > 320: return None
	p = w.eproj_pool.pop() if w.eproj_pool else EProj()
	p.x = x; p.y = y; p.vx = vx; p.vy = vy; p.dmg = dmg; p.col = col
	p.r = r; p.ttl = ttl; p.life0 = ttl; p.dead = False; p.kind = kind
	p.seed = w.rng.random() * 10.0
	p.a0 = kw.get('a0', 0.0); p.f0 = kw.get('f0', 0.0); p.owner = kw.get('owner', None)
	w.eprojs.append(p)
	return p


def update_eprojs(w, dt):
	pl = w.player
	alive = []
	for p in w.eprojs:
		p.ttl -= dt
		if p.ttl <= 0.0 or p.dead:
			if len(w.eproj_pool) < 200: w.eproj_pool.append(p)
			continue
		if p.kind == 'seek':
			dx, dy = norm(pl.x - p.x, pl.y - p.y)
			sp = math.hypot(p.vx, p.vy)
			p.vx += dx * 260.0 * dt; p.vy += dy * 260.0 * dt
			m = math.hypot(p.vx, p.vy)
			if m > sp: p.vx *= sp / m; p.vy *= sp / m
		elif p.kind == 'spin':
			a = math.atan2(p.vy, p.vx) + p.f0 * dt
			sp = math.hypot(p.vx, p.vy)
			p.vx = math.cos(a) * sp; p.vy = math.sin(a) * sp
		p.x += p.vx * dt; p.y += p.vy * dt
		rr = p.r + P_RADIUS
		if (p.x - pl.x) ** 2 + (p.y - pl.y) ** 2 < rr * rr:
			pl.hurt(w, p.dmg, p)
			w.fx.burst(p.x, p.y, 6, p.col, 160, 0.3, 2.6)
			if len(w.eproj_pool) < 200: w.eproj_pool.append(p)
			continue
		if dist2(p.x, p.y, pl.x, pl.y) > 1500 ** 2:
			if len(w.eproj_pool) < 200: w.eproj_pool.append(p)
			continue
		alive.append(p)
	w.eprojs = alive


def draw_eprojs(w, s, camx, camy):
	t = w.t
	for p in w.eprojs:
		x = p.x - camx; y = p.y - camy
		if x < -30 or y < -30 or x > s.get_width() + 30 or y > s.get_height() + 30: continue
		blit_glow(s, x, y, p.r * 3.0, p.col, 0.9)
		pygame.draw.circle(s, WHITE, (int(x), int(y)), max(1, int(p.r * 0.5)))
		pygame.draw.circle(s, p.col, (int(x), int(y)), int(p.r), 1)


# ------------------------------------------------------------------- update
def update_enemies(w, dt, frame):
	pl = w.player
	px, py = pl.x, pl.y
	alive = []
	pool = w.enemy_pool
	sep_phase = frame & 1
	grid = w.grid
	rng = w.rng
	far = DESPAWN_DIST * DESPAWN_DIST

	for e in w.enemies:
		if e.dead:
			if len(pool) < 300: pool.append(e)
			continue

		# --- status ticks
		if e.flash > 0.0: e.flash = max(0.0, e.flash - dt * 6.0)
		if e.burn_t > 0.0:
			e.burn_t -= dt
			d = e.burn_dps * dt
			e.hp -= d
			w.stats['dmg'] += d
			if e.burn_leech and rng.random() < dt * 1.4: pl.heal(0.35)
			if rng.random() < dt * 7.0:
				w.fx.part('ember', e.x + rng.uniform(-e.r, e.r), e.y + rng.uniform(-e.r, e.r),
				          rng.uniform(-8, 8), -34.0, 0.45, 3.2, (255, 140, 40), 1.0)
			if e.hp <= 0.0:
				kill_enemy(w, e, None, (255, 140, 40))
				if len(pool) < 300: pool.append(e)
				continue
		if e.frost_t > 0.0:
			e.frost_t -= dt
			if e.frost_t <= 0.0: e.frost = 0.0
		if e.mark_t > 0.0:
			e.mark_t -= dt
			if e.mark_t <= 0.0: e.mark = 0.0
		if e.corrupt_t > 0.0:
			e.corrupt_t -= dt
			if e.corrupt_t <= 0.0: e.corrupt = 0
		if e.elite and e.affix == 'regenerating' and e.hp < e.maxhp:
			e.hp = min(e.maxhp, e.hp + e.maxhp * 0.035 * dt)
		if e.shield_max > 0.0 and e.shield < e.shield_max:
			e.shield = min(e.shield_max, e.shield + e.shield_max * 0.09 * dt)

		if e.boss:
			from game.bosses import update_boss
			update_boss(w, e, dt)
			alive.append(e)
			continue

		e.t += dt
		dx = px - e.x; dy = py - e.y
		d2 = dx * dx + dy * dy

		if d2 > far and not e.boss:
			# recycle far away enemies back into the pressure budget
			w.director.recycle(w, e)
			if e.dead:
				if len(pool) < 300: pool.append(e)
				continue
			dx = px - e.x; dy = py - e.y
			d2 = dx * dx + dy * dy

		if e.stun_t > 0.0:
			e.stun_t -= dt
			e.vx *= (1.0 - 6.0 * dt); e.vy *= (1.0 - 6.0 * dt)
			e.x += e.vx * dt; e.y += e.vy * dt
			alive.append(e)
			continue

		d = math.sqrt(d2) or 1.0
		nx = dx / d; ny = dy / d
		slow = 1.0 - e.frost
		spd = e.spd * slow
		ai = e.ai
		wx = nx * spd; wy = ny * spd
		acc = 6.0

		if ai == 'zigzag':
			s = math.sin(e.t * 5.5 + e.seed) * 0.7
			wx = (nx * math.cos(s) - ny * math.sin(s)) * spd
			wy = (nx * math.sin(s) + ny * math.cos(s)) * spd
		elif ai == 'swarm':
			wx *= 1.0; wy *= 1.0
			if (e.uid & 1) == sep_phase:
				cx = cy = 0.0; n = 0
				for o in grid.query(e.x, e.y, 46.0):
					if o is e or o.dead: continue
					ox = e.x - o.x; oy = e.y - o.y
					dd = ox * ox + oy * oy
					if dd < 2116.0 and dd > 0.01:
						f = 1.0 / dd
						cx += ox * f; cy += oy * f; n += 1
				if n:
					m = math.hypot(cx, cy) or 1.0
					wx += cx / m * spd * 0.75; wy += cy / m * spd * 0.75
		elif ai == 'charge':
			if e.st == 0:
				e.f0 -= dt
				wx *= 0.35; wy *= 0.35
				if e.f0 <= 0.0 and d < 460.0:
					e.st = 1; e.f1 = 0.9
					e.f2 = math.atan2(dy, dx)
					w.fx.wave(e.x, e.y, 4, 30, 0.25, e.col, 2)
			else:
				e.f1 -= dt
				wx = math.cos(e.f2) * spd * 3.6
				wy = math.sin(e.f2) * spd * 3.6
				acc = 3.0
				if e.f1 <= 0.0:
					e.st = 0; e.f0 = 1.2 + rng.random() * 0.8
		elif ai == 'orbit':
			want = 190.0
			rad = (d - want) / 140.0
			tx = nx * clamp(rad, -1.0, 1.0)
			ty = ny * clamp(rad, -1.0, 1.0)
			px2 = -ny; py2 = nx
			wx = (tx + px2 * 0.9) * spd; wy = (ty + py2 * 0.9) * spd
			e.f0 -= dt
			if e.f0 <= 0.0 and d < 520.0:
				e.f0 = 1.7 + rng.random() * 0.6
				a = math.atan2(dy, dx)
				eshot(w, e.x, e.y, math.cos(a) * 230, math.sin(a) * 230, 7.0 * w.director.dmg_mult,
				      e.col, 6.0, 4.0)
		elif ai == 'turret':
			wx = wy = 0.0
			e.f0 -= dt
			if e.f0 <= 0.0 and d < 620.0:
				e.f0 = 2.1 + rng.random() * 0.7
				a = math.atan2(dy, dx)
				for k in (-1, 0, 1):
					eshot(w, e.x, e.y, math.cos(a + k * 0.22) * 250, math.sin(a + k * 0.22) * 250,
					      6.5 * w.director.dmg_mult, e.col, 5.5, 4.0)
		elif ai == 'phase':
			e.f0 -= dt
			if e.f0 <= 0.0:
				e.f0 = 1.5 + rng.random()
				e.st = 1 - e.st
			if e.st == 1:
				wx *= 1.85; wy *= 1.85
		elif ai == 'bloat':
			wx *= 0.85; wy *= 0.85
		elif ai == 'weave':
			s = math.sin(e.t * 3.2 + e.seed) * 1.15
			wx = (nx * math.cos(s) - ny * math.sin(s)) * spd
			wy = (nx * math.sin(s) + ny * math.cos(s)) * spd
			e.f0 -= dt
			if e.f0 <= 0.0:
				e.f0 = 0.28
				w.hazard_dot(e.x, e.y, e.col, 3.0 * w.director.dmg_mult)
		elif ai == 'mimic':
			# keeps its distance, then dashes through the player's position
			if e.st == 0:
				want = 260.0
				rad = (d - want) / 120.0
				wx = nx * clamp(rad, -1.0, 1.0) * spd
				wy = ny * clamp(rad, -1.0, 1.0) * spd
				e.f0 -= dt
				if e.f0 <= 0.0 and d < 360.0:
					e.st = 1; e.f1 = 0.55
					e.f2 = math.atan2(dy, dx)
					e.tele = 0.35
			else:
				e.f1 -= dt
				wx = math.cos(e.f2) * spd * 3.2; wy = math.sin(e.f2) * spd * 3.2
				acc = 4.0
				if e.f1 <= 0.0:
					e.st = 0; e.f0 = 1.4 + rng.random()

		if e.elite and e.affix == 'magnetic' and d < 300.0:
			pl.vx -= nx * 44.0 * dt * 60.0 * dt
			pl.vy -= ny * 44.0 * dt * 60.0 * dt

		f = acc * dt
		if f > 1.0: f = 1.0
		e.vx += (wx - e.vx) * f
		e.vy += (wy - e.vy) * f

		# separation so the horde stays a horde and not a single point
		if (e.uid & 1) == sep_phase and ai != 'turret':
			rr = e.r + 10.0
			for o in grid.query(e.x, e.y, rr + 20.0):
				if o is e or o.dead: continue
				ox = e.x - o.x; oy = e.y - o.y
				dd = ox * ox + oy * oy
				md = rr + o.r
				if 0.01 < dd < md * md:
					m = math.sqrt(dd)
					push = (md - m) / md * 190.0
					e.vx += ox / m * push; e.vy += oy / m * push

		e.x += e.vx * dt; e.y += e.vy * dt
		if e.tele > 0.0: e.tele -= dt

		# touch damage
		if e.hitpl > 0.0: e.hitpl -= dt
		rr = e.r + P_RADIUS
		if d2 < rr * rr and e.hitpl <= 0.0:
			if not (e.ai == 'phase' and e.st == 1 and e.f0 > 0.6):
				pl.hurt(w, e.touch, e)
				e.hitpl = 0.45
				e.vx -= nx * 220.0; e.vy -= ny * 220.0

		alive.append(e)
	w.enemies = alive


def on_death_special(w, e):
	"""Archetype specific death behaviour. Called from World.on_enemy_death."""
	k = e.kind
	if k == 'splitter' and e.r > 9:
		n = 2 if not e.elite else 3
		for i in range(n):
			a = w.rng.random() * TAU
			c = spawn(w, 'splitter', e.x + math.cos(a) * 14, e.y + math.sin(a) * 14, False,
			          mult=e.maxhp / A['splitter']['hp'] * 0.38)
			c.r = max(8, int(e.r * 0.62)); c.xp = 1
			c.vx = math.cos(a) * 190; c.vy = math.sin(a) * 190
			c.spd *= 1.25
	elif k == 'bloat':
		explode(w, e.x, e.y, 84.0, 0.0, (180, 220, 90), None, 0.0, 0.08)
		w.hazard_pool(e.x, e.y, 74.0, (180, 220, 90), 7.0 * w.director.dmg_mult, 3.4)
	elif e.elite and e.affix == 'volatile':
		w.explode_hostile(e.x, e.y, 110.0, 16.0 * w.director.dmg_mult, ORANGE)


# --------------------------------------------------------------------- draw
def draw_enemies(w, s, camx, camy):
	ADD = pygame.BLEND_ADD
	sw, sh = s.get_size()
	t = w.t
	for e in w.enemies:
		x = e.x - camx; y = e.y - camy
		r = e.r
		if x < -r - 20 or y < -r - 20 or x > sw + r + 20 or y > sh + r + 20: continue
		col = e.col
		alpha_phase = (e.ai == 'phase' and e.st == 1)
		if e.frost > 0.0: col = mix(col, (150, 220, 255), min(0.7, e.frost + 0.2))
		if e.corrupt: col = mix(col, VIOLET, 0.45)
		if e.burn_t > 0.0: col = mix(col, (255, 150, 40), 0.32)
		if e.flash > 0.0: col = mix(col, WHITE, e.flash * 0.85)

		if e.boss:
			draw_boss(w, s, e, x, y)
			continue

		rot = e.t * (1.4 if e.sides < 5 else 0.8) + e.seed
		if e.ai == 'charge' and e.st == 1: rot = math.atan2(e.vy, e.vx)

		if alpha_phase:
			g = ngon(e.sides, int(r), shade(col, 0.55), 2, rot)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
		else:
			blit_glow(s, x, y, r * 2.15, col, 0.75 if not e.elite else 1.25)
			g = ngon(e.sides, int(r), col, 0, rot)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
			g2 = ngon(e.sides, int(r * 0.52), shade(col, 1.45), 0, -rot * 1.6)
			s.blit(g2, (x - g2.get_width() * 0.5, y - g2.get_height() * 0.5))

		if e.shield > 0.0:
			a = int(90 * (e.shield / max(1.0, e.shield_max)))
			g = ring(int(r + 5), (150, 220, 255), 2, a)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
		if e.elite:
			g = ring(int(r + 8 + math.sin(t * 3 + e.seed) * 2), GOLD, 1, 120)
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
		if e.stun_t > 0.0:
			for i in range(3):
				a = t * 9 + i * 2.1
				blit_glow(s, x + math.cos(a) * (r + 7), y + math.sin(a) * (r + 7), 7, (200, 230, 255), 1.0)
		if e.maxhp > 160 and e.hp < e.maxhp:
			bw = int(r * 2.2)
			f = e.hp / e.maxhp
			pygame.draw.rect(s, (30, 30, 40), (int(x - bw * 0.5), int(y - r - 9), bw, 3))
			pygame.draw.rect(s, col, (int(x - bw * 0.5), int(y - r - 9), int(bw * f), 3))


def draw_boss(w, s, e, x, y):
	from game.bosses import draw_boss_body
	draw_boss_body(w, s, e, x, y)
