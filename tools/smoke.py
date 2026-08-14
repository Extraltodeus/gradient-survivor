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


def press(key):
	pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=''))


def step(n=1):
	for _ in range(n):
		g.handle_events(dt)
		g.update(dt)
		g.draw()


print('scene:', g.scene)
step(3)
# codex: every tab
press(pygame.K_DOWN); press(pygame.K_RETURN)
step(2)
print('scene:', g.scene)
for i in range(5):
	press(pygame.K_RIGHT); step(2)
press(pygame.K_DOWN); press(pygame.K_DOWN); step(2)
press(pygame.K_ESCAPE); step(2)
print('scene:', g.scene)

# start a run: menu -> boot select -> play
press(pygame.K_UP); press(pygame.K_RETURN)
step(2)
press(pygame.K_RIGHT); press(pygame.K_DOWN); step(2)
press(pygame.K_RETURN)
step(2)
print('scene:', g.scene, 'world?', g.world is not None)

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

print('scenes visited:', seen)
if g.world:
	w = g.world
	print('t=%s lv=%d kills=%d enemies=%d projs=%d evos=%s'
	      % (w.director.time_str(), w.player.level, w.stats['kills'], len(w.enemies),
	         len(w.projs), w.evo_log))
	print('biome:', w.level['name'])
print('OK')
