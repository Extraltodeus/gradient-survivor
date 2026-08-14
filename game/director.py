"""Difficulty director: pressure curve, wave composition, events, biome pacing."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.levels import BIOMES
from game.enemies import spawn, A
from game.pickups import drop

BIOME_TIME = 232.0      # seconds of normal play per biome
BOSS_WINDOW = 8.0       # gap between the last spawn wave and the boss


class Director:
	def __init__(self, w, seed=0):
		self.w = w
		self.t = 0.0
		self.tier = 0
		self.biome = BIOMES[0]
		self.next_biome_t = BIOME_TIME
		self.spawn_acc = 0.0
		self.event_t = 26.0
		self.event_name = None
		self.boss_pending = False
		self.boss_alive = False
		self.hazard_t = 8.0
		self.crate_t = 34.0
		self.endless = 0
		self.rng = random.Random(seed or random.randrange(1 << 30))
		self.pressure = 0.0
		self.kills_recent = 0.0
		self.recalc()

	# ------------------------------------------------------------- scaling
	def recalc(self):
		m = self.t / 60.0
		bm = self.biome['mods']
		endl = 1.0 + 0.55 * self.endless
		self.hp_mult = (1.0 + 0.45 * m + 0.050 * (m ** 2.1)) * bm.get('hp', 1.0) * endl
		self.spd_mult = min(1.34, 1.0 + 0.10 * (self.t / 300.0)) * bm.get('spd', 1.0)
		self.dmg_mult = (1.0 + 0.5 * (self.t / 300.0) ** 1.2) * (1.0 + 0.3 * self.endless)
		self.boss_hp_mult = (1.0 + 0.30 * m) * endl
		self.target_alive = min(MAX_ENEMIES, int((32 + 27 * m) * (1.0 + 0.4 * self.endless)))
		self.max_rate = 10.0 + 24.0 * m

	def biome_index(self):
		return BIOMES.index(self.biome)

	# ---------------------------------------------------------------- update
	def update(self, dt, w):
		self.t += dt
		self.recalc()
		self.kills_recent = max(0.0, self.kills_recent - dt * 3.0)

		alive = len(w.enemies)
		self.pressure = clamp(alive / max(20.0, self.target_alive * 0.8), 0.0, 1.0) * 0.6 \
		                + clamp(self.t / 900.0, 0.0, 1.0) * 0.4
		if self.boss_alive: self.pressure = 1.0

		# ---- biome / boss pacing
		if not self.boss_alive and not self.boss_pending and self.t >= self.next_biome_t - BOSS_WINDOW:
			self.boss_pending = True
			w.banner('WARNING', 'a supervising process has noticed you', RED)
			w.audio.play('warn', 1.0)
			w.fx.screen_flash((80, 10, 20), 0.5)

		if self.boss_pending and self.t >= self.next_biome_t - BOSS_WINDOW + 3.2:
			self.boss_pending = False
			self.boss_alive = True
			pl = w.player
			a = self.rng.random() * TAU
			from game.enemies import spawn_boss
			spawn_boss(w, self.biome['boss'], pl.x + math.cos(a) * 430, pl.y + math.sin(a) * 430)

		if self.t >= self.next_biome_t and not self.boss_alive:
			self.advance_biome(w)

		# ---- spawning
		if not self.boss_alive or self.rng.random() < 0.35:
			budget = self.max_rate * dt * (0.35 if self.boss_alive else 1.0)
			self.spawn_acc += budget
			room = self.target_alive - alive
			while self.spawn_acc >= 1.0 and room > 0:
				self.spawn_acc -= 1.0
				room -= 1
				self.spawn_one(w)

		# ---- events
		self.event_t -= dt
		if self.event_t <= 0.0 and not self.boss_alive:
			self.event_t = max(26.0, 52.0 - self.t / 40.0) + self.rng.uniform(-5, 5)
			self.run_event(w)

		# ---- ambient hazards
		hz = self.biome.get('hazard')
		if hz:
			self.hazard_t -= dt
			if self.hazard_t <= 0.0:
				self.hazard_t = max(2.6, 7.5 - self.t / 260.0) + self.rng.uniform(-1, 1)
				self.ambient_hazard(w, hz)

		# ---- crates
		self.crate_t -= dt
		if self.crate_t <= 0.0:
			self.crate_t = 46.0 + self.rng.uniform(-9, 9)
			pl = w.player
			a = self.rng.random() * TAU
			d = self.rng.uniform(320, 600)
			from game.pickups import drop
			drop(w, 'chest', pl.x + math.cos(a) * d, pl.y + math.sin(a) * d)

	def advance_biome(self, w):
		i = self.biome_index()
		if i + 1 < len(BIOMES):
			self.biome = BIOMES[i + 1]
			self.tier = i + 1
		else:
			self.endless += 1
			self.tier += 1
			self.biome = BIOMES[self.rng.randrange(len(BIOMES))]
		self.next_biome_t = self.t + BIOME_TIME
		w.enter_biome(self.biome)
		self.recalc()

	# ---------------------------------------------------------------- spawns
	def pool_weights(self):
		m = self.t / 60.0
		out = []
		for k in self.biome['pool']:
			c = A[k]['cost']
			# cheap fodder fades out, expensive archetypes ramp in
			wgt = max(0.12, 1.0 / (c ** 0.6)) * (1.0 + 0.30 * m * min(1.0, c / 2.5))
			if c > 2.0 and m < 1.5: wgt *= 0.25
			out.append((k, wgt))
		return out

	def spawn_pos(self, w, ang=None, dist=None):
		pl = w.player
		a = self.rng.random() * TAU if ang is None else ang
		d = self.rng.uniform(720.0, 860.0) if dist is None else dist
		return pl.x + math.cos(a) * d, pl.y + math.sin(a) * d

	def spawn_one(self, w, kind=None, elite=None):
		k = kind or weighted(self.rng, self.pool_weights())
		if elite is None:
			p = 0.005 + 0.0022 * (self.t / 60.0) + 0.005 * self.tier
			elite = self.rng.random() < p
		x, y = self.spawn_pos(w)
		return spawn(w, k, x, y, elite)

	def recycle(self, w, e):
		"""An enemy wandered too far: teleport it back into play, or retire it."""
		if len(w.enemies) > self.target_alive + 30 or e.elite:
			e.dead = True
			return
		pl = w.player
		a = math.atan2(pl.vy, pl.vx) if (pl.vx or pl.vy) else self.rng.random() * TAU
		a += self.rng.uniform(-1.2, 1.2)
		d = self.rng.uniform(700.0, 820.0)
		e.x = pl.x + math.cos(a) * d
		e.y = pl.y + math.sin(a) * d
		e.vx = e.vy = 0.0

	# ---------------------------------------------------------------- events
	def run_event(self, w):
		m = self.t / 60.0
		opts = [('swarm', 1.0), ('tide', 0.9), ('crates', 0.5)]
		if m > 1.5: opts += [('elites', 0.9), ('hunter', 0.7)]
		if m > 4.0: opts += [('gauntlet', 0.8), ('siege', 0.7)]
		name = weighted(self.rng, opts)
		self.event_name = name
		pl = w.player
		rng = self.rng

		if name == 'swarm':
			n = int(28 + 12 * m)
			k = 'mite' if 'mite' in self.biome['pool'] else self.biome['pool'][0]
			a0 = rng.random() * TAU
			for i in range(n):
				a = a0 + i / n * TAU
				x, y = self.spawn_pos(w, a, 700 + rng.uniform(-30, 30))
				e = spawn(w, k, x, y)
				e.vx = -math.cos(a) * 120; e.vy = -math.sin(a) * 120
			w.banner('SWARM DETECTED', 'a ring of noise closes in', self.biome['accent'])
		elif name == 'tide':
			n = int(20 + 9 * m)
			a0 = rng.random() * TAU
			for i in range(n):
				a = a0 + rng.uniform(-0.55, 0.55)
				x, y = self.spawn_pos(w, a, rng.uniform(700, 1000))
				e = self.spawn_one(w)
				e.x, e.y = x, y
			w.banner('TIDE', 'a dense front approaches', self.biome['accent'])
		elif name == 'elites':
			n = 2 + int(m / 3)
			for i in range(n):
				x, y = self.spawn_pos(w, rng.random() * TAU, 560)
				spawn(w, weighted(self.rng, self.pool_weights()), x, y, True)
			w.banner('ELITE PACK', 'high-parameter entities', GOLD)
		elif name == 'hunter':
			x, y = self.spawn_pos(w, rng.random() * TAU, 620)
			k = max(self.biome['pool'], key=lambda kk: A[kk]['cost'])
			e = spawn(w, k, x, y, True)
			e.maxhp = e.hp = e.hp * 2.6
			e.spd *= 1.25
			e.r = int(e.r * 1.25)
			e.col = mix(e.col, RED, 0.4)
			e.name = 'HUNTER ' + e.name
			w.banner('HUNTER', 'it is looking for you specifically', RED)
		elif name == 'crates':
			for i in range(2):
				a = rng.random() * TAU
				d = rng.uniform(280, 520)
				drop(w, 'chest', pl.x + math.cos(a) * d, pl.y + math.sin(a) * d)
			w.banner('CACHES FOUND', 'two of them, nearby', GOLD)
		elif name == 'gauntlet':
			w.hazard_ring(pl.x, pl.y, 620.0, 150.0, 6.5, self.biome['accent'], 12.0 * self.dmg_mult)
			for i in range(int(16 + 6 * m)):
				x, y = self.spawn_pos(w, rng.random() * TAU, rng.uniform(200, 480))
				self.spawn_one(w)
			w.banner('CONTAINMENT', 'the boundary is closing', RED)
		elif name == 'siege':
			for i in range(6):
				a = i / 6 * TAU
				x, y = self.spawn_pos(w, a, 380)
				spawn(w, 'sentry' if 'sentry' in A else self.biome['pool'][0], x, y)
			for i in range(int(10 + 4 * m)):
				self.spawn_one(w)
			w.banner('SIEGE', 'they are setting up turrets', ORANGE)

	# --------------------------------------------------------------- hazards
	def ambient_hazard(self, w, hz):
		pl = w.player
		rng = self.rng
		if hz == 'sweep':
			a = rng.choice((0.0, math.pi * 0.5))
			off = rng.uniform(-380, 380)
			x = pl.x + (0.0 if a == 0.0 else off)
			y = pl.y + (off if a == 0.0 else 0.0)
			w.hazard_beam(x - math.cos(a) * 1200, y - math.sin(a) * 1200, a, 2400.0, 22.0,
			              self.biome['accent'], 13.0 * self.dmg_mult, 1.5, tele=True, tele_t=1.1)
		elif hz == 'flames':
			for i in range(2 + self.tier // 2):
				a = rng.random() * TAU
				d = rng.uniform(120, 460)
				w.hazard_pool(pl.x + math.cos(a) * d, pl.y + math.sin(a) * d, rng.uniform(60, 110),
				              (255, 120, 50), 9.0 * self.dmg_mult, 5.0, tele=1.0)
		elif hz == 'glitch':
			for i in range(3):
				a = rng.random() * TAU
				d = rng.uniform(90, 420)
				w.hazard_pool(pl.x + math.cos(a) * d, pl.y + math.sin(a) * d, rng.uniform(50, 90),
				              (255, 47, 79), 11.0 * self.dmg_mult, 3.0, tele=0.8)
			if rng.random() < 0.35:
				w.glitch_t = 0.9

	# ----------------------------------------------------------------- info
	def time_str(self):
		m = int(self.t // 60); s = int(self.t % 60)
		return '%d:%02d' % (m, s)

	def biome_progress(self):
		return clamp(1.0 - (self.next_biome_t - self.t) / BIOME_TIME, 0.0, 1.0)
