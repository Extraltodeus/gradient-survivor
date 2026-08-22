"""HUD, level-up cards, pause inspector, codex, menus and end screens."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.weapons import (E, O, SYN, EVO_BY_EMIT, EMIT_ORDER, PASSIVE_BY_ID,
                          MAX_OPS_PER_PROC, ghost_process)

ROMAN = ('', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII')
GRACE = 0.6     # input lock when the level-up screen opens, anti-misclick

CONTROLS = (
	('WASD / arrows', 'move'),
	('hold LMB', 'move toward cursor'),
	('SPACE / RMB', 'dash or blink'),
	('ESC or P', 'pause / this screen'),
	('1-5 or click', 'pick an upgrade'),
	('R / X / ESC', 'reroll / banish / skip'),
	('T', 'the evolution tree'),
	('TAB (sandbox)', 'open the bench'),
	('F11 or Alt+Enter', 'fullscreen'),
	('F5', 'mouse mode: pointer or drag'),
	('F2 / F4', 'bloom / scanlines'),
	('F6', 'screenshake: full / light / off'),
	('F3', 'fps counter'),
	('M', 'mute'),
	('Q', 'quit to menu'),
)


def rk(n): return ROMAN[n] if n < len(ROMAN) else str(n)


def trim(s, n):
	return s if len(s) <= n else s[:n - 2] + '..'


def fit(dst, txt, x, y, size, col, bold, width, anchor='tl', floor=9):
	"""Shrink to fit rather than cut. Names in this game carry their whole build;
	an ellipsis in the middle of one throws away the part that was earned."""
	while size > floor and text_w(txt, size, bold) > width:
		size -= 1
	return draw_text(dst, txt, x, y, size, col, bold, anchor)


def pips(s, x, y, cur, mx, col, size=7, gap=4):
	for i in range(mx):
		c = col if i < cur else (34, 40, 56)
		pygame.draw.rect(s, c, (x + i * (size + gap), y, size, size), 0, 2)
		if i == cur - 1:
			pygame.draw.rect(s, WHITE, (x + i * (size + gap), y, size, size), 1, 2)


# ============================================================ EFFECT ART
def _dot(s, x, y, r, col, glowp=0.8):
	blit_glow(s, x, y, r * 2.6, col, glowp)
	pygame.draw.circle(s, WHITE, (int(x), int(y)), max(1, int(r * 0.55)))


def _foe(s, x, y, col=(150, 160, 190), r=7, dead=False):
	g = ngon(4 if not dead else 3, r, col if not dead else shade(col, 0.4), 0 if not dead else 1)
	s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))


def _arrow(s, x0, y0, x1, y1, col, wid=2, head=6):
	pygame.draw.line(s, col, (x0, y0), (x1, y1), wid)
	a = math.atan2(y1 - y0, x1 - x0)
	pygame.draw.polygon(s, col, [(x1, y1),
	                             (x1 - math.cos(a - 0.5) * head, y1 - math.sin(a - 0.5) * head),
	                             (x1 - math.cos(a + 0.5) * head, y1 - math.sin(a + 0.5) * head)])


def draw_art(s, rect, kind, key, col, t):
	"""A small animated diagram of what the upgrade actually does."""
	x, y, w_, h_ = rect
	cx = x + w_ * 0.5; cy = y + h_ * 0.5
	pygame.draw.rect(s, (9, 11, 18), rect, 0, 6)
	pygame.draw.rect(s, (28, 34, 48), rect, 1, 6)
	old = s.get_clip()
	s.set_clip(pygame.Rect(rect))
	ph = (t * 0.8) % 1.0            # 0..1 loop driving every animation
	L = x + 20; R = x + w_ - 20

	if kind == 'passive':
		_passive_art(s, rect, key, col, t, ph)
		s.set_clip(old); return
	if kind in ('new', 'rank', 'fuse', 'heal'):
		_emit_art(s, rect, key, col, t, ph)
		s.set_clip(old); return

	k = key
	if k == 'pierce':
		for i in range(3):
			_foe(s, x + 62 + i * 42, cy, (150, 160, 190), 8, ph > (0.2 + i * 0.22))
		px = L + (R - L) * ph
		_arrow(s, L, cy, px, cy, col, 3, 8)
		_dot(s, px, cy, 4, col)
	elif k == 'blast':
		_dot(s, cx, cy, 4, col, 1.0)
		r = 8 + ph * 34
		pygame.draw.circle(s, shade(col, 1.0 - ph), (int(cx), int(cy)), int(r), 2)
		pygame.draw.circle(s, shade(col, (1.0 - ph) * 0.5), (int(cx), int(cy)), int(r * 0.6), 1)
		for i in range(8):
			a = i * TAU / 8 + t
			d = 10 + ph * 30
			blit_glow(s, cx + math.cos(a) * d, cy + math.sin(a) * d, 7, col, (1.0 - ph) * 0.9)
		for i in (-1, 1):
			_foe(s, cx + i * 44, cy - 10, (150, 160, 190), 7, ph > 0.5)
	elif k == 'split':
		mx = cx - 14
		_arrow(s, L, cy, mx, cy, col, 3, 7)
		for i in (-1, 0, 1):
			ex = mx + 20 + ph * 28
			ey = cy + i * (10 + ph * 22)
			pygame.draw.line(s, shade(col, 1.0 - ph * 0.4), (mx, cy), (ex, ey), 2)
			_dot(s, ex, ey, 3, col, 0.8)
	elif k == 'chain':
		pts = [(L, cy + 12), (cx - 16, cy - 14), (cx + 20, cy + 10), (R, cy - 8)]
		n = int(ph * 3) + 1
		for i in range(min(n, 3)):
			a, b = pts[i], pts[i + 1]
			mid = ((a[0] + b[0]) * 0.5 + math.sin(t * 9 + i) * 5, (a[1] + b[1]) * 0.5 - 7)
			pygame.draw.lines(s, col, False, [a, mid, b], 2)
			pygame.draw.lines(s, WHITE, False, [a, mid, b], 1)
		for i, p in enumerate(pts[1:]):
			_foe(s, p[0], p[1], (150, 160, 190), 7, i < n - 1)
		_dot(s, pts[0][0], pts[0][1], 4, col)
	elif k == 'homing':
		tx = R - 8; ty = cy - 12
		a0 = math.pi * 0.9
		pp = []
		for i in range(15):
			f = i / 14.0
			px = L + (tx - L) * f
			py = cy + 22 * math.sin(a0 * f) * (1.0 - f)
			pp.append((px, py))
		pygame.draw.lines(s, shade(col, 0.45), False, pp, 2)
		i = int(ph * 14)
		_dot(s, pp[i][0], pp[i][1], 4, col)
		_foe(s, tx, ty, (150, 160, 190), 8)
		g = ring(13 + int(ph * 4), col, 1, int(200 * (1 - ph)))
		s.blit(g, (tx - g.get_width() * 0.5, ty - g.get_height() * 0.5), None, pygame.BLEND_ADD)
	elif k == 'bounce':
		pygame.draw.line(s, (46, 54, 74), (L - 6, y + 10), (R + 6, y + 10), 2)
		pygame.draw.line(s, (46, 54, 74), (L - 6, y + h_ - 10), (R + 6, y + h_ - 10), 2)
		pts = [(L, cy), (cx - 20, y + 14), (cx + 12, y + h_ - 14), (R, cy - 6)]
		pygame.draw.lines(s, shade(col, 0.5), False, pts, 2)
		i = ph * 3
		seg = min(2, int(i)); f = i - seg
		a, b = pts[seg], pts[seg + 1]
		_dot(s, a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, 4, col)
	elif k == 'orbitize':
		for i in range(26):
			f = i / 25.0
			a = f * 7.0 + t
			r = 4 + f * 30
			pygame.draw.circle(s, shade(col, 0.25 + 0.75 * f), (int(cx + math.cos(a) * r), int(cy + math.sin(a) * r)), 2)
		a = 7.0 * ph + t
		_dot(s, cx + math.cos(a) * (4 + ph * 30), cy + math.sin(a) * (4 + ph * 30), 4, col)
	elif k == 'multishot':
		for i in (-1, 0, 1):
			ex = L + (R - L) * (0.35 + ph * 0.65)
			_arrow(s, L, cy, ex, cy + i * 18 * (0.4 + ph), shade(col, 1.0 - abs(i) * 0.2), 2, 6)
	elif k == 'recursion':
		_foe(s, x + 40, cy, (150, 160, 190), 9, ph > 0.3)
		if ph > 0.3:
			f = (ph - 0.3) / 0.7
			_dot(s, x + 40 + f * 60, cy - math.sin(f * math.pi) * 18, 4, col)
			_foe(s, x + 40 + 70, cy, (150, 160, 190), 8, ph > 0.85)
		draw_text(s, 'kill', x + 26, cy + 16, 10, INK_FAINT)
		draw_text(s, 'again', x + 84, cy + 16, 10, shade(col, 0.9))
	elif k == 'echo':
		for i, off in enumerate((0, 26)):
			al = 1.0 if i == 0 else max(0.0, 1.0 - abs(ph - 0.45) * 2.2)
			if al <= 0.02: continue
			_arrow(s, L + off, cy + i * 14, L + off + 44, cy + i * 14, shade(col, al), 2, 6)
			_dot(s, L + off + 48, cy + i * 14, 3, col, al)
		draw_text(s, 'x2', R - 22, cy - 8, 14, col, True)
	elif k == 'giant':
		pygame.draw.circle(s, shade(col, 0.35), (int(cx - 34), int(cy)), 5)
		_arrow(s, cx - 22, cy, cx + 2, cy, INK_FAINT, 1, 5)
		r = 12 + ph * 6
		blit_glow(s, cx + 30, cy, r * 2.4, col, 0.9)
		pygame.draw.circle(s, col, (int(cx + 30), int(cy)), int(r), 2)
	elif k == 'swift':
		for i in range(4):
			yy = cy - 18 + i * 12
			off = ((ph + i * 0.17) % 1.0) * (R - L)
			pygame.draw.line(s, shade(col, 0.3 + 0.5 * (i % 2)), (L + off - 26, yy), (L + off, yy), 2)
		_dot(s, L + ((ph) % 1.0) * (R - L), cy, 4, col)
	elif k == 'crit':
		_foe(s, cx, cy, (150, 160, 190), 9, ph > 0.4)
		if ph > 0.4:
			f = (ph - 0.4) / 0.6
			for i in range(10):
				a = i * TAU / 10
				d = 12 + f * 26
				pygame.draw.line(s, shade(GOLD, 1.0 - f), (cx + math.cos(a) * 10, cy + math.sin(a) * 10),
				                 (cx + math.cos(a) * d, cy + math.sin(a) * d), 2)
			g = text('CRIT', 15, GOLD, True)
			g.set_alpha(int(255 * (1 - f)))
			s.blit(g, (cx - g.get_width() * 0.5, cy - 34 - f * 10))
	elif k == 'momentum':
		for i in range(9):
			f = i / 8.0
			px = L + (R - L) * f
			blit_glow(s, px, cy, 4 + f * 12, col, 0.25 + 0.7 * f)
		_dot(s, L + (R - L) * ph, cy, 3 + ph * 5, col)
		draw_text(s, 'far = harder', cx, cy + 22, 10, INK_FAINT, False, 'tc')
	elif k == 'overclock':
		bw = R - L
		f = min(1.0, ph * 1.4)
		pygame.draw.rect(s, (28, 20, 22), (L, cy - 7, bw, 14), 0, 4)
		pygame.draw.rect(s, mix(col, YELLOW, f), (L, cy - 7, int(bw * f), 14), 0, 4)
		pygame.draw.rect(s, shade(col, 0.7), (L, cy - 7, bw, 14), 1, 4)
		draw_text(s, 'HEAT', L, cy - 26, 10, INK_FAINT)
		draw_text(s, '+%d%% dmg' % int(f * 40), R, cy - 26, 10, col, True, 'tr')
	elif k == 'feedback':
		r = 22
		pygame.draw.arc(s, col, pygame.Rect(int(cx - r), int(cy - r), r * 2, r * 2), 0.4, 5.4, 3)
		a = 5.4
		_arrow(s, cx + math.cos(a) * r, cy + math.sin(a) * r,
		       cx + math.cos(a + 0.4) * r, cy + math.sin(a + 0.4) * r, col, 2, 7)
		_foe(s, cx, cy, (150, 160, 190), 8, ph > 0.5)
		draw_text(s, 'kill = faster', cx, cy + 26, 10, INK_FAINT, False, 'tc')
	elif k == 'burn':
		_foe(s, cx, cy + 16, (150, 160, 190), 11, ph > 0.75)
		for i in range(11):
			f = ((ph + i * 0.09) % 1.0)
			fx_ = cx + math.sin(t * 3 + i * 2) * 16
			blit_glow(s, fx_, cy + 16 - f * 52, 13 * (1 - f * 0.55),
			          mix((255, 200, 70), (255, 50, 15), f), 1.0 - f * 0.85)
	elif k == 'frost':
		_foe(s, cx, cy - 4, mix((150, 160, 190), col, 0.6), 12)
		for i in range(6):
			a = i * TAU / 6 + t * 0.3
			pygame.draw.line(s, shade(col, 0.5 + 0.5 * math.sin(t * 2 + i)),
			                 (cx, cy - 4), (cx + math.cos(a) * 36, cy - 4 + math.sin(a) * 32), 2)
			pygame.draw.line(s, col, (cx + math.cos(a) * 24, cy - 4 + math.sin(a) * 21),
			                 (cx + math.cos(a) * 36, cy - 4 + math.sin(a) * 32), 2)
		draw_text(s, 'slow + brittle', cx, cy + 26, 10, INK_FAINT, False, 'tc')
	elif k == 'shock':
		pts = [(cx - 26, cy - 32), (cx + 2, cy - 8), (cx - 12, cy - 2), (cx + 20, cy + 30)]
		wd = 5 if ph > 0.5 else 3
		pygame.draw.lines(s, col, False, pts, wd)
		pygame.draw.lines(s, WHITE, False, pts, 2)
		if ph > 0.5: blit_glow(s, cx, cy, 46, col, 0.8)
		_foe(s, cx + 44, cy + 4, (150, 160, 190), 10)
		draw_text(s, 'stun', cx + 30, cy - 30, 12, col, True)
	elif k == 'corrupt':
		_foe(s, cx, cy, mix((150, 160, 190), VIOLET, ph), 13, ph > 0.6)
		if ph > 0.6:
			f = (ph - 0.6) / 0.4
			for i in range(8):
				a = i * TAU / 8 + t
				_dot(s, cx + math.cos(a) * f * 52, cy + math.sin(a) * f * 40, 4.5, VIOLET, 1 - f * 0.8)
	elif k == 'void':
		for i in range(8):
			a = i * TAU / 8 + t * 0.5
			d0 = 40 - ph * 26
			_arrow(s, cx + math.cos(a) * (d0 + 8), cy + math.sin(a) * (d0 + 8),
			       cx + math.cos(a) * d0, cy + math.sin(a) * d0, shade(col, 0.9), 2, 5)
		blit_glow(s, cx, cy, 22, col, 1.0)
		pygame.draw.circle(s, (6, 6, 12), (int(cx), int(cy)), 7)
		pygame.draw.circle(s, col, (int(cx), int(cy)), 7, 1)
	elif k == 'drain':
		_foe(s, x + 34, cy, (150, 160, 190), 9)
		f = ph
		_dot(s, x + 34 + (w_ - 68) * f, cy - math.sin(f * math.pi) * 16, 4, HP_COL)
		g = text('+', 20, HP_COL, True)
		s.blit(g, (R - 12 - g.get_width() * 0.5, cy - g.get_height() * 0.5))
		blit_glow(s, R - 12, cy, 20, HP_COL, 0.5 + 0.5 * ph)
	else:
		g = text(O[k]['glyph'] if k in O else '?', 34, col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))
	s.set_clip(old)


def _passive_art(s, rect, key, col, t, ph):
	x, y, w_, h_ = rect
	cx = x + w_ * 0.5; cy = y + h_ * 0.5
	if key in ('power', 'crit'):
		_foe(s, cx + 26, cy, (150, 160, 190), 9, ph > 0.5)
		_arrow(s, cx - 40, cy, cx + 12, cy, col, 3, 8)
		draw_text(s, '+', cx - 52, cy - 10, 20, col, True)
	elif key in ('haste', 'speed', 'vel'):
		for i in range(4):
			off = ((ph + i * 0.2) % 1.0) * (w_ - 40)
			pygame.draw.line(s, shade(col, 0.3 + 0.6 * (i % 2)),
			                 (x + 20 + off - 24, cy - 18 + i * 12), (x + 20 + off, cy - 18 + i * 12), 2)
	elif key == 'area':
		for i in range(3):
			r = 12 + i * 12 + ph * 5
			pygame.draw.circle(s, shade(col, 0.9 - i * 0.25), (int(cx), int(cy)), int(r), 1)
		blit_glow(s, cx, cy, 16, col, 0.8)
	elif key in ('hp', 'regen', 'armor'):
		g = text('+' if key != 'armor' else '=', 30, HP_COL if key != 'armor' else col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))
		blit_glow(s, cx, cy, 26 + ph * 6, HP_COL if key != 'armor' else col, 0.6)
	elif key == 'magnet':
		for i in range(7):
			a = i * TAU / 7 + t
			d = 34 - ph * 24
			_dot(s, cx + math.cos(a) * d, cy + math.sin(a) * d, 3, XP_COL, 0.9)
		blit_glow(s, cx, cy, 22, CYAN, 0.9)
	elif key == 'xp':
		for i in range(4):
			f = (ph + i * 0.25) % 1.0
			_dot(s, x + 30 + i * 30, cy + 20 - f * 40, 4, XP_COL, 1.0 - f * 0.6)
	elif key == 'amount':
		for i in (-1, 0, 1):
			_arrow(s, x + 24, cy, x + w_ - 30, cy + i * 16, col, 2, 6)
	elif key == 'slot':
		for i in range(3):
			c = col if i < 2 else shade(col, 0.35)
			pygame.draw.rect(s, c, (cx - 46 + i * 32, cy - 12, 24, 24), 2, 4)
		draw_text(s, '+1', cx + 34, cy - 9, 16, col, True)
	elif key in ('luck', 'xp', 'reroll'):
		for i in range(7):
			f = (ph + i * 0.14) % 1.0
			xx = x + 20 + (w_ - 40) * ((i * 0.37) % 1.0)
			_dot(s, xx, y + 8 + f * (h_ - 20), 3.5, mix(col, GOLD, f), 1.0 - f * 0.5)
		blit_glow(s, cx, cy, 24, col, 0.5)
		g = text(PASSIVE_BY_ID[key]['glyph'], 22, col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))
	elif key == 'dodge':
		for i in range(3):
			al = 1.0 - i * 0.3
			pygame.draw.polygon(s, shade(CYAN, al * (0.3 + 0.7 * ph)),
			                    [(cx - 30 + i * 22, cy - 10), (cx - 18 + i * 22, cy), (cx - 30 + i * 22, cy + 10)], 1)
		draw_text(s, 'phase', cx + 22, cy - 8, 12, CYAN, True)
	else:
		g = text(PASSIVE_BY_ID[key]['glyph'] if key in PASSIVE_BY_ID else '?', 32, col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))
		blit_glow(s, cx, cy, 24, col, 0.5)


def _emit_art(s, rect, key, col, t, ph):
	"""Emitter cards run the real scene; the old diagram stays for odd keys."""
	from game.weapons import E
	if key in E:
		_weapon_scene(s, rect, key, col, t)
		return
	x, y, w_, h_ = rect
	cx = x + w_ * 0.5; cy = y + h_ * 0.5
	P = (cx - 44, cy)
	pygame.draw.polygon(s, CYAN, [(P[0] + 9, P[1]), (P[0] - 5, P[1] - 7), (P[0] - 2, P[1]), (P[0] - 5, P[1] + 7)])
	if key == 'bolt':
		_arrow(s, P[0] + 14, cy, P[0] + 20 + ph * 60, cy, col, 3, 8)
	elif key == 'swarm':
		for i in range(4):
			f = (ph + i * 0.25) % 1.0
			_dot(s, P[0] + 20 + f * 62, cy + math.sin(f * 6 + i * 2) * 16, 3.5, col)
	elif key == 'orbit':
		for i in range(3):
			a = t * 1.6 + i * TAU / 3
			_dot(s, P[0] + math.cos(a) * 34, cy + math.sin(a) * 26, 5, col)
		pygame.draw.ellipse(s, shade(col, 0.3), pygame.Rect(int(P[0] - 34), int(cy - 26), 68, 52), 1)
	elif key == 'aura':
		for i in range(3):
			r = 14 + i * 11 + ph * 4
			pygame.draw.circle(s, shade(col, 0.8 - i * 0.22), (int(P[0]), int(cy)), int(r), 1)
	elif key == 'nova':
		r = 6 + ph * 46
		pygame.draw.circle(s, shade(col, 1.0 - ph), (int(P[0]), int(cy)), int(r), 3)
		pygame.draw.circle(s, shade(WHITE, (1.0 - ph) * 0.7), (int(P[0]), int(cy)), int(r), 1)
	elif key == 'beam':
		a = t * 1.1
		ex = P[0] + math.cos(a) * 74; ey = cy + math.sin(a) * 30
		pygame.draw.line(s, shade(col, 0.5), (P[0], cy), (ex, ey), 6)
		pygame.draw.line(s, WHITE, (P[0], cy), (ex, ey), 2)
	elif key == 'mine':
		for i in range(3):
			mx = P[0] + 24 + i * 26; my = cy + math.sin(i * 2.1) * 14
			pulse = 0.5 + 0.5 * math.sin(t * 6 + i)
			blit_glow(s, mx, my, 12 * pulse, col, 0.9)
			pygame.draw.circle(s, col, (int(mx), int(my)), 7, 2)
	elif key == 'arc':
		pts = [(P[0] + 12, cy), (P[0] + 34, cy - 16), (P[0] + 52, cy + 8), (P[0] + 78, cy - 10)]
		pygame.draw.lines(s, col, False, pts, 2)
		pygame.draw.lines(s, WHITE, False, pts, 1)
	elif key == 'turret':
		for i in (-1, 1):
			tx = P[0] + 40; ty = cy + i * 20
			g = ngon(4, 8, col, 2, t * 1.4)
			s.blit(g, (tx - g.get_width() * 0.5, ty - g.get_height() * 0.5))
			_dot(s, tx + 10 + ph * 30, ty, 3, col)
	elif key == 'blade':
		f = math.sin(ph * math.pi)
		bx = P[0] + 16 + f * 62
		g = ngon(3, 11, col, 0, t * 6)
		s.blit(g, (bx - g.get_width() * 0.5, cy - g.get_height() * 0.5), None, pygame.BLEND_ADD)
		pygame.draw.arc(s, shade(col, 0.4), pygame.Rect(int(P[0] + 10), int(cy - 26), 76, 52), 0.2, 3.0, 1)
	elif key == 'spiral':
		for i in range(5):
			a = t * 1.4 + i * TAU / 5
			r = 10 + ((ph + i * 0.2) % 1.0) * 36
			_dot(s, P[0] + math.cos(a + r * 0.06) * r, cy + math.sin(a + r * 0.06) * r * 0.75, 3.5, col)
	elif key == 'rain':
		for i in range(4):
			f = (ph + i * 0.25) % 1.0
			rx = P[0] + 22 + i * 22
			if f < 0.7:
				pygame.draw.line(s, col, (rx, y + 6 + f * 40), (rx, y + 16 + f * 40), 3)
			else:
				rr = (f - 0.7) / 0.3
				pygame.draw.circle(s, shade(col, 1 - rr), (int(rx), int(y + 46)), int(4 + rr * 16), 2)
	else:
		g = text('+', 30, col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))


# ========================================================== WEAPON SCENES
# A card must not be a label with a decoration on it: it has to RUN the weapon.
# Every scene below takes the real stats of the process being offered (count,
# cadence, size) plus its real op set, so two evolutions of one emitter can never
# come out looking like the same animation in a different tint.
_FOE_DIR = ((0.50, 0.20), (0.68, 0.50), (0.48, 0.80), (0.86, 0.32), (0.84, 0.72))


def _scene_box(s, rect):
	x, y, w_, h_ = rect
	pygame.draw.rect(s, (8, 10, 17), rect, 0, 6)
	for gx in range(int(x) + 18, int(x + w_) - 4, 26):
		pygame.draw.line(s, (16, 20, 30), (gx, y + 3), (gx, y + h_ - 3))
	for gy in range(int(y) + 16, int(y + h_) - 4, 26):
		pygame.draw.line(s, (16, 20, 30), (x + 3, gy), (x + w_ - 3, gy))
	pygame.draw.rect(s, (30, 36, 52), rect, 1, 6)


def _agent(s, ax, ay, t, shape='dart', col=CYAN):
	blit_glow(s, ax, ay, 16, col, 0.5)
	agent_shape(s, ax, ay, math.sin(t * 1.7) * 0.3, shape, col, 8.0, t)


def _curve(ax, ay, tx, ty, f, ops, t, i):
	"""Where a projectile is at 0..1 along its flight, bent by whatever ops the
	process is carrying. This is why HOMING and BOUNCE and SPIN read differently
	on the card instead of all being a straight line."""
	x = ax + (tx - ax) * f
	y = ay + (ty - ay) * f
	dx = tx - ax; dy = ty - ay
	L = math.hypot(dx, dy) or 1.0
	nx = -dy / L; ny = dx / L
	off = 0.0
	if ops.get('homing'):
		off += math.sin(f * math.pi) * 30.0 * (1.0 - f) * (1 if i % 2 == 0 else -1)
	if ops.get('bounce'):
		off += (1.0 - abs((f * 3.0 % 1.0) * 2.0 - 1.0)) * 22.0 * (1 if int(f * 3) % 2 == 0 else -1)
	if ops.get('orbitize'):
		off += math.sin(f * 9.0 + t * 3.0 + i) * 16.0 * f
	return x + nx * off, y + ny * off


def _weapon_scene(s, rect, emit, col, t, ops=None, st=None, shape='dart', pcol=CYAN):
	from game.weapons import E
	em = E.get(emit)
	x, y, w_, h_ = rect
	_scene_box(s, rect)
	if em is None: return
	ops = dict(ops or {})
	cd = st['cd'] if st else em['cd']
	n = int(st['count']) if st else int(em['count'])
	n = max(1, min(8, n))
	base_sz = em['size'] or 1.0
	szf = clamp((st['size'] / base_sz) if st else 1.0, 0.55, 2.2)
	cx = x + w_ * 0.5; cy = y + h_ * 0.5
	period = clamp(cd * 1.25, 0.34, 2.1)
	ph = (t % period) / period
	radial = emit in ('orbit', 'aura', 'nova', 'spiral', 'beam', 'turret', 'rain')
	ax = cx if radial else x + w_ * 0.16
	ay = cy
	rx = w_ * 0.32; ry = h_ * 0.32
	foes = []
	if radial:
		for i in range(5):
			a = i * TAU / 5 - 0.5
			foes.append([cx + math.cos(a) * rx, cy + math.sin(a) * ry, False])
	else:
		for fx_, fy_ in _FOE_DIR:
			foes.append([x + w_ * fx_ + w_ * 0.08, y + h_ * fy_, False])
	pierce = ops.get('pierce', 0) + (3 if emit == 'flame' else (2 if emit == 'blade' else 0))
	old = s.get_clip()
	s.set_clip(pygame.Rect(int(x) + 1, int(y) + 1, int(w_) - 2, int(h_) - 2))

	if emit == 'bolt':
		for i in range(n):
			f = (ph + i / float(n)) % 1.0
			tx = x + w_ - 8; ty = cy + (i - (n - 1) * 0.5) * 13
			px, py = _curve(ax, ay, tx, ty, f, ops, t, i)
			pygame.draw.line(s, shade(col, 0.4), (px - 15, py), (px, py), max(2, int(3 * szf)))
			_dot(s, px, py, 4 * szf, col)
			for q in foes:
				if abs(q[1] - py) < 16 and q[0] < px and (pierce or not q[2]): q[2] = True
	elif emit == 'flame':
		# a cone, not a volley: the damage is in the overlap
		reach = w_ * 0.62 * (1.0 + 0.12 * ops.get('giant', 0))
		cone = 0.52 + 0.09 * ops.get('multishot', 0)
		for i in range(n * 3):
			f = ((t * 2.4 + i * 0.11) % 1.0)
			a = (i * 2.399) % (cone * 2) - cone
			d = f * reach
			px = ax + math.cos(a) * d; py = ay + math.sin(a) * d * 0.8
			r = (3.0 + f * 9.0) * szf
			blit_glow(s, px, py, r * 2.2, mix((255, 220, 120), col, min(1.0, f * 1.4)), 0.9 - f * 0.45)
		for q in foes:
			d = math.hypot(q[0] - ax, q[1] - ay)
			a = math.atan2(q[1] - ay, q[0] - ax)
			if d < reach and abs(a) < cone: q[2] = True
	elif emit == 'swarm':
		for i in range(n):
			f = (ph + i / float(n)) % 1.0
			tgt = foes[i % len(foes)]
			px, py = _curve(ax, ay, tgt[0], tgt[1], f, ops, t, i)
			if not ops.get('homing'):
				py += math.sin(f * 7 + i * 2) * 12 * (1 - f)
			_dot(s, px, py, 3 * szf, col, 0.9)
			if f > 0.88: tgt[2] = True
	elif emit == 'orbit':
		pygame.draw.ellipse(s, shade(col, 0.22), pygame.Rect(int(ax - rx), int(ay - ry),
		                                                     int(rx * 2), int(ry * 2)), 1)
		for i in range(n):
			a = t * 2.0 + i * TAU / n
			px = ax + math.cos(a) * rx; py = ay + math.sin(a) * ry
			blit_glow(s, px, py, 12 * szf, col, 0.85)
			pygame.draw.circle(s, WHITE, (int(px), int(py)), max(2, int(3 * szf)))
			for q in foes:
				if abs(q[0] - px) < 15 * szf and abs(q[1] - py) < 15 * szf: q[2] = True
	elif emit == 'aura':
		r = min(rx, ry) * (1.2 + 0.10 * math.sin(t * 3.4)) * szf
		g = hollow_glow(int(r), col, 0.55)
		s.blit(g, (ax - g.get_width() * 0.5, ay - g.get_height() * 0.5), None, pygame.BLEND_ADD)
		pygame.draw.circle(s, shade(col, 0.9), (int(ax), int(ay)), int(r), 2)
		for q in foes:
			if math.hypot(q[0] - ax, q[1] - ay) < r: q[2] = True
	elif emit == 'nova':
		for k in range(max(1, n // 2)):
			pk = (ph + k * 0.18) % 1.0
			r = pk * max(rx, ry) * 1.6 * szf
			pygame.draw.circle(s, shade(col, 1.0 - pk), (int(ax), int(ay)), int(r) + 1, 3)
			pygame.draw.circle(s, shade(WHITE, (1.0 - pk) * 0.8), (int(ax), int(ay)), int(r) + 1, 1)
			for q in foes:
				if math.hypot(q[0] - ax, q[1] - ay) < r: q[2] = True
	elif emit == 'beam':
		nb = max(1, min(4, n // 2))
		L = max(rx, ry) * 1.7 * szf
		for k in range(nb):
			a = t * 1.3 + k * TAU / nb
			ex = ax + math.cos(a) * L; ey = ay + math.sin(a) * L
			pygame.draw.line(s, shade(col, 0.45), (ax, ay), (ex, ey), int(7 * szf))
			pygame.draw.line(s, col, (ax, ay), (ex, ey), int(3 * szf))
			pygame.draw.line(s, WHITE, (ax, ay), (ex, ey), 1)
			for q in foes:
				d = abs(math.atan2(q[1] - ay, q[0] - ax) - a % TAU)
				if min(d % TAU, TAU - (d % TAU)) < 0.35: q[2] = True
	elif emit == 'mine':
		for i in range(n + 1):
			f = (ph + i * 0.3) % 1.0
			mx = ax + 22 + i * (w_ * 0.19); my = cy + math.sin(i * 2.2) * h_ * 0.22
			if mx > x + w_ - 10: continue
			if f < 0.72:
				pulse = 0.4 + 0.6 * abs(math.sin(t * 7 + i))
				blit_glow(s, mx, my, 11 * pulse * szf, col, 0.9)
				pygame.draw.circle(s, col, (int(mx), int(my)), int(6 * szf), 2)
			else:
				rr = (f - 0.72) / 0.28
				pygame.draw.circle(s, shade(col, 1 - rr), (int(mx), int(my)), int((6 + rr * 20) * szf), 2)
				for q in foes:
					if math.hypot(q[0] - mx, q[1] - my) < (6 + rr * 20) * szf: q[2] = True
	elif emit == 'arc':
		jumps = 2 + ops.get('chain', 0)
		order = sorted(foes, key=lambda q: math.hypot(q[0] - ax, q[1] - ay))[:jumps + 1]
		reach = int(ph * (jumps + 1)) + 1
		prev = (ax, ay)
		for i, q in enumerate(order[:reach]):
			mid = ((prev[0] + q[0]) * 0.5 + math.sin(t * 11 + i) * 7,
			       (prev[1] + q[1]) * 0.5 - 8)
			pygame.draw.lines(s, col, False, [prev, mid, (q[0], q[1])], 2)
			pygame.draw.lines(s, WHITE, False, [prev, mid, (q[0], q[1])], 1)
			q[2] = True
			prev = (q[0], q[1])
	elif emit == 'turret':
		nt = max(2, min(4, n))
		for k in range(nt):
			a = k * TAU / nt + 0.6
			tx = ax + math.cos(a) * w_ * 0.17; ty = ay + math.sin(a) * h_ * 0.24
			g = ngon(4, int(8 * szf), col, 2, t * 1.6)
			s.blit(g, (tx - g.get_width() * 0.5, ty - g.get_height() * 0.5))
			blit_glow(s, tx, ty, 12, col, 0.6)
			q = foes[k % len(foes)]
			f = (ph + k * 0.31) % 1.0
			px, py = _curve(tx, ty, q[0], q[1], f, ops, t, k)
			_dot(s, px, py, 3 * szf, col, 0.9)
			if f > 0.85: q[2] = True
	elif emit == 'blade':
		for i in range(min(4, n)):
			pk = (ph + i / float(min(4, n))) % 1.0
			f = math.sin(pk * math.pi)
			bx = ax + 16 + f * (w_ * 0.64)
			by = cy - math.sin(pk * TAU) * h_ * 0.16 + (i - (n - 1) * 0.5) * 9
			g = ngon(3, int(12 * szf), col, 0, t * 7 + i)
			s.blit(g, (bx - g.get_width() * 0.5, by - g.get_height() * 0.5), None, pygame.BLEND_ADD)
			for q in foes:
				if math.hypot(q[0] - bx, q[1] - by) < 20 * szf: q[2] = True
		pygame.draw.arc(s, shade(col, 0.35), pygame.Rect(int(ax + 8), int(cy - h_ * 0.34),
		                                                 int(w_ * 0.72), int(h_ * 0.68)), 0.2, 3.0, 1)
	elif emit == 'spiral':
		for i in range(n + 2):
			f = (ph + i / (n + 2.0)) % 1.0
			a = t * 1.8 + i * TAU / (n + 2) + f * 3.4
			px = ax + math.cos(a) * rx * f * 1.6; py = ay + math.sin(a) * ry * f * 1.6
			_dot(s, px, py, 3.4 * szf, col, 0.9)
			for q in foes:
				if math.hypot(q[0] - px, q[1] - py) < 13 * szf: q[2] = True
	elif emit == 'rain':
		for i in range(n + 1):
			f = (ph + i * 0.27) % 1.0
			q = foes[i % len(foes)]
			if f < 0.62:
				sy = y + 4 + (q[1] - y - 4) * (f / 0.62)
				pygame.draw.line(s, col, (q[0], sy - 12), (q[0], sy), 3)
				pygame.draw.circle(s, shade(col, 0.5), (int(q[0]), int(q[1])), int(9 * szf), 1)
			else:
				rr = (f - 0.62) / 0.38
				pygame.draw.circle(s, shade(col, 1 - rr), (int(q[0]), int(q[1])), int((4 + rr * 18) * szf), 2)
				q[2] = True
	else:
		g = text('?', 26, col, True)
		s.blit(g, (cx - g.get_width() * 0.5, cy - g.get_height() * 0.5))

	# ---- what the ops do once something is hit
	hitpos = [q for q in foes if q[2]]
	pulse = 0.5 + 0.5 * math.sin(t * 5.0)
	for i, q in enumerate(hitpos):
		if ops.get('blast'):
			pygame.draw.circle(s, shade(ORANGE, 0.9 - 0.5 * pulse),
			                   (int(q[0]), int(q[1])), int((9 + 9 * pulse) * (1 + 0.2 * ops['blast'])), 2)
		if ops.get('split'):
			for k in range(2 + ops['split']):
				a = t * 3 + k * 2.1
				_dot(s, q[0] + math.cos(a) * 13, q[1] + math.sin(a) * 13, 2.2, col, 0.9)
		if ops.get('frost'):
			pygame.draw.circle(s, (120, 210, 255), (int(q[0]), int(q[1])), 11, 1)
			for k in range(4):
				a = k * TAU / 4 + t * 0.4
				pygame.draw.line(s, (120, 210, 255), (q[0] + math.cos(a) * 7, q[1] + math.sin(a) * 7),
				                 (q[0] + math.cos(a) * 13, q[1] + math.sin(a) * 13), 1)
		if ops.get('burn'):
			for k in range(2):
				_dot(s, q[0] + math.sin(t * 6 + k * 3) * 5, q[1] - 8 - ((t * 22 + k * 11) % 16),
				     2.0, (255, 150, 60), 0.9)
		if ops.get('void'):
			pygame.draw.circle(s, VIOLET, (int(q[0]), int(q[1])), int(15 - 7 * pulse), 1)
		if ops.get('corrupt'):
			for k in range(3):
				a = t * 2.2 + k * 2.1
				_dot(s, q[0] + math.cos(a) * (6 + 10 * pulse), q[1] + math.sin(a) * (6 + 10 * pulse),
				     2.6, VIOLET, 0.95)
		if ops.get('recursion'):
			f2 = (t * 1.6 + i * 0.4) % 1.0
			_dot(s, q[0] + math.cos(f2 * 5.0) * 18 * f2, q[1] - 16 * f2, 2.6, (180, 255, 200), 1 - f2)
		if ops.get('drain') and i == 0:
			f2 = (t * 0.9) % 1.0
			_dot(s, q[0] + (ax - q[0]) * f2, q[1] + (ay - q[1]) * f2 - math.sin(f2 * math.pi) * 14,
			     3.0, HP_COL, 1.0)
		if ops.get('shock') and i + 1 < len(hitpos):
			n2 = hitpos[i + 1]
			pygame.draw.line(s, (150, 220, 255), (q[0], q[1]), (n2[0], n2[1]), 1)
	if ops.get('chain') and emit != 'arc':
		for i in range(min(len(hitpos) - 1, ops['chain'])):
			pygame.draw.line(s, WHITE, (hitpos[i][0], hitpos[i][1]),
			                 (hitpos[i + 1][0], hitpos[i + 1][1]), 1)
	if ops.get('crit') and hitpos:
		q = hitpos[0]
		g = text('CRIT', 11, GOLD, True)
		g.set_alpha(int(120 + 135 * pulse))
		s.blit(g, (q[0] + 8, q[1] - 20))
	if ops.get('echo'):
		g = text('x2', 12, shade(col, 0.5 + 0.5 * pulse), True)
		s.blit(g, (x + 8, y + h_ - 20))
	if ops.get('overclock'):
		bw = int(w_ * 0.3)
		pygame.draw.rect(s, (30, 20, 20), (x + w_ - bw - 8, y + h_ - 12, bw, 5), 0, 2)
		pygame.draw.rect(s, RED, (x + w_ - bw - 8, y + h_ - 12, int(bw * pulse), 5), 0, 2)

	for q in foes:
		_foe(s, q[0], q[1], (150, 160, 190), 7, q[2])
		if q[2]: blit_glow(s, q[0], q[1], 11, col, 0.5)
	_agent(s, ax, ay, t, shape, pcol)
	s.set_clip(old)


def _emit_scene_of(s, rect, pr, col, t, pl=None, shape='dart', pcol=CYAN):
	"""Run one live Process in a box, at its real numbers."""
	st = pr.stats(pl) if pl is not None else None
	_weapon_scene(s, rect, pr.emit, col, t, pr.ops, st, shape, pcol)


def panel(s, rect, alpha=210, border=LINE, radius=8, fill=PANEL):
	x, y, w, h = rect
	surf = pygame.Surface((w, h), pygame.SRCALPHA)
	pygame.draw.rect(surf, (fill[0], fill[1], fill[2], alpha), (0, 0, w, h), 0, radius)
	pygame.draw.rect(surf, (border[0], border[1], border[2], 255), (0, 0, w, h), 1, radius)
	s.blit(surf, (x, y))


def bar(s, x, y, w, h, f, col, bg=(24, 28, 40), radius=3, glow=False):
	pygame.draw.rect(s, bg, (x, y, w, h), 0, radius)
	fw = int(w * clamp(f, 0.0, 1.0))
	if fw > 0:
		pygame.draw.rect(s, col, (x, y, fw, h), 0, radius)
		if glow and fw > 3:
			blit_glow(s, x + fw, y + h * 0.5, h * 2.4, col, 0.8)


def glyph_box(s, x, y, size, ch, col, bg=(18, 22, 34), border=True, bold=True):
	pygame.draw.rect(s, bg, (x, y, size, size), 0, 5)
	if border: pygame.draw.rect(s, col, (x, y, size, size), 1, 5)
	g = text(ch, int(size * 0.62), col, bold)
	s.blit(g, (x + (size - g.get_width()) * 0.5, y + (size - g.get_height()) * 0.5))


# ==================================================================== HUD
def draw_hud(w, s):
	pl = w.player
	d = w.director
	# ---- xp bar across the top
	f = pl.xp / max(1.0, pl.xp_next)
	pygame.draw.rect(s, (10, 13, 20), (0, 0, W, 9))
	pygame.draw.rect(s, XP_COL, (0, 0, int(W * f), 9))
	pygame.draw.rect(s, shade(XP_COL, 1.3), (max(0, int(W * f) - 2), 0, 2, 9))
	pygame.draw.line(s, (40, 50, 70), (0, 9), (W, 9))

	draw_text(s, 'LV %d' % pl.level, 10, 13, 17, INK, True)
	tw = draw_text(s, d.time_str(), CX, 13, 21, INK, True, 'tc')[0]
	draw_text(s, '%d kills' % w.stats['kills'], W - 10, 15, 15, INK_DIM, False, 'tr')
	draw_text(s, w.pace['name'], CX + tw * 0.5 + 12, 18, 11, shade(w.pace['col'], 0.85), True)
	if w.sandbox:
		draw_text(s, 'LAB   TAB opens the bench', CX - tw * 0.5 - 12, 18, 11, VIOLET, True, 'tr')

	# ---- biome tag
	b = w.level
	bx = CX - 150
	draw_text(s, b['name'], CX, 38, 13, shade(b['accent'], 0.9), True, 'tc')
	bar(s, CX - 90, 54, 180, 3, d.biome_progress(), shade(b['accent'], 0.7), (22, 26, 36), 2)

	# ---- integrity
	hy = H - 40
	panel(s, (10, hy - 8, 268, 34), 190)
	f = pl.hp / pl.maxhp
	col = HP_COL if f > 0.35 else (RED if f < 0.18 else ORANGE)
	bar(s, 20, hy, 190, 12, f, col, (26, 30, 42), 4, True)
	draw_text(s, '%d/%d' % (int(pl.hp), int(pl.maxhp)), 218, hy + 6, 14, INK, True, 'ml')

	# ---- dash pip
	dx = 20; dy = H - 66
	dcol = CYAN if pl.dash_cd <= 0 else INK_FAINT
	glyph_box(s, dx, dy - 8, 22, '>', dcol, (16, 20, 30))
	if pl.dash_cd > 0:
		bar(s, dx + 27, dy - 1, 60, 6, 1.0 - pl.dash_cd / pl.dash_max, shade(CYAN, 0.7), (24, 28, 40), 3)
	else:
		draw_text(s, 'DASH', dx + 27, dy + 2, 12, CYAN, True, 'ml')

	# ---- processes column, empty slots included: how much room is left is
	# information, and it decides whether a new emitter is even offerable
	py = 78
	for pr in w.arsenal.procs:
		draw_proc_row(w, s, 10, py, pr)
		py += 46
	for i in range(len(w.arsenal.procs), w.arsenal.slots):
		draw_empty_slot(s, 10, py, i + 1)
		py += 46

	# ---- rerolls / banish
	if pl.banked:
		draw_text(s, '%d upgrade%s pending' % (pl.banked, 's' if pl.banked > 1 else ''),
		          CX, H - 26, 14, GOLD, True, 'tc')

	# ---- boss bar
	if w.boss is not None and not w.boss.dead:
		e = w.boss
		bw = 620
		x = CX - bw * 0.5
		panel(s, (x - 6, 66, bw + 12, 34), 200, shade(e.col, 0.5))
		bar(s, x, 78, bw, 12, e.hp / e.maxhp, e.col, (28, 20, 26), 4, True)
		draw_text(s, e.name, CX, 68, 13, INK, True, 'tc')
		ph = e.boss_data['phase']
		if ph: draw_text(s, 'PHASE %d' % (ph + 1), x + bw - 4, 68, 12, RED, True, 'tr')

	# ---- banners
	by = 150
	for b in w.banners:
		t = b.life / b.max
		a = clamp(min(t * 4.0, (1.0 - t) * 8.0 + 0.35), 0.0, 1.0)
		g = text(b.title, 30, b.col, True)
		g.set_alpha(int(255 * a))
		s.blit(g, (CX - g.get_width() * 0.5, by))
		g2 = text(b.sub, 14, INK_DIM)
		g2.set_alpha(int(220 * a))
		s.blit(g2, (CX - g2.get_width() * 0.5, by + 33))
		by += 60

	if w.freeze_t > 0:
		draw_text(s, 'TIME DILATION', CX, H - 60, 14, (150, 200, 255), True, 'tc')

	# ---- off-screen threat markers
	camx, camy = w.camx, w.camy
	for e in w.enemies:
		if not (e.elite or e.boss) or e.dead: continue
		x = e.x - camx; y = e.y - camy
		if -40 < x < W + 40 and -40 < y < H + 40: continue
		dx = x - CX; dy = y - CY
		m = math.hypot(dx, dy) or 1.0
		dx /= m; dy /= m
		px = CX + dx * (CX - 46); py = CY + dy * (CY - 46)
		px = clamp(px, 30, W - 30); py = clamp(py, 40, H - 30)
		col = e.col if not e.boss else RED
		a = math.atan2(dy, dx)
		pts = [(px + math.cos(a) * 11, py + math.sin(a) * 11),
		       (px + math.cos(a + 2.5) * 8, py + math.sin(a + 2.5) * 8),
		       (px + math.cos(a - 2.5) * 8, py + math.sin(a - 2.5) * 8)]
		pygame.draw.polygon(s, col, pts)
		blit_glow(s, px, py, 16, col, 0.7)

	# ---- cache toasts (auto-installed upgrades)
	ty = H - 96
	for g_, title, sub, col, life, mx in reversed(w.toasts):
		a = clamp(min(life * 2.2, 1.0), 0.0, 1.0)
		bw = max(190, text_w(title, 13, True) + 74)
		sx = W - bw - 14
		surf = pygame.Surface((bw, 38), pygame.SRCALPHA)
		pygame.draw.rect(surf, (14, 17, 26, int(225 * a)), (0, 0, bw, 38), 0, 7)
		pygame.draw.rect(surf, (col[0], col[1], col[2], int(200 * a)), (0, 0, bw, 38), 1, 7)
		s.blit(surf, (sx, ty))
		glyph_box(s, sx + 7, ty + 7, 24, g_, col, (10, 13, 20))
		draw_text(s, trim(title, 22), sx + 38, ty + 5, 13, INK, True)
		draw_text(s, trim(sub, 26), sx + 38, ty + 21, 10, INK_FAINT)
		ty -= 44

	# ---- low integrity vignette
	f = pl.hp / pl.maxhp
	if f < 0.34:
		p = (0.34 - f) / 0.34
		a = int(70 * p * (0.6 + 0.4 * math.sin(w.t * 7.0)))
		if a > 2:
			v = pygame.Surface((W, H), pygame.SRCALPHA)
			for i in range(6):
				k = i / 6.0
				pygame.draw.rect(v, (255, 30, 50, int(a * (1 - k) / 3)),
				                 (int(W * k * 0.06), int(H * k * 0.06),
				                  int(W * (1 - k * 0.12)), int(H * (1 - k * 0.12))), 14, 12)
			s.blit(v, (0, 0))


def draw_empty_slot(s, x, y, n):
	size = 30
	pygame.draw.rect(s, (22, 27, 40), (x, y, size, size), 0, 5)
	pygame.draw.rect(s, (40, 48, 68), (x, y, size, size), 1, 5)
	g = text('+', 17, (58, 68, 92), True)
	s.blit(g, (x + size * 0.5 - g.get_width() * 0.5, y + size * 0.5 - g.get_height() * 0.5))
	draw_text(s, 'PROCESS SLOT %d' % n, x + size + 8, y + 3, 11, (54, 64, 86), True)
	draw_text(s, 'empty', x + size + 8, y + 17, 10, (44, 52, 72))
	for k in range(0, 62, 6):
		pygame.draw.line(s, (32, 38, 54), (x + size + 8 + k, y + size + 2),
		                 (x + size + 11 + k, y + size + 2))


def draw_proc_row(w, s, x, y, pr):
	pl = w.player
	c = pr.stats(pl)
	col = pr.col
	size = 30
	fl = pr.flash
	bg = (26, 30, 44) if not pr.evo else (40, 34, 16)
	glyph_box(s, x, y, size, E[pr.emit]['glyph'], mix(col, WHITE, fl * 0.7), bg)
	# cooldown ring
	f = 1.0 - clamp(pr.t / max(0.001, c['cd']), 0.0, 1.0)
	pygame.draw.rect(s, shade(col, 0.8), (x, y + size + 2, int(size * f), 2))
	# name
	fit(s, pr.name, x + size + 8, y + 1, 12, GOLD if pr.evo else INK, bool(pr.evo), 246, 'tl', 8)
	# ops
	ox = x + size + 8
	oy = y + 16
	for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]):
		d = O[k]
		cc = d['col'] or INK_DIM
		g = text(d['glyph'], 12, cc, True)
		s.blit(g, (ox, oy))
		ox += g.get_width() + 1
		g = text(str(v), 10, shade(cc, 0.75))
		s.blit(g, (ox, oy + 2))
		ox += g.get_width() + 5
	if pr.syn:
		draw_text(s, '*' * len(pr.syn), ox + 2, oy, 12, VIOLET, True)
	if pr.heat_max > 0 and pr.heat > 0:
		bar(s, x + size + 8, y + 31, 60, 2, pr.heat / pr.heat_max, RED, (30, 20, 20), 1)


# ============================================================== LEVEL UP
class LevelUp:
	def __init__(self, w, offers):
		self.w = w
		self.offers = offers
		self.sel = 0
		self.t = 0.0
		self.done = None
		self.snap = None
		self.rects = []
		self.buttons = []        # [(rect, key, label, sub, col, enabled)]
		self.avoid = []          # keys of the last two rerolls, kept off the table
		self.tree = False        # the full combination tree, over the top
		self.tree_scroll = 0
		self.tree_max = 0
		self.tree_sel = 0

	def snapshot(self, s):
		small = pygame.transform.smoothscale(s, (W // 6, H // 6))
		self.snap = pygame.transform.smoothscale(small, (W, H))
		dark = pygame.Surface((W, H))
		dark.fill((6, 8, 14)); dark.set_alpha(160)
		self.snap.blit(dark, (0, 0))

	# ------------------------------------------------------------------ input
	def event(self, ev, w):
		# Commit actions are locked for GRACE seconds so a click or keypress meant
		# for the fight cannot pick an upgrade the instant the screen appears.
		live = self.t >= GRACE
		if self.tree:
			if ev.type == pygame.KEYDOWN:
				if ev.key in (pygame.K_t, pygame.K_ESCAPE, pygame.K_TAB): self.tree = False
				elif ev.key in (pygame.K_DOWN, pygame.K_s): self.tree_scroll += 70
				elif ev.key in (pygame.K_UP, pygame.K_w): self.tree_scroll -= 70
			elif ev.type == pygame.MOUSEWHEEL:
				self.tree_scroll -= ev.y * 60
			elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
				self.tree = False
			self.tree_scroll = clamp(self.tree_scroll, 0, max(0, self.tree_max))
			return
		if ev.type == pygame.KEYDOWN:
			n = len(self.offers)
			if ev.key in (pygame.K_LEFT, pygame.K_a):
				self.sel = (self.sel - 1) % n; w.audio.play('move', 0.6)
			elif ev.key in (pygame.K_RIGHT, pygame.K_d):
				self.sel = (self.sel + 1) % n; w.audio.play('move', 0.6)
			elif ev.key == pygame.K_t:
				self.tree = True; self.tree_scroll = 0
			elif not live:
				return
			elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
				self.pick(w)
			elif pygame.K_1 <= ev.key <= pygame.K_5:
				i = ev.key - pygame.K_1
				if i < n: self.sel = i; self.pick(w)
			elif ev.key == pygame.K_r:
				self.reroll(w)
			elif ev.key == pygame.K_x:
				self.banish(w)
			elif ev.key in (pygame.K_TAB, pygame.K_ESCAPE):
				self.skip(w)
		elif ev.type == pygame.MOUSEWHEEL and ev.y:
			self.sel = (self.sel - ev.y) % len(self.offers)
			w.audio.play('move', 0.5)
		elif ev.type == pygame.MOUSEMOTION:
			for i, r in enumerate(self.rects):
				if r.collidepoint(ev.pos):
					if self.sel != i: w.audio.play('move', 0.4)
					self.sel = i
		elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
			for r, key, _l, _s, _c, on in self.buttons:
				if r.collidepoint(ev.pos):
					if key == 'tree':
						self.tree = True; self.tree_scroll = 0
						w.audio.play('move', 0.7); return
					if not live or not on:
						w.audio.play('deny', 0.7); return
					{'reroll': self.reroll, 'banish': self.banish, 'skip': self.skip}[key](w)
					return
			if not live: return
			for i, r in enumerate(self.rects):
				if r.collidepoint(ev.pos):
					self.sel = i; self.pick(w); return

	def pick(self, w):
		o = self.offers[self.sel]
		o.apply()
		w.audio.play('pick', 1.0)
		w.audio.play('levelup', 0.7)
		self.done = 'picked'

	def reroll(self, w):
		if w.player.rerolls <= 0:
			w.audio.play('deny', 0.8); return
		w.player.rerolls -= 1
		from game.offers import build_offers
		self.avoid.insert(0, set(o.key for o in self.offers))
		del self.avoid[2:]
		self.offers = build_offers(w, len(self.offers), set().union(*self.avoid))
		self.sel = min(self.sel, len(self.offers) - 1)
		self.t = 0.0
		w.audio.play('gem', 0.8)

	def banish(self, w):
		if w.player.banishes <= 0:
			w.audio.play('deny', 0.8); return
		w.player.banishes -= 1
		w.banned.add(self.offers[self.sel].key)
		from game.offers import build_offers
		self.offers = build_offers(w, len(self.offers), set().union(*self.avoid) if self.avoid else None)
		self.sel = min(self.sel, len(self.offers) - 1)
		self.t = 0.0
		w.audio.play('deny', 1.0)

	def skip(self, w):
		w.player.heal(w.player.maxhp)
		w.audio.play('pick', 0.6)
		self.done = 'skipped'

	def update(self, dt):
		self.t += dt

	# ------------------------------------------------------------------- draw
	def draw(self, s, w):
		if self.snap: s.blit(self.snap, (0, 0))
		else: s.fill((6, 8, 14))
		t = min(1.0, self.t * 3.4)
		e = ease_out(t)
		mouse = pygame.mouse.get_pos()

		draw_text(s, 'EPOCH %d' % w.player.level, CX, int(26 - 14 * (1 - e)), 30, INK, True, 'tc')
		locked = self.t < GRACE
		draw_text(s, 'select a mutation', CX, 60, 13, INK_DIM if not locked else INK_FAINT, False, 'tc')
		if locked:
			bar(s, CX - 60, 80, 120, 3, self.t / GRACE, shade(CYAN, 0.55), (22, 26, 36), 2)

		n = len(self.offers)
		gap = 14
		cw = int(min(322, (W - 56 - (n - 1) * gap) / n))
		fy = H - 52
		pvh = int(clamp(H * 0.36, 196, 330))
		pvy = fy - pvh - 12
		cy = 92
		ch = int(clamp(pvy - cy - 12, 210, 430))
		x0 = CX - (n * cw + (n - 1) * gap) * 0.5
		self.rects = []

		for i, o in enumerate(self.offers):
			x = x0 + i * (cw + gap)
			r = pygame.Rect(int(x), int(cy), int(cw), int(ch))
			self.rects.append(r)
			self.draw_card(s, o, r, i == self.sel, e, i, n)

		# --- everything the selected card actually is, in the space nobody used
		if self.offers:
			draw_preview(s, (28, pvy, W - 56, pvh), w,
			             self.offers[clamp(self.sel, 0, n - 1)], self.t)

		self.draw_buttons(s, w, fy, mouse, locked)
		if self.tree:
			self.tree_max = draw_tree_screen(s, self.t, self.tree_scroll, mouse, w, True)

	# ---------------------------------------------------------------- buttons
	def draw_buttons(self, s, w, y, mouse, locked):
		"""Reroll used to be a keyboard-only verb, which made the most common
		action on this screen the one you had to leave the mouse for."""
		pl = w.player
		self.buttons = []
		defs = [('reroll', 'REROLL', 'R  -  %d left' % pl.rerolls, GOLD, pl.rerolls > 0),
		        ('banish', 'BANISH', 'X  -  %d left' % pl.banishes, VIOLET, pl.banishes > 0),
		        ('skip', 'SKIP', 'ESC  -  full repair', HP_COL, True),
		        ('tree', 'TREE', 'T  -  every evolution', CYAN, True)]
		bw = 208; bh = 38; g = 12
		x = CX - (len(defs) * bw + (len(defs) - 1) * g) * 0.5
		for key, lbl, sub, col, on in defs:
			r = pygame.Rect(int(x), int(y), bw, bh)
			self.buttons.append((r, key, lbl, sub, col, on))
			live = on and (not locked or key == 'tree')
			hot = r.collidepoint(mouse) and live
			c = col if live else INK_FAINT
			pygame.draw.rect(s, (24, 29, 42) if hot else (14, 18, 27), r, 0, 7)
			pygame.draw.rect(s, c if hot else shade(c, 0.55), r, 2 if hot else 1, 7)
			draw_text(s, lbl, r.x + 14, r.y + 6, 15, c, True)
			draw_text(s, sub, r.right - 14, r.y + 10, 11, INK_FAINT, False, 'tr')
			x += bw + g

	# ------------------------------------------------------------------ cards
	def draw_card(self, s, o, r, sel, e, i, n):
		t = clamp(e * 1.4 - i * 0.10, 0.0, 1.0)
		if t <= 0.01: return
		off = int((1.0 - ease_out(t)) * 60)
		rr = pygame.Rect(r.x, r.y + off, r.w, r.h)
		col = o.col
		rare = RARITY_COL.get(o.rarity, INK_DIM)
		tl = wrap(o.title, 17, rr.w - 112)[:2]
		sl = wrap(o.sub, 11, rr.w - 90)[:4]
		head = 46 + 20 * len(tl) + 14 * len(sl)

		surf = pygame.Surface((rr.w, rr.h), pygame.SRCALPHA)
		a = int(238 * t)
		pygame.draw.rect(surf, (13, 16, 24, a), (0, 0, rr.w, rr.h), 0, 10)
		pygame.draw.rect(surf, (rare[0], rare[1], rare[2], int((255 if sel else 110) * t)),
		                 (0, 0, rr.w, rr.h), 2 if sel else 1, 10)
		pygame.draw.rect(surf, (col[0] // 5, col[1] // 5, col[2] // 5, a), (0, 0, rr.w, head), 0, 10)
		pygame.draw.line(surf, (rare[0], rare[1], rare[2], int(160 * t)), (0, head), (rr.w, head))
		s.blit(surf, rr.topleft)

		if sel:
			blit_glow(s, rr.centerx, rr.centery, 260, shade(col, 0.5), 0.30)

		glyph_box(s, rr.x + 14, rr.y + 14, 48, o.glyph, col, (10, 13, 20))
		ty = rr.y + 15
		for line in tl:
			draw_text(s, line, rr.x + 72, ty, 17, INK, True)
			ty += 20
		for line in sl:
			draw_text(s, line, rr.x + 72, ty + 1, 11, shade(col, 0.95))
			ty += 14
		kindlbl = {'op': 'OP', 'new': 'EMITTER', 'passive': 'SYSTEM',
		           'fuse': 'FUSION', 'heal': 'REPAIR'}.get(o.kind, '')
		draw_text(s, kindlbl, rr.right - 14, rr.y + head - 20, 11, rare, True, 'tr')
		if o.kind == 'op' and o.proc is not None:
			cur = o.proc.ops.get(o.key[3:], 0)
			pips(s, rr.x + 16, rr.y + head - 18, cur + 1, MAX_TRAIT_RK, col)
		draw_text(s, str(i + 1), rr.right - 14, rr.y + 14, 14, INK_FAINT, True, 'tr')

		# --- the effect, running, at the numbers it will actually have
		note_lines = wrap(o.note, 12, rr.w - 34) if o.note else []
		note_h = 14 + 15 * len(note_lines)
		note_top = rr.bottom - (note_h + 10 if note_lines else 10)
		ah = int(clamp(rr.h * 0.42, 96, 210))
		art = (rr.x + 12, rr.y + head + 10, rr.w - 24, ah)
		pv = o.pv or {}
		if pv.get('mode') in ('ab', 'solo', 'fuse'):
			_weapon_scene(s, art, pv.get('emit'), col, self.t, _rk_map(pv.get('after')),
			              pv['ghost'].stats(self.w.player) if pv.get('ghost') else None,
			              self.w.player.shape, self.w.player.col)
		else:
			art_key = o.key.split(':', 1)[1] if ':' in o.key else o.key
			draw_art(s, art, o.kind, art_key, col, self.t)

		y = art[1] + ah + 10
		for line in wrap(o.desc, 13, rr.w - 32):
			if y + 15 > note_top - 4: break
			draw_text(s, line, rr.x + 16, y, 13, INK_DIM)
			y += 16

		if note_lines:
			pygame.draw.rect(s, (o.note_col[0] // 6, o.note_col[1] // 6, o.note_col[2] // 6),
			                 (rr.x + 10, note_top, rr.w - 20, note_h), 0, 6)
			for j, line in enumerate(note_lines):
				draw_text(s, line, rr.centerx, note_top + 4 + j * 15, 12, o.note_col, True, 'tc')


def _rk_map(keys):
	"""Scene ops want ranks; a plain set of op ids means 'one rank each'."""
	if keys is None: return None
	if isinstance(keys, dict): return keys
	return {k: 1 for k in keys}


# ====================================================== THE PREVIEW PANEL
def _mini(s, rect, label, lcol=INK_FAINT):
	pygame.draw.rect(s, (10, 13, 20), rect, 0, 6)
	pygame.draw.rect(s, (30, 36, 52), rect, 1, 6)
	draw_text(s, label, rect[0] + 8, rect[1] + 5, 10, lcol, True)


def _rows_table(s, x, y, w_, rows, maxrows=8):
	for label, a, b, sign in rows[:maxrows]:
		draw_text(s, label, x, y, 12, INK_FAINT)
		g = text(str(b), 13, GREEN if sign > 0 else RED, True)
		s.blit(g, (x + w_ - g.get_width(), y - 1))
		g2 = text(str(a) + '  >', 12, INK_DIM)
		s.blit(g2, (x + w_ - g.get_width() - 10 - g2.get_width(), y))
		y += 18
	return y


def _radius_ab(s, rect, r0, r1, col, unit=''):
	"""Two radii, drawn to scale against each other. For anything whose upgrade IS
	a radius, a number is not an image and an image is not a number: show both."""
	x, y, w_, h_ = rect
	cx = x + w_ * 0.5; cy = y + h_ * 0.52
	k = (min(w_, h_) * 0.42) / max(1.0, r1)
	pygame.draw.circle(s, (48, 58, 80), (int(cx), int(cy)), max(2, int(r0 * k)), 1)
	pygame.draw.circle(s, col, (int(cx), int(cy)), max(2, int(r1 * k)), 2)
	blit_glow(s, cx, cy, 14, col, 0.6)
	draw_text(s, '%d%s' % (int(r0), unit), cx, cy + int(r0 * k) + 2, 10, INK_FAINT, False, 'tc')
	draw_text(s, '%d%s' % (int(r1), unit), cx, y + h_ - 15, 11, col, True, 'tc')


def _passive_ab(s, rect, pid, pl, g, col, t):
	"""Before/after for a system upgrade, in the terms of the thing it changes."""
	if pid == 'magnet':
		_radius_ab(s, rect, pl.magnet, g.magnet, col)
	elif pid == 'area':
		_radius_ab(s, rect, 96 * pl.area_mult, 96 * g.area_mult, col)
	elif pid in ('hp', 'regen', 'armor'):
		x, y, w_, h_ = rect
		by = y + h_ * 0.42
		full = w_ - 28
		# the old bar drawn inside the new one, so the gain is the visible remainder
		pygame.draw.rect(s, (26, 30, 42), (x + 14, by, full, 12), 0, 4)
		pygame.draw.rect(s, shade(HP_COL, 0.45), (x + 14, by, int(full * (pl.maxhp / max(1.0, g.maxhp))), 12), 0, 4)
		pygame.draw.rect(s, HP_COL, (x + 14, by, full, 12), 1, 4)
		draw_text(s, '%d  >  %d max integrity' % (int(pl.maxhp), int(g.maxhp)), x + w_ * 0.5,
		          by + 20, 12, HP_COL, True, 'tc')
		if g.regen != pl.regen or g.armor != pl.armor:
			draw_text(s, 'regen %.1f/s   armour %d' % (g.regen, int(g.armor)), x + w_ * 0.5,
			          by + 38, 11, INK_FAINT, False, 'tc')
	elif pid in ('speed', 'haste', 'vel'):
		x, y, w_, h_ = rect
		for k, (v0, cc) in enumerate(((1.0, (60, 72, 96)), (g.move_mult / max(0.01, pl.move_mult), col))):
			yy = y + h_ * (0.4 + 0.22 * k)
			f = ((t * 0.55 * v0) % 1.0)
			pygame.draw.line(s, (26, 32, 46), (x + 16, yy), (x + w_ - 16, yy), 1)
			_dot(s, x + 16 + (w_ - 32) * f, yy, 4, cc, 0.9)
		draw_text(s, 'now  /  after', x + w_ * 0.5, y + h_ - 18, 11, INK_FAINT, False, 'tc')
	else:
		x, y, w_, h_ = rect
		_passive_art(s, rect, pid, col, t, (t * 0.8) % 1.0)


def draw_preview(s, rect, w, o, t):
	"""What the selected card IS -- not an ornament of it.

	Left: the weapon running now. Right of the arrow: the same weapon with this
	card taken. Beside them, every number that moves. Under them, the full text,
	unwrapped and unabridged, because a description you have to hunt for is a
	description nobody reads."""
	x, y, w_, h_ = rect
	panel(s, rect, 216)
	pl = w.player
	pv = o.pv or {'mode': 'none', 'rows': []}
	mode = pv.get('mode', 'none')
	col = o.col

	head = {'ab': 'WHAT CHANGES', 'solo': 'WHAT THIS WEAPON DOES',
	        'passive': 'WHAT CHANGES', 'fuse': 'WHAT THE MERGE PRODUCES',
	        'heal': 'WHAT THIS RESTORES'}.get(mode, 'PREVIEW')
	draw_text(s, head, x + 14, y + 8, 11, INK_FAINT, True)
	draw_text(s, o.title, x + 26 + text_w(head, 11, True), y + 7, 13, col, True)
	draw_text(s, 'T  full evolution tree', x + w_ - 14, y + 8, 10, INK_FAINT, False, 'tr')

	# ---- text band first: it owns the bottom and nothing overlaps it
	lines = wrap(o.desc, 14, w_ - 32)
	extra = None
	if mode == 'ab' and pv.get('evo_b') and not pv.get('evo_a'):
		extra = ('EVOLVES INTO ' + pv['evo_b']['name'], pv['evo_b']['desc'], GOLD)
	elif mode == 'fuse' and pv.get('evo_b'):
		extra = ('MERGE EVOLVES INTO ' + pv['evo_b']['name'], pv['evo_b']['desc'], GOLD)
	elif mode == 'fuse' and pv.get('dropped'):
		extra = ('DROPPED', ', '.join(O[k]['name'] for k in pv['dropped']), RED)
	elif o.note:
		extra = (o.note, '', o.note_col)
	eh = 0
	if extra:
		eh = 20 + 16 * len(wrap(extra[1], 13, w_ - 40)) if extra[1] else 22
	th = 8 + 17 * len(lines) + eh
	ty = y + h_ - th - 8
	pygame.draw.rect(s, (17, 21, 32), (x + 10, ty, w_ - 20, th + 2), 0, 6)
	yy = ty + 5
	for line in lines:
		draw_text(s, line, x + 20, yy, 14, INK, False)
		yy += 17
	if extra:
		pygame.draw.line(s, (34, 42, 60), (x + 20, yy + 1), (x + w_ - 20, yy + 1))
		yy += 5
		draw_text(s, extra[0], x + 20, yy, 13, extra[2], True)
		yy += 17
		for line in wrap(extra[1], 13, w_ - 40):
			draw_text(s, line, x + 20, yy, 13, shade(extra[2], 0.8))
			yy += 16

	# ---- scenes and numbers
	top = y + 26
	bot = ty - 8
	bh = max(70, bot - top)
	tw = 250
	sw = w_ - 28 - tw - 14
	rows = pv.get('rows', [])
	shape = pl.shape; pcol = pl.col

	if mode == 'ab':
		half = int((sw - 34) * 0.5)
		ra = (x + 14, top, half, bh)
		rb = (x + 14 + half + 34, top, half, bh)
		_weapon_scene(s, ra, pv['emit'], shade(col, 0.75), t, _rk_map(pv['before']),
		              o.proc.stats(pl) if o.proc else None, shape, pcol)
		_weapon_scene(s, rb, pv['emit'], col, t, _rk_map(pv['after']),
		              pv['ghost'].stats(pl), shape, pcol)
		_arrow(s, ra[0] + half + 6, top + bh * 0.5, rb[0] - 6, top + bh * 0.5, GOLD, 3, 9)
		draw_text(s, trim(pv.get('name_a', 'now'), int(half / 6.2)), ra[0] + 8, top + 4, 11, INK_FAINT, True)
		draw_text(s, trim(pv.get('name_b', 'after'), int(half / 6.2)), rb[0] + 8, top + 4, 11,
		          GOLD if pv.get('evo_b') else col, True)
	elif mode == 'solo':
		rb = (x + 14, top, sw, bh)
		_weapon_scene(s, rb, pv['emit'], col, t, None, pv['ghost'].stats(pl), shape, pcol)
		draw_text(s, pv.get('name_b', ''), rb[0] + 8, top + 4, 11, col, True)
	elif mode == 'fuse':
		third = int((sw - 46) / 3)
		bh = max(60, bh - 18)          # room for the merged op list under the result
		ra = (x + 14, top, third, bh)
		rbb = (x + 14 + third + 18, top, third, bh)
		rc = (x + 14 + 2 * (third + 18) + 10, top, third, bh)
		a, b, gh = pv['a'], pv['b'], pv['ghost']
		_weapon_scene(s, ra, a.emit, shade(a.col, 0.8), t, a.ops, a.stats(pl), shape, pcol)
		_weapon_scene(s, rbb, b.emit, shade(b.col, 0.8), t, b.ops, b.stats(pl), shape, pcol)
		_weapon_scene(s, rc, gh.emit, MAGENTA if not gh.evo else GOLD, t, gh.ops, gh.stats(pl), shape, pcol)
		draw_text(s, '+', ra[0] + third + 9, top + bh * 0.5 - 10, 20, MAGENTA, True, 'tc')
		_arrow(s, rbb[0] + third + 3, top + bh * 0.5, rc[0] - 4, top + bh * 0.5, MAGENTA, 3, 9)
		# the merged op set, spelled out: this is the answer to "is this a downgrade"
		oy = top + bh + 3
		for r_, pp, cc in ((ra, a, a.col), (rbb, b, b.col), (rc, gh, GOLD if gh.evo else MAGENTA)):
			fit(s, pp.name, r_[0] + 8, top + 4, 11, cc, True, third - 16, 'tl', 8)
			ox = r_[0]
			for k, v in sorted(pp.ops.items(), key=lambda kv: -kv[1]):
				gtx = text('%s%s' % (O[k]['glyph'], rk(v)), 12, O[k]['col'] or INK_DIM, True)
				if ox + gtx.get_width() > r_[0] + third: break
				s.blit(gtx, (ox, oy)); ox += gtx.get_width() + 7
	elif mode == 'passive' and pv.get('emit'):
		half = int((sw - 34) * 0.5)
		ra = (x + 14, top, half, bh)
		rb = (x + 14 + half + 34, top, half, bh)
		ops = pv['ops']
		_weapon_scene(s, ra, pv['emit'], shade(col, 0.7), t, ops, pv['st_a'], shape, pcol)
		_weapon_scene(s, rb, pv['emit'], col, t, ops, pv['st_b'], shape, pcol)
		_arrow(s, ra[0] + half + 6, top + bh * 0.5, rb[0] - 6, top + bh * 0.5, GOLD, 3, 9)
		fit(s, pv.get('name_a', ''), ra[0] + 8, top + 4, 11, INK_FAINT, True, half - 16, 'tl', 8)
		draw_text(s, 'with ' + o.title, rb[0] + 8, top + 4, 11, col, True)
	elif mode == 'passive':
		rb = (x + 14, top, sw, bh)
		_mini(s, rb, 'SYSTEM')
		_passive_ab(s, rb, pv['pid'], pl, pv['ghost'], col, t)
	else:
		rb = (x + 14, top, sw, bh)
		_mini(s, rb, 'REPAIR')
		draw_art(s, (rb[0] + 4, rb[1] + 16, rb[2] - 8, rb[3] - 22), o.kind,
		         o.key.split(':', 1)[-1], col, t)

	tx = x + w_ - tw - 14
	pygame.draw.line(s, (34, 42, 60), (tx - 8, top), (tx - 8, bot))
	draw_text(s, 'NOW   >   AFTER', tx + tw, top, 10, INK_FAINT, True, 'tr')
	if rows:
		_rows_table(s, tx, top + 18, tw, rows, max(1, int((bh - 20) / 18)))
	else:
		draw_text(s, 'no stat changes', tx, top + 20, 12, INK_FAINT)


# ============================================== THE COMBINATION TREE (browsable)
def _tree_rows():
	"""Left to right: every emitter, then the evolutions it can crystallise into."""
	out = []
	for k in EMIT_ORDER:
		out.append((k, list(EVO_BY_EMIT.get(k, ()))))
	return out


def draw_tree_screen(s, t, scroll, mouse, w=None, overlay=False):
	"""The whole system on one scrollable page: bases on the left, what each one
	becomes on the right, with the exact recipe and the effect running."""
	if overlay:
		o = pygame.Surface((W, H), pygame.SRCALPHA)
		o.fill((4, 6, 11, 240))
		s.blit(o, (0, 0))
	else:
		s.fill((6, 8, 13))
	draw_text(s, 'EVOLUTION TREE', 40, 22, 26, GOLD, True)
	draw_text(s, 'every emitter and everything it can become - scroll, hover a row',
	          40, 54, 12, INK_DIM)
	draw_text(s, 'ESC / T close' if overlay else 'ESC back', W - 40, 26, 12, INK_FAINT, False, 'tr')

	pl = w.player if w is not None else None
	have = {}
	if w is not None:
		for p in w.arsenal.procs: have[p.emit] = p

	PW = 300                          # the live preview column on the right
	x0 = 40
	cw = 236                          # emitter column
	gut = 46                          # connector gutter: nothing is ever drawn over a node
	ex = x0 + cw + gut                # evolution column
	ew = W - PW - 40 - ex - 20
	top = 84
	bot = H - 30
	y = top - scroll
	hover = None
	clip = s.get_clip()
	s.set_clip(pygame.Rect(0, top, W - PW - 30, bot - top))

	for emit, evos in _tree_rows():
		em = E[emit]
		rh = max(len(evos) * 62, 96) + 14
		if y + rh > top - 40 and y < bot:
			r = pygame.Rect(x0, int(y), cw, rh - 12)
			pr = have.get(emit)
			on = pr is not None
			pygame.draw.rect(s, (20, 25, 37) if on else (14, 17, 26), r, 0, 8)
			pygame.draw.rect(s, em['col'] if on else shade(em['col'], 0.4), r, 2 if on else 1, 8)
			glyph_box(s, r.x + 10, r.y + 10, 32, em['glyph'], em['col'], (10, 13, 20))
			draw_text(s, em['name'], r.x + 50, r.y + 10, 15, em['col'], True)
			draw_text(s, 'tier %d   %.0f dmg   x%d   %.2fs'
			          % (em['tier'], em['dmg'], em['count'], em['cd']),
			          r.x + 50, r.y + 30, 11, INK_FAINT)
			ax_ = r.x + 12; ay_ = r.y + 54
			draw_text(s, 'grows with', ax_, ay_, 10, INK_FAINT, True)
			ay_ += 14
			for k in em['affinity']:
				gk = text('%s %s' % (O[k]['glyph'], O[k]['name']), 11, O[k]['col'] or INK_DIM, True)
				if ax_ + gk.get_width() + 8 > r.right - 10:
					ax_ = r.x + 12; ay_ += 15
				if ay_ > r.bottom - 30: break
				s.blit(gk, (ax_, ay_))
				ax_ += gk.get_width() + 10
			if on:
				fit(s, 'RUNNING: ' + pr.name, r.x + 12, r.bottom - 18, 11, GREEN, True, cw - 24, 'tl', 8)
			if r.collidepoint(mouse):
				hover = ('emit', emit, None)
			for j, ev in enumerate(evos):
				ry = y + j * 62
				er = pygame.Rect(ex, int(ry), ew, 50)
				done = pr is not None and pr.evo is ev
				got = sum(min(pr.ops.get(k, 0) if pr else 0, v) for k, v in ev['req'].items())
				need = sum(ev['req'].values())
				cc = GOLD if done else (shade(GOLD, 0.75) if got else INK_FAINT)
				# elbow connector, drawn only inside the gutter
				my = r.y + rh * 0.5 - 6
				pygame.draw.line(s, shade(GOLD, 0.30), (r.right + 4, my), (ex - gut * 0.5, my), 1)
				pygame.draw.line(s, shade(GOLD, 0.30), (ex - gut * 0.5, my), (ex - gut * 0.5, ry + 25), 1)
				pygame.draw.line(s, shade(GOLD, 0.30), (ex - gut * 0.5, ry + 25), (ex - 4, ry + 25), 1)
				pygame.draw.rect(s, (24, 21, 12) if done else (14, 17, 26), er, 0, 7)
				pygame.draw.rect(s, cc if (done or er.collidepoint(mouse)) else (36, 42, 58),
				                 er, 2 if done else 1, 7)
				half = int(ew * 0.44)
				draw_text(s, ev['name'], er.x + 12, er.y + 6, 14, cc, True)
				recipe = '   +   '.join('%s %s' % (O[k]['name'], rk(v)) for k, v in ev['req'].items())
				draw_text(s, recipe, er.x + 12, er.y + 26, 11, INK_DIM)
				dy = er.y + 7
				for line in wrap(ev['desc'], 11, ew - half - 76)[:2]:
					draw_text(s, line, er.x + half, dy, 11, INK_FAINT)
					dy += 14
				pw = min(120, ew * 0.22)
				bar(s, er.right - pw - 12, er.y + 32, pw, 4, got / max(1, need),
				    GOLD if done else shade(GOLD, 0.7), (30, 34, 46), 2)
				draw_text(s, 'EVOLVED' if done else '%d/%d' % (got, need),
				          er.right - 12, er.y + 9, 11, cc, True, 'tr')
				if er.collidepoint(mouse):
					hover = ('evo', emit, ev)
		y += rh
	s.set_clip(clip)

	# ---- the live panel: whatever the mouse is on, running
	px = W - PW - 20
	panel(s, (px, top, PW, bot - top), 220)
	if hover is None: hover = ('emit', EMIT_ORDER[0], None)
	kind, emit, ev = hover
	em = E[emit]
	title = ev['name'] if ev else em['name']
	col = GOLD if ev else em['col']
	draw_text(s, title, px + 14, top + 10, 16, col, True)
	sc = (px + 14, top + 36, PW - 28, 150)
	ops = dict(ev['req']) if ev else {}
	if ev: ops.update(ev.get('grant', {}))
	st = None
	if ev:
		g = ghost_process(emit, ops, 3)
		st = g.stats(pl) if pl is not None else None
	_weapon_scene(s, sc, emit, col, t, ops or None, st,
	              pl.shape if pl else 'dart', pl.col if pl else CYAN)
	yy = top + 196
	for line in wrap(ev['desc'] if ev else em['desc'], 13, PW - 28):
		draw_text(s, line, px + 14, yy, 13, INK_DIM)
		yy += 17
	yy += 6
	if ev:
		draw_text(s, 'RECIPE', px + 14, yy, 11, INK_FAINT, True); yy += 17
		for k, v in ev['req'].items():
			draw_text(s, '%s  %s %s' % (O[k]['glyph'], O[k]['name'], rk(v)), px + 14, yy, 12,
			          O[k]['col'] or INK, True)
			yy += 16
		for k, v in ev.get('grant', {}).items():
			draw_text(s, 'grants %s +%d' % (O[k]['name'], v), px + 14, yy, 11, GREEN)
			yy += 15
	else:
		draw_text(s, 'AFFINITY', px + 14, yy, 11, INK_FAINT, True); yy += 17
		for k in em['affinity']:
			draw_text(s, '%s  %s' % (O[k]['glyph'], O[k]['name']), px + 14, yy, 12,
			          O[k]['col'] or INK, True)
			yy += 16
	mn = wrap('Any two processes can also MERGE into one: union of every op, ranks added, '
	          'a slot freed. A merge never loses an op.', 11, PW - 28)
	my_ = bot - 12 - 14 * len(mn)
	for line in mn:
		draw_text(s, line, px + 14, my_, 11, MAGENTA)
		my_ += 14
	return max(0, y + scroll - bot + 40)
# ================================================================= PAUSE
def draw_pause(w, s, tab=0):
	o = pygame.Surface((W, H), pygame.SRCALPHA)
	o.fill((5, 7, 12, 225))
	s.blit(o, (0, 0))
	pl = w.player
	draw_text(s, 'SUSPENDED', CX, 26, 30, INK, True, 'tc')
	draw_text(s, 'ESC resume   -   T evolution tree   -   Q quit to menu', CX, 62, 13, INK_DIM, False, 'tc')

	# ---- left: processes
	LW = int(W * 0.50)
	x = 40; y = 96
	panel(s, (x - 12, y - 12, LW, H - y - 40), 170)
	draw_text(s, 'ACTIVE PROCESSES  %d/%d' % (len(w.arsenal.procs), w.arsenal.slots),
	          x, y, 14, INK, True)
	y += 26
	for pr in w.arsenal.procs:
		c = pr.stats(pl)
		glyph_box(s, x, y, 34, E[pr.emit]['glyph'], pr.col, (18, 22, 34))
		draw_text(s, pr.name, x + 44, y, 15, GOLD if pr.evo else INK, True)
		draw_text(s, 'rank %d   %.0f dmg x%d   %.2fs' % (pr.rank, c['dmg'], c['count'], c['cd']),
		          x + 44, y + 19, 11, INK_DIM)
		ox = x + 44; oy = y + 34
		for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]):
			d = O[k]
			cc = d['col'] or INK_DIM
			g = text('%s%s %s' % (d['glyph'], rk(v), d['name']), 11, cc)
			s.blit(g, (ox, oy))
			ox += g.get_width() + 12
			if ox > x + LW - 110: ox = x + 44; oy += 14
		yy = oy + 16
		if pr.syn:
			draw_text(s, 'SYNERGY  ' + '   '.join('* ' + sid for sid in pr.syn), x + 44, yy, 11, VIOLET, True)
			yy += 15
		p = pr.evo_progress()
		if p:
			ev, missing, frac = p
			miss = '  '.join('%s%s' % (O[k]['name'], '+' + str(v)) for k, v in missing.items())
			draw_text(s, 'EVOLVES: %s  [%s]' % (ev['name'], miss), x + 44, yy, 11, shade(GOLD, 0.85))
			yy += 15
		elif pr.evo:
			draw_text(s, 'EVOLVED - ' + pr.evo['desc'], x + 44, yy, 11, GOLD)
			yy += 15
		y = yy + 12
		pygame.draw.line(s, (26, 32, 46), (x, y - 7), (x + LW - 40, y - 7))

	# ---- right: stats
	x = 40 + LW + 24; y = 96
	RW = W - x - 28
	panel(s, (x - 12, y - 12, RW, H - y - 40), 170)
	draw_text(s, 'SYSTEM', x, y, 14, INK, True)
	y += 26
	rows = [
		('integrity', '%d / %d' % (int(pl.hp), int(pl.maxhp))),
		('damage', '%d%%' % int(pl.dmg_mult * 100)),
		('cooldown', '%d%%' % int(pl.cd_mult * 100)),
		('area', '%d%%' % int(pl.area_mult * 100)),
		('proj speed', '%d%%' % int(pl.pspeed_mult * 100)),
		('amount', '+%d' % pl.amount),
		('crit', '%d%% / x%.1f' % (int(pl.crit_c * 100), 2.0 + pl.crit_m)),
		('move', '%d%%' % int(pl.move_mult * 100)),
		('armor', '%d' % int(pl.armor)),
		('dodge', '%d%%' % int(pl.dodge * 100)),
		('regen', '%.1f/s' % pl.regen),
		('magnet', '%d' % int(pl.magnet)),
		('luck', '%d%%' % int(pl.luck * 100)),
		('xp gain', '%d%%' % int(pl.xp_mult * 100)),
	]
	for k, v in rows:
		draw_text(s, k, x, y, 12, INK_FAINT)
		draw_text(s, v, x + RW - 36, y, 12, INK, True, 'tr')
		y += 17
	y += 10
	draw_text(s, 'RUN', x, y, 14, INK, True); y += 22
	d = w.director
	rows = [('schedule', w.pace['name']), ('time', d.time_str()), ('kills', str(w.stats['kills'])),
	        ('dps', '%d' % w.dps),
	        ('damage dealt', '%d' % w.stats['dmg']), ('damage taken', '%d' % w.stats['taken']),
	        ('evolutions', str(w.stats['evos'])), ('fusions', str(w.stats['fuses'])),
	        ('biome', w.level['name'])]
	for k, v in rows:
		draw_text(s, k, x, y, 12, INK_FAINT)
		draw_text(s, v, x + RW - 36, y, 12, INK, True, 'tr')
		y += 17

	y += 14
	pygame.draw.line(s, (26, 32, 46), (x, y - 6), (x + RW - 36, y - 6))
	draw_text(s, 'CONTROLS', x, y, 14, INK, True); y += 22
	for k, v in CONTROLS:
		draw_text(s, k, x, y, 12, CYAN, True)
		draw_text(s, v, x + 126, y, 12, INK_DIM)
		y += 17


# ================================================================== CODEX
CODEX_PAGES = 5


def draw_codex(s, page, scroll, t=0.0, mouse=(0, 0)):
	if page == 4:
		# the tree is its own full-page layout, scroll and all
		return draw_tree_screen(s, t, scroll, mouse, None) + H - 120
	s.fill((6, 8, 13))
	draw_text(s, 'CODEX', 40, 26, 30, INK, True)
	tabs = ['EMITTERS', 'OPS', 'SYNERGIES', 'EVOLUTIONS', 'TREE']
	x = 40
	for i, t in enumerate(tabs):
		col = CYAN if i == page else INK_FAINT
		draw_text(s, t, x, 70, 14, col, i == page)
		if i == page:
			pygame.draw.line(s, CYAN, (x, 90), (x + text_w(t, 14, True), 90), 2)
		x += text_w(t, 14, True) + 30
	draw_text(s, 'LEFT/RIGHT switch   UP/DOWN scroll   ESC back', W - 40, 74, 12, INK_FAINT, False, 'tr')

	y = 110 - scroll
	if page == 0:
		for k, em in E.items():
			if y > H: break
			if y > 60:
				glyph_box(s, 40, y, 30, em['glyph'], em['col'], (16, 20, 30))
				draw_text(s, em['name'], 82, y + 1, 16, em['col'], True)
				draw_text(s, em['desc'], 82, y + 21, 12, INK_DIM)
				draw_text(s, 'dmg %.0f   cd %.2fs   x%d   affinity: %s'
				          % (em['dmg'], em['cd'], em['count'], ', '.join(em['affinity'])),
				          420, y + 21, 11, INK_FAINT)
			y += 46
	elif page == 1:
		for k, d in O.items():
			if y > H: break
			if y > 60:
				col = d['col'] or INK
				glyph_box(s, 40, y, 26, d['glyph'], col, (16, 20, 30))
				draw_text(s, d['name'], 78, y + 1, 15, col, True)
				draw_text(s, d['desc'], 78, y + 19, 12, INK_DIM)
				draw_text(s, d['tag'], W - 60, y + 4, 11, INK_FAINT, False, 'tr')
			y += 40
	elif page == 2:
		draw_text(s, 'Ops interact. Reach these thresholds on ONE process and something new happens.',
		          40, y, 13, INK_DIM); y += 30
		for sid, req, desc in SYN:
			if y > H: break
			if y > 60:
				draw_text(s, '* ' + sid, 40, y, 15, VIOLET, True)
				need = '  +  '.join('%s %s' % (O[k]['name'], rk(v)) for k, v in req.items())
				draw_text(s, need, 250, y + 2, 12, INK)
				draw_text(s, desc, 250, y + 20, 12, INK_DIM)
			y += 44
	else:
		for ev in sum(EVO_BY_EMIT.values(), []):
			if y > H: break
			if y > 60:
				draw_text(s, ev['name'], 40, y, 15, GOLD, True)
				need = E[ev['emit']]['name'] + '  +  ' + '  '.join(
					'%s %s' % (O[k]['name'], rk(v)) for k, v in ev['req'].items())
				draw_text(s, need, 40, y + 20, 12, INK)
				draw_text(s, ev['desc'], 40, y + 36, 12, INK_DIM)
			y += 62
	return y + scroll


# ================================================================ CURSOR
def draw_cursor(s, w, mx, my, held, mode, anchor, fade):
	"""Reticle + drag indicator for mouse steering."""
	if fade <= 0.0 and not held: return
	a = clamp(fade if not held else 1.0, 0.0, 1.0)
	camx, camy = w.last_cam
	px = w.player.x - camx; py = w.player.y - camy
	col = CYAN if held else INK_DIM

	if held:
		if mode == 'joystick' and anchor:
			ax, ay = anchor
			dx = mx - ax; dy = my - ay
			d = math.hypot(dx, dy)
			g = ring(46, shade(CYAN, 0.5), 1, 90)
			s.blit(g, (ax - g.get_width() * 0.5, ay - g.get_height() * 0.5), None, pygame.BLEND_ADD)
			if d > 1.0:
				k = min(1.0, d / 90.0) * 44
				pygame.draw.line(s, shade(CYAN, 0.8), (ax, ay), (ax + dx / d * k, ay + dy / d * k), 3)
				blit_glow(s, ax + dx / d * k, ay + dy / d * k, 16, CYAN, 0.9)
		else:
			dx = mx - px; dy = my - py
			d = math.hypot(dx, dy)
			if d > 20:
				n = int(min(11, d / 24))
				ph = (w.t * 2.2) % 1.0
				for i in range(1, n + 1):
					f = (i - ph) / (n + 1)
					if f <= 0.0: continue
					blit_glow(s, px + dx * f, py + dy * f, 6, CYAN, 0.42 * (1.0 - f) + 0.16)
				pygame.draw.circle(s, shade(CYAN, 0.35), (int(px), int(py)), 26, 1)

	r = 13 if held else 10
	col2 = shade(col, a)
	for k in range(4):
		ang_ = k * (TAU / 4) + (w.t * 1.4 if held else 0.0)
		ox = math.cos(ang_); oy = math.sin(ang_)
		pygame.draw.line(s, col2, (mx + ox * r * 0.45, my + oy * r * 0.45),
		                 (mx + ox * r, my + oy * r), 2 if held else 1)
	pygame.draw.circle(s, col2, (int(mx), int(my)), 2)
	if held:
		blit_glow(s, mx, my, 22, CYAN, 0.55)


# ============================================================ BOOT SELECT
def draw_pace_strip(s, y, sel, t):
	"""The four run schedules, as one clickable strip. Returns their rects."""
	from core.pace import PACES
	n = len(PACES)
	cw = min(258, int((W - 80 - (n - 1) * 14) / n))
	ch = 74
	gap = 14
	x0 = CX - (n * cw + (n - 1) * gap) * 0.5
	rects = []
	for i, p in enumerate(PACES):
		x = int(x0 + i * (cw + gap))
		r = pygame.Rect(x, int(y), cw, ch)
		rects.append(r)
		selq = i == sel
		col = p['col']
		surf = pygame.Surface((cw, ch), pygame.SRCALPHA)
		pygame.draw.rect(surf, (12, 15, 23, 240), (0, 0, cw, ch), 0, 8)
		if selq:
			pygame.draw.rect(surf, (col[0] // 6, col[1] // 6, col[2] // 6, 255), (0, 0, cw, ch), 0, 8)
		pygame.draw.rect(surf, col if selq else LINE, (0, 0, cw, ch), 2 if selq else 1, 8)
		s.blit(surf, r.topleft)
		if selq: blit_glow(s, r.centerx, r.centery, 120, shade(col, 0.5), 0.30)
		draw_text(s, str(i + 1), r.x + 9, r.y + 7, 11, INK_FAINT, True)
		draw_text(s, p['name'], r.centerx, r.y + 8, 17, col if selq else INK, True, 'tc')
		draw_text(s, trim(p['tag'], int(cw / 6.2)), r.centerx, r.y + 30, 11, INK_DIM if selq else INK_FAINT,
		          False, 'tc')
		# speed pips
		bw = 22; bh = 7
		bx = r.centerx - (4 * bw + 3 * 5) * 0.5
		for k in range(4):
			on = k < p['bars']
			c = col if on else (30, 36, 50)
			if on and selq:
				c = mix(col, WHITE, 0.35 * (0.5 + 0.5 * math.sin(t * 5.0 - k * 0.6)))
			pygame.draw.rect(s, c, (int(bx + k * (bw + 5)), r.y + 52, bw, bh), 0, 2)
	return rects


def draw_select(s, t, sel, boots, pace_sel=0):
	from game.weapons import BOOTS, E, O, PASSIVE_BY_ID
	from core.pace import PACES
	p = PACES[pace_sel]
	# the schedule you picked owns the room: the backdrop is its colour, so the
	# choice is felt before it is read
	pc = p['col']
	s.fill((int(6 + pc[0] * 0.085), int(8 + pc[1] * 0.085), int(13 + pc[2] * 0.085)))
	g = pygame.Surface((W, H), pygame.SRCALPHA)
	for i in range(11):
		a = t * 0.18 + i * TAU / 11
		r = 250 + 90 * math.sin(t * 0.4 + i)
		pygame.draw.circle(g, (pc[0] // 5, pc[1] // 5, pc[2] // 5, 120),
		                   (int(CX + math.cos(a) * r), int(CY + math.sin(a) * r * 0.5)), 110, 2)
	s.blit(g, (0, 0))
	blit_glow(s, CX, 116, 900, pc, 0.18)
	rng = random.Random(2)
	for i in range(70):
		x = rng.randrange(W); y = rng.randrange(H)
		f = 0.15 + 0.85 * abs(math.sin(t * 0.9 + i * 0.7))
		pygame.draw.rect(s, shade(pc, f * 0.5), (x, y, 2, 2))

	draw_text(s, 'BOOT CONFIGURATION', CX, 26, 28, INK, True, 'tc')
	draw_text(s, 'TRAINING SCHEDULE   -   1-4 or click', CX, 62, 12, INK_FAINT, False, 'tc')
	pace_rects = draw_pace_strip(s, 80, pace_sel, t)
	draw_text(s, p['desc'], CX, 158, 12, INK_DIM, False, 'tc')
	from game.director import BIOME_TIME
	draw_text(s, 'xp x%.1f    caches x%.1f    biome %ds    pressure x%.1f    move +%d%%    cooldown %d%%'
	          % (p['xp'], p['chest'], int(BIOME_TIME / p['biome']), p['rate'],
	             round((p['move'] - 1.0) * 100), round(p['cd'] * 100)),
	          CX, 174, 11, shade(pc, 0.9), False, 'tc')

	n = len(boots)
	cols = 4 if n > 6 else 3
	cw = int(min(316, (W - 60 - (cols - 1) * 22) / cols))
	chh = int(clamp((H - 252) / ((n + cols - 1) // cols) - 18, 172, 300))
	gapx, gapy = 22, 18
	x0 = CX - (cols * cw + (cols - 1) * gapx) * 0.5
	y0 = 194
	rects = []
	for i, b in enumerate(boots):
		cx_ = x0 + (i % cols) * (cw + gapx)
		cy_ = y0 + (i // cols) * (chh + gapy)
		r = pygame.Rect(int(cx_), int(cy_), cw, chh)
		rects.append(r)
		em = E[b['emit']]
		op = O[b['op']]
		selq = i == sel
		col = b.get('col', em['col'])
		surf = pygame.Surface((cw, chh), pygame.SRCALPHA)
		pygame.draw.rect(surf, (13, 16, 24, 240), (0, 0, cw, chh), 0, 10)
		pygame.draw.rect(surf, (col[0] // 5, col[1] // 5, col[2] // 5, 230), (0, 0, cw, 66), 0, 10)
		pygame.draw.rect(surf, col if selq else LINE, (0, 0, cw, chh), 2 if selq else 1, 10)
		s.blit(surf, r.topleft)
		if selq: blit_glow(s, r.centerx, r.centery, 250, shade(col, 0.45), 0.3)

		# the unit itself, turning: no two boots are the same body any more
		ux = r.x + 38; uy = r.y + 33
		blit_glow(s, ux, uy, 40, col, 0.45)
		agent_shape(s, ux, uy, t * 0.9 + i, b.get('shape', 'dart'), col, 15.0, t)
		draw_text(s, b['name'], r.x + 70, r.y + 10, 19, INK, True)
		draw_text(s, em['name'], r.x + 70, r.y + 34, 12, shade(em['col'], 1.0))
		mb = b.get('mobility', 'dash')
		draw_text(s, 'BLINK' if mb == 'blink' else 'DASH', r.right - 12, r.y + 10, 11,
		          VIOLET if mb == 'blink' else INK_FAINT, True, 'tr')

		foot = r.y + chh - 24
		sh = int(clamp(chh - 66 - 80, 48, 108))
		_weapon_scene(s, (r.x + 12, r.y + 74, cw - 24, sh), b['emit'], em['col'], t,
		              {b['op']: 1}, None, b.get('shape', 'dart'), col)
		y = r.y + 74 + sh + 6
		room = max(0, int((foot - 8 - y) / 15))
		for line in wrap(b['desc'], 12, cw - 26)[:room]:
			draw_text(s, line, r.x + 13, y, 12, INK_DIM)
			y += 15
		y = foot
		pygame.draw.line(s, (30, 36, 52), (r.x + 13, y - 5), (r.x + cw - 13, y - 5))
		cc = op['col'] or col
		draw_text(s, '%s %s I' % (op['glyph'], op['name']), r.x + 13, y, 11, cc, True)
		pp = PASSIVE_BY_ID[b['passive']]
		draw_text(s, '+ ' + pp['name'], r.right - 13, y, 11, INK_FAINT, False, 'tr')

	draw_text(s, 'ARROWS choose    1-4 schedule    ENTER boot    ESC back', CX, H - 30, 13, CYAN, True, 'tc')
	return rects, pace_rects


# ================================================================== MENUS
def draw_title(s, t, sel, items, hiscore):
	s.fill((5, 7, 12))
	rng = random.Random(9)
	for i in range(64):
		x = rng.randrange(W); y = rng.randrange(H)
		f = 0.2 + 0.8 * abs(math.sin(t * 0.7 + i))
		pygame.draw.rect(s, shade((60, 120, 200), f * 0.4), (x, y, 2, 2))
	for i in range(9):
		a = t * 0.22 + i * TAU / 9
		r = 210 + 40 * math.sin(t * 0.5 + i)
		pygame.draw.circle(s, (16, 26, 44), (int(CX + math.cos(a) * r), int(260 + math.sin(a) * r * 0.42)), 60, 1)

	g = text(TITLE, 74, INK, True)
	blit_glow(s, CX, 200, 260, (40, 120, 220), 0.55)
	s.blit(g, (CX - g.get_width() * 0.5, 156))
	for i, ch in enumerate(TITLE):
		pass
	draw_text(s, SUBTITLE, CX, 238, 17, CYAN, False, 'tc')
	draw_text(s, 'you are the model. they are the data. survive the training run.',
	          CX, 268, 13, INK_DIM, False, 'tc')

	y = 350
	for i, it in enumerate(items):
		selq = i == sel
		col = CYAN if selq else INK_DIM
		if selq:
			pygame.draw.rect(s, (14, 22, 34), (CX - 150, y - 8, 300, 34), 0, 6)
			pygame.draw.rect(s, CYAN, (CX - 150, y - 8, 300, 34), 1, 6)
			draw_text(s, '>', CX - 132, y, 18, CYAN, True)
		draw_text(s, it, CX, y, 18, col, selq, 'tc')
		y += 44

	if hiscore:
		draw_text(s, 'best: %s  -  lv %d  -  %d kills%s' % (hiscore.get('time', '0:00'),
		          hiscore.get('level', 1), hiscore.get('kills', 0),
		          '  -  ' + hiscore['pace'] if hiscore.get('pace') else ''),
		          CX, H - 70, 13, INK_FAINT, False, 'tc')
	draw_text(s, 'WASD or HOLD LEFT MOUSE to move   SPACE / RIGHT CLICK dash   ESC pause',
	          CX, H - 42, 12, INK_FAINT, False, 'tc')
	draw_text(s, 'F11 fullscreen   F5 mouse mode   F6 screenshake   F2 bloom   F3 fps   M mute       '
	          'runs at %dx%d  (--res 1280x720 for max framerate)' % (W, H),
	          CX, H - 26, 12, INK_FAINT, False, 'tc')


def draw_end(w, s, t, win, scores=None):
	"""A run only ends by dying. `win` here means it converged on the way down."""
	o = pygame.Surface((W, H), pygame.SRCALPHA)
	o.fill((4, 6, 10, 240))
	s.blit(o, (0, 0))
	col = RED
	title = 'MODEL COLLAPSE'
	sub = 'converged, then kept going until it did not' if win else 'the gradients consumed you'
	sc = ease_pop(min(1.0, t * 1.6))
	g = text(title, int(48 * min(1.6, sc)), col, True)
	s.blit(g, (CX - g.get_width() * 0.5, 54))
	draw_text(s, sub, CX, 112, 15, INK_DIM, False, 'tc')
	if win:
		draw_text(s, 'CONVERGED', CX, 134, 14, GOLD, True, 'tc')

	d = w.director
	x = 60
	y = 176
	RW = int(W * 0.44)
	panel(s, (x - 20, y - 16, RW, 300), 200)
	rows = [('schedule', w.pace['name']), ('unit', (w.boot or {}).get('name', '-')),
	        ('survived', d.time_str()), ('level', str(w.player.level)),
	        ('laps past the end', str(d.endless)),
	        ('kills', str(w.stats['kills'])), ('damage dealt', '%d' % w.stats['dmg']),
	        ('damage taken', '%d' % w.stats['taken']),
	        ('evolutions', str(w.stats['evos'])), ('fusions', str(w.stats['fuses'])),
	        ('final biome', w.level['name'])]
	for k, v in rows:
		draw_text(s, k, x, y, 14, INK_FAINT)
		draw_text(s, v, x + RW - 56, y, 14, INK, True, 'tr')
		y += 25

	# ---- the board for this schedule only: runs are not comparable across them
	bx = 60 + RW + 20
	bw = W - bx - 60
	panel(s, (bx, 160, bw, 300), 200)
	draw_text(s, 'BEST RUNS  -  ' + w.pace['name'], bx + 18, 172, 15, shade(w.pace['col'], 0.95), True)
	yy = 202
	board = (scores or {}).get(w.pace['id'], [])
	if not board:
		draw_text(s, 'no runs recorded on this schedule yet', bx + 18, yy, 13, INK_FAINT)
	for i, e in enumerate(board[:8]):
		me = e.get('now')
		c = GOLD if me else INK_DIM
		draw_text(s, '%d.' % (i + 1), bx + 18, yy, 13, INK_FAINT, True)
		draw_text(s, e.get('time', '0:00'), bx + 48, yy, 13, c, bool(me))
		draw_text(s, 'lv %d' % e.get('level', 1), bx + 122, yy, 13, c)
		draw_text(s, '%d kills' % e.get('kills', 0), bx + 190, yy, 13, c)
		draw_text(s, e.get('unit', ''), bx + 300, yy, 12, INK_FAINT)
		if e.get('converged'):
			draw_text(s, 'CONVERGED', bx + bw - 18, yy, 11, GOLD, True, 'tr')
		yy += 22

	y = 486
	draw_text(s, 'FINAL BUILD', CX, y, 14, INK, True, 'tc')
	y += 24
	for pr in w.arsenal.procs:
		ops = '  '.join('%s%s' % (O[k]['glyph'], rk(v)) for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]))
		line = '%s  %s   %s' % (E[pr.emit]['glyph'], pr.name, ops)
		draw_text(s, line, CX, y, 13, GOLD if pr.evo else INK_DIM, bool(pr.evo), 'tc')
		y += 19
	draw_text(s, 'ENTER  run again      ESC  menu', CX, H - 40, 14, CYAN, True, 'tc')
