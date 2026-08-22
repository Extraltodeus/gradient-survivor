"""The bench: a live run you can install anything into, to see what it does.

Opened from the title menu, toggled with TAB. While it is open the world is
frozen; press START and whatever you just installed is immediately firing at real
enemies. Everything is a button -- ops go onto the process you selected on the
left, emitters take a process slot, evolutions force their whole recipe at once,
and the run itself (schedule, unit) can be rebuilt without leaving the bench.
"""

import math, random
import pygame
from core.settings import *
from core.utils import *
from core.pace import PACES
from game.weapons import (E, O, EMIT_ORDER, EVOS, EVO_BY_EMIT, PASSIVES, PASSIVE_BY_ID,
                          BOOTS, MAX_OPS_PER_PROC, Process, Arsenal)
from game.enemies import A, spawn, spawn_boss
from game.bosses import B, BOSS_ORDER
from game.ui import panel, glyph_box, bar, draw_art, trim, rk, _weapon_scene

TABS = ('EMITTERS', 'OPS', 'PASSIVES', 'EVOLUTIONS', 'SPAWN')

# label, action, what it actually does -- spelled out, because a button whose
# meaning you have to guess is a button you do not press
TOOLS = (
	('GOD',         'god',    'ignore all incoming damage'),
	('SPAWNS',      'spawns', 'let the director keep spawning waves'),
	('CLEAR',       'clear',  'delete every enemy, projectile and hazard'),
	('HEAL',        'heal',   'restore integrity to full'),
	('+10 LEVELS',  'level',  'bank ten levels of xp instantly'),
	('RANK +3',     'rank',   'three ranks on the selected process'),
	('CACHE',       'cache',  'auto-install the upgrade that fits the build best'),
	('NEXT BIOME',  'biome',  'fold straight into the next biome'),
	('SLOW-MO',     'time',   'eight seconds of time dilation'),
	('DROP PROC',   'drop',   'remove the selected process'),
	('WIPE BUILD',  'reset',  'back to one bare process and no passives'),
)


class Sandbox:
	def __init__(self, w):
		self.w = w
		self.tab = 1
		self.sel = 0
		self.hover = None
		self.tip = None
		self.scroll = 0
		self.proc = 0
		self.t = 0.0
		self.cards = []          # [(rect, kind, key, col, glyph, title, sub)]
		self.buttons = []        # [(rect, label, fn, col, on, desc)]
		self.tabrects = []
		self.procrects = []
		self.killrects = []
		self.pacerects = []
		self.bootrects = []
		self.slotrects = []
		w.player.god = True
		w.director.paused = True
		w.banner('BENCH ONLINE', 'TAB reopens it, START drops you back in', VIOLET)

	# ---------------------------------------------------------------- helpers
	def target(self):
		ps = self.w.arsenal.procs
		if not ps: return None
		self.proc = clamp(self.proc, 0, len(ps) - 1)
		return ps[self.proc]

	def say(self, title, sub, col=VIOLET):
		self.w.banner(title, sub, col)

	# ------------------------------------------------------------ reconfigure
	def set_pace(self, i):
		"""A bench you cannot re-point at another schedule is half a bench."""
		w = self.w
		p = PACES[i]
		if p is w.pace: return
		keep = dict(w.player.passives)
		w.pace = p
		w.director.pace = p
		from game.director import BIOME_TIME
		w.director.biome_time = BIOME_TIME / p['biome']
		w.director.recalc()
		from game.pickups import CHEST_GAP
		w.chest_gap = CHEST_GAP / p['chest']
		w.player.reset_stats()
		for pid, n in keep.items():
			for _ in range(n): w.player.apply_passive(pid)
		w.player.apply_pace(p)
		w.arsenal.mark_dirty()
		self.say(p['name'], p['tag'], p['col'])

	def set_boot(self, b):
		"""Rebuild the run on another unit: body, mobility, weapon, opening op."""
		w = self.w
		w.boot = b
		w.arsenal = Arsenal(w, b['emit'])
		w.arsenal.slots = max(4, w.arsenal.slots)
		w.arsenal.procs[0].add_op(b['op'])
		w.player.reset_stats()
		w.player.apply_passive(b['passive'])
		w.player.set_unit(b)
		w.player.apply_pace(w.pace)
		w.player.hp = w.player.maxhp
		self.proc = 0
		self.say(b['name'], 'unit rebuilt - ' + E[b['emit']]['name'], b.get('col', VIOLET))

	def add_slot(self, d):
		w = self.w
		n = clamp(w.arsenal.slots + d, 1, MAX_PROCESSES)
		while len(w.arsenal.procs) > n:
			w.arsenal.procs.pop()
		w.arsenal.slots = n
		self.proc = clamp(self.proc, 0, max(0, len(w.arsenal.procs) - 1))

	def kill_proc(self, i):
		"""Installed the wrong weapon? Take it back off."""
		ps = self.w.arsenal.procs
		if not (0 <= i < len(ps)): return
		nm = ps[i].name
		ps.pop(i)
		self.proc = clamp(self.proc, 0, max(0, len(ps) - 1))
		self.say('REMOVED', nm, RED)

	# ------------------------------------------------------------------ grants
	def grant_emit(self, k):
		w = self.w
		for i, pr in enumerate(w.arsenal.procs):
			if pr.emit == k:
				self.proc = i
				self.say(E[k]['name'], 'already running - selected it', E[k]['col'])
				return
		if not w.arsenal.can_add():
			self.say('NO SLOT FREE', '%d/%d used - raise the slot count or drop one'
			         % (len(w.arsenal.procs), w.arsenal.slots), RED)
			return
		pr = w.arsenal.add_process(k)
		self.proc = w.arsenal.procs.index(pr)
		self.say(E[k]['name'], 'installed in slot %d' % (self.proc + 1), E[k]['col'])

	def grant_op(self, k, n=1):
		pr = self.target()
		if pr is None: return
		if k not in pr.ops and len(pr.ops) >= pr.op_cap():
			self.say('NO ROOM', '%s already carries %d ops' % (pr.name, pr.op_cap()), RED)
			return
		ev = None
		for _ in range(n):
			ev = pr.add_op(k) or ev
		self.w.arsenal.mark_dirty()
		if ev:
			from game.offers import _evo_burst
			_evo_burst(self.w, pr, ev)
		else:
			self.say(O[k]['name'] + ' ' + rk(pr.ops[k]), pr.name, O[k]['col'] or pr.col)

	def drop_op(self, k):
		pr = self.target()
		if pr is None or k not in pr.ops: return
		pr.ops[k] -= 1
		if pr.ops[k] <= 0: del pr.ops[k]
		if pr.evo and any(pr.ops.get(a, 0) < b for a, b in pr.evo['req'].items()):
			pr.evo = None
		pr.refresh()
		self.w.arsenal.mark_dirty()
		self.say(O[k]['name'] + ' ' + (rk(pr.ops[k]) if k in pr.ops else 'removed'), pr.name, RED)

	def grant_passive(self, pid, n=1):
		for _ in range(n): self.w.player.apply_passive(pid)
		p = PASSIVE_BY_ID[pid]
		self.say(p['name'], 'x%d' % self.w.player.passives.get(pid, 1), INK)

	def drop_passive(self, pid):
		"""Right-click takes one back. Re-applies the rest from scratch, because
		several passives are multiplicative and cannot be undone by subtracting."""
		pl = self.w.player
		have = dict(pl.passives)
		if not have.get(pid):
			self.say('NOT INSTALLED', PASSIVE_BY_ID[pid]['name'], RED)
			return
		have[pid] -= 1
		if have[pid] <= 0: del have[pid]
		slots = self.w.arsenal.slots
		pl.reset_stats()
		self.w.arsenal.slots = 4
		for k, n in have.items():
			for _ in range(n): pl.apply_passive(k)
		pl.apply_pace(self.w.pace)
		pl.hp = min(pl.hp, pl.maxhp)
		if 'slot' not in have: self.w.arsenal.slots = max(4, min(slots, MAX_PROCESSES))
		self.say(PASSIVE_BY_ID[pid]['name'], 'x%d' % have.get(pid, 0), RED)

	def grant_evo(self, ev):
		"""Force a whole evolution recipe onto a process of the right emitter."""
		w = self.w
		pr = None
		for i, q in enumerate(w.arsenal.procs):
			if q.emit == ev['emit']:
				pr = q; self.proc = i; break
		if pr is None:
			self.grant_emit(ev['emit'])
			pr = self.target()
			if pr is None or pr.emit != ev['emit']: return
		if pr.evo:
			pr.evo = None
			pr.refresh()
		for k, v in ev['req'].items():
			pr.ops[k] = max(pr.ops.get(k, 0), v)
		if len(pr.ops) > pr.op_cap():
			keep = dict(sorted(pr.ops.items(), key=lambda kv: -kv[1])[:pr.op_cap()])
			for k in list(pr.ops):
				if k not in keep and k not in ev['req']: del pr.ops[k]
		pr.refresh()
		got = pr.check_evo()
		if got:
			from game.offers import _evo_burst
			_evo_burst(w, pr, got)
		else:
			self.say(ev['name'], 'recipe installed', GOLD)

	def do_spawn(self, key, n=4, elite=False):
		w = self.w
		pl = w.player
		if key in B:
			a = w.rng.random() * TAU
			spawn_boss(w, key, pl.x + math.cos(a) * 380, pl.y + math.sin(a) * 380)
			self.say(B[key]['name'], 'summoned', RED)
			return
		for i in range(n):
			a = w.rng.random() * TAU
			d = w.rng.uniform(220, 420)
			spawn(w, key, pl.x + math.cos(a) * d, pl.y + math.sin(a) * d, elite)
		self.say(A[key]['name'], '%d spawned%s' % (n, ' (elite)' if elite else ''), A[key]['col'])

	# ------------------------------------------------------------------ actions
	def act(self, name):
		w = self.w
		pl = w.player
		if name == 'god':
			pl.god = not pl.god
		elif name == 'spawns':
			w.director.paused = not w.director.paused
		elif name == 'clear':
			for e in w.enemies:
				if not e.boss: e.dead = True
			w.enemies = [e for e in w.enemies if not e.dead]
			w.eprojs = []
			w.hazards.clear()
		elif name == 'heal':
			pl.hp = pl.maxhp
		elif name == 'level':
			for _ in range(10): pl.add_xp(pl.xp_next)
			pl.banked = 0
		elif name == 'rank':
			pr = self.target()
			if pr:
				pr.rank += 3
				pr.refresh()
				ev = pr.check_evo()
				if ev:
					from game.offers import _evo_burst
					_evo_burst(w, pr, ev)
		elif name == 'reset':
			slots = w.arsenal.slots
			w.arsenal = Arsenal(w, w.boot['emit'] if w.boot else 'bolt')
			w.arsenal.slots = slots
			pl.reset_stats()
			pl.apply_pace(w.pace)
			self.proc = 0
			self.say('BUILD WIPED', 'back to one bare process', RED)
		elif name == 'drop':
			self.kill_proc(self.proc)
		elif name == 'biome':
			w.director.advance_biome(w)
		elif name == 'cache':
			w.auto_upgrade(1)
		elif name == 'time':
			w.freeze_t = 8.0 if w.freeze_t <= 0 else 0.0

	# ------------------------------------------------------------------- events
	def event(self, ev, w):
		if ev.type == pygame.KEYDOWN:
			if ev.key in (pygame.K_TAB, pygame.K_ESCAPE): return False
			if pygame.K_1 <= ev.key <= pygame.K_5:
				self.tab = ev.key - pygame.K_1; self.sel = 0; self.scroll = 0
			elif ev.key in (pygame.K_RIGHT, pygame.K_d): self.sel += 1
			elif ev.key in (pygame.K_LEFT, pygame.K_a): self.sel -= 1
			elif ev.key in (pygame.K_DOWN, pygame.K_s): self.sel += 4
			elif ev.key in (pygame.K_UP, pygame.K_w): self.sel -= 4
			elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
				if 0 <= self.sel < len(self.cards): self.fire(self.cards[self.sel], False)
			elif ev.key == pygame.K_q:
				self.proc = (self.proc - 1) % max(1, len(w.arsenal.procs))
			elif ev.key == pygame.K_e:
				self.proc = (self.proc + 1) % max(1, len(w.arsenal.procs))
			if self.cards: self.sel = self.sel % len(self.cards)
		elif ev.type == pygame.MOUSEWHEEL:
			self.scroll = max(0, self.scroll - ev.y * 60)
		elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
			alt = ev.button == 3
			for i, r in enumerate(self.pacerects):
				if r.collidepoint(ev.pos):
					self.set_pace(i); w.audio.play('gem', 0.7); return True
			for i, r in enumerate(self.bootrects):
				if r.collidepoint(ev.pos):
					self.set_boot(BOOTS[i]); w.audio.play('pick', 0.8); return True
			for r, d in self.slotrects:
				if r.collidepoint(ev.pos):
					self.add_slot(d); w.audio.play('move', 0.7); return True
			for i, r in enumerate(self.killrects):
				if r.collidepoint(ev.pos):
					self.kill_proc(i); w.audio.play('deny', 0.8); return True
			for i, r in enumerate(self.tabrects):
				if r.collidepoint(ev.pos):
					self.tab = i; self.sel = 0; self.scroll = 0
					w.audio.play('move', 0.6)
					return True
			for i, r in enumerate(self.procrects):
				if r.collidepoint(ev.pos):
					self.proc = i
					w.audio.play('move', 0.6)
					return True
			for r, lbl, fn, col, on, desc in self.buttons:
				if r.collidepoint(ev.pos):
					if fn == 'start':
						w.audio.play('pick', 1.0)
						return False
					self.act(fn)
					w.audio.play('pick', 0.7)
					return True
			for c in self.cards:
				if c[0].collidepoint(ev.pos):
					self.fire(c, alt)
					return True
		elif ev.type == pygame.MOUSEMOTION:
			self.hover = None
			self.tip = None
			for r, lbl, fn, col, on, desc in self.buttons:
				if r.collidepoint(ev.pos): self.tip = (lbl, desc)
			for i, c in enumerate(self.cards):
				if c[0].collidepoint(ev.pos):
					self.hover = i; self.sel = i; break
		return True

	def fire(self, card, alt):
		_r, kind, key = card[0], card[1], card[2]
		w = self.w
		big = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
		if kind == 'emit':
			if alt:
				for i, pr in enumerate(w.arsenal.procs):
					if pr.emit == key: self.kill_proc(i); break
			else: self.grant_emit(key)
		elif kind == 'op':
			if alt: self.drop_op(key)
			else: self.grant_op(key, 3 if big else 1)
		elif kind == 'passive':
			if alt: self.drop_passive(key)
			else: self.grant_passive(key, 5 if big else 1)
		elif kind == 'evo': self.grant_evo(key)
		elif kind == 'foe': self.do_spawn(key, 1 if alt else 6, alt)
		elif kind == 'boss': self.do_spawn(key)
		w.audio.play('pick', 0.8)

	def update(self, dt):
		self.t += dt

	# --------------------------------------------------------------------- draw
	def draw(self, s, w):
		o = pygame.Surface((W, H), pygame.SRCALPHA)
		o.fill((5, 7, 12, 214))
		s.blit(o, (0, 0))
		pl = w.player
		self.buttons = []
		self.cards = []
		self.procrects = []
		self.killrects = []
		self.pacerects = []
		self.bootrects = []
		self.slotrects = []

		draw_text(s, 'BENCH', 26, 14, 26, VIOLET, True)
		draw_text(s, 'a live run with the safety off', 118, 24, 12, INK_DIM)
		draw_text(s, 'dps %d' % int(getattr(w, 'dps', 0.0)), W - 26, 16, 16, GOLD, True, 'tr')
		draw_text(s, 'lv %d   %d enemies   %s' % (pl.level, len(w.enemies), w.level['name']),
		          W - 26, 36, 12, INK_DIM, False, 'tr')

		y = self._config(s, w, 26, 52)
		y = self._toolbar(s, w, 26, y + 6)

		LW = int(min(430, W * 0.30))
		x = 26
		gy = y + 4
		panel(s, (x - 10, gy - 8, LW, H - gy - 54), 200)
		self._build(s, w, x, gy, LW)

		rx = 26 + LW + 14
		rw = W - rx - 26
		ty = gy
		self.tabrects = []
		tx = rx
		for i, name in enumerate(TABS):
			tw = text_w(name, 13, True) + 22
			r = pygame.Rect(tx, ty - 4, tw, 26)
			self.tabrects.append(r)
			on = i == self.tab
			if on:
				pygame.draw.rect(s, (20, 24, 38), r, 0, 5)
				pygame.draw.line(s, VIOLET, (r.x + 4, r.bottom), (r.right - 4, r.bottom), 2)
			draw_text(s, '%d %s' % (i + 1, name), r.centerx, ty, 13, VIOLET if on else INK_FAINT, on, 'tc')
			tx += tw + 6
		ty += 34

		dh = 140
		gh = H - ty - dh - 42
		self._cards(s, w, rx, ty, rw, gh)
		self._detail(s, w, rx, H - dh - 34, rw, dh)

		foot = ('left click install   right click remove   shift+click x3   1-5 tabs   '
		        'TAB or ESC or START back to the fight')
		draw_text(s, foot, CX, H - 24, 12, INK_FAINT, False, 'tc')
		if self.tip:
			g = text('%s  -  %s' % self.tip, 12, INK, True)
			r = pygame.Rect(CX - g.get_width() * 0.5 - 10, H - 48, g.get_width() + 20, 22)
			pygame.draw.rect(s, (18, 22, 34), r, 0, 5)
			pygame.draw.rect(s, VIOLET, r, 1, 5)
			s.blit(g, (r.x + 10, r.y + 4))

	# ------------------------------------------------------------- config strip
	def _config(self, s, w, x, y):
		draw_text(s, 'SCHEDULE', x, y + 6, 11, INK_FAINT, True)
		cx_ = x + 82
		for i, p in enumerate(PACES):
			lbl = p['name']
			bw = text_w(lbl, 11, True) + 16
			r = pygame.Rect(cx_, y, bw, 24)
			self.pacerects.append(r)
			on = p is w.pace
			pygame.draw.rect(s, (22, 26, 40) if on else (14, 17, 26), r, 0, 5)
			pygame.draw.rect(s, p['col'] if on else LINE, r, 2 if on else 1, 5)
			draw_text(s, lbl, r.centerx, r.y + 5, 11, p['col'] if on else INK_FAINT, on, 'tc')
			cx_ += bw + 6

		draw_text(s, 'UNIT', cx_ + 14, y + 6, 11, INK_FAINT, True)
		cx_ += 56
		cur = (w.boot or {}).get('id')
		for i, b in enumerate(BOOTS):
			bw = text_w(b['name'], 11, True) + 16
			r = pygame.Rect(cx_, y, bw, 24)
			self.bootrects.append(r)
			on = b['id'] == cur
			col = b.get('col', VIOLET)
			pygame.draw.rect(s, (22, 26, 40) if on else (14, 17, 26), r, 0, 5)
			pygame.draw.rect(s, col if on else LINE, r, 2 if on else 1, 5)
			draw_text(s, b['name'], r.centerx, r.y + 5, 11, col if on else INK_FAINT, on, 'tc')
			cx_ += bw + 6
		return y + 26

	# ----------------------------------------------------------------- toolbar
	def _toolbar(self, s, w, x, y):
		pl = w.player
		state = {'god': pl.god, 'spawns': not w.director.paused, 'time': w.freeze_t > 0}
		bx = x; by = y
		rowh = 38
		items = [('START RUN', 'start', 'close the bench and play with this build')] + list(TOOLS)
		for lbl, fn, desc in items:
			bw = max(text_w(lbl, 12, True), text_w(desc, 10)) + 22
			if bx + bw > W - 26:
				bx = x; by += rowh + 5
			r = pygame.Rect(bx, by, bw, rowh)
			on = state.get(fn)
			if fn == 'start': col = GREEN
			else: col = GREEN if on else (RED if on is False else INK_DIM)
			pygame.draw.rect(s, (18, 26, 22) if fn == 'start' else (16, 20, 30), r, 0, 5)
			pygame.draw.rect(s, col if (on is not None or fn == 'start') else LINE,
			                 r, 2 if fn == 'start' else 1, 5)
			draw_text(s, lbl, r.centerx, r.y + 4, 12,
			          col if (on is not None or fn == 'start') else INK, True, 'tc')
			draw_text(s, desc, r.centerx, r.y + 20, 10, INK_FAINT, False, 'tc')
			self.buttons.append((r, lbl, fn, col, on, desc))
			bx += bw + 6
		return by + rowh

	# ----------------------------------------------------------------- the build
	def _build(self, s, w, x, y, LW):
		pl = w.player
		draw_text(s, 'PROCESSES', x, y, 12, INK, True)
		draw_text(s, 'Q/E or click to target', x + 92, y + 1, 11, INK_FAINT)
		sx = x + LW - 92
		draw_text(s, 'SLOTS %d' % w.arsenal.slots, sx, y, 11, INK_DIM, True)
		for lbl, d in (('-', -1), ('+', 1)):
			r = pygame.Rect(sx + 58 + (14 if d > 0 else 0), y - 2, 13, 15)
			self.slotrects.append((r, d))
			pygame.draw.rect(s, (20, 24, 36), r, 0, 3)
			pygame.draw.rect(s, VIOLET, r, 1, 3)
			draw_text(s, lbl, r.centerx, r.y + 1, 11, VIOLET, True, 'tc')
		y += 20
		for i, pr in enumerate(w.arsenal.procs):
			r = pygame.Rect(x, y, LW - 20, 42)
			self.procrects.append(r)
			sel = i == self.proc
			if sel:
				pygame.draw.rect(s, (22, 26, 40), r, 0, 6)
				pygame.draw.rect(s, VIOLET, r, 1, 6)
			glyph_box(s, x + 5, y + 6, 28, E[pr.emit]['glyph'], pr.col, (16, 20, 30))
			from game.ui import fit
			fit(s, pr.name, x + 40, y + 3, 13, GOLD if pr.evo else INK, bool(pr.evo), LW - 106, 'tl', 8)
			ops = '  '.join('%s%s' % (O[k]['glyph'], rk(v)) for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]))
			draw_text(s, 'r%d  %s' % (pr.rank, ops), x + 40, y + 21, 11, INK_DIM)
			c = pr.stats(pl)
			draw_text(s, '%.0f x%d  %.2fs' % (c['dmg'], c['count'], c['cd']),
			          x + LW - 44, y + 22, 11, INK_FAINT, False, 'tr')
			kr = pygame.Rect(x + LW - 42, y + 5, 16, 16)
			self.killrects.append(kr)
			pygame.draw.rect(s, (30, 16, 20), kr, 0, 3)
			pygame.draw.rect(s, RED, kr, 1, 3)
			draw_text(s, 'x', kr.centerx, kr.y + 1, 12, RED, True, 'tc')
			y += 46
		for i in range(len(w.arsenal.procs), w.arsenal.slots):
			pygame.draw.rect(s, (34, 40, 56), (x, y, LW - 20, 30), 1, 6)
			draw_text(s, 'slot %d - free' % (i + 1), x + 12, y + 8, 11, (60, 70, 94))
			y += 34
		y += 6
		pygame.draw.line(s, (26, 32, 46), (x, y), (x + LW - 20, y))
		y += 8
		rows = [('damage', '%d%%' % int(pl.dmg_mult * 100)), ('cooldown', '%d%%' % int(pl.cd_mult * 100)),
		        ('area', '%d%%' % int(pl.area_mult * 100)), ('proj speed', '%d%%' % int(pl.pspeed_mult * 100)),
		        ('amount', '+%d' % pl.amount), ('crit', '%d%% x%.1f' % (int(pl.crit_c * 100), 2.0 + pl.crit_m)),
		        ('move', '%d%%' % int(pl.move_mult * 100)),
		        ('armor / dodge', '%d / %d%%' % (int(pl.armor), int(pl.dodge * 100))),
		        ('regen', '%.1f/s' % pl.regen), ('luck', '%d%%' % int(pl.luck * 100)),
		        ('mobility', 'blink' if pl.mobility == 'blink' else 'dash')]
		for k, v in rows:
			if y > H - 76: break
			draw_text(s, k, x, y, 11, INK_FAINT)
			draw_text(s, v, x + LW - 26, y, 11, INK, True, 'tr')
			y += 15

	# ------------------------------------------------------------------- cards
	def _cards(self, s, w, x0, y0, ww, hh):
		pr = self.target()
		ww -= 12                                  # room for the scrollbar
		cols = max(2, int(ww / 250))
		cw = int((ww - (cols - 1) * 10) / cols)
		ch = 62
		items = []
		tab = self.tab
		if tab == 0:
			for k in EMIT_ORDER:
				em = E[k]
				have = any(p.emit == k for p in w.arsenal.procs)
				items.append(('emit', k, em['col'], em['glyph'], em['name'],
				              'running' if have else 'tier %d' % em['tier'], have))
		elif tab == 1:
			for k in O:
				d = O[k]
				cur = pr.ops.get(k, 0) if pr else 0
				items.append(('op', k, d['col'] or INK_DIM, d['glyph'], d['name'],
				              ('rank %d' % cur) if cur else d['tag'], cur > 0))
		elif tab == 2:
			for p in PASSIVES:
				lvl = w.player.passives.get(p['id'], 0)
				items.append(('passive', p['id'], RARITY_COL.get(p['rare'], INK), p['glyph'], p['name'],
				              ('x%d' % lvl) if lvl else 'system', lvl > 0))
		elif tab == 3:
			for ev in EVOS:
				pp = None
				for q in w.arsenal.procs:
					if q.emit == ev['emit']: pp = q
				items.append(('evo', ev, GOLD, E[ev['emit']]['glyph'], ev['name'],
				              E[ev['emit']]['name'], bool(pp and pp.evo is ev)))
		else:
			for k in A:
				a = A[k]
				items.append(('foe', k, a['col'], a['name'][0], a['name'],
				              'hp %d  cost %.1f' % (a['hp'], a['cost']), False))
			for k in BOSS_ORDER:
				d = B[k]
				items.append(('boss', k, RED, '@', d['name'], 'BOSS  hp %d' % d['hp'], False))

		rows = (len(items) + cols - 1) // cols
		maxscroll = max(0, rows * (ch + 10) - hh)
		self.scroll = clamp(self.scroll, 0, maxscroll)
		clip = s.get_clip()
		s.set_clip(pygame.Rect(x0, y0, ww, hh))
		for i, (kind, key, col, glyph, title, sub, on) in enumerate(items):
			cx_ = x0 + (i % cols) * (cw + 10)
			cy_ = y0 + (i // cols) * (ch + 10) - self.scroll
			r = pygame.Rect(cx_, cy_, cw, ch)
			self.cards.append((r, kind, key, col, glyph, title, sub))
			if cy_ > y0 + hh or cy_ + ch < y0: continue
			sel = i == self.sel
			pygame.draw.rect(s, (18, 21, 32) if not on else (24, 30, 40), r, 0, 7)
			pygame.draw.rect(s, col if sel else (LINE if not on else shade(col, 0.55)), r, 2 if sel else 1, 7)
			glyph_box(s, r.x + 8, r.y + 8, 34, glyph, col, (12, 15, 24))
			ts = 13
			while ts > 9 and text_w(title, ts, True) > cw - 58: ts -= 1
			draw_text(s, title, r.x + 50, r.y + 9, ts, INK, True)
			draw_text(s, sub, r.x + 50, r.y + 28, 11, shade(col, 0.9))
			if kind == 'op' and pr:
				cur = pr.ops.get(key, 0)
				for k in range(MAX_TRAIT_RK):
					pygame.draw.rect(s, col if k < cur else (34, 40, 56),
					                 (r.x + 50 + k * 10, r.y + 45, 7, 6), 0, 2)
		s.set_clip(clip)
		if maxscroll:
			bh = max(24, int(hh * hh / (hh + maxscroll)))
			byy = y0 + int((hh - bh) * self.scroll / maxscroll)
			pygame.draw.rect(s, (30, 36, 52), (x0 + ww + 5, y0, 3, hh), 0, 2)
			pygame.draw.rect(s, VIOLET, (x0 + ww + 5, byy, 3, bh), 0, 2)

	# ------------------------------------------------------------------ detail
	def _detail(self, s, w, x, y, ww, hh):
		if not self.cards: return
		i = clamp(self.sel, 0, len(self.cards) - 1)
		r_, kind, key, col, glyph, title, sub = self.cards[i]
		panel(s, (x, y, ww, hh), 210, shade(col, 0.6))
		draw_text(s, title, x + 16, y + 8, 17, col, True)
		pr = self.target()
		desc = ''
		art = None
		scene = None
		if kind == 'emit':
			em = E[key]
			desc = em['desc'] + '   grows well with: ' + ', '.join(O[a]['name'] for a in em['affinity'])
			scene = (key, None)
		elif kind == 'op':
			d = O[key]
			desc = d['desc']
			if pr is not None:
				nxt = dict(pr.ops)
				nxt[key] = min(MAX_TRAIT_RK, nxt.get(key, 0) + 1)
				scene = (pr.emit, nxt)
				desc += '     on %s: rank %d -> %d' % (pr.name, pr.ops.get(key, 0), nxt[key])
			else:
				art = ('op', key)
		elif kind == 'passive':
			p = PASSIVE_BY_ID[key]
			desc = p['desc'] + '     installed x%d' % w.player.passives.get(key, 0)
			art = ('passive', key)
		elif kind == 'evo':
			ev = key
			need = '   +   '.join('%s %s' % (O[k]['name'], rk(v)) for k, v in ev['req'].items())
			desc = ev['desc'] + '     requires ' + E[ev['emit']]['name'] + ' with ' + need
			ops = dict(ev['req']); ops.update(ev.get('grant', {}))
			scene = (ev['emit'], ops)
		elif kind in ('foe', 'boss'):
			d = A[key] if kind == 'foe' else B[key]
			desc = ('ai %s   hp %d   speed %d   damage %d' % (d.get('ai', 'chase'), d['hp'], d['spd'],
			                                                  d.get('dmg', 0))) if kind == 'foe' \
			       else d['title'] + '   attacks: ' + ', '.join(d['atks'])
		bw = ww - 214
		yy = y + 32
		for line in wrap(desc, 13, bw):
			if yy > y + hh - 18: break
			draw_text(s, line, x + 16, yy, 13, INK_DIM)
			yy += 18
		if scene:
			_weapon_scene(s, (x + ww - 200, y + 12, 186, hh - 24), scene[0], col, self.t,
			              scene[1], None, w.player.shape, w.player.col)
		elif art:
			draw_art(s, (x + ww - 200, y + 12, 186, hh - 24), art[0], art[1], col, self.t)
