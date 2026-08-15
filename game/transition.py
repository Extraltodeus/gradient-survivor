"""Biome change as a linear map.

The last frame of the old biome is treated as a textured plane in R^3. That plane
is rotated by R in SO(3), pushed through a pinhole camera, and eased back down to
z = 0 while it dissolves into the biome underneath.

Because the plane is flat, the whole projection collapses into a single 3x3
matrix acting on homogeneous coordinates:

	[X Y Wc]^T = M . [x y 1]^T ,  screen = (X/Wc, Y/Wc)
	M = [[f r00, f r01, 0], [f r10, f r11, 0], [-r20, -r21, f]]

so the frame is resampled by inverting that matmul and gathering -- one numpy
gather per frame at a third of the resolution, which is what makes it affordable.
The matrix printed on screen is that M's rotation part, live.
"""

import math
import numpy as np
import pygame
from core.settings import *
from core.utils import *

FOCAL = 1150.0
KEY = (255, 0, 255)


def _rot(ax, ay, az):
	ca, sa = math.cos(ax), math.sin(ax)
	cb, sb = math.cos(ay), math.sin(ay)
	cc, sc = math.cos(az), math.sin(az)
	rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], dtype=np.float32)
	ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]], dtype=np.float32)
	rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]], dtype=np.float32)
	return rz @ ry @ rx


class Matmul:
	"""One biome-to-biome fold. Draw it over the already-rendered new world."""

	def __init__(self, snap, accent=CYAN, dur=1.55):
		self.dur = dur
		self.t = 0.0
		self.accent = accent
		self.R = np.eye(3, dtype=np.float32)
		self.sw = max(160, min(384, W // 3))
		self.sh = max(90, int(self.sw * H / float(W)))
		small = pygame.transform.smoothscale(snap, (self.sw, self.sh))
		self.src = pygame.surfarray.array3d(small).astype(np.uint8)
		self.small = pygame.Surface((self.sw, self.sh))
		self.full = pygame.Surface((W, H))
		# colourkey alone is a fast blit; colourkey PLUS per-surface alpha is not
		# (SDL falls off a cliff, ~20x). So the dissolve is a dither into the key
		# colour rather than a fade, which costs nothing and looks more digital.
		self.full.set_colorkey(KEY)
		self.f = FOCAL * self.sw / float(W)
		u = (np.arange(self.sw, dtype=np.float32) - self.sw * 0.5)[:, None]
		v = (np.arange(self.sh, dtype=np.float32) - self.sh * 0.5)[None, :]
		self.u = np.broadcast_to(u, (self.sw, self.sh)).copy()
		self.v = np.broadcast_to(v, (self.sw, self.sh)).copy()
		self.key = np.array(KEY, dtype=np.uint8)
		rng = np.random.default_rng(11)
		rad = np.sqrt((self.u / (self.sw * 0.5)) ** 2 + (self.v / (self.sh * 0.5)) ** 2)
		d = rng.random((self.sw, self.sh)).astype(np.float32) * 0.72 + (2.0 - rad) * 0.22
		self.diss = ((d - d.min()) / max(1e-3, d.max() - d.min())).astype(np.float32)

	def update(self, dt):
		self.t += dt
		return self.t < self.dur

	# ------------------------------------------------------------------ draw
	def draw(self, s):
		p = clamp(self.t / self.dur, 0.0, 1.0)
		bump = math.sin(math.pi * p) ** 0.85        # leaves the plane and returns to it
		R = _rot(0.78 * bump, 1.06 * bump, 0.44 * bump * math.sin(p * 3.4))
		self.R = R
		f = self.f
		M = np.array([[f * R[0][0], f * R[0][1], 0.0],
		              [f * R[1][0], f * R[1][1], 0.0],
		              [-R[2][0], -R[2][1], f]], dtype=np.float32)
		try:
			Mi = np.linalg.inv(M)
		except np.linalg.LinAlgError:
			return

		# zoom out a little at mid-flight so the whole sheet stays in frame
		k = 1.0 + 0.22 * bump
		uu = self.u * k
		vv = self.v * k
		# homogeneous screen point [u v 1] pushed back through the inverse matmul
		X = Mi[0][0] * uu + Mi[0][1] * vv + Mi[0][2]
		Y = Mi[1][0] * uu + Mi[1][1] * vv + Mi[1][2]
		Wc = Mi[2][0] * uu + Mi[2][1] * vv + Mi[2][2]
		Wc = np.where(np.abs(Wc) < 1e-6, 1e-6, Wc)
		sx = X / Wc
		sy = Y / Wc

		# a wave travelling through the sheet: perturbing the sample coordinates is
		# free here, and it is what stops the fold from reading as a flat card flip
		if bump > 0.01:
			amp = 0.045 * self.sw * bump
			wave = np.sin(sy * 0.09 + p * 11.0)
			sx = sx + amp * wave
			sy = sy + amp * 0.5 * wave

		ix = sx + self.sw * 0.5
		iy = sy + self.sh * 0.5
		# the centre pixel is always on the visible side: cull whatever flipped sign
		side = 1.0 if Mi[2][2] >= 0 else -1.0
		ok = (ix >= 0) & (ix < self.sw - 1) & (iy >= 0) & (iy < self.sh - 1) & (Wc * side > 0)
		fade = clamp((p - 0.5) / 0.5, 0.0, 1.0)
		if fade > 0.0:
			ok &= self.diss > fade * fade
		np.clip(ix, 0, self.sw - 1, out=ix)
		np.clip(iy, 0, self.sh - 1, out=iy)
		out = self.src[ix.astype(np.int32), iy.astype(np.int32)]
		out[~ok] = self.key

		pygame.surfarray.blit_array(self.small, out)
		pygame.transform.scale(self.small, (W, H), self.full)
		s.blit(self.full, (0, 0))

		self._frame(s, R, bump, k)
		self._readout(s, R, p)

	def _frame(self, s, R, bump, k):
		"""The wireframe of the sheet plus its third axis, so the lift is legible."""
		if bump < 0.02: return
		col = shade(self.accent, 0.30 + 0.55 * bump)
		hw = W * 0.5 / k; hh = H * 0.5 / k
		pts = []
		for cx_, cy_ in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
			q = R @ np.array([cx_ * hw, cy_ * hh, 0.0], dtype=np.float32)
			kk = FOCAL / max(200.0, FOCAL - float(q[2]))
			pts.append((CX + float(q[0]) * kk / k, CY + float(q[1]) * kk / k))
		pygame.draw.lines(s, col, True, pts, 2)
		q = R @ np.array([0.0, 0.0, 260.0 * bump], dtype=np.float32)
		kk = FOCAL / max(200.0, FOCAL - float(q[2]))
		pygame.draw.line(s, shade(GOLD, 0.75 * bump), (CX, CY),
		                 (CX + float(q[0]) * kk, CY + float(q[1]) * kk), 2)
		blit_glow(s, CX, CY, 18, GOLD, 0.6 * bump)

	def _readout(self, s, R, p):
		a = clamp(min(p * 6.0, (1.0 - p) * 4.0), 0.0, 1.0)
		if a <= 0.02: return
		x = CX - 132; y = int(H * 0.70)
		bg = pygame.Surface((264, 100), pygame.SRCALPHA)
		pygame.draw.rect(bg, (8, 11, 18, int(195 * a)), (0, 0, 264, 100), 0, 8)
		pygame.draw.rect(bg, (self.accent[0], self.accent[1], self.accent[2], int(150 * a)),
		                 (0, 0, 264, 100), 1, 8)
		s.blit(bg, (x, y))
		g = text('frame <- R . frame', 12, shade(self.accent, 0.95), True)
		g.set_alpha(int(255 * a))
		s.blit(g, (x + 132 - g.get_width() * 0.5, y + 9))
		for r in range(3):
			row = '  '.join('%+.2f' % float(R[r][c]) for c in range(3))
			g = text(row, 13, INK if r != 2 else GOLD)
			g.set_alpha(int(235 * a))
			s.blit(g, (x + 132 - g.get_width() * 0.5, y + 32 + r * 19))
