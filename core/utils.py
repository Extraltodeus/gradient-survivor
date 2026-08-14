"""Math helpers, spatial hash and cached surface factories."""

import math, random
import pygame
from core.settings import FONT_MONO

TAU = math.pi * 2.0
_OFS = 1 << 14   # spatial hash origin shift so negative coords floor correctly

def clamp(v, a, b): return a if v < a else (b if v > b else v)
def lerp(a, b, t): return a + (b - a) * t
def approach(v, target, rate):
	d = target - v
	return target if abs(d) <= rate else v + (rate if d > 0 else -rate)

def dist(ax, ay, bx, by): return math.hypot(bx - ax, by - ay)
def dist2(ax, ay, bx, by):
	dx = bx - ax; dy = by - ay
	return dx * dx + dy * dy

def norm(dx, dy):
	m = math.hypot(dx, dy)
	return (0.0, 0.0) if m < 1e-9 else (dx / m, dy / m)

def ang(dx, dy): return math.atan2(dy, dx)
def vec(a, m=1.0): return (math.cos(a) * m, math.sin(a) * m)

def ease_out(t): return 1.0 - (1.0 - t) ** 3
def ease_in(t): return t * t * t
def ease_pop(t):  # overshoot then settle
	return 1.0 + 2.6 * math.sin(min(1.0, t) * math.pi) * (1.0 - t) ** 1.5

def shortest_angle(a, b):
	d = (b - a + math.pi) % TAU - math.pi
	return d

def mix(c1, c2, t):
	t = clamp(t, 0.0, 1.0)
	return (int(c1[0] + (c2[0] - c1[0]) * t),
	        int(c1[1] + (c2[1] - c1[1]) * t),
	        int(c1[2] + (c2[2] - c1[2]) * t))

def shade(c, f):
	return (clamp(int(c[0] * f), 0, 255), clamp(int(c[1] * f), 0, 255), clamp(int(c[2] * f), 0, 255))


class SpatialHash:
	"""Uniform grid bucketing. Rebuilt every frame; query returns a superset."""
	__slots__ = ('cells', 'inv', 'size')

	def __init__(self, size):
		self.size = size
		self.inv = 1.0 / size
		self.cells = {}

	def clear(self): self.cells.clear()

	def insert(self, o):
		k = (int((o.x + _OFS) * self.inv), int((o.y + _OFS) * self.inv))
		c = self.cells.get(k)
		if c is None: self.cells[k] = [o]
		else: c.append(o)

	def build(self, objs):
		self.cells.clear()
		inv = self.inv; cells = self.cells
		for o in objs:
			k = (int((o.x + _OFS) * inv), int((o.y + _OFS) * inv))
			c = cells.get(k)
			if c is None: cells[k] = [o]
			else: c.append(o)

	def query(self, x, y, r):
		out = []
		inv = self.inv; cells = self.cells; g = out.extend
		x0 = int((x - r + _OFS) * inv); x1 = int((x + r + _OFS) * inv)
		y0 = int((y - r + _OFS) * inv); y1 = int((y + r + _OFS) * inv)
		for gx in range(x0, x1 + 1):
			for gy in range(y0, y1 + 1):
				c = cells.get((gx, gy))
				if c: g(c)
		return out


# ---------------------------------------------------------------- surfaces
_glow_cache = {}
_disc_cache = {}
_ring_cache = {}
_poly_cache = {}

def glow(radius, color, power=1.0):
	"""Additive radial gradient. Blit with special_flags=BLEND_ADD."""
	r = int(radius)
	if r < 2: r = 2
	if r > 24: r = (r // 4) * 4
	key = (r, color[0] >> 3, color[1] >> 3, color[2] >> 3, int(power * 8))
	s = _glow_cache.get(key)
	if s is not None: return s
	d = r * 2
	s = pygame.Surface((d, d))
	steps = min(r, 26)
	for i in range(steps, 0, -1):
		t = i / steps
		rr = int(r * t)
		f = ((1.0 - t) ** 2.1) * power
		col = (clamp(int(color[0] * f), 0, 255), clamp(int(color[1] * f), 0, 255), clamp(int(color[2] * f), 0, 255))
		pygame.draw.circle(s, col, (r, r), rr)
	# no colorkey: BLEND_ADD already treats black as transparent, and a colorkey
	# forces a per-pixel test that costs more than the pixels it skips
	_glow_cache[key] = s
	return s

def disc(radius, color, alpha=255):
	r = max(1, int(radius))
	key = (r, color, alpha)
	s = _disc_cache.get(key)
	if s is None:
		s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
		pygame.draw.circle(s, (color[0], color[1], color[2], alpha), (r + 1, r + 1), r)
		_disc_cache[key] = s
	return s

def ring(radius, color, width=2, alpha=255):
	r = max(2, int(radius))
	key = (r, color, width, alpha)
	s = _ring_cache.get(key)
	if s is None:
		s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
		pygame.draw.circle(s, (color[0], color[1], color[2], alpha), (r + 2, r + 2), r, width)
		_ring_cache[key] = s
	return s

def ngon(sides, radius, color, width=0, rot=0.0):
	"""Cached regular polygon surface (rotation quantised to 16 steps)."""
	r = max(2, int(radius))
	rq = int(rot / TAU * 16) % 16
	key = (sides, r, color, width, rq)
	s = _poly_cache.get(key)
	if s is None:
		pad = width + 2
		s = pygame.Surface((r * 2 + pad * 2, r * 2 + pad * 2), pygame.SRCALPHA)
		c = r + pad
		a0 = rq / 16.0 * TAU
		pts = [(c + math.cos(a0 + i * TAU / sides) * r, c + math.sin(a0 + i * TAU / sides) * r) for i in range(sides)]
		pygame.draw.polygon(s, color, pts, width)
		_poly_cache[key] = s
	return s

_glow_half = {}

def glow_c(radius, color, power=1.0):
	"""glow() plus its half-extent, so callers can batch blits without get_size()."""
	r = int(radius)
	if r < 2: r = 2
	if r > 24: r = (r // 4) * 4
	key = (r, color[0] >> 3, color[1] >> 3, color[2] >> 3, int(power * 8))
	e = _glow_half.get(key)
	if e is None:
		s = glow(radius, color, power)
		e = (s, s.get_width() * 0.5)
		_glow_half[key] = e
	return e


def blit_c(dst, src, x, y, flags=0):
	dst.blit(src, (x - src.get_width() * 0.5, y - src.get_height() * 0.5), None, flags)

def blit_glow(dst, x, y, radius, color, power=1.0):
	g = glow(radius, color, power)
	dst.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5), None, pygame.BLEND_ADD)


# ---------------------------------------------------------------- text
_fonts = {}
_text_cache = {}

def font(size, bold=False):
	key = (size, bold)
	f = _fonts.get(key)
	if f is None:
		f = pygame.font.SysFont(FONT_MONO, size, bold=bold)
		_fonts[key] = f
	return f

def text(s, size, color, bold=False):
	key = (s, size, color, bold)
	t = _text_cache.get(key)
	if t is None:
		t = font(size, bold).render(s, True, color)
		if len(_text_cache) > 3000: _text_cache.clear()
		_text_cache[key] = t
	return t

def draw_text(dst, s, x, y, size, color, bold=False, anchor='tl'):
	t = text(s, size, color, bold)
	w, h = t.get_size()
	if   anchor == 'c':  x -= w * 0.5; y -= h * 0.5
	elif anchor == 'tc': x -= w * 0.5
	elif anchor == 'tr': x -= w
	elif anchor == 'ml': y -= h * 0.5
	elif anchor == 'mr': x -= w; y -= h * 0.5
	elif anchor == 'bl': y -= h
	dst.blit(t, (int(x), int(y)))
	return t.get_size()

def text_w(s, size, bold=False): return font(size, bold).size(s)[0]

def wrap(s, size, width, bold=False):
	f = font(size, bold)
	words = s.split(' ')
	lines, cur = [], ''
	for w in words:
		t = w if not cur else cur + ' ' + w
		if f.size(t)[0] <= width: cur = t
		else:
			if cur: lines.append(cur)
			cur = w
	if cur: lines.append(cur)
	return lines


def rrect(dst, rect, color, radius=6, width=0):
	pygame.draw.rect(dst, color, rect, width, border_radius=radius)

def weighted(rng, pairs):
	"""pairs: [(item, weight), ...]"""
	tot = 0.0
	for _, w in pairs: tot += w
	if tot <= 0: return pairs[0][0] if pairs else None
	r = rng.random() * tot
	for it, w in pairs:
		r -= w
		if r <= 0: return it
	return pairs[-1][0]
