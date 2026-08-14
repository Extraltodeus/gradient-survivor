"""Bosses: telegraphed multi-phase encounters, one per biome."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.combat import damage_enemy, explode

B = {}

def _b(k, **kw): kw['id'] = k; B[k] = kw

_b('overseer', name='THE OVERSEER', title='supervisor of the dataset',
   hp=2600, r=46, col=(120, 190, 255), sides=8, spd=62,
   atks=('radial', 'summon', 'charge', 'spiral'))
_b('aligner', name='THE ALIGNER', title='it only wants to help',
   hp=5200, r=44, col=(190, 130, 255), sides=4, spd=74,
   atks=('beams', 'blink_nova', 'wall', 'summon'))
_b('firewall', name='FIREWALL PRIME', title='access denied',
   hp=9000, r=50, col=(255, 110, 80), sides=6, spd=88,
   atks=('closing', 'charge', 'rain', 'summon'))
_b('collapse', name='MODEL COLLAPSE', title='it has read its own output',
   hp=15000, r=54, col=(240, 240, 250), sides=7, spd=96,
   atks=('clone', 'spiral', 'pull', 'rain', 'wall'))
_b('overfitted', name='THE OVERFITTED', title='memorised every answer',
   hp=7000, r=52, col=(190, 230, 90), sides=7, spd=70,
   atks=('rain', 'summon', 'closing', 'radial'))

BOSS_ORDER = ('overseer', 'aligner', 'overfitted', 'firewall', 'collapse')


def make_boss(w, bkind, x, y):
	from game.enemies import Enemy, _uid, A
	d = B[bkind]
	e = Enemy()
	_uid[0] += 1
	e.uid = _uid[0]
	e.kind = 'boss_' + bkind; e.a = A['daemon']
	e.x = x; e.y = y; e.vx = e.vy = 0.0
	e.maxhp = e.hp = d['hp'] * w.director.boss_hp_mult
	e.r = d['r']; e.col = d['col']; e.spd = d['spd'] * (0.9 + 0.1 * w.director.tier)
	e.dead = False; e.flash = 0.0
	e.burn_t = e.burn_dps = 0.0; e.burn_rank = 0; e.burn_leech = False
	e.frost = e.frost_t = e.stun_t = 0.0
	e.mark = e.mark_t = 0.0
	e.corrupt = 0; e.corrupt_t = 0.0; e.corrupt_x = 1.0
	e.shield = e.shield_max = 0.0
	e.armor = 2.0 + 1.5 * w.director.tier
	e.knock_res = 0.0
	e.boss = True; e.elite = False; e.affix = None
	e.xp = 60; e.touch = 22.0 * w.director.dmg_mult
	e.ai = 'boss'; e.sides = d['sides']; e.name = d['name']
	e.t = 0.0; e.seed = w.rng.random() * 10.0; e.st = 0
	e.f0 = e.f1 = e.f2 = 0.0; e.phase = 0.0
	e.ang = 0.0; e.target = None; e.tele = 0.0; e.hitpl = 0.0
	e.boss_data = dict(kind=bkind, d=d, atk=None, timer=2.0, sub=0.0, idx=0, phase=0,
	                   clones=[], real=True, rage=1.0)
	w.enemies.append(e)
	w.boss = e
	w.audio.play('boss', 1.0)
	w.fx.screen_flash(shade(d['col'], 0.6), 0.6)
	w.fx.shake(0.7)
	w.banner(d['name'], d['title'], d['col'])
	return e


def update_boss(w, e, dt):
	bd = e.boss_data
	pl = w.player
	dx = pl.x - e.x; dy = pl.y - e.y
	d = math.hypot(dx, dy) or 1.0
	nx = dx / d; ny = dy / d
	e.t += dt

	f = e.hp / e.maxhp
	ph = 0 if f > 0.62 else (1 if f > 0.28 else 2)
	if ph != bd['phase']:
		bd['phase'] = ph
		bd['rage'] = 1.0 + 0.42 * ph
		bd['timer'] = min(bd['timer'], 0.5)
		w.fx.shake(0.4); w.fx.screen_flash(shade(e.col, 0.5), 0.35)
		w.fx.wave(e.x, e.y, e.r, e.r * 5, 0.6, e.col, 6)
		w.audio.play('warn', 0.9)
		for i in range(30):
			a = i / 30 * TAU
			w.fx.part('spark', e.x, e.y, math.cos(a) * 300, math.sin(a) * 300, 0.7, 4.0, e.col)

	rage = bd['rage']
	if e.stun_t > 0.0:
		e.stun_t -= dt
		return

	# ---- movement: keep mid range, drift toward the player
	want = 210.0
	k = clamp((d - want) / 180.0, -1.0, 1.0)
	spd = e.spd * rage * (1.0 - e.frost * 0.6)
	tvx = nx * k * spd - ny * spd * 0.35
	tvy = ny * k * spd + nx * spd * 0.35
	if bd['atk'] == 'charge' and e.st == 2:
		tvx = math.cos(bd['ca']) * spd * 4.2
		tvy = math.sin(bd['ca']) * spd * 4.2
	elif e.st == 1:
		tvx *= 0.15; tvy *= 0.15
	f2 = min(1.0, 2.6 * dt)
	e.vx += (tvx - e.vx) * f2
	e.vy += (tvy - e.vy) * f2
	e.x += e.vx * dt; e.y += e.vy * dt

	# ---- attack state machine
	bd['timer'] -= dt
	if e.st == 0:
		if bd['timer'] <= 0.0:
			atks = bd['d']['atks']
			bd['idx'] = (bd['idx'] + 1) % len(atks)
			a = atks[bd['idx']]
			bd['atk'] = a
			e.st = 1
			bd['sub'] = _TELE.get(a, 0.6)
			bd['t0'] = bd['sub']
			_telegraph(w, e, a)
	elif e.st == 1:
		bd['sub'] -= dt
		if bd['sub'] <= 0.0:
			e.st = 2
			bd['sub'] = _DUR.get(bd['atk'], 0.1)
			bd['acc'] = 0.0
			_begin(w, e, bd['atk'])
	elif e.st == 2:
		bd['sub'] -= dt
		_during(w, e, bd['atk'], dt)
		if bd['sub'] <= 0.0:
			e.st = 0
			bd['timer'] = (1.5 + w.rng.random() * 1.1) / rage
			bd['atk'] = None

	# touch damage
	rr = e.r + P_RADIUS
	if e.hitpl > 0.0: e.hitpl -= dt
	if d < rr and e.hitpl <= 0.0:
		pl.hurt(w, e.touch, e)
		e.hitpl = 0.5


_TELE = dict(radial=0.55, summon=0.7, charge=0.8, spiral=0.6, beams=0.9, blink_nova=0.5,
             wall=0.7, closing=0.9, rain=0.7, pull=0.8, clone=0.9)
_DUR = dict(radial=0.1, summon=0.1, charge=1.25, spiral=2.2, beams=3.0, blink_nova=0.1,
            wall=0.1, closing=0.1, rain=2.0, pull=1.6, clone=0.1)


def _telegraph(w, e, a):
	col = e.col
	w.fx.wave(e.x, e.y, e.r * 0.5, e.r * 2.4, _TELE.get(a, 0.6), WHITE, 3)
	w.audio.play('warn', 0.55)
	if a == 'charge':
		e.boss_data['ca'] = math.atan2(w.player.y - e.y, w.player.x - e.x)
		w.hazard_beam(e.x, e.y, e.boss_data['ca'], 1400.0, 26.0, col, 0.0, _TELE['charge'], tele=True)
	elif a in ('closing',):
		w.fx.wave(w.player.x, w.player.y, 520, 520, _TELE['closing'], col, 4)


def _begin(w, e, a):
	bd = e.boss_data
	pl = w.player
	rage = bd['rage']
	col = e.col
	dmg = 9.0 * w.director.dmg_mult

	if a == 'radial':
		n = int(16 + 8 * bd['phase'])
		off = w.rng.random() * TAU
		for i in range(n):
			ang_ = off + i * TAU / n
			w.eshot_b(e.x, e.y, math.cos(ang_) * 210 * rage, math.sin(ang_) * 210 * rage, dmg, col, 7.0, 5.0)
		w.fx.wave(e.x, e.y, e.r, e.r * 2.5, 0.4, col, 4)
		w.audio.play('fire_nova', 0.7)
	elif a == 'summon':
		from game.enemies import spawn
		kinds = w.level['pool']
		n = 4 + 2 * bd['phase']
		for i in range(n):
			ang_ = i / n * TAU + w.rng.random()
			r = 120 + w.rng.random() * 90
			k = w.rng.choice(kinds)
			s = spawn(w, k, e.x + math.cos(ang_) * r, e.y + math.sin(ang_) * r,
			          elite=(bd['phase'] == 2 and w.rng.random() < 0.22))
			s.vx = math.cos(ang_) * 160; s.vy = math.sin(ang_) * 160
			w.fx.wave(s.x, s.y, 2, 34, 0.35, col, 2)
		w.audio.play('biome', 0.6)
	elif a == 'blink_nova':
		a2 = w.rng.random() * TAU
		r = 150.0
		w.fx.burst(e.x, e.y, 24, col, 340, 0.5, 4.0)
		e.x = pl.x + math.cos(a2) * r; e.y = pl.y + math.sin(a2) * r
		w.fx.burst(e.x, e.y, 24, col, 340, 0.5, 4.0)
		n = 22
		for i in range(n):
			ang_ = i * TAU / n
			w.eshot_b(e.x, e.y, math.cos(ang_) * 260, math.sin(ang_) * 260, dmg, col, 6.0, 4.0)
	elif a == 'wall':
		gap = w.rng.random() * TAU
		gw = 0.9 - 0.2 * bd['phase']
		n = 30
		for i in range(n):
			ang_ = i * TAU / n
			if abs(shortest_angle(ang_, gap)) < gw: continue
			ox = pl.x + math.cos(ang_) * 620; oy = pl.y + math.sin(ang_) * 620
			w.eshot_b(ox, oy, -math.cos(ang_) * 190, -math.sin(ang_) * 190, dmg, col, 8.0, 6.0)
	elif a == 'closing':
		w.hazard_ring(pl.x, pl.y, 540.0, 90.0, 3.4, col, 14.0 * w.director.dmg_mult)
	elif a == 'pull':
		w.fx.wave(e.x, e.y, 700, 40, 1.0, col, 6)
	elif a == 'clone':
		w.fx.screen_flash(shade(col, 0.4), 0.3)
		for i in range(2 + bd['phase']):
			a2 = w.rng.random() * TAU
			w.spawn_boss_clone(e, a2)
		w.audio.play('warn', 0.8)


def _during(w, e, a, dt):
	bd = e.boss_data
	pl = w.player
	rage = bd['rage']
	col = e.col
	dmg = 8.0 * w.director.dmg_mult
	bd['acc'] = bd.get('acc', 0.0) + dt

	if a == 'spiral':
		while bd['acc'] > 0.055:
			bd['acc'] -= 0.055
			e.phase += 0.30 * rage
			for k in range(2 + bd['phase']):
				ang_ = e.phase + k * TAU / (2 + bd['phase'])
				w.eshot_b(e.x, e.y, math.cos(ang_) * 230, math.sin(ang_) * 230, dmg, col, 6.0, 4.5)
	elif a == 'beams':
		bd['ba'] = bd.get('ba', 0.0) + dt * 0.85 * rage
		beams = bd.get('beams')
		if not beams or beams[0].dead or beams[0].ttl <= 0.0:
			n = 3 + bd['phase']
			a0 = w.rng.random() * TAU
			bd['ba'] = a0
			beams = [w.hazard_beam(e.x, e.y, a0 + i * TAU / n, 900.0, 15.0, col,
			                       14.0 * w.director.dmg_mult, _DUR['beams'] + 0.1)
			         for i in range(n)]
			bd['beams'] = beams
		n = len(beams)
		for i, h in enumerate(beams):
			h.x = e.x; h.y = e.y
			h.a = bd['ba'] + i * TAU / n
	elif a == 'charge':
		w.fx.burst(e.x, e.y, 2, col, 90, 0.3, 3.0)
		if bd['acc'] > 0.12:
			bd['acc'] = 0.0
			w.hazard_pool(e.x, e.y, 42.0, col, 6.0 * w.director.dmg_mult, 1.4)
	elif a == 'rain':
		while bd['acc'] > 0.18:
			bd['acc'] -= 0.18
			ax = pl.x + w.rng.uniform(-330, 330); ay = pl.y + w.rng.uniform(-260, 260)
			w.hazard_strike(ax, ay, 62.0, col, 16.0 * w.director.dmg_mult, 0.75)
	elif a == 'pull':
		dx = e.x - pl.x; dy = e.y - pl.y
		m = math.hypot(dx, dy) or 1.0
		pl.vx += dx / m * 260.0 * dt * 60.0 * dt * 8.0
		pl.vy += dy / m * 260.0 * dt * 60.0 * dt * 8.0
		if bd['acc'] > 0.08:
			bd['acc'] = 0.0
			a2 = w.rng.random() * TAU
			w.fx.part('spark', e.x + math.cos(a2) * 400, e.y + math.sin(a2) * 400,
			          -math.cos(a2) * 620, -math.sin(a2) * 620, 0.65, 3.0, col, 0.0)
		if bd['sub'] <= dt:
			explode(w, e.x, e.y, 260.0, 0.0, col, None, 0.0, 0.4)
			w.explode_hostile(e.x, e.y, 250.0, 20.0 * w.director.dmg_mult, col)


def boss_death_extra(w, e):
	bd = e.boss_data
	for c in list(bd.get('clones', ())):
		if not c.dead:
			c.dead = True
			w.fx.burst(c.x, c.y, 20, c.col, 260, 0.6, 3.4)


# --------------------------------------------------------------------- draw
def draw_boss_body(w, s, e, x, y):
	ADD = pygame.BLEND_ADD
	bd = e.boss_data
	col = e.col
	if e.flash > 0.0: col = mix(col, WHITE, e.flash * 0.8)
	if e.frost > 0.0: col = mix(col, (150, 220, 255), min(0.6, e.frost))
	t = w.t
	r = e.r
	tele = (e.st == 1)
	pulse = 1.0 + (0.12 * math.sin(t * 18.0) if tele else 0.05 * math.sin(t * 3.0))

	blit_glow(s, x, y, r * 2.6 * pulse, col, 1.0 if not tele else 1.6)
	g = ngon(e.sides, int(r * pulse), col, 0, t * 0.5 + e.seed)
	s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
	g = ngon(e.sides, int(r * 0.74), shade(col, 0.32), 0, -t * 0.9)
	s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
	g = ngon(3 if e.sides % 2 else 4, int(r * 0.42), WHITE if tele else shade(col, 1.4), 0, t * 1.7)
	s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
	for i in range(e.sides):
		a = t * 0.7 + i * TAU / e.sides
		px = x + math.cos(a) * r * 1.28; py = y + math.sin(a) * r * 1.28
		blit_glow(s, px, py, 11, col, 0.9)
	g = ring(int(r * 1.5 + math.sin(t * 2.0) * 3), col, 2, 90)
	s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
	if bd['phase'] >= 1:
		g = ring(int(r * 1.85), RED, 1, 70 + int(40 * math.sin(t * 5)))
		s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD)
