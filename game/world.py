"""The world: owns every entity list, ticks the simulation, draws the scene."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from core.pace import get as get_pace
from core.fx import FX
from game.player import Player
from game.weapons import Arsenal, Process, fire
from game.projectiles import update_projs, draw_projs, new_proj
from game.enemies import (update_enemies, draw_enemies, update_eprojs, draw_eprojs,
                          eshot, spawn, on_death_special, A)
from game.pickups import update_pickups, draw_pickups, drop, CHEST_GAP
from game.director import Director
from game.levels import Backdrop, BIOMES
from game.combat import enemies_in, damage_enemy


class Hazard:
	__slots__ = ('kind', 'x', 'y', 'r', 'r1', 'a', 'len', 'wid', 'col', 'dmg', 'ttl', 'life0',
	             'tele', 'tele0', 'seed', 'dead', 'hits')
	def __init__(self): self.dead = True


class Arc:
	__slots__ = ('x0', 'y0', 'x1', 'y1', 'col', 'life', 'max', 'seed')


class Banner:
	__slots__ = ('title', 'sub', 'col', 'life', 'max')


class World:
	def __init__(self, seed=None, opts=None, audio=None, boot=None, pace=None, sandbox=False):
		self.rng = random.Random(seed if seed is not None else random.randrange(1 << 30))
		self.seed = seed
		self.pace = pace if isinstance(pace, dict) else get_pace(pace)
		self.chest_gap = CHEST_GAP / self.pace['chest']
		self.sandbox = sandbox
		self.banned = set()
		self.last_fuse_lv = -9
		self.opts = opts or {'dmgnum': True, 'shake': 1.0, 'quality': 1.0}
		self.t = 0.0
		self.frame = 0
		self.fx = FX()
		self.audio = audio
		self.enemies = []; self.enemy_pool = []
		self.projs = []; self.proj_pool = []
		self.eprojs = []; self.eproj_pool = []
		self.pickups = []; self.pick_pool = []
		self.hazards = []
		self.arcs = []
		self.timers = []
		self.banners = []
		self.toasts = []
		self.grid = SpatialHash(CELL)
		self.player = Player(self)
		self.boot = boot
		self.arsenal = Arsenal(self, boot['emit'] if boot else 'bolt')
		if boot:
			self.arsenal.procs[0].add_op(boot['op'])
			self.player.apply_passive(boot['passive'])
			self.player.hp = self.player.maxhp
		self.player.apply_pace(self.pace)
		self.director = Director(self, seed, self.pace)
		self.backdrop = Backdrop()
		self.level = BIOMES[0]
		self.camx = self.player.x - CX
		self.camy = self.player.y - CY
		self.boss = None
		self.trans = None
		self.trans_pending = False
		self.freeze_t = 0.0
		self.glitch_t = 0.0
		self.win = False
		self.last_cam = (self.camx, self.camy)
		self.last_chest = -99.0
		self.stats = {'kills': 0, 'dmg': 0.0, 'taken': 0.0, 'xp': 0.0, 'evos': 0, 'fuses': 0}
		self.dps = 0.0
		self._dmg_prev = 0.0
		self.evo_log = []
		self.backdrop.set_biome(self.level)
		self.audio.set_music(self.level['music'])
		self.banner(self.level['name'], self.level['sub'], self.level['accent'])
		if self.pace['gift']:
			self.auto_upgrade(self.pace['gift'])

	# ------------------------------------------------------------- helpers
	def enter_biome(self, b):
		self.level = b
		self.backdrop.set_biome(b)
		self.audio.set_music(b['music'])
		self.audio.play('biome', 1.0)
		self.fx.screen_flash(shade(b['accent'], 0.55), 0.6)
		self.banner(b['name'], b['sub'], b['accent'])
		self.hazards.clear()
		# the fold takes over the screen for a moment: do not get shot through it
		self.player.iframe = max(self.player.iframe, 1.35)
		self.trans_pending = True

	def folding(self):
		"""True from the moment a biome change is decided until its fold ends.
		`trans_pending` matters: the Matmul itself is only built on the next draw,
		and a level-up opening in that gap would eat the animation before it starts."""
		return self.trans is not None or self.trans_pending

	def banner(self, title, sub, col=INK):
		for old in self.banners:
			if old.title == title:          # don't stack duplicates, just refresh
				old.sub = sub; old.life = old.max
				return
		b = Banner()
		b.title = title; b.sub = sub; b.col = col; b.life = b.max = 3.0
		self.banners.append(b)
		if len(self.banners) > 2: self.banners.pop(0)

	def auto_upgrade(self, n=1):
		"""Apply upgrades without stopping play: pick whatever fits the build best."""
		from game.offers import build_offers
		got = []
		for _ in range(n):
			offers = build_offers(self, 6)
			if not offers: break
			def score(o):
				s = 0.0
				if o.note and 'EVOLVES' in o.note: s += 100.0
				elif o.note and 'SYNERGY' in o.note: s += 55.0
				elif o.note and 'toward' in o.note: s += 26.0
				s += {'op': 12.0, 'fuse': 9.0, 'rank': 6.0, 'new': 8.0, 'passive': 7.0}.get(o.kind, 4.0)
				s += o.rarity * 3.0
				return s + self.rng.random() * 6.0
			o = max(offers, key=score)
			o.apply()
			got.append(o)
		if got:
			names = ' + '.join(o.title for o in got)
			sub = got[0].sub if len(got) == 1 else 'installed'
			self.banner('CACHE: ' + names, sub, GOLD)
			self.toast(got)
		return got

	def toast(self, offers):
		for o in offers:
			self.toasts.append([o.glyph, o.title, o.sub, o.col, 3.4, 3.4])
		if len(self.toasts) > 4: self.toasts = self.toasts[-4:]

	def fx_arc(self, x0, y0, x1, y1, col):
		a = Arc()
		a.x0 = x0; a.y0 = y0; a.x1 = x1; a.y1 = y1; a.col = col
		a.life = a.max = 0.16; a.seed = self.rng.random() * 10
		self.arcs.append(a)

	def eshot_b(self, x, y, vx, vy, dmg, col, r=6.0, ttl=4.0, kind='dot', **kw):
		return eshot(self, x, y, vx, vy, dmg, col, r, ttl, kind, **kw)

	def spawn_recursion(self, x, y, proc):
		if proc is None: return
		c = proc.stats(self.player)
		a = self.rng.random() * TAU
		sp = max(220.0, c['speed'] * 0.8)
		new_proj(self, 'shot', x, y, math.cos(a) * sp, math.sin(a) * sp,
		         c['dmg'] * 0.55, mix(c['col'], WHITE, 0.3), proc, r=max(3.0, c['size'] * 0.65),
		         ttl=1.1, gen=3, crit_c=c['crit_c'], crit_m=c['crit_m'])
		self.fx.burst(x, y, 4, WHITE, 160, 0.25, 2.0)

	def spawn_corrupt_shot(self, x, y, a, dmg, rank):
		sp = 260.0
		new_proj(self, 'shot', x, y, math.cos(a) * sp, math.sin(a) * sp, dmg, VIOLET, None,
		         r=4.5, ttl=1.3, gen=3)

	def explode_friendly(self, x, y, radius, dmg):
		from game.combat import explode
		explode(self, x, y, radius, dmg, ORANGE, None, 320.0, 0.3)

	def explode_hostile(self, x, y, radius, dmg, col=ORANGE):
		self.fx.wave(x, y, radius * 0.2, radius, 0.4, col, 6)
		self.fx.burst(x, y, 22, col, radius * 3, 0.5, 3.6)
		self.audio.play('explode', 0.8)
		if dist2(x, y, self.player.x, self.player.y) < radius * radius:
			self.player.hurt(self, dmg)

	# --------------------------------------------------------------- hazards
	def _hz(self, kind, **kw):
		h = Hazard()
		h.kind = kind; h.dead = False
		h.x = kw.get('x', 0.0); h.y = kw.get('y', 0.0)
		h.r = kw.get('r', 40.0); h.r1 = kw.get('r1', h.r)
		h.a = kw.get('a', 0.0); h.len = kw.get('len', 0.0); h.wid = kw.get('wid', 12.0)
		h.col = kw.get('col', RED); h.dmg = kw.get('dmg', 8.0)
		h.ttl = h.life0 = kw.get('ttl', 3.0)
		h.tele = h.tele0 = kw.get('tele', 0.0)
		h.seed = self.rng.random() * 10.0
		h.hits = None
		self.hazards.append(h)
		if len(self.hazards) > 90: self.hazards.pop(0)
		return h

	def hazard_pool(self, x, y, r, col, dmg, ttl, tele=0.0):
		return self._hz('pool', x=x, y=y, r=r, col=col, dmg=dmg, ttl=ttl, tele=tele)

	def hazard_dot(self, x, y, col, dmg):
		return self._hz('pool', x=x, y=y, r=17.0, col=col, dmg=dmg, ttl=2.2, tele=0.0)

	def hazard_beam(self, x, y, a, length, wid, col, dmg, ttl, tele=False, tele_t=0.7, transient=False):
		return self._hz('beam', x=x, y=y, a=a, len=length, wid=wid, col=col, dmg=dmg,
		                ttl=ttl, tele=(tele_t if tele else 0.0))

	def hazard_ring(self, x, y, r0, r1, ttl, col, dmg):
		return self._hz('ring', x=x, y=y, r=r0, r1=r1, col=col, dmg=dmg, ttl=ttl)

	def hazard_well(self, x, y, r, col, dmg, ttl, tele=0.8):
		return self._hz('well', x=x, y=y, r=r, col=col, dmg=dmg, ttl=ttl, tele=tele)

	def hazard_strike(self, x, y, r, col, dmg, tele=0.7):
		return self._hz('strike', x=x, y=y, r=r, col=col, dmg=dmg, ttl=tele + 0.25, tele=tele)

	def update_hazards(self, dt):
		pl = self.player
		alive = []
		for h in self.hazards:
			if h.tele > 0.0:
				h.tele -= dt
				if h.tele <= 0.0 and h.kind == 'strike':
					from game.combat import explode
					explode(self, h.x, h.y, h.r, 0.0, h.col, None, 0.0, 0.12)
					if dist2(h.x, h.y, pl.x, pl.y) < h.r * h.r:
						pl.hurt(self, h.dmg)
				alive.append(h)
				continue
			h.ttl -= dt
			if h.ttl <= 0.0 or h.dead: continue
			k = h.kind
			if k == 'pool':
				if dist2(h.x, h.y, pl.x, pl.y) < (h.r + P_RADIUS * 0.5) ** 2:
					pl.hurt(self, h.dmg)
				if self.rng.random() < dt * 12.0:
					a = self.rng.random() * TAU
					d = self.rng.random() * h.r
					self.fx.part('ember', h.x + math.cos(a) * d, h.y + math.sin(a) * d,
					             0, -26, 0.5, 3.0, h.col)
			elif k == 'beam':
				dx = math.cos(h.a); dy = math.sin(h.a)
				t = ((pl.x - h.x) * dx + (pl.y - h.y) * dy)
				if 0.0 <= t <= h.len:
					qx = h.x + dx * t; qy = h.y + dy * t
					if dist2(qx, qy, pl.x, pl.y) < (h.wid + P_RADIUS) ** 2:
						pl.hurt(self, h.dmg)
			elif k == 'well':
				dx = h.x - pl.x; dy = h.y - pl.y
				d = math.hypot(dx, dy)
				if d < h.r:
					f = (1.0 - d / h.r) ** 1.5
					pl.x += dx / max(1.0, d) * 260.0 * f * dt
					pl.y += dy / max(1.0, d) * 260.0 * f * dt
					if d < h.r * 0.3: pl.hurt(self, h.dmg)
				if self.rng.random() < dt * 16.0:
					a = self.rng.random() * TAU
					self.fx.part('dot', h.x + math.cos(a) * h.r, h.y + math.sin(a) * h.r,
					             -math.cos(a) * h.r * 0.9, -math.sin(a) * h.r * 0.9, 0.9, 2.4, h.col, 0.0)
			elif k == 'ring':
				f = 1.0 - h.ttl / h.life0
				rr = h.r + (h.r1 - h.r) * f
				d = dist(h.x, h.y, pl.x, pl.y)
				if d > rr:
					pl.hurt(self, h.dmg)
					dxx, dyy = norm(h.x - pl.x, h.y - pl.y)
					pl.vx += dxx * 400.0 * dt * 60 * dt
					pl.vy += dyy * 400.0 * dt * 60 * dt
			alive.append(h)
		self.hazards = alive

	def draw_hazards(self, s, camx, camy):
		t = self.t
		for h in self.hazards:
			x = h.x - camx; y = h.y - camy
			k = h.kind
			tele = h.tele > 0.0
			pulse = 0.35 + 0.65 * abs(math.sin(t * 9.0 + h.seed)) if tele else 1.0
			col = shade(h.col, pulse * (0.55 if tele else 1.0))
			if k in ('pool', 'strike'):
				r = int(h.r)
				if tele:
					pygame.draw.circle(s, col, (int(x), int(y)), r, 2)
					f = 1.0 - h.tele / max(0.01, h.tele0)
					pygame.draw.circle(s, shade(h.col, 0.5), (int(x), int(y)), max(1, int(r * f)), 1)
				else:
					g = soft_disc(r, h.col, 0.30)
					s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, pygame.BLEND_ADD)
					pygame.draw.circle(s, shade(h.col, 0.9), (int(x), int(y)), r, 2)
			elif k == 'beam':
				ex = x + math.cos(h.a) * h.len; ey = y + math.sin(h.a) * h.len
				if tele:
					pygame.draw.line(s, col, (x, y), (ex, ey), 2)
				else:
					pygame.draw.line(s, shade(h.col, 0.5), (x, y), (ex, ey), int(h.wid * 2))
					pygame.draw.line(s, h.col, (x, y), (ex, ey), int(h.wid))
					pygame.draw.line(s, WHITE, (x, y), (ex, ey), max(1, int(h.wid * 0.35)))
			elif k == 'well':
				r = int(h.r)
				if tele:
					pygame.draw.circle(s, col, (int(x), int(y)), r, 1)
				else:
					g = hollow_glow(r, h.col, 0.26)
					s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, pygame.BLEND_ADD)
					for k_ in range(3):
						a0 = t * 2.2 + h.seed + k_ * TAU / 3
						pts = [(x + math.cos(a0 + i * 0.5) * r * (1.0 - i * 0.11),
						        y + math.sin(a0 + i * 0.5) * r * (1.0 - i * 0.11)) for i in range(8)]
						pygame.draw.lines(s, shade(h.col, 0.75), False, pts, 2)
					blit_glow(s, x, y, 22, WHITE, 0.6)
			elif k == 'ring':
				f = 1.0 - h.ttl / h.life0
				rr = int(h.r + (h.r1 - h.r) * f)
				pygame.draw.circle(s, shade(h.col, 0.8), (int(x), int(y)), rr, 3)
				pygame.draw.circle(s, shade(h.col, 0.35), (int(x), int(y)), rr + 6, 1)

	# ----------------------------------------------------------------- death
	def on_enemy_death(self, e):
		rng = self.rng
		luck = self.player.luck
		on_death_special(self, e)
		if e.boss:
			from game.bosses import boss_death_extra
			boss_death_extra(self, e)
			self.boss = None
			self.director.boss_alive = False
			self.player.banked += 1          # the boss reward is a real, chosen upgrade
			drop(self, 'chest', e.x + rng.uniform(-40, 40), e.y + rng.uniform(-40, 40), 1, True)
			drop(self, 'hp', e.x, e.y, 45)
			for i in range(26):
				drop(self, 'xp', e.x + rng.uniform(-70, 70), e.y + rng.uniform(-70, 70), 12)
			self.stats['kills'] += 1
			bi = self.director.biome_index()
			if self.sandbox:
				self.director.advance_biome(self)
			elif self.director.biome['id'] == 'collapse' and self.director.endless == 0:
				self.win = True
				self.director.next_biome_t = self.director.t + 999.0
			else:
				self.director.advance_biome(self)
			return
		if e.xp > 0:
			drop(self, 'xp', e.x, e.y, e.xp)
		r = rng.random()
		if e.elite:
			if r < 0.30 + luck * 0.5: drop(self, 'chest', e.x, e.y)
			elif r < 0.8: drop(self, 'hp', e.x, e.y, 25)
			else: drop(self, 'bomb', e.x, e.y)
		else:
			if r < 0.008: drop(self, 'hp', e.x, e.y, 18)
			elif r < 0.013: drop(self, 'magnet', e.x, e.y)
			elif r < 0.0165: drop(self, 'bomb', e.x, e.y)
			elif r < 0.019: drop(self, 'clock', e.x, e.y)
		self.director.kills_recent += 1.0

	def spawn_boss_clone(self, e, a):
		from game.enemies import Enemy, _uid
		import copy
		c = Enemy()
		_uid[0] += 1
		for slot in Enemy.__slots__:
			try: setattr(c, slot, getattr(e, slot))
			except Exception: pass
		c.uid = _uid[0]
		c.boss = False
		c.elite = True
		c.affix = 'hasted'
		c.maxhp = c.hp = e.maxhp * 0.10
		c.r = int(e.r * 0.62)
		c.xp = 12
		c.ai = 'charge'
		c.boss_data = None
		c.name = e.name + ' [copy]'
		c.col = mix(e.col, (70, 70, 96), 0.55)
		c.x = e.x + math.cos(a) * 90; c.y = e.y + math.sin(a) * 90
		c.st = 0; c.f0 = 0.4; c.f1 = 0.0; c.f2 = 0.0
		c.hitpl = 0.0; c.knock_res = 0.4
		self.enemies.append(c)
		e.boss_data['clones'].append(c)
		self.fx.burst(c.x, c.y, 16, c.col, 260, 0.5, 3.0)

	# ---------------------------------------------------------------- update
	def update(self, dt, keys, mvec=None):
		self.frame += 1
		fx = self.fx
		fx.update(dt)
		if self.trans is not None and not self.trans.update(dt):
			self.trans = None
		if fx.hitstop > 0.0:
			fx.hitstop -= dt
			return
		self.t += dt
		pl = self.player

		if self.freeze_t > 0.0: self.freeze_t -= dt
		slow = 0.25 if self.freeze_t > 0.0 else 1.0
		edt = dt * slow
		if self.glitch_t > 0.0: self.glitch_t -= dt

		pl.update(dt, keys, self, mvec)
		self.grid.build(self.enemies)
		self.arsenal.update(dt, self)
		update_projs(self, dt)
		update_enemies(self, edt, self.frame)
		update_eprojs(self, edt)
		update_pickups(self, dt)
		self.update_hazards(dt)
		self.director.update(dt, self)

		if self.timers:
			keep = []
			for tt, fn in self.timers:
				if self.t >= tt: fn()
				else: keep.append((tt, fn))
			self.timers = keep

		alive = []
		for a in self.arcs:
			a.life -= dt
			if a.life > 0.0: alive.append(a)
		self.arcs = alive
		alive = []
		for t_ in self.toasts:
			t_[4] -= dt
		self.toasts = [t_ for t_ in self.toasts if t_[4] > 0.0]
		for b in self.banners:
			b.life -= dt
			if b.life > 0.0: alive.append(b)
		self.banners = alive

		self.backdrop.update(dt)

		d = self.stats['dmg'] - self._dmg_prev
		self._dmg_prev = self.stats['dmg']
		self.dps += (d / dt - self.dps) * min(1.0, dt * 1.6)

		# camera: follow with a little lead in the direction of travel
		tx = pl.x - CX + clamp(pl.vx * 0.18, -110, 110)
		ty = pl.y - CY + clamp(pl.vy * 0.18, -110, 110)
		f = min(1.0, 7.0 * dt)
		self.camx += (tx - self.camx) * f
		self.camy += (ty - self.camy) * f

		if self.audio:
			self.audio.update(dt, self.director.pressure)

	# ------------------------------------------------------------------ draw
	def bloom(self, s, strength=136, div=10):
		"""Cheap neon bloom: downscale hard, dim, smooth-upscale, add back."""
		small = pygame.transform.smoothscale(s, (W // div, H // div))
		small.fill((strength, strength, strength), None, pygame.BLEND_MULT)
		s.blit(pygame.transform.smoothscale(small, (W, H)), (0, 0), None, pygame.BLEND_ADD)

	def draw(self, s):
		if self.trans_pending:
			# `s` still holds the last frame of the biome we are leaving: that is the
			# sheet we are about to lift into R^3
			from game.transition import Matmul
			self.trans_pending = False
			self.trans = Matmul(s.copy(), self.level['accent'])
		sk = self.opts.get('shake', 1.0) * self.pace['shake']
		sx = self.fx.shake_x * sk
		sy = self.fx.shake_y * sk
		if self.glitch_t > 0.0:
			sx += self.rng.uniform(-9, 9); sy += self.rng.uniform(-5, 5)
		camx = self.camx + sx; camy = self.camy + sy

		self.last_cam = (camx, camy)
		self.backdrop.draw(s, camx, camy, self.t)
		self.draw_hazards(s, camx, camy)
		draw_pickups(self, s, camx, camy)
		draw_enemies(self, s, camx, camy)
		self.draw_arcs(s, camx, camy)
		draw_eprojs(self, s, camx, camy)
		self.player.draw(s, camx, camy, self)
		draw_projs(self, s, camx, camy)
		self.fx.draw(s, camx, camy)
		if self.opts.get('bloom'): self.bloom(s)
		self.fx.draw_nums(s, camx, camy)
		self.fx.draw_flash(s)
		if self.trans is not None: self.trans.draw(s)
		return camx, camy

	def draw_arcs(self, s, camx, camy):
		rng = self.rng
		for a in self.arcs:
			t = a.life / a.max
			col = shade(a.col, 0.4 + 0.6 * t)
			x0 = a.x0 - camx; y0 = a.y0 - camy
			x1 = a.x1 - camx; y1 = a.y1 - camy
			dx = x1 - x0; dy = y1 - y0
			n = 5
			pts = [(x0, y0)]
			for i in range(1, n):
				f = i / n
				j = (math.sin(a.seed * 13 + i * 2.7) * 0.5) * 26
				pts.append((x0 + dx * f - dy / max(1.0, math.hypot(dx, dy)) * j,
				            y0 + dy * f + dx / max(1.0, math.hypot(dx, dy)) * j))
			pts.append((x1, y1))
			pygame.draw.lines(s, col, False, pts, max(1, int(4 * t)))
			pygame.draw.lines(s, shade(WHITE, t), False, pts, 1)
			blit_glow(s, x1, y1, 16 * t + 4, a.col, t)
