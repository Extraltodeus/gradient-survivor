"""Render a biome's music (and optionally the SFX bank) to a wav, offline.

	python tools/audition.py                 -> every biome, 24s each
	python tools/audition.py farm 40 0.9     -> one biome, 40s, intensity 0.9
	python tools/audition.py sfx             -> one hit of every sound effect

Output lands in shots/ so it stays out of the repo.
"""

import os, sys, wave
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import numpy as np
import pygame
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

from core.audio import Audio, SR
from game.levels import BIOMES, BIOME_BY_ID

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shots')


class Recorder(Audio):
	"""Same engine, but every trigger is written to a buffer instead of a channel."""

	def start(self, seconds):
		self.buf = np.zeros((int(SR * seconds) + SR, 2), dtype=np.float32)
		self.clock = 0.0

	def _stamp(self, snd, vol):
		if snd is None: return
		a = pygame.sndarray.array(snd).astype(np.float32) / 32768.0
		i = int(self.clock * SR)
		n = min(len(a), len(self.buf) - i)
		if n > 0: self.buf[i:i + n] += a[:n] * vol

	def play(self, name, vol=1.0, throttle=0.0, pitch_var=0.0):
		if self.muted: return
		if throttle:
			t = self.last.get(name, -9.0)
			if self.time - t < throttle: return
			self.last[name] = self.time
		self._stamp(self.sfx.get(name), vol)

	def note(self, bank, semitone, vol=1.0):
		arr = self.notes.get(bank)
		if not arr: return
		i = int(semitone)
		while i >= len(arr): i -= 12
		while i < 0: i += 12
		if 0 <= i < len(arr): self._stamp(arr[i], vol)


def write(path, buf):
	peak = float(np.abs(buf).max()) or 1.0
	rms = float(np.sqrt((buf ** 2).mean()))
	x = np.clip(buf / max(1.0, peak), -1.0, 1.0)
	with wave.open(path, 'wb') as f:
		f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR)
		f.writeframes((x * 32000).astype('<i2').tobytes())
	print('%-42s peak %.2f  rms %.3f  %.1fs' % (path, peak, rms, len(buf) / SR))


def render_biome(a, b, seconds, intensity, boss=False):
	a.start(seconds)
	a.set_music(b['music'])
	a.set_boss(boss)
	dt = 1.0 / 120.0
	n = int(seconds / dt)
	for i in range(n):
		a.clock = i * dt
		# ramp the intensity across the take so every layer gets to show up
		f = intensity if intensity is not None else min(1.0, i / (n * 0.75))
		a.update(dt, f)
	return a.buf


if __name__ == '__main__':
	os.makedirs(OUT, exist_ok=True)
	a = Recorder()
	arg = sys.argv[1] if len(sys.argv) > 1 else None
	secs = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
	inten = float(sys.argv[3]) if len(sys.argv) > 3 else None

	if arg == 'sfx':
		names = [k for k in a.sfx]
		a.start(len(names) * 0.9 + 2)
		for i, k in enumerate(names):
			a.clock = i * 0.9
			a._stamp(a.sfx[k], 1.0)
			print('%2d  %s' % (i, k))
		write(os.path.join(OUT, 'audio_sfx.wav'), a.buf)
	elif arg:
		b = BIOME_BY_ID[arg]
		write(os.path.join(OUT, 'audio_%s.wav' % arg), render_biome(a, b, secs, inten))
	else:
		for b in BIOMES:
			write(os.path.join(OUT, 'audio_%s.wav' % b['id']), render_biome(a, b, secs, inten))
		write(os.path.join(OUT, 'audio_boss.wav'),
		      render_biome(a, BIOME_BY_ID['firewall'], secs, 0.9, True))
