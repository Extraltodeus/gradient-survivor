"""Fully procedural audio: synthesised SFX + a generative sequencer per biome."""

import math, random
import numpy as np
import pygame

SR = 44100
MASTER = 0.55


def _env(n, attack=0.004, shape=2.6, hold=0.0):
	a = max(1, int(SR * attack))
	e = np.ones(n, dtype=np.float32)
	if a < n: e[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
	h = int(SR * hold)
	rest = n - a - h
	if rest > 0:
		e[a + h:] = (1.0 - np.linspace(0.0, 1.0, rest, dtype=np.float32)) ** shape
	return e


def _osc(freq, n, wave='sin', phase=0.0):
	t = np.arange(n, dtype=np.float32) / SR
	if callable(freq):
		f = freq(t)
		ph = np.cumsum(f) * (TAU_F / SR) + phase
	else:
		ph = t * (TAU_F * freq) + phase
	if wave == 'sin':  return np.sin(ph)
	if wave == 'saw':  return 2.0 * ((ph / TAU_F) % 1.0) - 1.0
	if wave == 'sq':   return np.sign(np.sin(ph))
	if wave == 'tri':  return 2.0 * np.abs(2.0 * ((ph / TAU_F) % 1.0) - 1.0) - 1.0
	if wave == 'pulse':return np.where((ph / TAU_F) % 1.0 < 0.24, 1.0, -1.0)
	return np.sin(ph)


TAU_F = float(np.pi * 2.0)
_rng = np.random.default_rng(7)


def _noise(n): return _rng.standard_normal(n).astype(np.float32)


_lp_kern = {}

def _lp(x, a=0.22):
	"""One-pole lowpass as an FIR convolution (exact impulse response, truncated)."""
	h = _lp_kern.get(a)
	if h is None:
		n = min(2048, max(8, int(math.ceil(math.log(1e-4) / math.log(max(1e-6, 1.0 - a))))))
		h = (a * (1.0 - a) ** np.arange(n)).astype(np.float32)
		_lp_kern[a] = h
	return np.convolve(x, h)[:len(x)].astype(np.float32)


def _hp(x): return np.concatenate(([0.0], np.diff(x))).astype(np.float32)


def _snd(mono, vol=1.0, pan=0.0):
	mono = np.clip(mono * vol * MASTER, -1.0, 1.0)
	l = mono * min(1.0, 1.0 - pan)
	r = mono * min(1.0, 1.0 + pan)
	st = np.stack([l, r], axis=1)
	return pygame.sndarray.make_sound(np.ascontiguousarray((st * 32000).astype(np.int16)))


def _sec(d): return max(64, int(SR * d))


class Audio:
	def __init__(self, enabled=True):
		self.ok = False
		self.muted = not enabled
		self.sfx = {}
		self.last = {}
		self.time = 0.0
		self.music_on = True
		self.beat = 0
		self.tick_t = 0.0
		self.bpm = 104.0
		self.pattern = None
		self.notes = {}
		self.intensity = 0.0
		try:
			pygame.mixer.set_num_channels(48)
			self.ok = True
		except Exception:
			return
		self._build()

	# ---------------------------------------------------------------- build
	def _build(self):
		S = self.sfx

		# --- weapon blips (one timbre per emitter family)
		def blip(f0, f1, d, wave, vol, sh=3.2, noise=0.0):
			n = _sec(d)
			t = np.linspace(0.0, 1.0, n, dtype=np.float32)
			freq = lambda tt, f0=f0, f1=f1, d=d: f0 * (f1 / f0) ** np.clip(tt / d, 0, 1)
			x = _osc(freq, n, wave)
			if noise: x = x * (1.0 - noise) + _noise(n) * noise
			return _snd(x * _env(n, 0.002, sh), vol)

		S['fire_bolt']  = blip(880, 300, 0.10, 'sq', 0.20)
		S['fire_swarm'] = blip(1500, 900, 0.06, 'tri', 0.13)
		S['fire_nova']  = blip(220, 90, 0.35, 'saw', 0.26, 2.2)
		S['fire_beam']  = blip(180, 175, 0.22, 'saw', 0.14, 1.2)
		S['fire_mine']  = blip(300, 150, 0.14, 'tri', 0.18)
		S['fire_arc']   = blip(1200, 420, 0.13, 'pulse', 0.17, 2.4, 0.35)
		S['fire_turret']= blip(600, 420, 0.09, 'pulse', 0.15)
		S['fire_orb']   = blip(520, 700, 0.10, 'sin', 0.13)
		S['fire_boom']  = blip(420, 720, 0.14, 'tri', 0.16)

		# --- impact / death
		n = _sec(0.07)
		S['hit'] = _snd(_hp(_noise(n)) * _env(n, 0.001, 4.5) * 0.6, 0.10)
		n = _sec(0.16)
		S['kill'] = _snd((_osc(lambda t: 420 * np.exp(-t * 14), n, 'sq') * 0.5 + _noise(n) * 0.5)
		                 * _env(n, 0.001, 3.2), 0.16)
		n = _sec(0.5)
		S['explode'] = _snd((_lp(_noise(n), 0.10) * 1.6 + _osc(lambda t: 120 * np.exp(-t * 6), n, 'sin'))
		                    * _env(n, 0.002, 2.0), 0.34)
		n = _sec(0.28)
		S['shatter'] = _snd((_hp(_noise(n)) * 1.4 + _osc(lambda t: 2400 * np.exp(-t * 9), n, 'tri') * 0.4)
		                    * _env(n, 0.001, 3.0), 0.20)
		n = _sec(0.35)
		S['zap'] = _snd((_hp(_noise(n)) * 0.9 + _osc(lambda t: 900 * np.exp(-t * 5), n, 'pulse') * 0.6)
		                * _env(n, 0.001, 3.4), 0.18)

		# --- player
		n = _sec(0.34)
		S['hurt'] = _snd((_osc(lambda t: 300 * np.exp(-t * 5), n, 'saw') * 0.7 + _noise(n) * 0.3)
		                 * _env(n, 0.001, 2.2), 0.34)
		n = _sec(0.09)
		S['pickup'] = _snd(_osc(lambda t: 700 + 900 * t / 0.09, n, 'sin') * _env(n, 0.002, 3.0), 0.10)
		n = _sec(0.14)
		S['gem'] = _snd(_osc(lambda t: 1200 + 600 * t / 0.14, n, 'tri') * _env(n, 0.002, 3.0), 0.14)
		n = _sec(0.28)
		S['heal'] = _snd((_osc(lambda t: 520 + 260 * t / 0.28, n, 'sin')
		                  + _osc(lambda t: 780 + 390 * t / 0.28, n, 'sin') * 0.5) * _env(n, 0.01, 2.2), 0.20)

		# --- chords / stingers
		def chord(freqs, d, wave='tri', vol=0.3, slide=1.0, sh=2.0):
			n = _sec(d)
			x = np.zeros(n, dtype=np.float32)
			for i, f in enumerate(freqs):
				x += _osc(lambda t, f=f: f * (slide ** (t / d)), n, wave) / (i + 1.6)
			return _snd(x * _env(n, 0.006, sh), vol)

		S['levelup'] = chord([523, 659, 784, 1046], 0.7, 'tri', 0.30, 1.06)
		S['evolve']  = chord([392, 523, 659, 784, 1175], 1.5, 'saw', 0.30, 1.5, 1.4)
		S['merge']   = chord([294, 440, 587, 880], 1.1, 'sq', 0.22, 1.25, 1.6)
		S['pick']    = chord([740, 1109], 0.14, 'sq', 0.16)
		S['move']    = chord([420], 0.05, 'sq', 0.10)
		S['deny']    = chord([180, 190], 0.18, 'sq', 0.16, 0.8)

		n = _sec(2.4)
		S['boss'] = _snd((_osc(lambda t: 90 * np.exp(-t * 0.6), n, 'saw') * 0.8
		                  + _lp(_noise(n), 0.05) * 0.9
		                  + _osc(lambda t: 45 + 3 * np.sin(t * 22), n, 'sin')) * _env(n, 0.05, 1.4, 0.5), 0.42)
		n = _sec(1.8)
		S['bossdie'] = _snd((_lp(_noise(n), 0.08) * 1.4
		                     + _osc(lambda t: 260 * np.exp(-t * 2.2), n, 'saw') * 0.7) * _env(n, 0.004, 1.6), 0.44)
		n = _sec(1.2)
		S['gameover'] = _snd((_osc(lambda t: 220 * (0.5 ** (t / 1.2)), n, 'saw') * 0.7
		                      + _osc(lambda t: 110 * (0.5 ** (t / 1.2)), n, 'sin')) * _env(n, 0.02, 1.6), 0.34)
		n = _sec(0.8)
		S['warn'] = _snd(_osc(lambda t: 320 + 90 * np.sin(t * 26), n, 'sq') * _env(n, 0.02, 1.4, 0.35), 0.18)
		n = _sec(0.45)
		S['biome'] = _snd((_osc(lambda t: 160 * (3.0 ** (t / 0.45)), n, 'tri')
		                   + _noise(n) * 0.25) * _env(n, 0.01, 2.0), 0.26)

		# --- musical voices, chromatic bank around A1..A5
		self.notes = {'bass': [], 'lead': [], 'pad': []}
		for i in range(36):
			f = 55.0 * (2.0 ** (i / 12.0))
			n = _sec(0.30)
			x = (_osc(f, n, 'saw') * 0.55 + _osc(f * 0.5, n, 'sq') * 0.45)
			self.notes['bass'].append(_snd(_lp(x, 0.30) * _env(n, 0.004, 2.4), 0.20))
		for i in range(36):
			f = 220.0 * (2.0 ** (i / 12.0))
			n = _sec(0.24)
			x = _osc(f, n, 'pulse') * 0.5 + _osc(f * 2.01, n, 'sin') * 0.3
			self.notes['lead'].append(_snd(x * _env(n, 0.002, 3.6), 0.13))
		for i in range(36):
			f = 110.0 * (2.0 ** (i / 12.0))
			n = _sec(1.6)
			x = (_osc(f, n, 'saw') + _osc(f * 1.005, n, 'saw') + _osc(f * 0.999, n, 'tri')) / 3.0
			self.notes['pad'].append(_snd(_lp(x, 0.06) * _env(n, 0.35, 1.2, 0.35), 0.10))

		n = _sec(0.30)
		self.sfx['kick'] = _snd((_osc(lambda t: 145 * np.exp(-t * 22) + 44, n, 'sin')
		                         + _noise(n) * np.exp(-np.linspace(0, 1, n) * 40) * 0.5) * _env(n, 0.001, 2.6), 0.42)
		n = _sec(0.06)
		self.sfx['hat'] = _snd(_hp(_noise(n)) * _env(n, 0.001, 5.0), 0.10)
		n = _sec(0.22)
		self.sfx['snare'] = _snd((_hp(_noise(n)) * 1.2 + _osc(190, n, 'tri') * 0.4) * _env(n, 0.001, 3.4), 0.20)

	# ---------------------------------------------------------------- play
	def play(self, name, vol=1.0, throttle=0.0, pitch_var=0.0):
		if self.muted or not self.ok: return
		s = self.sfx.get(name)
		if s is None: return
		if throttle:
			t = self.last.get(name, -9.0)
			if self.time - t < throttle: return
			self.last[name] = self.time
		ch = pygame.mixer.find_channel(True)
		if ch is None: return
		s.set_volume(vol)
		ch.play(s)

	def note(self, bank, semitone, vol=1.0):
		if self.muted or not self.ok or not self.music_on: return
		arr = self.notes.get(bank)
		if not arr: return
		i = int(semitone)
		while i >= len(arr): i -= 12
		while i < 0: i += 12
		if i < 0 or i >= len(arr): return
		ch = pygame.mixer.find_channel(True)
		if ch is None: return
		arr[i].set_volume(vol)
		ch.play(arr[i])

	# ---------------------------------------------------------------- music
	def set_music(self, pattern):
		self.pattern = pattern
		self.bpm = pattern.get('bpm', 104)
		self.beat = 0

	def update(self, dt, intensity=0.0):
		self.time += dt
		self.intensity = intensity
		if not self.ok or self.muted or not self.music_on or not self.pattern: return
		spb = 60.0 / self.bpm / 2.0   # eighth notes
		self.tick_t += dt
		while self.tick_t >= spb:
			self.tick_t -= spb
			self._tick()
			self.beat += 1

	def _tick(self):
		p = self.pattern
		b = self.beat
		st = b % 16
		root = p['root']
		sc = p['scale']
		inten = self.intensity

		bass = p['bass']
		v = bass[st % len(bass)]
		if v >= 0:
			self.note('bass', root + sc[v % len(sc)] + 12 * (v // len(sc)), 0.85)

		if inten > 0.12 or p.get('always_lead'):
			lead = p['lead']
			v = lead[b % len(lead)]
			if v >= 0:
				self.note('lead', root + 12 + sc[v % len(sc)] + 12 * (v // len(sc)),
				          0.35 + 0.5 * min(1.0, inten))

		dr = p['drums']
		d = dr[st % len(dr)]
		if d & 1: self.play('kick', 0.85)
		if d & 2 and inten > 0.05: self.play('hat', 0.30 + 0.4 * inten)
		if d & 4 and inten > 0.3: self.play('snare', 0.45)

		if st == 0 and (b // 16) % 2 == 0:
			self.note('pad', root + sc[0], 0.5)
			self.note('pad', root + sc[2 % len(sc)], 0.36)

	def toggle_mute(self):
		self.muted = not self.muted
		if self.muted: pygame.mixer.stop()
		return self.muted
