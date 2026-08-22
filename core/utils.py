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

_radial_cache = {}

def _radial(radius, color, power, profile, key):
	"""Additive disc whose brightness follows `profile(t)`, t = 0 centre .. 1 rim.

	BLEND_ADD ignores the source alpha entirely, so a flat disc blitted at alpha 6
	still adds its full colour to every pixel it covers -- which is exactly how a
	big field ends up as an opaque slab over the player. The falloff has to live in
	the pixels, so it is baked here once per (radius, colour, power) and cached."""
	r = max(2, int(radius))
	if r > 16: r = (r // 8) * 8
	k = (key, r, color[0] >> 3, color[1] >> 3, color[2] >> 3, int(power * 10))
	s = _radial_cache.get(k)
	if s is not None: return s
	s = pygame.Surface((r * 2 + 2, r * 2 + 2))
	steps = min(r, 44)
	c = r + 1
	for i in range(steps, 0, -1):
		t = i / steps
		f = profile(t) * power
		if f <= 0.002: continue
		col = (clamp(int(color[0] * f), 0, 255), clamp(int(color[1] * f), 0, 255),
		       clamp(int(color[2] * f), 0, 255))
		pygame.draw.circle(s, col, (c, c), max(1, int(r * t)))
	_radial_cache[k] = s
	return s


def _rim(t):
	# nothing at all until the outer third, then a soft band up to the edge
	f = (t - 0.66) * 2.94
	return f * f if f > 0.0 else 0.0


def hollow_glow(radius, color, power=0.55):
	"""Rim-lit band of light with a completely clear centre: safe to stand in."""
	return _radial(radius, color, power, _rim, 'h')


def soft_disc(radius, color, power=0.34):
	"""Filled wash that fades out toward the rim. Safe to blit additively."""
	return _radial(radius, color, power, lambda t: (1.0 - t) ** 1.6 * 0.55 + 0.45 * (1.0 - t * t), 's')


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

# ============================================================ AGENT SHAPES
# Each boot profile is a different unit, and a unit you cannot tell apart from
# the next one is not a choice. These are drawn from vectors at any radius so the
# same routine serves the player, the boot cards and the end screen.
AGENT_SHAPES = ('dart', 'hex', 'trilobe', 'annulus', 'cross', 'blade', 'prism')


def agent_shape(s, x, y, a, shape, col, r=11.0, t=0.0, filled=True, wire=None):
	"""Draw one unit facing `a`. `filled` off = the invulnerability blink."""
	wire = wire if wire is not None else (255, 255, 255)
	cs = math.cos(a); sn = math.sin(a)
	def P(fwd, side):
		return (x + cs * fwd - sn * side, y + sn * fwd + cs * side)

	if shape == 'hex':
		pts = [P(math.cos(i * TAU / 6 + 0.5) * r * 1.25, math.sin(i * TAU / 6 + 0.5) * r * 1.25)
		       for i in range(6)]
		inner = [P(math.cos(i * TAU / 6 + 0.5) * r * 0.6, math.sin(i * TAU / 6 + 0.5) * r * 0.6)
		         for i in range(6)]
		if filled:
			pygame.draw.polygon(s, col, pts)
			pygame.draw.polygon(s, wire, pts, 1)
			pygame.draw.polygon(s, shade(col, 0.35), inner)
		else:
			pygame.draw.polygon(s, shade(col, 0.5), pts, 1)
		pygame.draw.line(s, wire if filled else shade(col, 0.5), P(r * 0.6, 0), P(r * 1.7, 0), 2)
	elif shape == 'trilobe':
		for i in range(3):
			aa = a + t * 1.9 + i * TAU / 3
			px = x + math.cos(aa) * r * 0.72; py = y + math.sin(aa) * r * 0.72
			if filled:
				pygame.draw.circle(s, col, (int(px), int(py)), max(2, int(r * 0.52)))
				pygame.draw.circle(s, wire, (int(px), int(py)), max(2, int(r * 0.52)), 1)
			else:
				pygame.draw.circle(s, shade(col, 0.5), (int(px), int(py)), max(2, int(r * 0.52)), 1)
		pygame.draw.polygon(s, wire if filled else shade(col, 0.4),
		                    [P(r * 1.6, 0), P(r * 0.2, r * 0.4), P(r * 0.2, -r * 0.4)],
		                    0 if filled else 1)
	elif shape == 'annulus':
		g = ring(int(r * 1.5), col, max(2, int(r * 0.34)), 255 if filled else 110)
		s.blit(g, (x - g.get_width() * 0.5, y - g.get_height() * 0.5))
		for i in range(4):
			aa = a - t * 1.3 + i * TAU / 4
			pygame.draw.line(s, wire if filled else shade(col, 0.4),
			                 (x + math.cos(aa) * r * 0.35, y + math.sin(aa) * r * 0.35),
			                 (x + math.cos(aa) * r * 1.05, y + math.sin(aa) * r * 1.05), 2)
		pygame.draw.circle(s, col if filled else shade(col, 0.4), (int(x), int(y)), max(2, int(r * 0.3)))
	elif shape == 'cross':
		w_ = r * 0.42
		for k in (0, 1):
			b = a + k * math.pi * 0.5
			c2 = math.cos(b); s2 = math.sin(b)
			L = r * (1.55 if k == 0 else 1.05)
			pts = [(x + c2 * L - s2 * w_, y + s2 * L + c2 * w_),
			       (x + c2 * L + s2 * w_, y + s2 * L - c2 * w_),
			       (x - c2 * L + s2 * w_, y - s2 * L - c2 * w_),
			       (x - c2 * L - s2 * w_, y - s2 * L + c2 * w_)]
			if filled:
				pygame.draw.polygon(s, col, pts)
				pygame.draw.polygon(s, wire, pts, 1)
			else:
				pygame.draw.polygon(s, shade(col, 0.5), pts, 1)
	elif shape == 'blade':
		pts = [P(r * 1.9, 0), P(r * 0.1, r * 0.85), P(-r * 0.9, 0), P(r * 0.1, -r * 0.85)]
		if filled:
			pygame.draw.polygon(s, col, pts)
			pygame.draw.polygon(s, wire, pts, 1)
			pygame.draw.line(s, wire, P(r * 1.9, 0), P(-r * 0.9, 0), 1)
		else:
			pygame.draw.polygon(s, shade(col, 0.5), pts, 1)
	elif shape == 'prism':
		k = 0.55 + 0.45 * abs(math.sin(t * 2.2))
		pts = [P(r * 1.5, 0), P(0, r * 1.0), P(-r * 1.1, 0), P(0, -r * 1.0)]
		inner = [P(r * 1.5 * k, 0), P(0, r * 1.0 * k), P(-r * 1.1 * k, 0), P(0, -r * 1.0 * k)]
		if filled:
			pygame.draw.polygon(s, shade(col, 0.55), pts)
			pygame.draw.polygon(s, wire, pts, 1)
			pygame.draw.polygon(s, col, inner)
		else:
			pygame.draw.polygon(s, shade(col, 0.5), pts, 1)
	else:                                   # dart, the original
		pts = [P(r * 1.7, 0), P(-r * 0.737, r * 0.675), P(-r * 0.5, 0), P(-r * 0.737, -r * 0.675)]
		if filled:
			pygame.draw.polygon(s, col, pts)
			pygame.draw.polygon(s, wire, pts, 1)
		else:
			pygame.draw.polygon(s, shade(col, 0.5), pts, 1)


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
