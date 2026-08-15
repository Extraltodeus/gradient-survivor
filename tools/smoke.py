"""Drives the real Game object through every scene to catch runtime errors."""

import os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
import main as M

pygame.init()
g = M.Game()
dt = 1.0 / 60.0


def press(key, mod=0):
	pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=''))


def click(pos, button=1):
	pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))


def step(n=1):
	for _ in range(n):
		g.handle_events(dt)
		g.update(dt)
		g.draw()


def menu_pick(name):
	"""Walk the title menu to `name` and press enter."""
	g.scene = 'title'
	while g.menu[g.sel] != name:
		press(pygame.K_DOWN); step(1)
	press(pygame.K_RETURN); step(2)


print('scene:', g.scene)
step(3)

# ---------------------------------------------------------------- codex
menu_pick('CODEX')
print('scene:', g.scene)
for i in range(5):
	press(pygame.K_RIGHT); step(2)
press(pygame.K_DOWN); press(pygame.K_DOWN); step(2)
press(pygame.K_ESCAPE); step(2)
print('scene:', g.scene)

# ------------------------------------------------------- boot select + pace
menu_pick('START RUN')
for k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_TAB):
	press(k); step(2)
press(pygame.K_4); step(2)                  # insanity: fastest biome rotation
press(pygame.K_RIGHT); press(pygame.K_DOWN); step(2)
press(pygame.K_RETURN)
step(2)
print('scene:', g.scene, 'world?', g.world is not None, 'pace:', g.world.pace['id'])

seen = set()
random.seed(3)
for i in range(60 * 60 * 7):
	if g.scene == 'levelup':
		seen.add('levelup')
		if i % 4 == 0:
			press(random.choice([pygame.K_RETURN, pygame.K_r, pygame.K_x, pygame.K_TAB]))
	elif g.scene == 'play':
		if i % 900 == 0:
			press(pygame.K_ESCAPE)          # pause
		if g.world and g.world.boss: seen.add('boss')
		if g.world and g.world.trans is not None: seen.add('matmul')
		if i % 240 == 0: press(pygame.K_SPACE)
		if i % 300 == 17:
			pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(900, 300), button=1))
		if i % 300 == 180:
			pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(700, 500), button=1))
		if i % 137 == 0:
			pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=(400 + i % 500, 200 + i % 300),
			                                     rel=(1, 1), buttons=(1, 0, 0)))
		if i % 600 == 59:
			pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(800, 400), button=3))
		if i % 700 == 33: press(pygame.K_F11)
		if i % 500 == 41: press(pygame.K_F5)
	elif g.scene == 'pause':
		seen.add('pause')
		press(pygame.K_ESCAPE)
	elif g.scene == 'end':
		seen.add('end')
		break
	g.handle_events(dt)
	# fake movement
	ks = pygame.key.get_pressed()
	if g.scene == 'play' and g.world:
		w = g.world
		wp = w.player
		wp.x += math.cos(i * 0.013) * 3.2
		wp.y += math.sin(i * 0.011) * 3.2
	g.update(dt)
	if i % 3 == 0: g.draw()

print('scenes visited:', sorted(seen))
if g.world:
	w = g.world
	print('t=%s lv=%d kills=%d enemies=%d projs=%d evos=%s'
	      % (w.director.time_str(), w.player.level, w.stats['kills'], len(w.enemies),
	         len(w.projs), w.evo_log))
	print('biome:', w.level['name'])

# ---------------------------------------------------------------- the bench
press(pygame.K_ESCAPE); step(2)
g.world = None
menu_pick('SANDBOX')
print('scene:', g.scene, 'sandbox?', g.sandbox is not None)
sb = g.sandbox
for tab in range(5):
	press(pygame.K_1 + tab); step(2)
	for r, _l, _fn, _c, _o in list(sb.buttons):
		click(r.center); step(1)
	for c in list(sb.cards)[:14]:
		click(c[0].center, 1 if random.random() < 0.7 else 3)
		step(1)
	press(pygame.K_RETURN); press(pygame.K_DOWN); press(pygame.K_e); step(2)
press(pygame.K_TAB); step(1)
print('scene after TAB:', g.scene)
for i in range(60 * 45):
	if g.scene == 'levelup': press(pygame.K_RETURN)
	elif g.scene == 'play' and i % 400 == 0: press(pygame.K_TAB)
	elif g.scene == 'sandbox' and i % 400 == 200: press(pygame.K_TAB)
	g.handle_events(dt); g.update(dt)
	if i % 3 == 0: g.draw()
print('bench: procs=%d lv=%d enemies=%d dps=%d biome=%s'
      % (len(g.world.arsenal.procs), g.world.player.level, len(g.world.enemies),
         int(g.world.dps), g.world.level['id']))
print('OK')
