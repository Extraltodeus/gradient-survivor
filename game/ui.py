"""HUD, level-up cards, pause inspector, codex, menus and end screens."""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.weapons import E, O, SYN, EVO_BY_EMIT, PASSIVE_BY_ID, MAX_OPS_PER_PROC

ROMAN = ('', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII')
GRACE = 0.4     # input lock when the level-up screen opens, anti-misclick

CONTROLS = (
	('WASD / arrows', 'move'),
	('hold LMB', 'move toward cursor'),
	('SPACE / RMB', 'dash (brief i-frames)'),
	('ESC or P', 'pause / this screen'),
	('1-4 or click', 'pick an upgrade'),
	('R / X / TAB', 'reroll / banish / skip'),
	('TAB (sandbox)', 'open the bench'),
	('F11 or Alt+Enter', 'fullscreen'),
	('F5', 'mouse mode: pointer or drag'),
	('F2 / F4', 'bloom / scanlines'),
	('F3', 'fps counter'),
	('M', 'mute'),
	('Q', 'quit to menu'),
)


def rk(n): return ROMAN[n] if n < len(ROMAN) else str(n)


def trim(s, n):
	return s if len(s) <= n else s[:n - 2] + '..'


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
	"""Diagram for a whole emitter (new process / rank / fusion cards)."""
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

	# ---- processes column
	py = 78
	for pr in w.arsenal.procs:
		draw_proc_row(w, s, 10, py, pr)
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
	nm = pr.name
	if len(nm) > 30: nm = nm[:29] + '.'
	draw_text(s, nm, x + size + 8, y + 1, 12, GOLD if pr.evo else INK, bool(pr.evo))
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

	def snapshot(self, s):
		small = pygame.transform.smoothscale(s, (W // 6, H // 6))
		self.snap = pygame.transform.smoothscale(small, (W, H))
		dark = pygame.Surface((W, H))
		dark.fill((6, 8, 14)); dark.set_alpha(160)
		self.snap.blit(dark, (0, 0))

	def event(self, ev, w):
		# Commit actions are locked for GRACE seconds so a click or keypress meant
		# for the fight cannot pick an upgrade the instant the screen appears.
		live = self.t >= GRACE
		if ev.type == pygame.KEYDOWN:
			n = len(self.offers)
			if ev.key in (pygame.K_LEFT, pygame.K_a):
				self.sel = (self.sel - 1) % n; w.audio.play('move', 0.6)
			elif ev.key in (pygame.K_RIGHT, pygame.K_d):
				self.sel = (self.sel + 1) % n; w.audio.play('move', 0.6)
			elif not live:
				return
			elif ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
				self.pick(w)
			elif pygame.K_1 <= ev.key <= pygame.K_4:
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
		elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and live:
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
		self.offers = build_offers(w, len(self.offers))
		self.sel = min(self.sel, len(self.offers) - 1)
		self.t = 0.0
		w.audio.play('gem', 0.8)

	def banish(self, w):
		if w.player.banishes <= 0:
			w.audio.play('deny', 0.8); return
		w.player.banishes -= 1
		w.banned.add(self.offers[self.sel].key)
		from game.offers import build_offers
		self.offers = build_offers(w, len(self.offers))
		self.sel = min(self.sel, len(self.offers) - 1)
		self.t = 0.0
		w.audio.play('deny', 1.0)

	def skip(self, w):
		w.player.heal(12)
		w.audio.play('pick', 0.6)
		self.done = 'skipped'

	def update(self, dt):
		self.t += dt

	def draw(self, s, w):
		if self.snap: s.blit(self.snap, (0, 0))
		else: s.fill((6, 8, 14))
		t = min(1.0, self.t * 3.4)
		e = ease_out(t)

		draw_text(s, 'EPOCH %d' % w.player.level, CX, int(46 - 20 * (1 - e)), 34, INK, True, 'tc')
		locked = self.t < GRACE
		draw_text(s, 'select a mutation', CX, 86, 14, INK_DIM if not locked else INK_FAINT, False, 'tc')
		if locked:
			bar(s, CX - 60, 106, 120, 3, self.t / GRACE, shade(CYAN, 0.55), (22, 26, 36), 2)

		n = len(self.offers)
		cw = 286 if n <= 3 else 250
		gap = 22
		total = n * cw + (n - 1) * gap
		x0 = CX - total * 0.5
		ch = 392
		cy = 124
		self.rects = []
		mouse = pygame.mouse.get_pos()

		for i, o in enumerate(self.offers):
			x = x0 + i * (cw + gap)
			r = pygame.Rect(int(x), int(cy), int(cw), int(ch))
			self.rects.append(r)
			self.draw_card(s, o, r, i == self.sel, e, i, n)

		# footer
		pl = w.player
		fy = cy + ch + 22
		dim = self.t < GRACE
		items = [('ENTER / CLICK', 'take', INK_FAINT if dim else INK),
		         ('R', 'reroll (%d)' % pl.rerolls, INK_FAINT if dim else (GOLD if pl.rerolls else INK_FAINT)),
		         ('X', 'banish (%d)' % pl.banishes, INK_FAINT if dim else (VIOLET if pl.banishes else INK_FAINT)),
		         ('TAB / ESC', 'skip +12 hp', INK_DIM)]
		tw = sum(text_w(a + '  ' + b, 13) + 34 for a, b in [(a, b) for a, b, _ in items])
		fx_ = CX - tw * 0.5
		for key, lbl, col in items:
			g = text(key, 13, col, True)
			s.blit(g, (fx_, fy))
			fx_ += g.get_width() + 7
			g = text(lbl, 13, INK_FAINT)
			s.blit(g, (fx_, fy))
			fx_ += g.get_width() + 27

	def draw_card(self, s, o, r, sel, e, i, n):
		t = clamp(e * 1.4 - i * 0.10, 0.0, 1.0)
		if t <= 0.01: return
		off = int((1.0 - ease_out(t)) * 60)
		rr = pygame.Rect(r.x, r.y + off, r.w, r.h)
		col = o.col
		rare = RARITY_COL.get(o.rarity, INK_DIM)

		surf = pygame.Surface((rr.w, rr.h), pygame.SRCALPHA)
		a = int(238 * t)
		pygame.draw.rect(surf, (13, 16, 24, a), (0, 0, rr.w, rr.h), 0, 10)
		pygame.draw.rect(surf, (rare[0], rare[1], rare[2], int((255 if sel else 110) * t)),
		                 (0, 0, rr.w, rr.h), 2 if sel else 1, 10)
		# header band
		pygame.draw.rect(surf, (col[0] // 5, col[1] // 5, col[2] // 5, a), (0, 0, rr.w, 92), 0, 10)
		pygame.draw.line(surf, (rare[0], rare[1], rare[2], int(160 * t)), (0, 92), (rr.w, 92))
		s.blit(surf, rr.topleft)

		if sel:
			blit_glow(s, rr.centerx, rr.centery, 260, shade(col, 0.5), 0.30)

		glyph_box(s, rr.x + 16, rr.y + 18, 56, o.glyph, col, (10, 13, 20))
		draw_text(s, trim(o.title, 20), rr.x + 84, rr.y + 22, 19, INK, True)
		draw_text(s, trim(o.sub, 24), rr.x + 84, rr.y + 47, 12, shade(col, 0.95))
		# (rank pips are drawn below for op cards)
		kindlbl = {'op': 'OP', 'new': 'EMITTER', 'rank': 'RANK', 'passive': 'SYSTEM',
		           'fuse': 'FUSION', 'heal': 'REPAIR'}.get(o.kind, '')
		draw_text(s, kindlbl, rr.x + rr.w - 14, rr.y + 68, 11, rare, True, 'tr')
		if o.kind == 'op' and o.proc is not None:
			cur = o.proc.ops.get(o.key[3:], 0)
			pips(s, rr.x + 84, rr.y + 68, cur + 1, MAX_TRAIT_RK, col)

		# --- animated diagram of the actual effect
		art_key = o.key.split(':', 1)[1] if ':' in o.key else o.key
		if o.kind == 'fuse': art_key = o.proc.emit if o.proc else 'bolt'
		elif o.kind == 'rank': art_key = o.proc.emit if o.proc else 'bolt'
		draw_art(s, (rr.x + 14, rr.y + 100, rr.w - 28, 78), o.kind, art_key, col, self.t)

		y = rr.y + 186
		for line in wrap(o.desc, 13, rr.w - 32)[:3]:
			draw_text(s, line, rr.x + 16, y, 13, INK_DIM)
			y += 17

		# the note banner is laid out first: it owns the bottom of the card, and
		# everything above has to know where it stops
		note_lines = wrap(o.note, 12, rr.w - 34)[:2] if o.note else []
		note_h = 18 + 15 * len(note_lines)
		note_top = rr.y + rr.h - (note_h + 10 if note_lines else 12)

		# process preview
		if o.proc is not None and o.kind in ('op', 'rank', 'fuse'):
			y = max(y + 10, rr.y + 244)
			pygame.draw.line(s, LINE, (rr.x + 16, y - 8), (rr.x + rr.w - 16, y - 8))
			draw_text(s, 'PROCESS STATE', rr.x + 16, y, 10, INK_FAINT, True)
			y += 16
			ox = rr.x + 16
			for k, v in sorted(o.proc.ops.items(), key=lambda kv: -kv[1]):
				d = O[k]
				cc = d['col'] or INK_DIM
				lbl = d['glyph'] + rk(v)
				g = text(lbl, 13, cc, True)
				if ox + g.get_width() + 6 > rr.x + rr.w - 16:
					ox = rr.x + 16; y += 17
				s.blit(g, (ox, y))
				ox += g.get_width() + 9
			y += 22
			for sid in o.proc.syn:
				draw_text(s, '* ' + sid, rr.x + 16, y, 11, VIOLET, True)
				y += 14
			p = o.proc.evo_progress()
			if p and not o.proc.evo and y + 26 < note_top:
				ev, missing, frac = p
				draw_text(s, trim(ev['name'], 24), rr.x + 16, y + 4, 11, shade(GOLD, 0.8), True)
				bar(s, rr.x + 16, y + 20, rr.w - 32, 3, frac, GOLD, (30, 28, 20), 2)
			elif o.proc.evo and y + 16 < note_top:
				draw_text(s, 'EVOLVED', rr.x + 16, y + 4, 11, GOLD, True)

		if note_lines:
			pygame.draw.rect(s, (o.note_col[0] // 6, o.note_col[1] // 6, o.note_col[2] // 6),
			                 (rr.x + 10, note_top, rr.w - 20, note_h), 0, 6)
			for j, line in enumerate(note_lines):
				draw_text(s, line, rr.x + rr.w * 0.5, note_top + 6 + j * 15, 12, o.note_col, True, 'tc')

		draw_text(s, str(i + 1), rr.x + rr.w - 16, rr.y + 16, 14, INK_FAINT, True, 'tr')


# ================================================================= PAUSE
def draw_pause(w, s, tab=0):
	o = pygame.Surface((W, H), pygame.SRCALPHA)
	o.fill((5, 7, 12, 225))
	s.blit(o, (0, 0))
	pl = w.player
	draw_text(s, 'SUSPENDED', CX, 26, 30, INK, True, 'tc')
	draw_text(s, 'ESC resume   -   Q quit to menu', CX, 62, 13, INK_DIM, False, 'tc')

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
def draw_codex(s, page, scroll):
	s.fill((6, 8, 13))
	draw_text(s, 'CODEX', 40, 26, 30, INK, True)
	tabs = ['EMITTERS', 'OPS', 'SYNERGIES', 'EVOLUTIONS']
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
	s.fill((5, 7, 12))
	rng = random.Random(2)
	for i in range(70):
		x = rng.randrange(W); y = rng.randrange(H)
		f = 0.15 + 0.85 * abs(math.sin(t * 0.9 + i * 0.7))
		pygame.draw.rect(s, shade((50, 110, 190), f * 0.35), (x, y, 2, 2))

	draw_text(s, 'BOOT CONFIGURATION', CX, 26, 28, INK, True, 'tc')
	draw_text(s, 'TRAINING SCHEDULE   -   1-4 or click', CX, 62, 12, INK_FAINT, False, 'tc')
	pace_rects = draw_pace_strip(s, 80, pace_sel, t)
	p = PACES[pace_sel]
	draw_text(s, p['desc'], CX, 158, 12, INK_DIM, False, 'tc')
	from game.director import BIOME_TIME
	draw_text(s, 'xp x%.1f    caches x%.1f    biome %ds    pressure x%.1f    move +%d%%    cooldown %d%%'
	          % (p['xp'], p['chest'], int(BIOME_TIME / p['biome']), p['rate'],
	             round((p['move'] - 1.0) * 100), round(p['cd'] * 100)),
	          CX, 174, 11, shade(p['col'], 0.85), False, 'tc')

	n = len(boots)
	cols = 3
	cw, chh = 340, 196
	gapx, gapy = 26, 22
	rows = (n + cols - 1) // cols
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
		col = em['col']
		surf = pygame.Surface((cw, chh), pygame.SRCALPHA)
		pygame.draw.rect(surf, (13, 16, 24, 240), (0, 0, cw, chh), 0, 10)
		pygame.draw.rect(surf, (col[0] // 5, col[1] // 5, col[2] // 5, 230), (0, 0, cw, 74), 0, 10)
		pygame.draw.rect(surf, col if selq else LINE, (0, 0, cw, chh), 2 if selq else 1, 10)
		s.blit(surf, r.topleft)
		if selq: blit_glow(s, r.centerx, r.centery, 250, shade(col, 0.45), 0.3)

		glyph_box(s, r.x + 14, r.y + 14, 46, em['glyph'], col, (10, 13, 20))
		draw_text(s, b['name'], r.x + 72, r.y + 18, 20, INK, True)
		draw_text(s, em['name'], r.x + 72, r.y + 44, 12, shade(col, 1.0))
		y = r.y + 86
		for line in wrap(b['desc'], 13, cw - 30)[:3]:
			draw_text(s, line, r.x + 15, y, 13, INK_DIM)
			y += 17
		y = r.y + chh - 42
		pygame.draw.line(s, (30, 36, 52), (r.x + 15, y - 6), (r.x + cw - 15, y - 6))
		cc = op['col'] or col
		draw_text(s, '%s %s I' % (op['glyph'], op['name']), r.x + 15, y, 12, cc, True)
		draw_text(s, 'grows well with: ' + ', '.join(em['affinity'][:2]), r.x + cw - 15, y + 1, 10,
		          INK_FAINT, False, 'tr')
		p = PASSIVE_BY_ID[b['passive']]
		draw_text(s, '+ ' + p['name'], r.x + 15, y + 17, 11, INK_FAINT)

	draw_text(s, 'ARROWS choose    1-4 schedule    ENTER boot    ESC back', CX, H - 40, 13, CYAN, True, 'tc')
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
	draw_text(s, 'F11 fullscreen   F5 mouse mode   F2 bloom   F3 fps   M mute       '
	          'runs at %dx%d  (--res 1280x720 for max framerate)' % (W, H),
	          CX, H - 26, 12, INK_FAINT, False, 'tc')


def draw_end(w, s, t, win):
	o = pygame.Surface((W, H), pygame.SRCALPHA)
	o.fill((4, 6, 10, 240))
	s.blit(o, (0, 0))
	col = GOLD if win else RED
    # noqa
	title = 'CONVERGED' if win else 'MODEL COLLAPSE'
	sub = 'you survived the training run' if win else 'the gradients consumed you'
	sc = ease_pop(min(1.0, t * 1.6))
	g = text(title, int(52 * min(1.6, sc)), col, True)
	s.blit(g, (CX - g.get_width() * 0.5, 70))
	draw_text(s, sub, CX, 136, 15, INK_DIM, False, 'tc')

	d = w.director
	x = CX - 300
	y = 190
	panel(s, (x - 20, y - 16, 640, 250), 200)
	rows = [('schedule', w.pace['name']), ('survived', d.time_str()), ('level', str(w.player.level)),
	        ('kills', str(w.stats['kills'])), ('damage dealt', '%d' % w.stats['dmg']),
	        ('damage taken', '%d' % w.stats['taken']),
	        ('evolutions', str(w.stats['evos'])), ('fusions', str(w.stats['fuses'])),
	        ('final biome', w.level['name'])]
	for k, v in rows:
		draw_text(s, k, x, y, 14, INK_FAINT)
		draw_text(s, v, x + 600, y, 14, INK, True, 'tr')
		y += 27

	y = 470
	draw_text(s, 'FINAL BUILD', CX, y, 14, INK, True, 'tc')
	y += 26
	for pr in w.arsenal.procs:
		ops = '  '.join('%s%s' % (O[k]['glyph'], rk(v)) for k, v in sorted(pr.ops.items(), key=lambda kv: -kv[1]))
		line = '%s  %s   %s' % (E[pr.emit]['glyph'], pr.name, ops)
		draw_text(s, line, CX, y, 13, GOLD if pr.evo else INK_DIM, bool(pr.evo), 'tc')
		y += 19
	draw_text(s, 'ENTER  restart      ESC  menu', CX, H - 44, 14, CYAN, True, 'tc')
