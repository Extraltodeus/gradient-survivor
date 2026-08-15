"""The bench: a live run you can install anything into, to see what it does.

Opened from the title menu, toggled with TAB. While it is open the world is
frozen; close it and whatever you just installed is immediately firing at real
enemies. Everything is a button -- ops go onto the process you selected on the
left, emitters open new slots, evolutions force their whole recipe at once.
"""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.weapons import (E, O, EMIT_ORDER, EVOS, EVO_BY_EMIT, PASSIVES, PASSIVE_BY_ID,
                          MAX_OPS_PER_PROC, Process)
from game.enemies import A, spawn, spawn_boss
from game.bosses import B, BOSS_ORDER
from game.ui import panel, glyph_box, bar, draw_art, trim, rk

TABS = ('EMITTERS', 'OPS', 'PASSIVES', 'EVOLUTIONS', 'SPAWN')


class Sandbox:
	def __init__(self, w):
		self.w = w
		self.tab = 1
		self.sel = 0
		self.hover = None
		self.scroll = 0
		self.proc = 0
		self.t = 0.0
		self.cards = []          # [(rect, kind, key, col, glyph, title, sub)]
		self.buttons = []        # [(rect, label, fn, col, on)]
		self.tabrects = []
		self.procrects = []
		w.player.god = True
		w.arsenal.slots = MAX_PROCESSES
		w.director.paused = True
		w.banner('BENCH ONLINE', 'TAB opens the bench, ESC closes it', VIOLET)

	# ---------------------------------------------------------------- helpers
	def target(self):
		ps = self.w.arsenal.procs
		if not ps: return None
		self.proc = clamp(self.proc, 0, len(ps) - 1)
		return ps[self.proc]

	def say(self, title, sub, col=VIOLET):
		self.w.banner(title, sub, col)

	# ------------------------------------------------------------------ grants
	def grant_emit(self, k):
		w = self.w
		for i, pr in enumerate(w.arsenal.procs):
			if pr.emit == k:
				self.proc = i
				self.say(E[k]['name'], 'already running - selected it', E[k]['col'])
				return
		if len(w.arsenal.procs) >= MAX_PROCESSES:
			w.arsenal.procs.pop()
		pr = w.arsenal.add_process(k)
		self.proc = w.arsenal.procs.index(pr)
		self.say(E[k]['name'], 'installed as a new process', E[k]['col'])

	def grant_op(self, k, n=1):
		pr = self.target()
		if pr is None: return
		if k not in pr.ops and len(pr.ops) >= MAX_OPS_PER_PROC:
			self.say('NO ROOM', '%s already carries %d ops' % (pr.name, MAX_OPS_PER_PROC), RED)
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
		pr.refresh()
		self.w.arsenal.mark_dirty()

	def grant_passive(self, pid, n=1):
		for _ in range(n): self.w.player.apply_passive(pid)
		p = PASSIVE_BY_ID[pid]
		self.say(p['name'], 'x%d' % self.w.player.passives.get(pid, 1), INK)

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
		if pr.evo:
			pr.evo = None
			pr.refresh()
		for k, v in ev['req'].items():
			pr.ops[k] = max(pr.ops.get(k, 0), v)
		if len(pr.ops) > MAX_OPS_PER_PROC:
			keep = dict(sorted(pr.ops.items(), key=lambda kv: -kv[1])[:MAX_OPS_PER_PROC])
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
			from game.weapons import Arsenal
			w.arsenal = Arsenal(w, w.boot['emit'] if w.boot else 'bolt')
			w.arsenal.slots = MAX_PROCESSES
			pl.reset_stats()
			pl.pace_xp = w.pace['xp']
			pl.cd_mult *= w.pace['cd']
			self.proc = 0
			self.say('BUILD WIPED', 'back to one bare process', RED)
		elif name == 'drop':
			ps = w.arsenal.procs
			if len(ps) > 1:
				ps.pop(clamp(self.proc, 0, len(ps) - 1))
				self.proc = max(0, self.proc - 1)
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
			for r, lbl, fn, col, on in self.buttons:
				if r.collidepoint(ev.pos):
					self.act(fn)
					w.audio.play('pick', 0.7)
					return True
			for c in self.cards:
				if c[0].collidepoint(ev.pos):
					self.fire(c, alt)
					return True
		elif ev.type == pygame.MOUSEMOTION:
			self.hover = None
			for i, c in enumerate(self.cards):
				if c[0].collidepoint(ev.pos):
					self.hover = i; self.sel = i; break
		return True

	def fire(self, card, alt):
		_r, kind, key = card[0], card[1], card[2]
		w = self.w
		if kind == 'emit': self.grant_emit(key)
		elif kind == 'op':
			if alt: self.drop_op(key)
			else: self.grant_op(key, 3 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1)
		elif kind == 'passive': self.grant_passive(key, 5 if alt else 1)
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

		draw_text(s, 'BENCH', 26, 18, 28, VIOLET, True)
		draw_text(s, 'a live run with the safety off', 128, 28, 12, INK_DIM)
		draw_text(s, 'dps %d' % int(getattr(w, 'dps', 0.0)), W - 26, 24, 16, GOLD, True, 'tr')
		draw_text(s, '%s   lv %d   %d enemies' % (w.pace['name'], pl.level, len(w.enemies)),
		          W - 26, 44, 12, INK_DIM, False, 'tr')

		# ---- toolbar
		bx = 26; by = 56
		tools = [('GOD', 'god', pl.god), ('SPAWNS', 'spawns', not w.director.paused),
		         ('CLEAR', 'clear', None), ('HEAL', 'heal', None), ('+10 LV', 'level', None),
		         ('RANK +3', 'rank', None), ('CACHE', 'cache', None), ('NEXT BIOME', 'biome', None),
		         ('SLOW-MO', 'time', w.freeze_t > 0), ('DROP PROC', 'drop', None),
		         ('WIPE BUILD', 'reset', None)]
		for lbl, fn, on in tools:
			bw = text_w(lbl, 12, True) + 20
			r = pygame.Rect(bx, by, bw, 24)
			col = GREEN if on else (RED if on is False else INK_DIM)
			pygame.draw.rect(s, (16, 20, 30), r, 0, 5)
			pygame.draw.rect(s, col if on is not None else LINE, r, 1, 5)
			draw_text(s, lbl, r.centerx, r.y + 5, 12, col if on is not None else INK, True, 'tc')
			self.buttons.append((r, lbl, fn, col, on))
			bx += bw + 7

		# ---- left column: the build
		LW = int(min(430, W * 0.30))
		x = 26; y = 96
		panel(s, (x - 10, y - 8, LW, H - y - 54), 200)
		draw_text(s, 'PROCESSES   Q/E or click to target', x, y, 12, INK, True)
		y += 20
		for i, pr in enumerate(w.arsenal.procs):
			r = pygame.Rect(x, y, LW - 20, 42)
			self.procrects.append(r)
			sel = i == self.proc
			if sel:
				pygame.draw.rect(s, (22, 26, 40), r, 0, 6)
				pygame.draw.rect(s, VIOLET, r, 1, 6)
			glyph_box(s, x + 5, y + 6, 28, E[pr.emit]['glyph'], pr.col, (16, 20, 30))
			draw_text(s, trim(pr.name, 26), x + 40, y + 4, 13, GOLD if pr.evo else INK, bool(pr.evo))
			ops = '  '.join('%s%s' % (O[k]['glyph'], rk(v)) for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]))
			draw_text(s, 'r%d  %s' % (pr.rank, ops), x + 40, y + 22, 11, INK_DIM)
			c = pr.stats(pl)
			draw_text(s, '%.0f x%d' % (c['dmg'], c['count']), x + LW - 26, y + 6, 11, INK_FAINT, False, 'tr')
			draw_text(s, '%.2fs' % c['cd'], x + LW - 26, y + 22, 11, INK_FAINT, False, 'tr')
			y += 46
		y += 6
		pygame.draw.line(s, (26, 32, 46), (x, y), (x + LW - 20, y))
		y += 8
		rows = [('damage', '%d%%' % int(pl.dmg_mult * 100)), ('cooldown', '%d%%' % int(pl.cd_mult * 100)),
		        ('area', '%d%%' % int(pl.area_mult * 100)), ('proj speed', '%d%%' % int(pl.pspeed_mult * 100)),
		        ('amount', '+%d' % pl.amount), ('crit', '%d%% x%.1f' % (int(pl.crit_c * 100), 2.0 + pl.crit_m)),
		        ('move', '%d%%' % int(pl.move_mult * 100)), ('armor / dodge', '%d / %d%%' % (int(pl.armor), int(pl.dodge * 100))),
		        ('regen', '%.1f/s' % pl.regen), ('luck', '%d%%' % int(pl.luck * 100))]
		for k, v in rows:
			if y > H - 80: break
			draw_text(s, k, x, y, 11, INK_FAINT)
			draw_text(s, v, x + LW - 26, y, 11, INK, True, 'tr')
			y += 15

		# ---- right: tabs and cards
		rx = 26 + LW + 14
		rw = W - rx - 26
		ty = 96
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

		gh = H - ty - 156
		self._cards(s, w, rx, ty, rw, gh)
		self._detail(s, w, rx, H - 150, rw)

		draw_text(s, 'click install   right-click remove / elite   shift+click x3   '
		             '1-5 tabs   TAB or ESC back to the fight',
		          CX, H - 26, 12, INK_FAINT, False, 'tc')

	# ------------------------------------------------------------------- cards
	def _cards(self, s, w, x0, y0, ww, hh):
		pr = self.target()
		ww -= 12                                  # room for the scrollbar
		cols = max(2, int(ww / 232))
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
			draw_text(s, trim(title, int((cw - 60) / 7.4)), r.x + 50, r.y + 9, 13, INK, True)
			draw_text(s, trim(sub, int((cw - 60) / 6.2)), r.x + 50, r.y + 28, 11, shade(col, 0.9))
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
	def _detail(self, s, w, x, y, ww):
		if not self.cards: return
		i = clamp(self.sel, 0, len(self.cards) - 1)
		r_, kind, key, col, glyph, title, sub = self.cards[i]
		panel(s, (x, y, ww, 126), 210, shade(col, 0.6))
		draw_text(s, title, x + 16, y + 10, 17, col, True)
		desc = ''
		art = None
		if kind == 'emit':
			em = E[key]; desc = em['desc'] + '   affinity: ' + ', '.join(em['affinity'])
			art = ('new', key)
		elif kind == 'op':
			desc = O[key]['desc']
			art = ('op', key)
		elif kind == 'passive':
			desc = PASSIVE_BY_ID[key]['desc']
			art = ('passive', key)
		elif kind == 'evo':
			ev = key
			need = '  '.join('%s %d' % (O[k]['name'], v) for k, v in ev['req'].items())
			desc = ev['desc'] + '     requires: ' + need
			art = ('new', ev['emit'])
		elif kind in ('foe', 'boss'):
			d = A[key] if kind == 'foe' else B[key]
			desc = 'ai %s   hp %d   speed %d' % (d.get('ai', 'chase'), d['hp'], d['spd']) if kind == 'foe' \
			       else d['title'] + '   attacks: ' + ', '.join(d['atks'])
		for j, line in enumerate(wrap(desc, 13, ww - 210)[:3]):
			draw_text(s, line, x + 16, y + 36 + j * 18, 13, INK_DIM)
		if art:
			draw_art(s, (x + ww - 190, y + 14, 176, 96), art[0], art[1], col, self.t)
