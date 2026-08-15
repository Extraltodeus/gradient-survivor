"""Fully procedural audio: a small synth rack rendered at boot, plus a sequencer
that arranges it per biome and follows how much trouble you are in.

Everything here is numpy into pygame.sndarray -- no samples ship with the game.
The rack is: six pitched voices (sub, bass, pluck, lead, bell, pad), a drum kit,
and the SFX bank. The sequencer is chord-relative: patterns store scale degrees
and chord-tone indices, never absolute notes, so a biome's progression can walk
underneath its own riff and stay in key.

Filters are cumsum boxcars rather than convolutions: O(n) regardless of cutoff,
which is what keeps the whole rack under a second of boot time.
"""

import math, random
import numpy as np
import pygame

SR = 44100
MASTER = 0.55
TAU_F = float(np.pi * 2.0)

_rng = np.random.default_rng(7)


# ---------------------------------------------------------------- helpers
def _sec(d): return max(64, int(SR * d))


def _t(n): return np.arange(n, dtype=np.float32) / SR


def _noise(n): return _rng.standard_normal(n).astype(np.float32)


def _osc(freq, n, wave='sin', phase=0.0):
	t = np.arange(n, dtype=np.float32) / SR
	if callable(freq):
		f = freq(t)
		ph = np.cumsum(f) * (TAU_F / SR) + phase
	else:
		ph = t * (TAU_F * freq) + phase
	if wave == 'sin':   return np.sin(ph)
	if wave == 'saw':   return 2.0 * ((ph / TAU_F) % 1.0) - 1.0
	if wave == 'sq':    return np.sign(np.sin(ph))
	if wave == 'tri':   return 2.0 * np.abs(2.0 * ((ph / TAU_F) % 1.0) - 1.0) - 1.0
	if wave == 'pulse': return np.where((ph / TAU_F) % 1.0 < 0.24, 1.0, -1.0)
	return np.sin(ph)


def _ma(x, width, passes=2):
	"""Boxcar lowpass via cumsum. Two passes is a gentle, musical rolloff."""
	w = int(width)
	if w < 2: return x
	y = x
	n = len(x)
	for _ in range(passes):
		c = np.cumsum(np.concatenate((np.zeros(1, np.float32), y)), dtype=np.float32)
		z = (c[w:] - c[:-w]) * (1.0 / w)
		if len(z) < n:
			z = np.concatenate((z, np.full(n - len(z), z[-1] if len(z) else 0.0, np.float32)))
		y = z
	return y.astype(np.float32)


def _lp(x, hz, passes=2):
	return _ma(x, max(2, int(SR / max(20.0, hz))), passes)


def _hp(x, hz=2000.0):
	return (x - _lp(x, hz, 1)).astype(np.float32)


def _sat(x, k=2.2):
	return np.tanh(x * k).astype(np.float32)


def _env(n, attack=0.004, shape=2.6, hold=0.0):
	a = max(1, int(SR * attack))
	e = np.ones(n, dtype=np.float32)
	if a < n: e[:a] = np.linspace(0.0, 1.0, a, dtype=np.float32)
	h = int(SR * hold)
	rest = n - a - h
	if rest > 0:
		e[a + h:] = (1.0 - np.linspace(0.0, 1.0, rest, dtype=np.float32)) ** shape
	return e


def _exp(n, k=8.0):
	return np.exp(-_t(n) * k).astype(np.float32)


def _delay(x, time, fb=0.4, taps=3, mix=0.55):
	y = x.copy()
	d = int(SR * time)
	if d < 1: return y
	for k in range(1, taps + 1):
		o = d * k
		if o >= len(x): break
		y[o:] += x[:len(x) - o] * (fb ** k) * mix
	return y


_VERB_T = (0.029, 0.041, 0.059, 0.077, 0.101, 0.131, 0.163)

def _verb(x, amount=0.30, n=6):
	y = x.copy()
	for i, tt in enumerate(_VERB_T[:n]):
		d = int(SR * tt)
		if d >= len(x): break
		y[d:] += x[:len(x) - d] * amount * (0.72 ** i)
	return y


def _metal(n, base, ratios=(1.0, 1.41, 1.87, 2.34, 2.93, 3.71)):
	"""Inharmonic cluster: the raw material of every cymbal."""
	x = np.zeros(n, dtype=np.float32)
	for r in ratios:
		x += _osc(base * r, n, 'sq')
	return x / len(ratios)


def _snd(mono, vol=1.0, pan=0.0):
	mono = np.clip(mono * vol * MASTER, -1.0, 1.0)
	l = mono * min(1.0, 1.0 - pan)
	r = mono * min(1.0, 1.0 + pan)
	st = np.stack([l, r], axis=1)
	return pygame.sndarray.make_sound(np.ascontiguousarray((st * 32000).astype(np.int16)))


def _deg(scale, d):
	"""Scale degree -> semitones, wrapping octaves in both directions."""
	n = len(scale)
	return scale[d % n] + 12 * (d // n)


def chord_tones(scale, degree, n=4):
	"""Stack thirds inside the scale: always in key, never a wrong note."""
	return [_deg(scale, degree + 2 * i) for i in range(n)]


# ------------------------------------------------------------ voice bank
# id: (base freq, count, duration)
VOICES = {
	'sub':   (41.20, 26, 0.50),
	'bass':  (55.00, 26, 0.52),
	'pluck': (220.0, 30, 0.42),
	'lead':  (220.0, 30, 0.62),
	'bell':  (330.0, 24, 1.00),
	'warm':  (110.0, 24, 2.00),
}


def _render_voice(kind, f):
	if kind == 'sub':
		n = _sec(0.50)
		x = _osc(f, n, 'sin') + _osc(f * 2.0, n, 'sin') * 0.22 + _osc(f, n, 'tri') * 0.18
		return _sat(x * _env(n, 0.006, 2.2), 1.4) * 0.5

	if kind == 'bass':
		n = _sec(0.52)
		x = _osc(f, n, 'saw') * 0.6 + _osc(f * 0.5, n, 'sq') * 0.35 + _osc(f * 1.005, n, 'saw') * 0.3
		x = _lp(x, f * 6.0 + 180.0)
		return _sat(x * _env(n, 0.005, 2.4), 1.8) * 0.45

	if kind == 'pluck':
		n = _sec(0.42)
		idx = _exp(n, 16.0) * 5.0
		ph = _t(n) * (TAU_F * f)
		x = np.sin(ph + idx * np.sin(ph * 2.0)).astype(np.float32)
		return x * _env(n, 0.002, 3.4) * 0.5

	if kind == 'lead':
		n = _sec(0.62)
		x = (_osc(f, n, 'pulse') * 0.45 + _osc(f * 1.007, n, 'saw') * 0.35
		     + _osc(f * 0.993, n, 'saw') * 0.3 + _osc(f * 2.0, n, 'sin') * 0.18)
		x = _lp(x, f * 7.0 + 600.0) * _env(n, 0.004, 3.0)
		return _delay(x, 0.135, 0.42, 3, 0.42) * 0.34

	if kind == 'bell':
		n = _sec(1.00)
		ph = _t(n) * (TAU_F * f)
		idx = _exp(n, 5.0) * 3.2
		x = np.sin(ph + idx * np.sin(ph * 3.51)).astype(np.float32)
		x = x * _env(n, 0.002, 1.6)
		return _verb(x, 0.26, 5) * 0.3

	# warm pad: detuned stack, slow attack, breathing
	n = _sec(2.00)
	x = np.zeros(n, dtype=np.float32)
	for d in (0.994, 0.999, 1.0, 1.006, 1.012):
		x += _osc(f * d, n, 'saw')
	x += _osc(f * 0.5, n, 'tri') * 1.4
	x = _lp(x / 6.0, f * 4.0 + 320.0)
	trem = 1.0 - 0.22 * (0.5 + 0.5 * np.sin(_t(n) * TAU_F * 2.6))
	x = x * _env(n, 0.42, 1.1, 0.30) * trem
	return _verb(x, 0.22, 6) * 0.5


class Audio:
	def __init__(self, enabled=True):
		self.ok = False
		self.muted = not enabled
		self.sfx = {}
		self.last = {}
		self.time = 0.0
		self.music_on = True
		self.step = 0
		self.tick_t = 0.0
		self.step_dur = 0.12
		self.bpm = 104.0
		self.pattern = None
		self.notes = {}
		self.intensity = 0.0
		self.boss = False
		try:
			pygame.mixer.set_num_channels(56)
			self.ok = True
		except Exception:
			return
		self._build()

	# ---------------------------------------------------------------- build
	def _build(self):
		S = self.sfx

		# --- weapon voices: a body, a transient and a tail, per emitter family
		def blip(f0, f1, d, wave, vol, sh=3.2, noise=0.0, body=0.0, sat=1.0):
			n = _sec(d)
			freq = lambda tt, f0=f0, f1=f1, d=d: f0 * (f1 / f0) ** np.clip(tt / d, 0, 1)
			x = _osc(freq, n, wave)
			if body: x += _osc(lambda tt: freq(tt) * 0.5, n, 'sin') * body
			if noise: x = x * (1.0 - noise) + _hp(_noise(n), 1200) * noise
			x = x * _env(n, 0.002, sh)
			if sat != 1.0: x = _sat(x, sat)
			return _snd(x, vol)

		S['fire_bolt']  = blip(940, 280, 0.11, 'sq', 0.19, 3.4, 0.06, 0.5, 1.6)
		S['fire_swarm'] = blip(1650, 820, 0.07, 'tri', 0.12, 3.0, 0.10)
		S['fire_nova']  = blip(240, 70, 0.38, 'saw', 0.25, 2.0, 0.05, 0.7, 2.4)
		S['fire_beam']  = blip(190, 168, 0.24, 'saw', 0.13, 1.2, 0.08, 0.4)
		S['fire_mine']  = blip(320, 130, 0.16, 'tri', 0.17, 2.6, 0.0, 0.6)
		S['fire_arc']   = blip(1400, 380, 0.14, 'pulse', 0.16, 2.4, 0.40)
		S['fire_turret']= blip(660, 400, 0.10, 'pulse', 0.14, 3.0, 0.12)
		S['fire_orb']   = blip(520, 780, 0.11, 'sin', 0.13, 3.0, 0.0, 0.5)
		S['fire_boom']  = blip(400, 760, 0.15, 'tri', 0.15, 2.6, 0.12, 0.4)

		# --- impact / death
		n = _sec(0.08)
		S['hit'] = _snd(_hp(_noise(n), 2600) * _env(n, 0.001, 4.5) * 0.7
		                + _osc(lambda t: 700 * np.exp(-t * 30), n, 'sin') * _exp(n, 40) * 0.3, 0.11)
		n = _sec(0.18)
		S['kill'] = _snd(_sat((_osc(lambda t: 460 * np.exp(-t * 15), n, 'sq') * 0.45
		                       + _hp(_noise(n), 900) * 0.55) * _env(n, 0.001, 3.0), 1.5), 0.17)
		n = _sec(0.62)
		body = _osc(lambda t: 130 * np.exp(-t * 5.5) + 32, n, 'sin')
		S['explode'] = _snd(_sat((_lp(_noise(n), 900) * 2.2 + body * 1.1) * _env(n, 0.002, 1.9), 1.6), 0.36)
		n = _sec(0.32)
		S['shatter'] = _snd((_hp(_noise(n), 3200) * 1.5
		                     + _metal(n, 900) * _exp(n, 14) * 0.5) * _env(n, 0.001, 3.0), 0.20)
		n = _sec(0.38)
		S['zap'] = _snd((_hp(_noise(n), 1800) * 0.9
		                 + _osc(lambda t: 1100 * np.exp(-t * 6), n, 'pulse') * 0.6)
		                * _env(n, 0.001, 3.4), 0.19)

		# --- player
		n = _sec(0.38)
		S['hurt'] = _snd(_sat((_osc(lambda t: 320 * np.exp(-t * 5.5), n, 'saw') * 0.7
		                       + _lp(_noise(n), 700) * 0.5) * _env(n, 0.001, 2.0), 1.7), 0.35)
		n = _sec(0.10)
		S['pickup'] = _snd(_osc(lambda t: 760 + 1100 * t / 0.10, n, 'sin') * _env(n, 0.002, 3.0), 0.10)
		n = _sec(0.16)
		S['gem'] = _snd((_osc(lambda t: 1250 + 700 * t / 0.16, n, 'tri') * 0.7
		                 + _osc(lambda t: 2500 + 1400 * t / 0.16, n, 'sin') * 0.3) * _env(n, 0.002, 3.0), 0.14)
		n = _sec(0.34)
		S['heal'] = _snd(_verb((_osc(lambda t: 523 + 262 * t / 0.34, n, 'sin')
		                        + _osc(lambda t: 784 + 392 * t / 0.34, n, 'sin') * 0.5)
		                       * _env(n, 0.01, 2.2), 0.2, 3), 0.21)

		# --- chords / stingers
		def chord(freqs, d, wave='tri', vol=0.3, slide=1.0, sh=2.0, verb=0.0):
			n = _sec(d)
			x = np.zeros(n, dtype=np.float32)
			for i, f in enumerate(freqs):
				x += _osc(lambda t, f=f: f * (slide ** (t / d)), n, wave) / (i + 1.6)
			x = x * _env(n, 0.006, sh)
			if verb: x = _verb(x, verb, 5)
			return _snd(x, vol)

		S['levelup'] = chord([523, 659, 784, 1046], 0.75, 'tri', 0.30, 1.06, 2.0, 0.22)
		S['evolve']  = chord([392, 523, 659, 784, 1175], 1.6, 'saw', 0.28, 1.5, 1.4, 0.30)
		S['merge']   = chord([294, 440, 587, 880], 1.2, 'sq', 0.21, 1.25, 1.6, 0.25)
		S['pick']    = chord([740, 1109], 0.15, 'sq', 0.16)
		S['move']    = chord([440], 0.05, 'sq', 0.09)
		S['deny']    = chord([175, 185], 0.20, 'sq', 0.16, 0.82)

		n = _sec(2.6)
		S['boss'] = _snd(_sat((_osc(lambda t: 92 * np.exp(-t * 0.55), n, 'saw') * 0.9
		                       + _lp(_noise(n), 300) * 1.1
		                       + _osc(lambda t: 46 + 4 * np.sin(t * 19), n, 'sin') * 1.2)
		                      * _env(n, 0.06, 1.4, 0.55), 1.5), 0.44)
		n = _sec(2.0)
		S['bossdie'] = _snd(_verb(_sat((_lp(_noise(n), 700) * 1.6
		                                + _osc(lambda t: 280 * np.exp(-t * 2.4), n, 'saw') * 0.8)
		                               * _env(n, 0.004, 1.5), 1.4), 0.24, 5), 0.46)
		n = _sec(1.4)
		S['gameover'] = _snd(_verb((_osc(lambda t: 220 * (0.5 ** (t / 1.4)), n, 'saw') * 0.6
		                            + _osc(lambda t: 110 * (0.5 ** (t / 1.4)), n, 'sin') * 0.8)
		                           * _env(n, 0.02, 1.5), 0.3, 6), 0.34)
		n = _sec(0.9)
		S['warn'] = _snd(_osc(lambda t: 330 + 110 * np.sin(t * 24), n, 'sq') * _env(n, 0.02, 1.4, 0.4), 0.19)
		n = _sec(0.7)
		S['biome'] = _snd(_verb((_osc(lambda t: 150 * (4.0 ** (t / 0.7)), n, 'tri') * 0.8
		                         + _metal(n, 420) * _exp(n, 6) * 0.4) * _env(n, 0.01, 1.8), 0.3, 6), 0.28)

		# --- drum kit
		n = _sec(0.36)
		click = _hp(_noise(n), 3000) * _exp(n, 90) * 0.6
		S['kick'] = _snd(_sat((_osc(lambda t: 170 * np.exp(-t * 26) + 46, n, 'sin') * 1.2 + click)
		                      * _env(n, 0.001, 2.4), 2.0), 0.44)
		n = _sec(0.055)
		S['hat'] = _snd(_hp(_metal(n, 640) * 0.6 + _noise(n) * 0.5, 5500) * _env(n, 0.001, 5.0), 0.11)
		n = _sec(0.26)
		S['ohat'] = _snd(_hp(_metal(n, 640) * 0.6 + _noise(n) * 0.5, 5000) * _env(n, 0.001, 2.4), 0.09)
		n = _sec(0.26)
		S['snare'] = _snd(_sat((_hp(_noise(n), 1400) * 1.3 + _osc(196, n, 'tri') * 0.35
		                        + _osc(331, n, 'sin') * 0.2) * _env(n, 0.001, 3.2), 1.3), 0.21)
		n = _sec(0.30)
		cl = np.zeros(n, dtype=np.float32)
		for k, off in enumerate((0.0, 0.009, 0.019, 0.030)):
			o = int(SR * off)
			seg = _hp(_noise(n - o), 1500) * _exp(n - o, 55 if k < 3 else 16)
			cl[o:] += seg * (0.9 ** k)
		S['clap'] = _snd(cl * 0.8, 0.19)
		n = _sec(0.34)
		S['tom'] = _snd(_sat((_osc(lambda t: 250 * np.exp(-t * 9) + 90, n, 'sin') * 1.1
		                      + _lp(_noise(n), 900) * 0.3) * _env(n, 0.001, 2.6), 1.4), 0.24)
		n = _sec(0.85)
		S['ride'] = _snd(_hp(_metal(n, 520, (1.0, 1.63, 2.21, 3.07, 4.13)), 4200)
		                 * _env(n, 0.001, 2.0) * 0.7, 0.10)
		n = _sec(1.5)
		S['crash'] = _snd(_verb(_hp(_metal(n, 400) * 0.7 + _noise(n) * 0.8, 3000)
		                        * _env(n, 0.002, 1.5), 0.2, 4) * 0.7, 0.20)

		# --- pitched voices
		for name, (base, count, _d) in VOICES.items():
			bank = []
			for i in range(count):
				f = base * (2.0 ** (i / 12.0))
				bank.append(_snd(_render_voice(name, f), 1.0))
			self.notes[name] = bank

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
		self.step = 0
		self.tick_t = 0.0

	def set_boss(self, on):
		self.boss = bool(on)

	def update(self, dt, intensity=0.0):
		self.time += dt
		self.intensity = intensity
		if not self.ok or self.muted or not self.music_on or not self.pattern: return
		spb = 60.0 / self.bpm / 4.0        # sixteenths
		sw = self.pattern.get('swing', 0.0)
		self.tick_t += dt
		guard = 0
		while guard < 8:
			guard += 1
			dur = spb * (1.0 + sw if (self.step & 1) == 0 else 1.0 - sw)
			if self.tick_t < dur: break
			self.tick_t -= dur
			self._step()
			self.step += 1

	def _step(self):
		p = self.pattern
		st = self.step
		i16 = st % 16
		bar = (st // 16) % 4
		inten = min(1.0, self.intensity + (0.35 if self.boss else 0.0))
		scale = p['scale']
		root = p['root']
		prog = p.get('prog', (0,))
		deg = prog[bar % len(prog)]
		tones = chord_tones(scale, deg)
		vb = p.get('voices', ('bass', 'pluck', 'lead', 'warm'))
		v_bass, v_arp, v_lead, v_pad = vb

		# --- pad: one chord per bar, held
		if i16 == 0:
			oct_ = 0 if not self.boss else -12
			self.note(v_pad, root + tones[0] + oct_, 0.42 + 0.16 * inten)
			self.note(v_pad, root + tones[1] + oct_, 0.30 + 0.12 * inten)
			self.note(v_pad, root + tones[2] + oct_, 0.24 + 0.10 * inten)
			if bar == 0 and inten > 0.45:
				self.play('crash', 0.28 + 0.3 * inten)

		# --- bass: scale-degree offsets from the running chord root
		bp = p['bass']
		v = bp[st % len(bp)]
		if v >= 0:
			self.note(v_bass, root + _deg(scale, deg + v) - (12 if self.boss else 0), 0.88)

		# --- arp: chord tones, comes in once things move
		ap = p.get('arp')
		if ap and inten > 0.10:
			v = ap[st % len(ap)]
			if v >= 0:
				n = len(tones)
				semi = tones[v % n] + 12 * (v // n)
				self.note(v_arp, root + 12 + semi, 0.22 + 0.30 * inten)

		# --- lead: the melody only shows up when it is earned
		if inten > 0.42 or p.get('always_lead') or self.boss:
			lp = p['lead']
			v = lp[st % len(lp)]
			if v >= 0:
				self.note(v_lead, root + 12 + _deg(scale, v), 0.26 + 0.42 * min(1.0, inten))

		# --- drums
		dr = p['drums']
		d = dr[i16 % len(dr)]
		if d & 1: self.play('kick', 0.88)
		if d & 2 and inten > 0.06: self.play('hat', 0.22 + 0.32 * inten)
		if d & 4 and inten > 0.22: self.play('snare', 0.42 + 0.2 * inten)
		if d & 8 and inten > 0.30: self.play('ohat', 0.30)
		if d & 16 and inten > 0.50: self.play('clap', 0.38)
		if d & 32 and inten > 0.55: self.play('tom', 0.40)
		if d & 64 and inten > 0.70: self.play('ride', 0.30)
		if self.boss and i16 in (6, 14): self.play('tom', 0.34)

		# --- fill: last beat of the 4-bar loop, once the fight is hot
		if bar == 3 and i16 >= 12 and inten > 0.35:
			if i16 % 2 == 0: self.play('tom', 0.30 + 0.1 * (i16 - 12))
			else: self.play('snare', 0.26)

	def toggle_mute(self):
		self.muted = not self.muted
		if self.muted: pygame.mixer.stop()
		return self.muted
