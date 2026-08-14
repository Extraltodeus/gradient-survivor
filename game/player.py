"""The agent: movement, dash, integrity, global stat multipliers, levelling."""

import math
import pygame
from core.settings import *
from core.utils import *


class Player:
	def __init__(self, w):
		self.w = w
		self.x = 0.0; self.y = 0.0
		self.vx = 0.0; self.vy = 0.0
		self.fx_ = 1.0; self.fy_ = 0.0
		self.hp = P_HP; self.maxhp = P_HP
		self.iframe = 0.0
		self.dash_cd = 0.0
		self.dash_t = 0.0
		self.dash_max = 3.2
		self.level = 1
		self.xp = 0.0
		self.xp_next = xp_for_level(1)
		self.dead = False
		self.t = 0.0
		self.hurt_flash = 0.0
		self.trail_t = 0.0
		self.banked = 0          # pending level-ups
		self.rerolls = 2
		self.banishes = 1
		self.revives = 0
		self.reset_stats()

	def reset_stats(self):
		self.dmg_mult = 1.0
		self.cd_mult = 1.0
		self.area_mult = 1.0
		self.pspeed_mult = 1.0
		self.dur_mult = 1.0
		self.amount = 0
		self.crit_c = 0.03
		self.crit_m = 0.0
		self.move_mult = 1.0
		self.magnet = P_MAGNET
		self.xp_mult = 1.0
		self.luck = 0.0
		self.armor = 0.0
		self.dodge = 0.0
		self.regen = 0.0
		self.cool_mult = 1.0
		self.passives = {}

	# ------------------------------------------------------------- passives
	def apply_passive(self, pid):
		self.passives[pid] = self.passives.get(pid, 0) + 1
		if   pid == 'power':  self.dmg_mult += 0.12
		elif pid == 'haste':  self.cd_mult *= 0.91
		elif pid == 'area':   self.area_mult += 0.14
		elif pid == 'vel':    self.pspeed_mult += 0.16
		elif pid == 'hp':     self.maxhp += 22; self.hp = min(self.maxhp, self.hp + 22)
		elif pid == 'regen':  self.regen += 0.6
		elif pid == 'speed':  self.move_mult += 0.09
		elif pid == 'magnet': self.magnet *= 1.35
		elif pid == 'xp':     self.xp_mult += 0.16
		elif pid == 'armor':  self.armor += 1.0
		elif pid == 'crit':   self.crit_c += 0.06
		elif pid == 'luck':   self.luck += 0.12
		elif pid == 'dodge':  self.dodge += 0.06
		elif pid == 'cool':   self.cool_mult *= 0.6
		elif pid == 'amount': self.amount += 1
		elif pid == 'slot':   self.w.arsenal.slots += 1
		elif pid == 'reroll': self.rerolls += 2; self.banishes += 1
		self.w.arsenal.mark_dirty()

	# ---------------------------------------------------------------- update
	def update(self, dt, keys, w, mvec=None):
		self.t += dt
		mx = my = 0.0
		if keys[pygame.K_a] or keys[pygame.K_LEFT]:  mx -= 1.0
		if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mx += 1.0
		if keys[pygame.K_w] or keys[pygame.K_UP]:    my -= 1.0
		if keys[pygame.K_s] or keys[pygame.K_DOWN]:  my += 1.0
		m = math.hypot(mx, my)
		if m > 0.0:
			mx /= m; my /= m
			self.fx_ = mx; self.fy_ = my
		elif mvec is not None:
			# analogue: magnitude of mvec is already 0..1, so short drags creep
			mx, my = mvec
			m = math.hypot(mx, my)
			if m > 0.0:
				self.fx_ = mx / m; self.fy_ = my / m

		spd = P_SPEED * self.move_mult
		if self.dash_t > 0.0:
			self.dash_t -= dt
			self.iframe = max(self.iframe, 0.08)
			dsp = 980.0
			self.vx = self.fx_ * dsp; self.vy = self.fy_ * dsp
			self.trail_t -= dt
			if self.trail_t <= 0.0:
				self.trail_t = 0.02
				w.fx.part('dot', self.x, self.y, 0, 0, 0.32, 8.0, CYAN, 0.0, glowp=0.8)
		else:
			tvx = mx * spd; tvy = my * spd
			f = min(1.0, 15.0 * dt)
			self.vx += (tvx - self.vx) * f
			self.vy += (tvy - self.vy) * f

		self.x += self.vx * dt
		self.y += self.vy * dt

		if self.dash_cd > 0.0: self.dash_cd -= dt
		if self.iframe > 0.0: self.iframe -= dt
		if self.hurt_flash > 0.0: self.hurt_flash -= dt * 3.0
		if self.regen > 0.0 and self.hp < self.maxhp:
			self.heal(self.regen * dt, False)

	def try_dash(self, w):
		if self.dash_cd > 0.0 or self.dash_t > 0.0: return False
		self.dash_t = 0.16
		self.dash_cd = self.dash_max
		w.fx.wave(self.x, self.y, 6, 46, 0.3, CYAN, 3)
		w.fx.burst(self.x, self.y, 10, CYAN, 220, 0.35, 3.0, adir=math.atan2(-self.fy_, -self.fx_), spread=1.6)
		w.audio.play('fire_swarm', 0.5)
		return True

	# ---------------------------------------------------------------- damage
	def hurt(self, w, amount, src=None):
		if self.iframe > 0.0 or self.dead: return
		if self.dodge > 0.0 and w.rng.random() < self.dodge:
			w.fx.dmg(self.x, self.y - 20, 'PHASE', CYAN, False, 14)
			self.iframe = 0.25
			return
		amount = max(1.0, amount - self.armor)
		self.hp -= amount
		self.iframe = P_IFRAMES
		self.hurt_flash = 1.0
		w.stats['taken'] += amount
		w.fx.shake(0.22 + min(0.3, amount / 90.0))
		w.fx.screen_flash((90, 10, 20), 0.22)
		w.fx.burst(self.x, self.y, 12, RED, 240, 0.4, 3.0)
		w.fx.dmg(self.x, self.y - 22, '-' + str(int(amount)), RED, False, 17)
		w.audio.play('hurt', 0.8, 0.1)
		if self.hp <= 0.0:
			if self.revives > 0:
				self.revives -= 1
				self.hp = self.maxhp * 0.6
				self.iframe = 2.5
				w.fx.screen_flash(CYAN, 0.8)
				w.fx.wave(self.x, self.y, 10, 400, 0.8, CYAN, 6)
				w.banner('CHECKPOINT RESTORED', 'a backup was found', CYAN)
				w.audio.play('evolve', 1.0)
				w.explode_friendly(self.x, self.y, 360.0, 999.0)
			else:
				self.hp = 0.0
				self.dead = True

	def heal(self, amount, show=True):
		if self.hp >= self.maxhp: return
		self.hp = min(self.maxhp, self.hp + amount)
		if show:
			self.w.fx.dmg(self.x, self.y - 24, '+' + str(int(amount)), HP_COL, False, 15)

	# ------------------------------------------------------------------- xp
	def add_xp(self, amount):
		self.xp += amount * self.xp_mult
		while self.xp >= self.xp_next:
			self.xp -= self.xp_next
			self.level += 1
			self.banked += 1
			self.xp_next = xp_for_level(self.level)

	# ----------------------------------------------------------------- draw
	def draw(self, s, camx, camy, w):
		x = self.x - camx; y = self.y - camy
		t = self.t
		col = CYAN
		if self.hurt_flash > 0.0: col = mix(CYAN, RED, self.hurt_flash)
		inv = self.iframe > 0.0 and int(t * 22) % 2 == 0

		blit_glow(s, x, y, 34, col, 0.85 if not inv else 0.4)
		a = math.atan2(self.fy_, self.fx_)
		r = P_RADIUS
		pts = [(x + math.cos(a) * r * 1.7, y + math.sin(a) * r * 1.7),
		       (x + math.cos(a + 2.4) * r, y + math.sin(a + 2.4) * r),
		       (x + math.cos(a + math.pi) * r * 0.5, y + math.sin(a + math.pi) * r * 0.5),
		       (x + math.cos(a - 2.4) * r, y + math.sin(a - 2.4) * r)]
		if not inv:
			pygame.draw.polygon(s, col, pts)
			pygame.draw.polygon(s, WHITE, pts, 1)
		else:
			pygame.draw.polygon(s, shade(col, 0.5), pts, 1)

		# orbiting integrity nodes
		n = 3
		for i in range(n):
			aa = t * 1.6 + i * TAU / n
			px = x + math.cos(aa) * 21; py = y + math.sin(aa) * 21
			blit_glow(s, px, py, 7, col, 0.7)

		if self.dash_cd > 0.0:
			f = 1.0 - self.dash_cd / self.dash_max
			pygame.draw.arc(s, shade(CYAN, 0.55), pygame.Rect(int(x - 26), int(y - 26), 52, 52),
			                -math.pi * 0.5, -math.pi * 0.5 + TAU * f, 2)
		else:
			g = ring(25, CYAN, 1, 60 + int(40 * math.sin(t * 4)))
			s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, pygame.BLEND_ADD)
