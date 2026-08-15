"""Run pacing profiles.

Everything that decides how fast a run *feels* is a multiplier here, relative to
the original tuning (now called SLOW). Three dials matter and they must move
together: incoming power (xp, caches), incoming pressure (density, spawn rate,
events) and the run clock (biome length, difficulty ramp). Move only one and the
run breaks -- compress the biomes without compressing the difficulty curve and
the fast modes turn into a walk.
"""

from core.settings import BLUE, CYAN, ORANGE, RED

PACES = [
	dict(id='slow', name='GRADIENT', tag='the long descent',
	     desc='The original pace. Every upgrade is earned, every biome is a chapter.',
	     col=BLUE, bars=1,
	     xp=1.00, chest=1.00, biome=1.00, clock=1.00, density=1.00, rate=1.00,
	     events=1.00, hazard=1.00, ehp=1.00, edmg=1.00, cd=1.00, shake=1.00, gift=0),

	dict(id='normal', name='LEARNING RATE', tag='a healthy schedule',
	     desc='Palpable progress: levels land often, biomes rotate before they get old.',
	     col=CYAN, bars=2,
	     xp=1.60, chest=1.45, biome=1.35, clock=1.35, density=1.20, rate=1.32,
	     events=1.25, hazard=1.20, ehp=1.04, edmg=1.00, cd=0.95, shake=1.05, gift=0),

	dict(id='fast', name='OVERCLOCK', tag='fast action paced blast',
	     desc='Pew pew. Power arrives faster than you can read it, and so do they.',
	     col=ORANGE, bars=3,
	     xp=2.70, chest=2.20, biome=1.90, clock=1.85, density=1.55, rate=1.95,
	     events=1.70, hazard=1.55, ehp=1.16, edmg=1.05, cd=0.85, shake=1.15, gift=1),

	dict(id='insanity', name='DIVERGENCE', tag='KABOUUUM ZWIIIING PO PO PO',
	     desc='The loss went to NaN and took the screen with it. Nothing is readable. Good.',
	     col=RED, bars=4,
	     xp=5.20, chest=4.00, biome=3.00, clock=2.90, density=2.40, rate=3.30,
	     events=2.60, hazard=2.20, ehp=1.38, edmg=1.15, cd=0.68, shake=1.30, gift=3),
]

PACE_BY_ID = {p['id']: p for p in PACES}
DEFAULT_PACE = 'normal'


def get(pid):
	return PACE_BY_ID.get(pid) or PACE_BY_ID[DEFAULT_PACE]
