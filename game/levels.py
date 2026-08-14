"""Biomes: palettes, procedural backdrops, enemy pools, ambient hazards, music."""

import math, random
import pygame
from core.settings import *
from core.utils import *

TILE = 256


def _biome(**kw):
	kw.setdefault('hazard', None)
	kw.setdefault('fog', 0)
	kw.setdefault('mods', {})
	return kw

BIOMES = [
	_biome(id='dataset', name='THE DATASET', sub='epoch 1 // clean, labelled, harmless',
	       bg=(7, 11, 20), grid=(20, 36, 60), accent=(63, 169, 245), dust=(90, 150, 220),
	       pool=('null', 'bug', 'spam', 'mite'), boss='overseer',
	       music=dict(bpm=100, root=9, scale=(0, 3, 5, 7, 10),
	                  bass=(0, -1, -1, 0, -1, -1, 3, -1, 2, -1, -1, 2, -1, -1, 0, -1),
	                  lead=(-1, 4, -1, 5, 7, -1, 4, 2, -1, 3, 5, -1, 7, -1, 5, 4),
	                  drums=(1, 0, 2, 0, 5, 0, 2, 2, 1, 0, 2, 0, 5, 0, 2, 3))),

	_biome(id='latent', name='THE LATENT SPACE', sub='epoch 2 // nothing here has a name',
	       bg=(11, 7, 21), grid=(38, 22, 60), accent=(180, 92, 255), dust=(190, 140, 255),
	       pool=('null', 'crawler', 'phantom', 'bug', 'spam', 'orbiter'), boss='aligner',
	       fog=1, mods=dict(spd=1.10, hp=0.92),
	       music=dict(bpm=96, root=8, scale=(0, 1, 5, 7, 8),
	                  bass=(0, -1, 0, -1, -1, 5, -1, -1, 3, -1, 3, -1, -1, 1, -1, -1),
	                  lead=(-1, -1, 7, -1, 5, -1, 8, -1, -1, 5, -1, 3, -1, 1, -1, 0),
	                  drums=(1, 0, 2, 0, 4, 0, 2, 0, 1, 2, 2, 0, 4, 0, 2, 2))),

	_biome(id='farm', name='THE SERVER FARM', sub='epoch 3 // do not touch the coolant',
	       bg=(4, 16, 12), grid=(18, 54, 38), accent=(60, 255, 158), dust=(120, 255, 190),
	       pool=('null', 'crawler', 'sentry', 'splitter', 'spam', 'charger', 'weaver'), boss='overfitted',
	       hazard='sweep', mods=dict(hp=1.12),
	       music=dict(bpm=116, root=7, scale=(0, 2, 3, 7, 9),
	                  bass=(0, 0, -1, 0, -1, 0, 3, -1, 5, -1, 5, -1, 3, -1, 0, -1),
	                  lead=(7, -1, 5, -1, 3, 5, -1, 7, 9, -1, 7, -1, 5, 3, -1, 2),
	                  drums=(1, 2, 2, 2, 5, 2, 2, 2, 1, 2, 3, 2, 5, 2, 2, 3))),

	_biome(id='firewall', name='THE FIREWALL', sub='epoch 4 // you are not supposed to be here',
	       bg=(20, 8, 7), grid=(66, 24, 18), accent=(255, 90, 60), dust=(255, 160, 90),
	       pool=('bug', 'charger', 'daemon', 'weaver', 'sentry', 'phantom', 'mimic'), boss='firewall',
	       hazard='flames', mods=dict(hp=1.25, spd=1.06),
	       music=dict(bpm=128, root=5, scale=(0, 1, 4, 5, 8),
	                  bass=(0, 0, 0, -1, 0, 0, -1, 0, 4, -1, 4, -1, 1, -1, 1, -1),
	                  lead=(0, 4, 5, 4, 8, -1, 5, 4, 1, 5, -1, 4, 8, 9, -1, 5),
	                  drums=(1, 2, 3, 2, 5, 2, 3, 2, 1, 2, 3, 2, 5, 3, 3, 7))),

	_biome(id='collapse', name='MODEL COLLAPSE', sub='epoch 5 // it is only reading itself now',
	       bg=(10, 10, 12), grid=(52, 52, 60), accent=(255, 47, 79), dust=(230, 230, 240),
	       pool=('mite', 'phantom', 'mimic', 'daemon', 'splitter', 'bloat', 'charger', 'orbiter'),
	       boss='collapse', hazard='glitch', mods=dict(hp=1.3, spd=1.12),
	       music=dict(bpm=142, root=3, scale=(0, 1, 3, 6, 7),
	                  bass=(0, 0, -1, 3, 0, -1, 6, -1, 1, 1, -1, 0, -1, 7, -1, 6),
	                  lead=(0, 6, 7, 6, 3, 1, 0, -1, 6, 7, 10, 7, 6, 3, 1, 0),
	                  drums=(1, 2, 3, 2, 5, 2, 3, 6, 1, 2, 3, 2, 5, 2, 7, 3), always_lead=True)),
]
BIOME_BY_ID = {b['id']: b for b in BIOMES}

_tiles = {}


def tile_for(b):
	t = _tiles.get(b['id'])
	if t is not None: return t
	rng = random.Random(hash(b['id']) & 0xffff)
	# transparent so the far parallax layer stays visible underneath
	s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
	g = b['grid']; ac = b['accent']
	bid = b['id']

	def ca(col, a): return (col[0], col[1], col[2], a)

	def wrapblit(fn):
		for ox in (-TILE, 0, TILE):
			for oy in (-TILE, 0, TILE):
				fn(ox, oy)

	if bid == 'dataset':
		# scattered records, some highlighted, plus faint column separators
		for i in range(120):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			big = rng.random() < 0.12
			c = ca(ac, rng.randint(30, 110) if not big else rng.randint(120, 190))
			pygame.draw.rect(s, c, (x, y, 2 + 2 * big, 2))
		for i in range(7):
			x = rng.randrange(TILE)
			pygame.draw.line(s, ca(ac, 22), (x, 0), (x, TILE), 1)
		for i in range(5):
			y = rng.randrange(TILE)
			pygame.draw.line(s, ca(ac, 16), (0, y), (TILE, y), 1)
	elif bid == 'latent':
		for i in range(30):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			r = rng.randint(18, 66)
			col = ca(mix(ac, (255, 120, 220), rng.random()), rng.randint(4, 12))
			wrapblit(lambda ox, oy, x=x, y=y, r=r, col=col: pygame.draw.circle(s, col, (x + ox, y + oy), r))
		for i in range(130):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			pygame.draw.rect(s, ca(b['dust'], rng.randint(20, 80)), (x, y, 1, 1))
	elif bid == 'farm':
		for i in range(26):
			x = rng.randrange(0, TILE, 16); y = rng.randrange(0, TILE, 16)
			L = rng.randint(2, 7) * 16
			c = ca(ac, rng.randint(26, 70))
			if rng.random() < 0.5:
				pygame.draw.line(s, c, (x, y), (min(TILE, x + L), y), 2)
				pygame.draw.circle(s, ca(ac, 110), (min(TILE, x + L), y), 3)
			else:
				pygame.draw.line(s, c, (x, y), (x, min(TILE, y + L)), 2)
				pygame.draw.circle(s, ca(ac, 110), (x, min(TILE, y + L)), 3)
		for i in range(30):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			pygame.draw.rect(s, ca(ac, rng.randint(20, 60)), (x, y, 2, 2))
	elif bid == 'firewall':
		for gy in range(0, TILE + 40, 40):
			for gx in range(0, TILE + 46, 46):
				ox = 23 if (gy // 40) % 2 else 0
				pts = [(gx + ox + math.cos(i * TAU / 6) * 22, gy + math.sin(i * TAU / 6) * 22)
				       for i in range(6)]
				pygame.draw.polygon(s, ca(mix(g, ac, 0.3), rng.randint(26, 90)), pts, 1)
				if rng.random() < 0.10:
					pygame.draw.polygon(s, ca(ac, 22), pts, 0)
	else:
		# collapse: torn scanline garbage
		for i in range(260):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			pygame.draw.rect(s, ca((230, 230, 240), rng.randint(8, 40)), (x, y, rng.randint(1, 3), 1))
		for i in range(16):
			y = rng.randrange(TILE); h = rng.randint(1, 4)
			pygame.draw.rect(s, ca(ac, rng.randint(20, 70)), (0, y, TILE, h))
		for i in range(8):
			y = rng.randrange(TILE)
			pygame.draw.rect(s, ca((120, 255, 220), rng.randint(14, 40)), (0, y, TILE, 1))

	_tiles[b['id']] = s
	return s


class Backdrop:
	"""Draws the infinite scrolling world floor for the active biome."""

	def __init__(self):
		self.b = BIOMES[0]
		self.dust = []
		self.rng = random.Random(4)
		self.blend = 0.0
		self.prev = None

	def set_biome(self, b):
		self.prev = self.b
		self.b = b
		self.blend = 1.0
		self.dust = []
		for i in range(90):
			self.dust.append([self.rng.uniform(0, W), self.rng.uniform(0, H),
			                  self.rng.uniform(0.25, 0.9), self.rng.uniform(1.0, 2.6)])

	def update(self, dt):
		if self.blend > 0.0: self.blend = max(0.0, self.blend - dt * 0.7)

	def draw(self, s, camx, camy, t):
		b = self.b
		s.fill(b['bg'])

		# --- far parallax: slow structures anchored in world space
		acc = b['accent']
		far = shade(acc, 0.26)
		cell = 620
		fx_ = camx * 0.35; fy_ = camy * 0.35
		x0 = int((fx_ - 300) // cell); x1 = int((fx_ + W + 300) // cell)
		y0 = int((fy_ - 300) // cell); y1 = int((fy_ + H + 300) // cell)
		for ix in range(x0, x1 + 1):
			for iy in range(y0, y1 + 1):
				h = (ix * 73856093 ^ iy * 19349663) & 0x1ff
				wx = ix * cell + (h % 380) - fx_; wy = iy * cell + (h * 7 % 380) - fy_
				r = 70 + h % 150
				if h & 1:
					pygame.draw.circle(s, far, (int(wx), int(wy)), r, 1)
					pygame.draw.circle(s, shade(acc, 0.14), (int(wx), int(wy)), int(r * 0.55), 1)
				else:
					n = 6 if (h & 2) else 4
					a0 = h * 0.02 + t * 0.05
					pts = [(wx + math.cos(a0 + i * TAU / n) * r, wy + math.sin(a0 + i * TAU / n) * r)
					       for i in range(n)]
					pygame.draw.polygon(s, far, pts, 1)

		# --- mid: the tiled substrate
		tile = tile_for(b)
		ox = int(-camx * 0.62) % TILE
		oy = int(-camy * 0.62) % TILE
		for x in range(ox - TILE, W + TILE, TILE):
			for y in range(oy - TILE, H + TILE, TILE):
				s.blit(tile, (x, y))

		# --- near: the working grid, brighter every 4th line, glowing nodes
		g = b['grid']
		gb = mix(g, acc, 0.42)
		step = 96
		gx = int(-camx) % step
		gy = int(-camy) % step
		ix0 = int(math.floor(camx / step))
		iy0 = int(math.floor(camy / step))
		i = 0
		for x in range(gx - step, W + step, step):
			major = ((ix0 + i - 1) & 3) == 0
			pygame.draw.line(s, gb if major else g, (x, 0), (x, H), 1)
			i += 1
		j = 0
		for y in range(gy - step, H + step, step):
			major = ((iy0 + j - 1) & 3) == 0
			pygame.draw.line(s, gb if major else g, (0, y), (W, y), 1)
			j += 1
		i = 0
		for x in range(gx - step, W + step, step):
			if ((ix0 + i - 1) & 3) == 0:
				j = 0
				for y in range(gy - step, H + step, step):
					if ((iy0 + j - 1) & 3) == 0:
						pl = 0.35 + 0.3 * math.sin(t * 1.7 + (x + y) * 0.01)
						blit_glow(s, x, y, 9, acc, pl)
					j += 1
			i += 1

		# --- dust motes drifting through the layer
		d = b['dust']
		for p in self.dust:
			p[0] -= (30.0 * p[2]) * 0.016
			if p[0] < -10: p[0] = W + 10; p[1] = self.rng.uniform(0, H)
			px = (p[0] - camx * p[2] * 0.25) % (W + 20) - 10
			py = (p[1] - camy * p[2] * 0.25) % (H + 20) - 10
			sz = int(p[3])
			pygame.draw.rect(s, shade(d, p[2] * 0.55), (int(px), int(py), sz, sz))

		if self.blend > 0.0 and self.prev is not None:
			# quick colour wash while the biome swaps over
			o = pygame.Surface((W, H))
			o.fill(shade(self.prev['accent'], self.blend * 0.22))
			s.blit(o, (0, 0), None, pygame.BLEND_ADD)
