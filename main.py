"""GRADIENT DESCENT - an AI survivor.  Run me:  python main.py"""

import os, sys, math, json, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

import core.settings as S


def _pick_resolution(argv):
	"""Render natively at the display resolution: this game is all vectors, so
	there is no reason to draw small and upscale."""
	want = None
	for i, a in enumerate(argv):
		if a == '--res' and i + 1 < len(argv):
			try:
				ww, hh = argv[i + 1].lower().split('x')
				want = (int(ww), int(hh))
			except Exception:
				want = None
	if want is None:
		try:
			dw, dh = pygame.display.get_desktop_sizes()[0]
		except Exception:
			dw, dh = 1280, 720
		# cap the pixel budget: this is a CPU-side renderer
		if dw * dh > 1920 * 1080:
			k = (1920 * 1080 / float(dw * dh)) ** 0.5
			dw, dh = int(dw * k) & ~1, int(dh * k) & ~1
		want = (max(1024, dw), max(600, dh))
	S.set_res(*want)


_pick_resolution(sys.argv)

from core.settings import *
from core.utils import *
from core.audio import Audio
from core.pace import PACES, DEFAULT_PACE


LVL_DELAY = 1.0     # let the level-up burst finish before the cards take the screen



# Everything the player is allowed to turn off, in one table: the pause screen
# renders it, the save file stores it, and the old function keys still work.
# `vals` holds the real values, `labels` what the option screen shows.
OPTIONS = (
	dict(id='defer', name='LEVEL-UP PROMPT', key='',
	     vals=(False, True), labels=('INTERRUPT', 'BANK IT'),
	     desc='Whether a new level stops the fight at once, or waits for you to press T.'),
	dict(id='shake', name='SCREENSHAKE', key='F6',
	     vals=(1.0, 0.5, 0.0), labels=('FULL', 'LIGHT', 'OFF'),
	     desc='Camera trauma on hits and explosions. Late waves shake more than they settle.'),
	dict(id='bloom', name='BLOOM', key='F2',
	     vals=(True, False), labels=('ON', 'OFF'),
	     desc='Additive glow pass. Costs 5-12 ms, and drops itself if the framerate slips.'),
	dict(id='overlay', name='SCANLINES', key='F4',
	     vals=(True, False), labels=('ON', 'OFF'),
	     desc='Vignette and CRT lines over the play field. Free, purely a look.'),
	dict(id='dmgnum', name='DAMAGE NUMBERS', key='',
	     vals=(True, False), labels=('ON', 'OFF'),
	     desc='Floating numbers on every hit. Off is calmer and slightly faster in dense waves.'),
	dict(id='mouse_mode', name='MOUSE STEERING', key='F5',
	     vals=('pointer', 'joystick'), labels=('POINTER', 'DRAG STICK'),
	     desc='Held left button steers toward the cursor, or from wherever you pressed down.'),
	dict(id='fullscreen', name='FULLSCREEN', key='F11',
	     vals=(False, True), labels=('WINDOWED', 'FULLSCREEN'),
	     desc='The game renders at your display resolution either way, so neither is blurrier.'),
	dict(id='mute', name='AUDIO', key='M',
	     vals=(False, True), labels=('ON', 'MUTED'),
	     desc='All sound is synthesised at boot: muting frees nothing, it is only quiet.'),
	dict(id='show_fps', name='FPS COUNTER', key='F3',
	     vals=(False, True), labels=('OFF', 'ON'),
	     desc='Framerate plus live enemy, projectile and particle counts, bottom right.'),
)

OPT_BY_ID = {o['id']: o for o in OPTIONS}

KEY_OPT = {pygame.K_F2: 'bloom', pygame.K_F3: 'show_fps', pygame.K_F4: 'overlay',
           pygame.K_F5: 'mouse_mode', pygame.K_F6: 'shake', pygame.K_m: 'mute'}

def ui_pages():
	from game.ui import CODEX_PAGES
	return CODEX_PAGES


def _pace_index(pid):
	for i, p in enumerate(PACES):
		if p['id'] == pid: return i
	return next(i for i, p in enumerate(PACES) if p['id'] == DEFAULT_PACE)

def _here():
	"""Where the program lives: next to the exe once frozen, else the source dir."""
	if getattr(sys, 'frozen', False): return os.path.dirname(os.path.abspath(sys.executable))
	return os.path.dirname(os.path.abspath(__file__))


def asset(*parts):
	"""A bundled read-only file. PyInstaller unpacks datas into _MEIPASS."""
	return os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), *parts)


def _save_path():
	"""Portable first: the save sits beside the exe. If that folder is read-only
	(a USB stick, Program Files, a zip run in place) fall back to APPDATA."""
	p = os.path.join(_here(), 'save.json')
	try:
		with open(p, 'a'):
			return p
	except Exception:
		d = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'GradientDescent')
		try:
			os.makedirs(d, exist_ok=True)
		except Exception:
			pass
		return os.path.join(d, 'save.json')


SAVE = _save_path()


def load_save():
	try:
		with open(SAVE, 'r') as f:
			d = json.load(f)
	except Exception:
		d = {}
	d.setdefault('best', None)
	d.setdefault('runs', 0)
	d.setdefault('seen_evos', [])
	d.setdefault('mute', False)
	d.setdefault('scores', {})       # one board per training schedule
	return d


def save_data(d):
	try:
		with open(SAVE, 'w') as f: json.dump(d, f, indent=1)
	except Exception:
		pass


def make_overlay(W=None, H=None):
	"""Vignette + scanlines baked into one surface."""
	W = W or S.W; H = H or S.H
	o = pygame.Surface((W, H), pygame.SRCALPHA)
	cx, cy = W * 0.5, H * 0.5
	maxd = math.hypot(cx, cy)
	step = 8
	for y in range(0, H, step):
		for x in range(0, W, step):
			d = math.hypot(x + step * 0.5 - cx, (y + step * 0.5 - cy) * 1.15) / maxd
			a = int(clamp((d - 0.52) * 300.0, 0, 165))
			if a > 0:
				pygame.draw.rect(o, (0, 0, 0, a), (x, y, step, step))
	for y in range(0, H, 3):
		pygame.draw.line(o, (0, 0, 0, 26), (0, y), (W, y))
	return o


class Game:
	def __init__(self):
		self.save = load_save()
		self.fullscreen = bool(self.save.get('fullscreen'))
		# SCALED lets SDL stretch the 1280x720 logical surface to any display while
		# still reporting mouse positions in logical coordinates
		self.screen = pygame.display.set_mode((W, H), self._flags(), vsync=0)
		# the display may hand back something smaller than we asked for; adopt it
		# before any game module is imported, since they star-import W/H
		if self.screen.get_size() != (W, H):
			S.set_res(*self.screen.get_size())
			globals().update(W=S.W, H=S.H, CX=S.CX, CY=S.CY)
		pygame.display.set_caption(TITLE + '  //  ' + SUBTITLE)
		self.clock = pygame.time.Clock()

		self.splash()
		try:
			ic = pygame.image.load(asset('misc', 'gradient.png'))
			pygame.display.set_icon(pygame.transform.smoothscale(ic, (64, 64)))
		except Exception:
			pass
		self.audio = Audio()
		self.audio.muted = bool(self.save.get('mute'))
		self.overlay = make_overlay()

		self.scene = 'title'
		self.t = 0.0
		self.sel = 0
		self.menu = ['START RUN', 'SANDBOX', 'CODEX', 'OPTIONS', 'QUIT']
		self.codex_page = 0
		self.boot_sel = self.save.get('boot_sel', 0)
		self.pace_sel = _pace_index(self.save.get('pace'))
		self.boot_rects = []
		self.pace_rects = []
		self.sandbox = None
		self.codex_scroll = 0
		self.codex_max = 0
		self.world = None
		self.levelup = None
		self.lvl_wait = 0.0
		self.tree_scroll = 0
		self.tree_max = 0
		self.tree_back = 'pause'
		self.end_t = 0.0
		self.fps_acc = 0.0
		self.fps_n = 0
		self.show_fps = bool(self.save.get('show_fps', False))
		self.opt_sel = 0
		self.opt_rects = []
		self.pause_btns = []
		self.opt_btns = []
		self.lvl_hold = False
		self.lvl_last = 0
		self.mouse_mode = self.save.get('mouse_mode', 'pointer')
		self.mouse_held = False
		self.mouse_anchor = None
		self.mouse_fade = 0.0
		self.mouse_last = (CX, CY)
		# Bloom is a full-screen additive pass: ~12 ms at 1080p, ~5 ms at 720p. We
		# render natively for a crisp fullscreen, so on big displays it starts off.
		self.opts = {'dmgnum': bool(self.save.get('dmgnum', True)),
		             'shake': float(self.save.get('shake', 1.0)),
		             'quality': 1.0,
		             'defer': bool(self.save.get('defer', False)),
		             'overlay': bool(self.save.get('overlay', True)),
		             'bloom': bool(self.save.get('bloom', W * H <= 1500000))}
		self.slow_frames = 0

	def _flags(self):
		# no SCALED: we already render at display resolution, so fullscreen is 1:1
		return pygame.FULLSCREEN if self.fullscreen else 0

	def toggle_fullscreen(self):
		self.fullscreen = not self.fullscreen
		try:
			self.screen = pygame.display.set_mode((W, H), self._flags(), vsync=0)
		except Exception:
			self.fullscreen = not self.fullscreen
			self.screen = pygame.display.set_mode((W, H), self._flags(), vsync=0)
		self.save['fullscreen'] = self.fullscreen
		save_data(self.save)

	# --------------------------------------------------------------- options
	def opt_get(self, o):
		"""Which of the option's values is live right now, as an index."""
		i = o['id']
		if i == 'mouse_mode': v = self.mouse_mode
		elif i == 'fullscreen': v = self.fullscreen
		elif i == 'mute': v = self.audio.muted
		elif i == 'show_fps': v = self.show_fps
		else: v = self.opts.get(i)
		try:
			return list(o['vals']).index(v)
		except ValueError:
			return 0

	def opt_cycle(self, o, d=1):
		v = o['vals'][(self.opt_get(o) + d) % len(o['vals'])]
		i = o['id']
		if i == 'mouse_mode': self.mouse_mode = v
		elif i == 'fullscreen':
			if v != self.fullscreen: self.toggle_fullscreen()
		elif i == 'mute':
			if v != self.audio.muted: self.audio.toggle_mute()
		elif i == 'show_fps': self.show_fps = v
		else:
			self.opts[i] = v
			if i == 'bloom': self.slow_frames = 0
		self.persist_opts()
		return v

	def persist_opts(self):
		for o in OPTIONS:
			self.save[o['id']] = o['vals'][self.opt_get(o)]
		save_data(self.save)

	def opt_rows(self):
		return [(o['name'], o['key'], o['labels'][self.opt_get(o)], o['desc'],
		         self.opt_get(o), len(o['vals'])) for o in OPTIONS]

	def mouse_vec(self):
		"""Movement vector from the mouse, magnitude 0..1, or None when idle."""
		if not self.mouse_held or not self.world: return None
		mx, my = self.mouse_last
		if self.mouse_mode == 'joystick' and self.mouse_anchor:
			ox, oy = self.mouse_anchor
			dead, full = 7.0, 86.0
		else:
			camx, camy = self.world.last_cam
			ox = self.world.player.x - camx; oy = self.world.player.y - camy
			dead, full = 16.0, 78.0
		dx = mx - ox; dy = my - oy
		d = math.hypot(dx, dy)
		if d <= dead: return (0.0, 0.0)
		f = min(1.0, (d - dead) / full)
		return (dx / d * f, dy / d * f)

	def splash(self):
		s = self.screen
		s.fill((5, 7, 12))
		draw_text(s, TITLE, CX, CY - 30, 52, INK, True, 'tc')
		draw_text(s, 'compiling kernels...', CX, CY + 40, 15, INK_DIM, False, 'tc')
		pygame.display.flip()

	# ---------------------------------------------------------------- run
	def start(self, seed=None, boot=None, sandbox=False):
		from game.world import World
		from game.weapons import BOOTS
		if boot is None: boot = BOOTS[self.boot_sel]
		pace = PACES[self.pace_sel]
		self.world = World(seed, self.opts, self.audio, boot, pace, sandbox)
		self.world.banned = set()
		self.scene = 'play'
		self.levelup = None
		self.end_t = 0.0
		self.save['pace'] = pace['id']
		self.save['boot_sel'] = self.boot_sel
		if sandbox:
			from game.sandbox import Sandbox
			self.sandbox = Sandbox(self.world)
			self.scene = 'sandbox'
		else:
			self.sandbox = None

	def loop(self):
		while True:
			dt = min(0.05, self.clock.tick(FPS) / 1000.0)
			self.t += dt
			if not self.handle_events(dt): break
			self.update(dt)
			self.draw()
			pygame.display.flip()
		save_data(self.save)
		pygame.quit()

	# ------------------------------------------------------------- events
	def handle_events(self, dt):
		for ev in pygame.event.get():
			if ev.type == pygame.QUIT: return False
			if ev.type == pygame.KEYDOWN:
				hot = KEY_OPT.get(ev.key)
				if hot:
					o = OPT_BY_ID[hot]
					self.opt_cycle(o)
					if self.world:
						self.world.banner('%s  %s' % (o['name'], o['labels'][self.opt_get(o)]),
						                  o['desc'], CYAN)
					continue
				if ev.key == pygame.K_F11 or (ev.key == pygame.K_RETURN and (ev.mod & pygame.KMOD_ALT)):
					self.toggle_fullscreen()
					continue
			if ev.type == pygame.MOUSEMOTION:
				self.mouse_last = ev.pos
				self.mouse_fade = 1.6

			if self.scene == 'title':
				if ev.type == pygame.KEYDOWN:
					if ev.key in (pygame.K_UP, pygame.K_w):
						self.sel = (self.sel - 1) % len(self.menu); self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_DOWN, pygame.K_s):
						self.sel = (self.sel + 1) % len(self.menu); self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
						self.audio.play('pick', 1.0)
						m = self.menu[self.sel]
						if m == 'START RUN': self.scene = 'select'
						elif m == 'SANDBOX': self.start(sandbox=True)
						elif m == 'CODEX': self.scene = 'codex'; self.codex_scroll = 0
						elif m == 'OPTIONS': self.scene = 'options'
						else: return False
					elif ev.key == pygame.K_ESCAPE:
						return False
				elif ev.type == pygame.MOUSEWHEEL and ev.y:
					self.sel = (self.sel - ev.y) % len(self.menu); self.audio.play('move', 0.7)

			elif self.scene == 'select':
				from game.weapons import BOOTS
				if ev.type == pygame.KEYDOWN:
					n = len(BOOTS)
					if pygame.K_1 <= ev.key <= pygame.K_4:
						self.pace_sel = ev.key - pygame.K_1; self.audio.play('gem', 0.6)
					elif ev.key == pygame.K_TAB:
						self.pace_sel = (self.pace_sel + 1) % len(PACES); self.audio.play('gem', 0.6)
					elif ev.key in (pygame.K_RIGHT, pygame.K_d):
						self.boot_sel = (self.boot_sel + 1) % n; self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_LEFT, pygame.K_a):
						self.boot_sel = (self.boot_sel - 1) % n; self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_DOWN, pygame.K_s):
						self.boot_sel = (self.boot_sel + 3) % n; self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_UP, pygame.K_w):
						self.boot_sel = (self.boot_sel - 3) % n; self.audio.play('move', 0.7)
					elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
						self.audio.play('pick', 1.0); self.start()
					elif ev.key == pygame.K_ESCAPE:
						self.scene = 'title'
				elif ev.type == pygame.MOUSEWHEEL and ev.y:
					n = len(BOOTS)
					self.boot_sel = (self.boot_sel - ev.y) % n
					self.audio.play('move', 0.7)
				elif ev.type == pygame.MOUSEMOTION:
					for i, r in enumerate(self.boot_rects):
						if r.collidepoint(ev.pos): self.boot_sel = i
				elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
					for i, r in enumerate(self.pace_rects):
						if r.collidepoint(ev.pos):
							self.pace_sel = i; self.audio.play('gem', 0.7); break
					else:
						for i, r in enumerate(self.boot_rects):
							if r.collidepoint(ev.pos):
								self.boot_sel = i; self.audio.play('pick', 1.0); self.start(); break

			elif self.scene == 'codex':
				if ev.type == pygame.KEYDOWN:
					if ev.key == pygame.K_ESCAPE: self.scene = 'title'
					elif ev.key in (pygame.K_RIGHT, pygame.K_d):
						self.codex_page = (self.codex_page + 1) % ui_pages(); self.codex_scroll = 0
					elif ev.key in (pygame.K_LEFT, pygame.K_a):
						self.codex_page = (self.codex_page - 1) % ui_pages(); self.codex_scroll = 0
					elif ev.key in (pygame.K_DOWN, pygame.K_s):
						self.codex_scroll = min(max(0, self.codex_max - H + 120), self.codex_scroll + 60)
					elif ev.key in (pygame.K_UP, pygame.K_w):
						self.codex_scroll = max(0, self.codex_scroll - 60)
				elif ev.type == pygame.MOUSEWHEEL:
					self.codex_scroll = clamp(self.codex_scroll - ev.y * 50, 0,
					                          max(0, self.codex_max - H + 120))

			elif self.scene == 'play':
				if ev.type == pygame.KEYDOWN:
					if ev.key == pygame.K_TAB and self.sandbox is not None:
						self.scene = 'sandbox'; self.mouse_held = False
					elif ev.key == pygame.K_t:
						if self.world.player.banked > 0:
							self.open_levelup()
						else:
							self.scene = 'tree'; self.tree_scroll = 0
							self.tree_back = 'play'; self.mouse_held = False
					elif ev.key == pygame.K_ESCAPE or ev.key == pygame.K_p:
						self.scene = 'pause'
					elif ev.key == pygame.K_SPACE:
						self.world.player.try_dash(self.world)
				elif ev.type == pygame.MOUSEBUTTONDOWN:
					if ev.button == 1:
						self.mouse_held = True
						self.mouse_anchor = ev.pos
						self.mouse_last = ev.pos
					elif ev.button == 3:
						self.world.player.try_dash(self.world)
				elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
					self.mouse_held = False
					self.mouse_anchor = None

			elif self.scene == 'sandbox':
				self.mouse_held = False
				if not self.sandbox.event(ev, self.world):
					self.scene = 'play'

			elif self.scene == 'pause':
				self.mouse_held = False
				if ev.type == pygame.KEYDOWN:
					if ev.key in (pygame.K_ESCAPE, pygame.K_p): self.pause_do('resume')
					elif ev.key == pygame.K_t: self.pause_do('tree')
					elif ev.key == pygame.K_o: self.pause_do('options')
					elif ev.key == pygame.K_q: self.pause_do('quit')
				elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
					for r, key, on in self.pause_btns:
						if on and r.collidepoint(ev.pos):
							self.audio.play('pick', 0.8); self.pause_do(key); break

			elif self.scene == 'options':
				self.mouse_held = False
				n = len(OPTIONS)
				if ev.type == pygame.KEYDOWN:
					if ev.key in (pygame.K_ESCAPE, pygame.K_o, pygame.K_RETURN):
						self.scene = 'pause' if self.world else 'title'
					elif ev.key in (pygame.K_DOWN, pygame.K_s):
						self.opt_sel = (self.opt_sel + 1) % n; self.audio.play('move', 0.6)
					elif ev.key in (pygame.K_UP, pygame.K_w):
						self.opt_sel = (self.opt_sel - 1) % n; self.audio.play('move', 0.6)
					elif ev.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_SPACE):
						self.opt_cycle(OPTIONS[self.opt_sel]); self.audio.play('gem', 0.7)
					elif ev.key in (pygame.K_LEFT, pygame.K_a):
						self.opt_cycle(OPTIONS[self.opt_sel], -1); self.audio.play('gem', 0.7)
				elif ev.type == pygame.MOUSEMOTION:
					for i, r in enumerate(self.opt_rects):
						if r.collidepoint(ev.pos): self.opt_sel = i
				elif ev.type == pygame.MOUSEWHEEL and ev.y:
					self.opt_sel = (self.opt_sel - ev.y) % n
				elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button in (1, 3):
					for r, key, on in self.opt_btns:
						if r.collidepoint(ev.pos):
							self.scene = 'pause' if self.world else 'title'; break
					else:
						for i, r in enumerate(self.opt_rects):
							if r.collidepoint(ev.pos):
								self.opt_sel = i
								self.opt_cycle(OPTIONS[i], 1 if ev.button == 1 else -1)
								self.audio.play('gem', 0.7); break

			elif self.scene == 'tree':
				self.mouse_held = False
				if ev.type == pygame.KEYDOWN:
					if ev.key in (pygame.K_ESCAPE, pygame.K_t, pygame.K_TAB): self.scene = self.tree_back
					elif ev.key in (pygame.K_DOWN, pygame.K_s): self.tree_scroll += 70
					elif ev.key in (pygame.K_UP, pygame.K_w): self.tree_scroll -= 70
				elif ev.type == pygame.MOUSEWHEEL:
					self.tree_scroll -= ev.y * 60
				elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
					self.scene = self.tree_back
				self.tree_scroll = max(0, min(self.tree_scroll, self.tree_max))

			elif self.scene == 'levelup':
				self.levelup.event(ev, self.world)

			elif self.scene == 'end':
				if ev.type == pygame.KEYDOWN:
					if ev.key == pygame.K_RETURN: self.scene = 'select'
					elif ev.key == pygame.K_ESCAPE: self.scene = 'title'; self.world = None
		return True

	# ------------------------------------------------------------- update
	def update(self, dt):
		if self.scene == 'play':
			w = self.world
			keys = pygame.key.get_pressed()
			if self.mouse_held and not pygame.mouse.get_pressed()[0]:
				self.mouse_held = False      # button released while we were elsewhere
			self.mouse_fade = max(0.0, self.mouse_fade - dt)
			w.update(dt, keys, self.mouse_vec())
			# adaptive particle budget
			f = self.clock.get_fps()
			if f > 5:
				w.fx.quality = clamp(w.fx.quality + (0.35 if f > 56 else -0.6) * dt, 0.28, 1.0)
				# bloom is the first thing to go if the frame budget slips
				if f < 52:
					self.slow_frames += 1
					if self.slow_frames > 140 and self.opts['bloom']:
						self.opts['bloom'] = False
						w.banner('BLOOM DISABLED', 'framerate too low - F2 to re-enable', INK_DIM)
				else:
					self.slow_frames = max(0, self.slow_frames - 1)
			if w.player.dead:
				self.end_run(False)
			else:
				# a fresh level always re-arms the prompt, even if the last one was
				# dismissed: the point is new, so the offer to spend it is too
				if w.player.banked > self.lvl_last: self.lvl_hold = False
				self.lvl_last = w.player.banked
				ready = (w.player.banked > 0 and w.fx.hitstop <= 0 and not w.folding()
				         and not self.lvl_hold and not self.opts.get('defer'))
				if ready:
					# a biome fold owns the screen for 1.5s: let it finish before the
					# upgrade screen takes over, and give the level-up burst itself a
					# second to play out instead of being cut off by its own reward
					self.lvl_wait -= dt
					if self.lvl_wait <= 0.0:
						self.open_levelup()
				else:
					self.lvl_wait = LVL_DELAY
		elif self.scene == 'levelup':
			self.levelup.update(dt)
			if self.levelup.done:
				self.levelup = None
				self.scene = 'play'
				self.lvl_wait = LVL_DELAY
				self.lvl_hold = self.world.player.banked > 0
				self.lvl_last = self.world.player.banked
		elif self.scene == 'sandbox':
			self.sandbox.update(dt)
			self.world.fx.update(dt)
			self.audio.update(dt, 0.25)
		elif self.scene == 'end':
			self.end_t += dt
			self.audio.update(dt, 0.0)
		elif self.scene in ('title', 'codex', 'select', 'options'):
			self.audio.update(dt, 0.0)

	def pause_do(self, key):
		if key == 'resume': self.scene = 'play'
		elif key == 'tree': self.scene = 'tree'; self.tree_scroll = 0; self.tree_back = 'pause'
		elif key == 'options': self.scene = 'options'
		elif key == 'quit':
			self.scene = 'title'; self.world = None; self.sandbox = None
			self.levelup = None; self.lvl_hold = False

	def open_levelup(self):
		from game.offers import build_offers
		from game.ui import LevelUp
		w = self.world
		offers = build_offers(w)
		self.levelup = LevelUp(w, offers)
		self.levelup.snapshot(self.screen)
		self.scene = 'levelup'
		self.lvl_hold = False
		self.lvl_last = w.player.banked
		self.lvl_wait = LVL_DELAY
		self.audio.play('levelup', 0.8)

	def end_run(self, win):
		"""Only death gets here now: beating the last boss just raises the ramp."""
		w = self.world
		self.scene = 'end'
		self.end_t = 0.0
		self.audio.play('gameover', 1.0)
		w.fx.screen_flash(RED, 0.8)
		if w.sandbox: return          # a lab run is not a score
		self.save['runs'] = self.save.get('runs', 0) + 1
		entry = {'t': w.director.t, 'time': w.director.time_str(),
		         'level': w.player.level, 'kills': w.stats['kills'],
		         'converged': bool(w.win), 'unit': (w.boot or {}).get('name', ''),
		         'pace': w.pace['name']}
		board = self.save.setdefault('scores', {}).setdefault(w.pace['id'], [])
		mark = dict(entry); mark['now'] = True
		board.append(mark)
		board.sort(key=lambda e: -e.get('t', 0))
		del board[10:]
		for e in board:
			if e is not mark: e.pop('now', None)
		best = self.save.get('best') or {}
		if w.director.t > best.get('t', -1):
			self.save['best'] = dict(entry)
		save_data(self.save)

	# --------------------------------------------------------------- draw
	def draw(self):
		s = self.screen
		from game import ui
		vis = self.scene != 'play'
		if vis != pygame.mouse.get_visible(): pygame.mouse.set_visible(vis)
		if self.scene == 'title':
			ui.draw_title(s, self.t, self.sel, self.menu, self.save.get('best'))
		elif self.scene == 'codex':
			self.codex_max = ui.draw_codex(s, self.codex_page, self.codex_scroll,
			                               self.t, pygame.mouse.get_pos())
		elif self.scene == 'tree':
			if self.world: self.world.draw(s)
			self.tree_max = ui.draw_tree_screen(s, self.t, self.tree_scroll,
			                                    pygame.mouse.get_pos(), self.world, True)
		elif self.scene == 'select':
			from game.weapons import BOOTS
			self.boot_rects, self.pace_rects = ui.draw_select(s, self.t, self.boot_sel, BOOTS, self.pace_sel)
		elif self.scene in ('play', 'pause', 'end', 'sandbox') and self.world:
			self.world.draw(s)
			if self.opts['overlay']: s.blit(self.overlay, (0, 0))
			ui.draw_hud(self.world, s)
			if self.scene == 'play':
				ui.draw_cursor(s, self.world, self.mouse_last[0], self.mouse_last[1],
				               self.mouse_held, self.mouse_mode, self.mouse_anchor, self.mouse_fade)
			if self.scene == 'pause':
				self.pause_btns = ui.draw_pause(self.world, s, pygame.mouse.get_pos())
			elif self.scene == 'sandbox': self.sandbox.draw(s, self.world)
			elif self.scene == 'end':
				ui.draw_end(self.world, s, self.end_t, self.world.win, self.save.get('scores'))
		elif self.scene == 'levelup':
			self.levelup.draw(s, self.world)
		if self.scene == 'options':
			if self.world:
				self.world.draw(s)
				if self.opts['overlay']: s.blit(self.overlay, (0, 0))
			else:
				ui.draw_title(s, self.t, self.sel, self.menu, self.save.get('best'))
			self.opt_rects, self.opt_btns = ui.draw_options(s, self.opt_rows(), self.opt_sel,
			                                                pygame.mouse.get_pos())
		if self.scene in ('play',) and self.opts['overlay']:
			pass
		if self.show_fps:
			draw_text(s, '%d fps  e%d p%d f%d' % (self.clock.get_fps(),
			          len(self.world.enemies) if self.world else 0,
			          len(self.world.projs) if self.world else 0,
			          len(self.world.fx.parts) if self.world else 0),
			          W - 8, H - 20, 12, GREEN, True, 'tr')


if __name__ == '__main__':
	Game().loop()
