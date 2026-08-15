"""Biomes: palettes, procedural backdrops, enemy pools, ambient hazards, music.

Each biome owns three drawing layers and none of them are shared: a far parallax
built from its own idea of "structure", a baked 256px substrate tile, and a near
layer that is the one animated thing you actually read while playing (a read
head, a warped manifold, blinking racks, packet lanes, a tearing frame). They are
dispatched by biome id -- one biome, one look, no generic fallback.
"""

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

# Music note: patterns are chord-relative. `bass` holds scale-degree offsets from
# the running chord root, `arp` holds chord-tone indices, `lead` holds degrees
# from the key root. The progression walks `prog` one chord per bar, so a pattern
# stays in key no matter where the sequencer is.

BIOMES = [
	_biome(id='dataset', name='THE DATASET', sub='epoch 1 // clean, labelled, harmless',
	       bg=(6, 10, 19), grid=(18, 33, 56), accent=(63, 169, 245), dust=(120, 175, 235),
	       pool=('null', 'bug', 'spam', 'mite'), boss='overseer',
	       music=dict(bpm=102, root=9, scale=(0, 3, 5, 7, 10), prog=(0, 3, 1, 2),
	                  voices=('sub', 'pluck', 'lead', 'warm'), swing=0.14,
	                  bass=(0, -1, -1, 0, -1, -1, 4, -1, 0, -1, -1, 0, -1, 2, -1, -1),
	                  arp=(0, 2, 1, 3, 0, 2, 4, 2, 1, 3, 2, 4, 0, 2, 1, -1),
	                  lead=(-1, -1, 4, -1, 5, -1, 7, -1, -1, 5, -1, 4, -1, 2, -1, -1,
	                        -1, -1, 7, -1, 9, -1, 7, 5, -1, 4, -1, 5, -1, -1, -1, -1),
	                  drums=(1, 0, 2, 0, 4, 0, 2, 8, 1, 0, 2, 0, 4, 0, 2, 2))),

	_biome(id='latent', name='THE LATENT SPACE', sub='epoch 2 // nothing here has a name',
	       bg=(10, 6, 21), grid=(40, 22, 66), accent=(180, 92, 255), dust=(205, 155, 255),
	       pool=('null', 'crawler', 'phantom', 'bug', 'spam', 'orbiter'), boss='aligner',
	       fog=1, mods=dict(spd=1.10, hp=0.92), hazard='well',
	       music=dict(bpm=94, root=8, scale=(0, 1, 5, 7, 8), prog=(0, 4, 2, 3),
	                  voices=('sub', 'bell', 'lead', 'warm'), swing=0.06,
	                  bass=(0, -1, -1, -1, 0, -1, -1, 4, -1, -1, 2, -1, -1, -1, -1, -1),
	                  arp=(0, -1, 2, -1, 4, -1, 3, -1, 1, -1, 3, -1, 5, -1, 2, -1),
	                  lead=(-1, -1, -1, 7, -1, -1, 5, -1, -1, 8, -1, -1, -1, 4, -1, -1,
	                        -1, -1, 10, -1, -1, 7, -1, -1, 5, -1, -1, 4, -1, -1, -1, -1),
	                  drums=(1, 0, 0, 2, 0, 0, 4, 0, 1, 0, 2, 0, 0, 4, 0, 8))),

	_biome(id='farm', name='THE SERVER FARM', sub='epoch 3 // do not touch the coolant',
	       bg=(3, 15, 12), grid=(16, 52, 38), accent=(60, 255, 158), dust=(140, 255, 205),
	       pool=('null', 'crawler', 'sentry', 'splitter', 'spam', 'charger', 'weaver'), boss='overfitted',
	       hazard='sweep', mods=dict(hp=1.12),
	       music=dict(bpm=120, root=7, scale=(0, 2, 3, 7, 9), prog=(0, 2, 3, 1),
	                  voices=('bass', 'pluck', 'lead', 'warm'), swing=0.0,
	                  bass=(0, 0, -1, 0, -1, 0, 4, -1, 2, -1, 2, -1, 4, -1, 0, 0),
	                  arp=(0, 2, 4, 2, 1, 3, 5, 3, 0, 2, 4, 2, 3, 1, 2, 4),
	                  lead=(4, -1, 2, -1, 0, 2, -1, 4, 5, -1, 4, -1, 2, 0, -1, -1,
	                        7, -1, 5, -1, 4, 5, -1, 7, 9, -1, 7, -1, 5, 4, 2, -1),
	                  drums=(1, 2, 2, 2, 4, 2, 2, 10, 1, 2, 3, 2, 4, 2, 2, 18))),

	_biome(id='firewall', name='THE FIREWALL', sub='epoch 4 // you are not supposed to be here',
	       bg=(19, 6, 6), grid=(70, 22, 16), accent=(255, 90, 60), dust=(255, 170, 95),
	       pool=('bug', 'charger', 'daemon', 'weaver', 'sentry', 'phantom', 'mimic'), boss='firewall',
	       hazard='flames', mods=dict(hp=1.25, spd=1.06),
	       music=dict(bpm=132, root=5, scale=(0, 1, 4, 5, 8), prog=(0, 0, 3, 4),
	                  voices=('bass', 'pluck', 'lead', 'warm'), swing=0.0,
	                  bass=(0, 0, 0, -1, 0, 0, -1, 0, 4, -1, 4, -1, 1, -1, 1, 1),
	                  arp=(0, 3, 2, 4, 1, 3, 5, 2, 0, 3, 2, 4, 3, 5, 4, 2),
	                  lead=(0, -1, 4, 5, -1, 4, -1, 8, -1, 5, 4, -1, 1, -1, -1, -1,
	                        8, -1, 9, -1, 8, 5, 4, -1, 5, -1, 4, 1, -1, 0, -1, -1),
	                  drums=(1, 2, 4, 2, 5, 2, 4, 2, 1, 2, 4, 10, 5, 4, 4, 34))),

	_biome(id='collapse', name='MODEL COLLAPSE', sub='epoch 5 // it is only reading itself now',
	       bg=(9, 9, 12), grid=(56, 54, 62), accent=(255, 47, 79), dust=(235, 235, 245),
	       pool=('mite', 'phantom', 'mimic', 'daemon', 'splitter', 'bloat', 'charger', 'orbiter'),
	       boss='collapse', hazard='glitch', mods=dict(hp=1.3, spd=1.12),
	       music=dict(bpm=146, root=3, scale=(0, 1, 3, 6, 7), prog=(0, 4, 1, 3),
	                  voices=('bass', 'pluck', 'lead', 'warm'), swing=0.0, always_lead=True,
	                  bass=(0, 0, -1, 3, 0, -1, 4, -1, 1, 1, -1, 0, -1, 4, -1, 3),
	                  arp=(0, 4, 2, 5, 1, 3, 0, 4, 2, 5, 3, 1, 4, 2, 5, 3),
	                  lead=(0, 4, 5, 4, 2, 1, 0, -1, 4, 5, 7, 5, 4, 2, 1, 0,
	                        7, 5, 4, 5, 7, 9, 7, 5, 4, 2, 1, 2, 4, 1, 0, -1),
	                  drums=(1, 2, 4, 2, 5, 2, 4, 34, 1, 2, 4, 2, 5, 6, 4, 42))),
]
BIOME_BY_ID = {b['id']: b for b in BIOMES}

_tiles = {}


def ca(col, a): return (col[0], col[1], col[2], a)


# ------------------------------------------------------------ mid substrate
def tile_for(b):
	"""The baked 256px substrate. Transparent, so the far layer shows through."""
	t = _tiles.get(b['id'])
	if t is not None: return t
	rng = random.Random(hash(b['id']) & 0xffff)
	s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
	g = b['grid']; ac = b['accent']
	bid = b['id']

	def wrapblit(fn):
		for ox in (-TILE, 0, TILE):
			for oy in (-TILE, 0, TILE):
				fn(ox, oy)

	if bid == 'dataset':
		# a sheet of records: dense rows of samples, a few of them labelled
		for row in range(0, TILE, 22):
			n = rng.randint(7, 12)
			for i in range(n):
				x = rng.randrange(TILE); w_ = rng.randint(6, 26)
				pygame.draw.rect(s, ca(ac, rng.randint(22, 54)), (x, row + 6, w_, 3))
			if rng.random() < 0.34:
				x = rng.randrange(TILE - 40)
				pygame.draw.rect(s, ca(ac, 90), (x, row + 4, rng.randint(16, 34), 6))
				pygame.draw.rect(s, ca((255, 255, 255), 40), (x, row + 4, 3, 6))
		for i in range(4):
			x = rng.randrange(TILE)
			pygame.draw.line(s, ca(ac, 20), (x, 0), (x, TILE), 1)

	elif bid == 'latent':
		# soft density first -- pygame's draw calls write alpha instead of blending it,
		# so anything drawn after would be erased by these
		for i in range(22):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			r = rng.randint(14, 46)
			base = mix(ac, (120, 200, 255), rng.random())
			for k in range(4):
				col = ca(base, 5 + k * 4)
				rr = int(r * (1.0 - k * 0.22))
				wrapblit(lambda ox, oy, x=x, y=y, rr=rr, col=col: pygame.draw.circle(s, col, (x + ox, y + oy), rr))
		# unlabelled clusters: point clouds joined by faint edges
		for c in range(6):
			cx_ = rng.randrange(TILE); cy_ = rng.randrange(TILE)
			col = mix(ac, (255, 120, 220), rng.random())
			pts = []
			for i in range(rng.randint(8, 15)):
				px = cx_ + int(rng.gauss(0, 18)); py = cy_ + int(rng.gauss(0, 18))
				pts.append((px, py))
				pygame.draw.rect(s, ca(col, rng.randint(70, 165)), (px, py, 2, 2))
			for i in range(len(pts) - 1):
				pygame.draw.line(s, ca(col, 26), pts[i], pts[i + 1], 1)

	elif bid == 'farm':
		# cable trays and coolant runs on a hard orthogonal plan
		for i in range(9):
			y = rng.randrange(0, TILE, 8)
			pygame.draw.line(s, ca(ac, rng.randint(18, 44)), (0, y), (TILE, y), rng.randint(1, 3))
			for k in range(rng.randint(1, 3)):
				x = rng.randrange(TILE)
				pygame.draw.rect(s, ca(ac, 120), (x, y - 2, 5, 5))
		for i in range(6):
			x = rng.randrange(0, TILE, 8)
			pygame.draw.line(s, ca(mix(g, ac, 0.5), rng.randint(20, 50)), (x, 0), (x, TILE), 2)
		for i in range(14):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			pygame.draw.rect(s, ca(ac, rng.randint(30, 70)), (x, y, 9, 4), 1)

	elif bid == 'firewall':
		# hex mesh, a few cells sealed shut
		R = 26
		for gy in range(-R, TILE + R * 2, int(R * 1.5)):
			row = (gy // int(R * 1.5)) & 1
			for gx in range(-R, TILE + R * 2, int(R * 1.74)):
				ox = int(R * 0.87) if row else 0
				pts = [(gx + ox + math.cos(i * TAU / 6 + 0.52) * R,
				        gy + math.sin(i * TAU / 6 + 0.52) * R) for i in range(6)]
				pygame.draw.polygon(s, ca(mix(g, ac, 0.35), rng.randint(30, 78)), pts, 1)
				if rng.random() < 0.09:
					pygame.draw.polygon(s, ca(ac, 26), pts, 0)
				elif rng.random() < 0.06:
					pygame.draw.line(s, ca(ac, 70), pts[0], pts[3], 1)

	else:
		# collapse: the same strip pasted at slightly wrong offsets, forever
		for i in range(200):
			x = rng.randrange(TILE); y = rng.randrange(TILE)
			pygame.draw.rect(s, ca((225, 225, 238), rng.randint(6, 34)), (x, y, rng.randint(1, 4), 1))
		for i in range(13):
			y = rng.randrange(TILE); h = rng.randint(1, 5)
			pygame.draw.rect(s, ca(ac, rng.randint(18, 62)), (0, y, TILE, h))
			# the ghost of the same band, offset: the model re-reading its own output
			pygame.draw.rect(s, ca((120, 255, 220), rng.randint(10, 26)),
			                 (rng.randint(-14, 14), y + rng.randint(2, 7), TILE, max(1, h - 1)))
		for i in range(5):
			x = rng.randrange(TILE)
			pygame.draw.rect(s, ca((255, 255, 255), rng.randint(8, 20)), (x, 0, 1, TILE))

	_tiles[b['id']] = s
	return s


# --------------------------------------------------------------- far layers
def _far_dataset(s, b, camx, camy, t):
	"""Distant histograms: the shape of the data you are standing on."""
	acc = b['accent']
	fx = camx * 0.28
	base = H * 0.80 - camy * 0.08
	cell = 132
	i0 = int((fx - cell) // cell)
	line = shade(acc, 0.22)
	fill = shade(acc, 0.07)
	for i in range(i0, i0 + int(W / cell) + 3):
		h = (i * 73856093) & 0x3ff
		hh = 30 + (h % 300)
		x = int(i * cell - fx)
		y = int(base - hh)
		if y > H: continue
		pygame.draw.rect(s, fill, (x, y, cell - 30, hh))
		pygame.draw.rect(s, line, (x, y, cell - 30, hh), 1)
		if h & 3 == 0:
			pygame.draw.line(s, shade(acc, 0.34), (x, y), (x + cell - 30, y), 2)
	pygame.draw.line(s, shade(acc, 0.20), (0, int(base)), (W, int(base)), 1)


def _far_latent(s, b, camx, camy, t):
	"""Contours of a manifold nobody labelled."""
	acc = b['accent']
	fx = camx * 0.22; fy = camy * 0.22
	for k in range(5):
		r = 120 + k * 78
		col = shade(mix(acc, (255, 120, 220), k * 0.2), 0.16 + 0.05 * (4 - k))
		cx_ = CX - fx * (0.6 + k * 0.1) % 900 + 200
		cy_ = CY - fy * (0.6 + k * 0.1) % 700 + 60
		pts = []
		for i in range(23):
			a = i / 22.0 * TAU
			rr = r * (1.0 + 0.22 * math.sin(a * 3 + t * 0.4 + k) + 0.12 * math.sin(a * 5 - t * 0.3))
			pts.append((cx_ + math.cos(a) * rr, cy_ + math.sin(a) * rr * 0.72))
		pygame.draw.lines(s, col, True, pts, 1)


def _far_farm(s, b, camx, camy, t):
	"""Rack aisles receding into the room."""
	acc = b['accent']
	fx = camx * 0.34
	horizon = H * 0.42 - camy * 0.06
	cell = 190
	i0 = int((fx - cell) // cell)
	for i in range(i0, i0 + int(W / cell) + 3):
		h = (i * 19349663) & 0x1ff
		x = int(i * cell - fx)
		hh = 150 + (h % 190)
		y = int(horizon - hh * 0.5)
		pygame.draw.rect(s, shade(acc, 0.07), (x, y, cell - 46, hh))
		pygame.draw.rect(s, shade(acc, 0.20), (x, y, cell - 46, hh), 1)
		for k in range(4, hh, 26):
			pygame.draw.line(s, shade(acc, 0.13), (x + 4, y + k), (x + cell - 50, y + k), 1)
			if ((h + k) & 7) == 0:
				bl = 0.4 + 0.6 * abs(math.sin(t * 2.4 + i + k * 0.3))
				pygame.draw.rect(s, shade((120, 255, 190), bl), (x + cell - 56, y + k - 1, 3, 3))
	pygame.draw.line(s, shade(acc, 0.16), (0, int(horizon + 90)), (W, int(horizon + 90)), 1)


def _far_firewall(s, b, camx, camy, t):
	"""The barrier itself: hexagonal plates the size of buildings."""
	acc = b['accent']
	fx = camx * 0.30; fy = camy * 0.30
	R = 264
	stepx = int(R * 1.74); stepy = int(R * 1.5)
	x0 = int((fx - stepx) // stepx); x1 = x0 + int(W / stepx) + 3
	y0 = int((fy - stepy) // stepy); y1 = y0 + int(H / stepy) + 3
	for iy in range(y0, y1):
		for ix in range(x0, x1):
			ox = int(R * 0.87) if (iy & 1) else 0
			cx_ = ix * stepx + ox - fx
			cy_ = iy * stepy - fy
			h = (ix * 73856093 ^ iy * 19349663) & 0xff
			pulse = 0.13 + 0.13 * abs(math.sin(t * 0.9 + h * 0.05))
			pts = [(cx_ + math.cos(i * TAU / 6 + 0.52) * R,
			        cy_ + math.sin(i * TAU / 6 + 0.52) * R) for i in range(6)]
			if h & 7 == 0:
				pygame.draw.polygon(s, shade(acc, 0.06), pts, 0)
			pygame.draw.polygon(s, shade(acc, pulse), pts, 1)


def _far_collapse(s, b, camx, camy, t):
	"""Frames inside frames: the output folded back into the input."""
	acc = b['accent']
	cx_ = CX - camx * 0.16 % 640
	cy_ = CY - camy * 0.16 % 480
	for k in range(9):
		f = 1.0 - k / 9.0
		w_ = int(W * 0.9 * f); h_ = int(H * 0.9 * f)
		a = math.sin(t * 0.25 + k * 0.7) * 0.05 * k
		col = shade(mix((150, 150, 165), acc, k / 9.0), 0.10 + 0.09 * f)
		ca_, sa = math.cos(a), math.sin(a)
		pts = []
		for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
			px = sx * w_ * 0.5; py = sy * h_ * 0.5
			pts.append((cx_ + px * ca_ - py * sa, cy_ + px * sa + py * ca_))
		pygame.draw.polygon(s, col, pts, 1)


# -------------------------------------------------------------- near layers
def _grid(s, b, camx, camy, step=96, glowdots=True, t=0.0):
	"""The plain working grid, brighter every 4th line."""
	g = b['grid']
	acc = b['accent']
	gb = mix(g, acc, 0.42)
	gx = int(-camx) % step
	gy = int(-camy) % step
	ix0 = int(math.floor(camx / step))
	iy0 = int(math.floor(camy / step))
	majx = []
	i = 0
	for x in range(gx - step, W + step, step):
		major = ((ix0 + i - 1) & 3) == 0
		pygame.draw.line(s, gb if major else g, (x, 0), (x, H), 1)
		if major: majx.append(x)
		i += 1
	majy = []
	j = 0
	for y in range(gy - step, H + step, step):
		major = ((iy0 + j - 1) & 3) == 0
		pygame.draw.line(s, gb if major else g, (0, y), (W, y), 1)
		if major: majy.append(y)
		j += 1
	if glowdots:
		for x in majx:
			for y in majy:
				pl = 0.35 + 0.3 * math.sin(t * 1.7 + (x + y) * 0.01)
				blit_glow(s, x, y, 9, acc, pl)


def _near_dataset(s, b, camx, camy, t):
	_grid(s, b, camx, camy, 96, True, t)
	# the read head: one row of the set is being sampled, right now
	acc = b['accent']
	ys = (t * 128.0) % (H + 260) - 130
	for k in range(5):
		a = 0.30 * (1.0 - k / 5.0)
		pygame.draw.rect(s, shade(acc, a * 0.35), (0, int(ys - k * 9), W, 8))
	pygame.draw.line(s, shade(acc, 0.85), (0, int(ys)), (W, int(ys)), 2)
	pygame.draw.line(s, WHITE, (0, int(ys)), (int(W * 0.18), int(ys)), 1)
	blit_glow(s, W * 0.5, ys, 20, acc, 0.5)


def _near_latent(s, b, camx, camy, t):
	"""No grid survives here: the coordinates themselves are curved."""
	acc = b['accent']
	g = mix(b['grid'], acc, 0.35)
	step = 128
	gx = int(-camx * 0.9) % step
	gy = int(-camy * 0.9) % step
	for x in range(gx - step, W + step, step):
		pts = [(x + math.sin((y + camy) * 0.006 + t * 0.5) * 26, y) for y in range(-20, H + 40, 40)]
		pygame.draw.lines(s, g, False, pts, 1)
	for y in range(gy - step, H + step, step):
		pts = [(x, y + math.cos((x + camx) * 0.006 + t * 0.4) * 22) for x in range(-20, W + 40, 40)]
		pygame.draw.lines(s, g, False, pts, 1)
	# drifting unlabelled tokens
	for i in range(9):
		h = (i * 2654435761) & 0xffff
		px = (h % 1600 - camx * 0.55 + math.sin(t * 0.3 + i) * 40) % (W + 120) - 60
		py = ((h >> 5) % 900 - camy * 0.55 + math.cos(t * 0.26 + i * 1.7) * 30) % (H + 120) - 60
		gl = text('?x' [h & 1] + chr(97 + (h % 26)), 15, shade(acc, 0.5 + 0.3 * math.sin(t + i)))
		s.blit(gl, (int(px), int(py)))


def _near_farm(s, b, camx, camy, t):
	_grid(s, b, camx, camy, 128, False, t)
	acc = b['accent']
	# coolant mains with junction lamps
	step = 384
	gx = int(-camx) % step
	gy = int(-camy) % step
	for x in range(gx - step, W + step, step):
		pygame.draw.line(s, shade(acc, 0.30), (x, 0), (x, H), 3)
		pygame.draw.line(s, shade(acc, 0.55), (x - 1, 0), (x - 1, H), 1)
	for y in range(gy - step, H + step, step):
		pygame.draw.line(s, shade(acc, 0.22), (0, y), (W, y), 2)
	ix0 = int(math.floor(camx / step)); iy0 = int(math.floor(camy / step))
	for i, x in enumerate(range(gx - step, W + step, step)):
		for j, y in enumerate(range(gy - step, H + step, step)):
			h = ((ix0 + i) * 73856093 ^ (iy0 + j) * 19349663) & 0xff
			bl = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * (2.0 + (h & 7) * 0.4) + h))
			blit_glow(s, x, y, 13, (120, 255, 190) if h & 1 else acc, bl * 0.8)
			pygame.draw.rect(s, shade((190, 255, 220), bl), (x - 2, y - 2, 4, 4))


def _near_firewall(s, b, camx, camy, t):
	"""Traffic still flows through the wall. None of it is yours."""
	acc = b['accent']
	g = b['grid']
	step = 112
	gy = int(-camy) % step
	iy0 = int(math.floor(camy / step))
	for j, y in enumerate(range(gy - step, H + step, step)):
		h = ((iy0 + j) * 19349663) & 0xff
		pygame.draw.line(s, g, (0, y), (W, y), 1)
		spd = 210.0 + (h % 5) * 90.0
		d = -1 if h & 1 else 1
		off = (t * spd * d - camx) % 190
		col = shade(acc, 0.55) if h & 3 else (255, 220, 120)
		for k in range(int(W / 190) + 2):
			x = off + k * 190 - 190
			pygame.draw.rect(s, col, (int(x), y - 2, 22, 3))
			pygame.draw.rect(s, shade(col, 0.4), (int(x) - 16, y - 1, 14, 1))
	# a denied packet, stamped
	ph = (t * 0.5) % 1.0
	if ph < 0.22:
		a = 1.0 - ph / 0.22
		x = (int(t * 0.5) * 613) % max(1, W - 200) + 40
		y = (int(t * 0.5) * 887) % max(1, H - 160) + 60
		draw_text(s, 'DENY', x, y, int(30 + 26 * (1 - a)), shade(RED, 0.25 + 0.55 * a), True, 'c')


def _near_collapse(s, b, camx, camy, t):
	"""The frame tears and re-reads itself a few rows too late."""
	acc = b['accent']
	g = b['grid']
	step = 96
	gx = int(-camx) % step
	gy = int(-camy) % step
	rng = random.Random(int(t * 8.0))
	for x in range(gx - step, W + step, step):
		off = rng.randint(-7, 7) if rng.random() < 0.3 else 0
		pygame.draw.line(s, g, (x + off, 0), (x + off, H), 1)
	for y in range(gy - step, H + step, step):
		off = rng.randint(-7, 7) if rng.random() < 0.3 else 0
		pygame.draw.line(s, g, (0, y + off), (W, y + off), 1)
	for k in range(3):
		if rng.random() < 0.55:
			bh = rng.randint(10, 40)
			by = rng.randrange(0, max(1, H - bh))
			dx = rng.randint(-40, 40)
			band = s.subsurface(pygame.Rect(0, by, W, bh)).copy()
			s.blit(band, (dx, by))
			pygame.draw.rect(s, shade(acc, 0.25), (dx, by, W, 1))
	for k in range(4):
		y = rng.randrange(H)
		pygame.draw.line(s, shade((120, 255, 230), 0.35), (0, y), (W, y), 1)


_FAR = {'dataset': _far_dataset, 'latent': _far_latent, 'farm': _far_farm,
        'firewall': _far_firewall, 'collapse': _far_collapse}
_NEAR = {'dataset': _near_dataset, 'latent': _near_latent, 'farm': _near_farm,
         'firewall': _near_firewall, 'collapse': _near_collapse}

# dust: (count, drift x, drift y, size, wobble)
_DUST = {'dataset': (70, -34.0, 0.0, 2.2, 0.0),
         'latent': (95, -8.0, -5.0, 2.0, 1.0),
         'farm': (70, 0.0, -46.0, 2.0, 0.3),
         'firewall': (85, 12.0, -60.0, 2.4, 0.6),
         'collapse': (110, 0.0, 0.0, 2.0, 2.2)}


class Backdrop:
	"""Draws the infinite scrolling world floor for the active biome."""

	def __init__(self):
		self.b = BIOMES[0]
		self.dust = []
		self.rng = random.Random(4)
		self.blend = 0.0
		self.prev = None
		self.t = 0.0

	def set_biome(self, b):
		self.prev = self.b
		self.b = b
		self.blend = 1.0
		self.dust = []
		n = _DUST.get(b['id'], (90, -30.0, 0.0, 2.0, 0.0))[0]
		for i in range(n):
			self.dust.append([self.rng.uniform(0, W), self.rng.uniform(0, H),
			                  self.rng.uniform(0.25, 0.9), self.rng.uniform(1.0, 2.6),
			                  self.rng.uniform(0, TAU)])

	def update(self, dt):
		self.t += dt
		if self.blend > 0.0: self.blend = max(0.0, self.blend - dt * 0.7)

	def draw(self, s, camx, camy, t):
		b = self.b
		s.fill(b['bg'])
		_FAR[b['id']](s, b, camx, camy, t)

		tile = tile_for(b)
		ox = int(-camx * 0.62) % TILE
		oy = int(-camy * 0.62) % TILE
		for x in range(ox - TILE, W + TILE, TILE):
			for y in range(oy - TILE, H + TILE, TILE):
				s.blit(tile, (x, y))

		_NEAR[b['id']](s, b, camx, camy, t)

		# --- dust motes drifting through the layer
		d = b['dust']
		cnt, dx_, dy_, sz_, wob = _DUST.get(b['id'], (90, -30.0, 0.0, 2.0, 0.0))
		for p in self.dust:
			p[0] += dx_ * p[2] * 0.016
			p[1] += dy_ * p[2] * 0.016
			if wob:
				p[0] += math.sin(t * 1.7 + p[4]) * wob * 0.4
				p[1] += math.cos(t * 1.3 + p[4]) * wob * 0.4
			px = (p[0] - camx * p[2] * 0.25) % (W + 20) - 10
			py = (p[1] - camy * p[2] * 0.25) % (H + 20) - 10
			sz = int(p[3] * sz_ * 0.5) or 1
			pygame.draw.rect(s, shade(d, p[2] * 0.55), (int(px), int(py), sz, sz))

		if self.blend > 0.0 and self.prev is not None:
			# quick colour wash while the biome swaps over
			o = pygame.Surface((W, H))
			o.fill(shade(self.prev['accent'], self.blend * 0.22))
			s.blit(o, (0, 0), None, pygame.BLEND_ADD)
