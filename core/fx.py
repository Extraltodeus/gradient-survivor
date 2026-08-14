"""Particles, damage numbers, shockwaves, screenshake, hitstop, flashes."""

import math, random
import pygame
from core.settings import *
from core.utils import *

GLYPHS = "01{}[]#%<>/\\|+*=~^&$@aeixnzλΣ∇"


class Particle:
	__slots__ = ('kind', 'x', 'y', 'vx', 'vy', 'life', 'max', 'size', 'col', 'drag', 'grav',
	             'rot', 'spin', 'glowp', 'ch', 'sides')

	def __init__(self):
		self.kind = 'spark'; self.life = 0.0


class DmgNum:
	__slots__ = ('x', 'y', 'vx', 'vy', 'life', 'max', 'val', 'col', 'size', 'crit')


class Wave:
	__slots__ = ('x', 'y', 'r', 'r0', 'r1', 'life', 'max', 'col', 'width', 'follow')


class FX:
	def __init__(self):
		self.parts = []
		self.pool = []
		self.nums = []
		self.numpool = []
		self.waves = []
		self.trauma = 0.0
		self.hitstop = 0.0
		self.flash = None      # [color, life, max]
		self.rng = random.Random(1337)
		self.shake_x = self.shake_y = 0.0
		self.t = 0.0
		self.quality = 0.9     # scaled down when the frame budget slips

	# ------------------------------------------------------------ emitters
	def _new(self):
		if self.pool: return self.pool.pop()
		return Particle()

	def part(self, kind, x, y, vx, vy, life, size, col, drag=2.4, grav=0.0, glowp=1.0, spin=0.0, ch=None, sides=0):
		if len(self.parts) >= MAX_PARTS: return
		p = self._new()
		p.kind = kind; p.x = x; p.y = y; p.vx = vx; p.vy = vy
		p.life = p.max = life; p.size = size; p.col = col
		p.drag = drag; p.grav = grav; p.glowp = glowp
		p.rot = self.rng.random() * TAU; p.spin = spin; p.ch = ch; p.sides = sides
		self.parts.append(p)

	def burst(self, x, y, n, col, speed=170.0, life=0.36, size=3.0, spread=TAU, adir=0.0, kind='spark', drag=3.0):
		n = max(1, int(n * self.quality))
		rng = self.rng
		for _ in range(n):
			a = adir + (rng.random() - 0.5) * spread
			s = speed * (0.35 + rng.random() * 0.9)
			self.part(kind, x, y, math.cos(a) * s, math.sin(a) * s,
			          life * (0.6 + rng.random() * 0.8), size * (0.7 + rng.random() * 0.7), col, drag)

	def shards(self, x, y, n, col, speed=200.0, life=0.6):
		n = max(1, int(n * self.quality))
		rng = self.rng
		for _ in range(n):
			a = rng.random() * TAU
			s = speed * (0.3 + rng.random())
			self.part('shard', x, y, math.cos(a) * s, math.sin(a) * s, life * (0.6 + rng.random() * 0.7),
			          2.6 + rng.random() * 3.4, col, 1.9, spin=(rng.random() - 0.5) * 16.0,
			          sides=rng.randint(3, 5))

	def glyphs(self, x, y, n, col, speed=90.0, life=0.9):
		n = max(1, int(n * self.quality))
		rng = self.rng
		for _ in range(n):
			a = rng.random() * TAU
			s = speed * (0.3 + rng.random())
			self.part('glyph', x, y, math.cos(a) * s, math.sin(a) * s - 30.0, life * (0.7 + rng.random() * 0.6),
			          11 + rng.randint(0, 5), col, 1.5, grav=-24.0, ch=GLYPHS[rng.randrange(len(GLYPHS))])

	def smoke(self, x, y, n, col, speed=40.0, life=0.9, size=9.0):
		n = max(1, int(n * self.quality))
		rng = self.rng
		for _ in range(n):
			a = rng.random() * TAU
			s = speed * rng.random()
			self.part('smoke', x, y, math.cos(a) * s, math.sin(a) * s, life * (0.6 + rng.random() * 0.8),
			          size * (0.6 + rng.random() * 0.9), col, 1.2, glowp=0.55)

	def trail(self, x, y, col, size=2.4, life=0.22):
		self.part('dot', x, y, 0.0, 0.0, life, size, col, 0.0, glowp=0.8)

	def wave(self, x, y, r0, r1, life, col, width=3, follow=None):
		w = Wave()
		w.x = x; w.y = y; w.r = r0; w.r0 = r0; w.r1 = r1
		w.life = w.max = life; w.col = col; w.width = width; w.follow = follow
		self.waves.append(w)

	def dmg(self, x, y, val, col=INK, crit=False, size=15):
		if len(self.nums) > 90: return
		d = self.numpool.pop() if self.numpool else DmgNum()
		d.x = x + self.rng.uniform(-6, 6); d.y = y - 4
		d.vx = self.rng.uniform(-26, 26); d.vy = -74.0 - self.rng.random() * 30.0
		d.life = d.max = 0.72 if not crit else 0.95
		d.val = val; d.col = col; d.size = size; d.crit = crit
		self.nums.append(d)

	def shake(self, amount):
		self.trauma = min(1.0, self.trauma + amount)

	def stop(self, seconds):
		self.hitstop = max(self.hitstop, seconds)

	def screen_flash(self, col, life=0.18):
		self.flash = [col, life, life]

	# ------------------------------------------------------------ update
	def update(self, dt):
		self.t += dt
		self.trauma = max(0.0, self.trauma - dt * 1.9)
		tr = self.trauma * self.trauma
		if tr > 0.0001:
			f = self.t * 46.0
			self.shake_x = (math.sin(f * 1.7) + math.sin(f * 3.1) * 0.5) * 17.0 * tr
			self.shake_y = (math.cos(f * 2.3) + math.cos(f * 4.7) * 0.5) * 17.0 * tr
		else:
			self.shake_x = self.shake_y = 0.0

		alive = []
		pool = self.pool
		for p in self.parts:
			p.life -= dt
			if p.life <= 0.0:
				if len(pool) < 900: pool.append(p)
				continue
			if p.drag:
				f = 1.0 - p.drag * dt
				if f < 0.0: f = 0.0
				p.vx *= f; p.vy *= f
			if p.grav: p.vy += p.grav * dt
			p.x += p.vx * dt; p.y += p.vy * dt
			if p.spin: p.rot += p.spin * dt
			alive.append(p)
		self.parts = alive

		alive = []
		for d in self.nums:
			d.life -= dt
			if d.life <= 0.0:
				if len(self.numpool) < 80: self.numpool.append(d)
				continue
			d.x += d.vx * dt; d.y += d.vy * dt
			d.vy += 190.0 * dt; d.vx *= (1.0 - 2.0 * dt)
			alive.append(d)
		self.nums = alive

		alive = []
		for w in self.waves:
			w.life -= dt
			if w.life <= 0.0: continue
			if w.follow is not None:
				w.x = w.follow.x; w.y = w.follow.y
			t = 1.0 - w.life / w.max
			w.r = w.r0 + (w.r1 - w.r0) * ease_out(t)
			alive.append(w)
		self.waves = alive

		if self.flash:
			self.flash[1] -= dt
			if self.flash[1] <= 0: self.flash = None

	# ------------------------------------------------------------ draw
	def draw(self, s, camx, camy):
		ADD = pygame.BLEND_ADD
		w_, h_ = s.get_size()
		batch = []
		add = batch.append
		for p in self.parts:
			x = p.x - camx; y = p.y - camy
			if x < -60 or y < -60 or x > w_ + 60 or y > h_ + 60: continue
			t = p.life / p.max
			k = p.kind
			if k == 'spark':
				g, hw = glow_c(p.size * (0.35 + t * 0.9) * 2.6, p.col, t * t * p.glowp)
				add((g, (x - hw, y - hw), None, ADD))
			elif k == 'dot':
				g, hw = glow_c(p.size * 2.4, p.col, t * p.glowp)
				add((g, (x - hw, y - hw), None, ADD))
			elif k == 'smoke':
				f = (1.0 - t)
				g, hw = glow_c(p.size * (0.5 + f * 1.6), p.col, t * t * 0.45 * p.glowp)
				add((g, (x - hw, y - hw), None, ADD))
			elif k == 'ember':
				g, hw = glow_c(p.size * (0.6 + t * 2.2), p.col, t * p.glowp)
				add((g, (x - hw, y - hw), None, ADD))
			elif k == 'shard':
				f = t
				col = shade(p.col, 0.4 + 0.6 * f)
				g = ngon(p.sides, max(2, int(p.size * (0.4 + f * 0.9))), col, 0, p.rot)
				add((g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, ADD))
			elif k == 'glyph':
				a = int(255 * min(1.0, t * 1.6))
				g = text(p.ch, int(p.size), shade(p.col, 0.35 + 0.65 * t))
				g.set_alpha(a)
				s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))

		if batch: s.blits(batch, False)

		for w in self.waves:
			t = w.life / w.max
			x = w.x - camx; y = w.y - camy
			if x < -w.r - 40 or y < -w.r - 40 or x > w_ + w.r + 40 or y > h_ + w.r + 40: continue
			col = shade(w.col, t * t * 0.95)
			wd = max(1, int(w.width * t))
			r = int(w.r)
			if r > 1:
				pygame.draw.circle(s, col, (int(x), int(y)), r, wd)

	def draw_nums(self, s, camx, camy):
		for d in self.nums:
			t = d.life / d.max
			x = d.x - camx; y = d.y - camy
			if x < -40 or y < -40 or x > s.get_width() + 40 or y > s.get_height() + 40: continue
			sz = d.size
			if d.crit:
				sz = int(sz * (1.0 + 0.5 * max(0.0, (t - 0.6) * 2.5)))
			g = text(d.val, int(sz), d.col, d.crit)
			g.set_alpha(int(255 * min(1.0, t * 2.2)))
			sh = text(d.val, int(sz), (0, 0, 0), d.crit)
			sh.set_alpha(int(150 * min(1.0, t * 2.2)))
			s.blit(sh, (x - g.get_width() * 0.5 + 1, y + 1))
			s.blit(g, (x - g.get_width() * 0.5, y))

	def draw_flash(self, s):
		if not self.flash: return
		col, life, mx = self.flash
		f = 0.85 * (life / mx) ** 1.6
		if f <= 0.01: return
		# per-surface alpha is ignored by BLEND_ADD, so fade the colour itself
		o = pygame.Surface(s.get_size())
		o.fill(shade(col, f))
		s.blit(o, (0, 0), None, pygame.BLEND_ADD)

	def clear(self):
		self.parts.clear(); self.nums.clear(); self.waves.clear()
		self.trauma = 0.0; self.hitstop = 0.0; self.flash = None
