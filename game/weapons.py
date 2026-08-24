"""The arsenal: emitters, ops, synergies and evolutions.

A weapon is not a fixed thing. It is a PROCESS: one emitter (how matter leaves
the agent) plus a bag of ranked OPS (what that matter then does). Ops combine
with each other -- declared SYNERGIES are read by the projectile pipeline -- and
when a process accumulates the right shape it CRYSTALLISES into an evolution.
Processes can also be FUSED, merging their op-sets and freeing a slot.
"""

import math, random
import pygame
from core.settings import *
from core.utils import *
from game.combat import nearest_enemy, random_enemy
from game.projectiles import new_proj, MAX_GEN

# ============================================================== EMITTERS
E = {}

def _em(k, **kw):
	kw['id'] = k
	kw.setdefault('affinity', ())
	E[k] = kw

_em('bolt', name='INFERENCE BOLT', glyph='>', col=CYAN, tier=0,
    desc='A fast bolt seeks the nearest threat.',
    dmg=16.0, cd=0.62, count=1, speed=640.0, size=5.0, ttl=1.5, pierce=0,
    crowd=1.00, affinity=('pierce', 'crit', 'momentum', 'split'))

_em('swarm', name='TOKEN SWARM', glyph='~', col=(120, 255, 210), tier=0,
    desc='Three slow tokens drift toward whatever they can find.',
    dmg=7.0, cd=0.95, count=3, speed=300.0, size=4.0, ttl=2.4, pierce=0, homing=1,
    crowd=1.00, affinity=('homing', 'multishot', 'recursion', 'corrupt'))

_em('orbit', name='ATTENTION RING', glyph='O', col=(150, 190, 255), tier=0,
    desc='Weights orbit the agent, grinding anything they touch.',
    dmg=12.0, cd=2.00, count=2, speed=2.3, size=9.0, ttl=2.06, orbit_r=78.0,
    crowd=11.30, affinity=('giant', 'frost', 'blast', 'void'))

_em('aura', name='LOSS FIELD', glyph='@', col=(255, 120, 190), tier=0,
    desc='A field of descending loss burns everything nearby.',
    dmg=8.0, cd=3.00, count=1, speed=0.0, size=96.0, ttl=3.06, tick=0.52,
    crowd=52.80, affinity=('burn', 'drain', 'void', 'giant'))

_em('nova', name='SOFTMAX NOVA', glyph='(', col=(255, 200, 90), tier=1,
    desc='A normalising shockwave erupts outward.',
    dmg=17.0, cd=2.60, count=1, speed=0.0, size=190.0, ttl=0.55,
    crowd=25.00, affinity=('blast', 'void', 'frost', 'giant'))

_em('beam', name='BACKPROP BEAM', glyph='|', col=(255, 90, 120), tier=1,
    desc='A rotating gradient beam sweeps the field.',
    dmg=5.4, cd=2.50, count=1, speed=1.15, size=7.0, ttl=2.56, length=250.0,
    crowd=46.00, affinity=('chain', 'burn', 'overclock', 'giant'))

_em('mine', name='DROPOUT MINE', glyph='x', col=(255, 150, 60), tier=1,
    desc='Drops unstable nodes that detonate on contact.',
    dmg=26.0, cd=1.70, count=1, speed=150.0, size=11.0, ttl=7.0, blast_r=76.0,
    crowd=4.60, affinity=('blast', 'split', 'void', 'burn'))

_em('arc', name='CHAIN LOGIT', glyph='z', col=(190, 220, 255), tier=1,
    desc='A near-continuous stutter of lightning that hops between activations.',
    dmg=4.4, cd=0.40, count=1, speed=0.0, size=0.0, ttl=0.1, jumps=2,
    crowd=2.58, affinity=('chain', 'shock', 'frost', 'crit'))

_em('flame', name='FLASH ATTENTION', glyph='f', col=(255, 118, 38), tier=1,
    desc='A sustained cone of fire poured out in front of you. Short range, no gaps.',
    dmg=2.9, cd=0.13, count=4, speed=440.0, size=7.0, ttl=0.40, pierce=3, cone=0.52,
    crowd=2.00, affinity=('burn', 'giant', 'multishot', 'void'))

_em('turret', name='SENTINEL NODE', glyph='T', col=(140, 255, 140), tier=2,
    desc='Deploys an autonomous node that fires on its own.',
    dmg=8.0, cd=4.20, count=1, speed=0.0, size=5.0, ttl=8.0, rate=0.44,
    crowd=15.40, affinity=('multishot', 'swift', 'crit', 'homing'))

_em('blade', name='RECURSION BLADE', glyph='%', col=(255, 240, 120), tier=2,
    desc='A blade thrown outward that returns through everything.',
    dmg=19.0, cd=1.60, count=1, speed=520.0, size=13.0, ttl=3.2, pierce=2,
    crowd=6.13, affinity=('pierce', 'bounce', 'giant', 'crit'))

_em('spiral', name='DIFFUSION SPIRAL', glyph='6', col=(200, 150, 255), tier=2,
    desc='Noise unrolls outward in a widening spiral.',
    dmg=8.5, cd=1.30, count=4, speed=270.0, size=5.0, ttl=2.2,
    crowd=1.00, affinity=('orbitize', 'split', 'multishot', 'corrupt'))

_em('rain', name='STOCHASTIC RAIN', glyph='v', col=(120, 200, 255), tier=2,
    desc='Samples the field and strikes at random hot spots.',
    dmg=22.0, cd=1.80, count=2, speed=0.0, size=46.0, ttl=0.45,
    crowd=1.73, affinity=('blast', 'burn', 'multishot', 'frost'))

EMIT_ORDER = list(E.keys())
STARTERS = ('bolt', 'swarm', 'orbit', 'aura')

# Boot profiles: each seeds one process with one op already attached, so the
# combinatorial system is visible from the first second of the run. `shape`,
# `col` and `mobility` are the unit itself -- two boots must never be the same
# triangle in a different tint.
BOOTS = [
	dict(id='vector',  name='VECTOR',   emit='bolt',  op='pierce', passive='power',
	     shape='dart', col=CYAN, mobility='dash',
	     desc='One clean line of inference. Starts already able to punch through.'),
	dict(id='census',  name='CENSUS',   emit='swarm', op='homing', passive='amount',
	     shape='trilobe', col=(120, 255, 210), mobility='dash',
	     desc='A cloud of small opinions that all agree to find you a target.'),
	dict(id='halo',    name='HALO',     emit='orbit', op='frost',  passive='area',
	     shape='annulus', col=(150, 190, 255), mobility='dash',
	     desc='Cold weights in orbit. Anything that touches you slows down.'),
	dict(id='descent', name='DESCENT',  emit='aura',  op='burn',   passive='hp',
	     shape='hex', col=(255, 120, 190), mobility='dash',
	     desc='A burning loss field. You are the hazard now.'),
	dict(id='dropout', name='DROPOUT',  emit='mine',  op='blast',  passive='area',
	     shape='cross', col=(255, 150, 60), mobility='dash',
	     desc='Leave unstable nodes behind you and never look back.'),
	dict(id='recurse', name='RECURSE',  emit='blade', op='bounce', passive='speed',
	     shape='blade', col=(255, 240, 120), mobility='dash',
	     desc='A blade with a bad exit condition. It comes back. Repeatedly.'),
	dict(id='quantum', name='QUANTUM',  emit='flame', op='burn',   passive='haste',
	     shape='prism', col=VIOLET, mobility='blink',
	     desc='Blinks instead of dashing. Carries a flamethrower for where it lands.'),
]
BOOT_BY_ID = {b['id']: b for b in BOOTS}


# ================================================================== OPS
O = {}

def _op(k, name, glyph, desc, col=None, mods=None, rare=1, tag='behaviour'):
	O[k] = dict(id=k, name=name, glyph=glyph, desc=desc, col=col, mods=mods or {}, rare=rare, tag=tag)

# -- behaviour ---------------------------------------------------------
_op('pierce', 'PIERCE', '/', 'Shots punch through +1 more target per rank.',
    mods={'dmg': 0.04})
_op('blast', 'BLAST', '*', 'Impacts detonate for area damage.',
    col=ORANGE, mods={'dmg': 0.02})
_op('split', 'SPLIT', 'Y', 'Impacts fork into +1 smaller shard per rank.',
    mods={'dmg': -0.02})
_op('chain', 'CHAIN', 'z', 'Hits arc to +1 nearby target per rank.',
    col=(170, 220, 255))
_op('homing', 'HOMING', '@', 'Shots steer toward targets.',
    mods={'speed': -0.03})
_op('bounce', 'BOUNCE', 'b', 'Shots ricochet +1 time per rank.')
_op('orbitize', 'SPIN', '6', 'Shots curve, sweeping a wide arc.', col=VIOLET)
_op('multishot', 'MULTISHOT', '3', '+1 projectile per rank, slightly weaker each.',
    mods={'count': 1.0, 'dmg': -0.06}, rare=2)
_op('recursion', 'RECURSION', 'r', 'Kills have a chance to fire a smaller copy.',
    col=(180, 255, 200), rare=2)
_op('echo', 'ECHO', 'e', 'Every volley repeats at 55% power.', rare=2,
    mods={'dmg': -0.03})

# -- quality -----------------------------------------------------------
_op('giant', 'GIANT', 'G', 'Much bigger shots: they cover ground the small ones miss.',
    col=(255, 220, 160), mods={'size': 0.36, 'dmg': 0.10, 'speed': -0.05}, tag='stat')
_op('swift', 'SWIFT', 's', 'Faster shots, faster cycling.', col=(180, 255, 255),
    mods={'speed': 0.16, 'cd': -0.075}, tag='stat')
_op('crit', 'CRIT', '!', '+8% critical chance, +25% critical damage.', col=GOLD,
    mods={'crit_c': 0.08, 'crit_m': 0.25}, tag='stat')
_op('momentum', 'MOMENTUM', '>', 'Shots accelerate and grow stronger as they travel.',
    mods={'dmg': 0.05}, tag='stat')
_op('overclock', 'OVERCLOCK', '^', 'Firing builds heat: up to +% damage while sustained.',
    col=RED, rare=2, tag='stat')
_op('feedback', 'FEEDBACK', 'f', 'Every kill shortens this process cooldown.',
    col=GREEN, rare=2, tag='stat')

# -- elemental ---------------------------------------------------------
_op('burn', 'IGNITE', 'i', 'Targets burn over time.', col=(255, 130, 50), tag='element')
_op('frost', 'QUANTIZE', 'q', 'Targets are chilled: slower and brittle.', col=(140, 220, 255), tag='element')
_op('shock', 'SHOCK', 'k', 'Chance to stun targets outright.', col=(190, 230, 255), tag='element')
_op('corrupt', 'CORRUPT', 'c', 'Corrupted targets burst into hostile shards on death.',
    col=VIOLET, rare=2, tag='element')
_op('void', 'VOID', 'v', 'Impacts drag everything inward.', col=(160, 120, 255), tag='element')
_op('drain', 'DRAIN', 'd', 'Damage sometimes restores your integrity.', col=HP_COL, rare=2, tag='element')

OP_ORDER = list(O.keys())
MAX_OPS_PER_PROC = 5

PREFIX = {'burn': 'BLAZING', 'frost': 'GLACIAL', 'shock': 'ARCING', 'corrupt': 'VIRAL',
          'void': 'HOLLOW', 'drain': 'LEECHING', 'crit': 'PRECISE', 'giant': 'MASSIVE',
          'swift': 'RAPID', 'overclock': 'SEETHING', 'momentum': 'DRIVEN', 'recursion': 'NESTED'}
SUFFIX = {'blast': 'of Detonation', 'split': 'of Fractals', 'chain': 'of Conduction',
          'pierce': 'of Penetration', 'bounce': 'of Ricochet', 'homing': 'of Pursuit',
          'orbitize': 'of Spirals', 'multishot': 'of Multitudes', 'echo': 'of Echoes',
          'feedback': 'of Feedback', 'void': 'of the Well'}


# ============================================================ SYNERGIES
SYN = [
	('CASCADE',     {'pierce': 2, 'blast': 2},      'Detonates on EVERY perforation.'),
	('FRACTAL',     {'split': 3},                   'Shards split again. Recursion all the way down.'),
	('SHATTER',     {'frost': 2, 'blast': 2},       'Blasts deal massive bonus damage to chilled targets.'),
	('WILDFIRE',    {'burn': 2, 'chain': 2},        'Burns 50% harder and spreads down every arc.'),
	('STALKER',     {'homing': 2, 'bounce': 2},     'Ricochets re-acquire a new target instantly.'),
	('IMPLOSION',   {'void': 2, 'blast': 2},        'Blasts inhale first, then detonate 45% harder.'),
	('CONTAGION',   {'corrupt': 2, 'split': 2},     'Corruption bursts throw twice the shards.'),
	('AVALANCHE',   {'crit': 3, 'recursion': 2},    'Every critical hit guarantees a recursion.'),
	('JUGGERNAUT',  {'giant': 2, 'pierce': 2},      '+2 pierce and shots never slow down.'),
	('SUPERCONDUCT',{'shock': 2, 'frost': 2},       'Shocking a chilled target discharges an area burst.'),
	('PENETRATOR',  {'momentum': 2, 'pierce': 2},   'Damage scales up to +60% with distance travelled.'),
	('RUNAWAY',     {'swift': 2, 'overclock': 2},   'Heat builds twice as fast and decays slower.'),
	('LEECH',       {'drain': 2, 'burn': 2},        'Your burns siphon integrity back to you.'),
	('VORTEX',      {'multishot': 2, 'orbitize': 2},'Volleys coil into one coherent vortex.'),
	('OVERDRIVE',   {'overclock': 2, 'crit': 2},    'Heat also raises critical chance.'),
	('HYDRA',       {'split': 2, 'recursion': 2},   'Shards keep 78% power and can split again.'),
]
SYN_BY_ID = {s[0]: s for s in SYN}


# ============================================================ EVOLUTIONS
def _ev(eid, emit, req, name, desc, mods, grant=None, col=GOLD):
	return dict(id=eid, emit=emit, req=req, name=name, desc=desc, mods=mods, grant=grant or {}, col=col)

EVOS = [
	_ev('railgun', 'bolt', {'pierce': 3, 'blast': 3}, 'RAILGUN OF TRUTH',
	    'An unstoppable lance. Every perforation detonates twice as hard.',
	    {'dmg': 0.55, 'speed': 0.45, 'size': 0.3}, {'pierce': 2}),
	_ev('oneshot', 'bolt', {'crit': 3, 'momentum': 3}, 'ONE-SHOT LEARNER',
	    'Converges on a single, devastating conclusion.',
	    {'dmg': 0.9, 'crit_c': 0.18, 'crit_m': 1.1, 'cd': 0.25}),
	_ev('viral', 'swarm', {'recursion': 3, 'corrupt': 2}, 'VIRAL LOAD',
	    'Self-replicating payloads. The swarm never really ends.',
	    {'dmg': 0.45, 'count': 3}, {'homing': 1}),
	_ev('consensus', 'swarm', {'homing': 3, 'multishot': 3}, 'SWARM CONSENSUS',
	    'A cloud that votes on your enemies and always agrees.',
	    {'dmg': 0.35, 'count': 4, 'cd': 0.2}),
	_ev('glacier', 'orbit', {'frost': 3, 'giant': 2}, 'GLACIER RING',
	    'Vast frozen weights grind everything to a halt.',
	    {'dmg': 0.6, 'size': 0.5, 'count': 1}),
	_ev('singular', 'orbit', {'blast': 3, 'void': 2}, 'SINGULARITY RING',
	    'Each orbiting node is a collapsing star.',
	    {'dmg': 0.5, 'count': 2}, {'blast': 1}),
	_ev('horizon', 'aura', {'burn': 3, 'void': 3}, 'EVENT HORIZON',
	    'Nothing escapes the field. Not even light.',
	    {'dmg': 0.7, 'size': 0.45}),
	_ev('entropy', 'aura', {'drain': 3, 'frost': 2}, 'ENTROPY WELL',
	    'Heat flows out of them and into you.',
	    {'dmg': 0.5, 'size': 0.3, 'cd': 0.2}, {'drain': 1}),
	_ev('oracle', 'beam', {'chain': 3, 'overclock': 3}, 'LIGHTNING ORACLE',
	    'A sweeping arc-net that only ever accelerates.',
	    {'dmg': 0.6, 'speed': 0.5, 'size': 0.4}),
	_ev('solar', 'beam', {'giant': 3, 'burn': 3}, 'SOLAR PROMPT',
	    'A column of pure inference. Everything it touches is already ash.',
	    {'dmg': 0.75, 'size': 0.8}),
	_ev('cluster', 'mine', {'blast': 3, 'split': 3}, 'CLUSTER DROPOUT',
	    'Every node is a bomb full of smaller bombs.',
	    {'dmg': 0.5, 'count': 2}, {'blast': 1}),
	_ev('thunder', 'arc', {'shock': 3, 'chain': 4}, 'THUNDER TRANSFORMER',
	    'One activation, propagated across the entire layer.',
	    {'dmg': 0.55}, {'chain': 3}),
	_ev('array', 'turret', {'multishot': 3, 'swift': 3}, 'SENTINEL ARRAY',
	    'A standing garrison of autonomous defenders.',
	    {'dmg': 0.5, 'count': 2, 'cd': 0.3}),
	_ev('loop', 'blade', {'bounce': 3, 'pierce': 3}, 'PERPETUAL LOOP',
	    'A blade with no base case. It simply never returns.',
	    {'dmg': 0.6, 'size': 0.35}, {'bounce': 2}),
	_ev('galaxy', 'spiral', {'orbitize': 3, 'split': 3}, 'GALAXY BRAIN',
	    'A self-similar arm of noise, spiralling outward forever.',
	    {'dmg': 0.5, 'count': 3}),
	_ev('collapse', 'nova', {'void': 3, 'blast': 3}, 'COLLAPSE PULSE',
	    'The field folds inward, then everything is deleted.',
	    {'dmg': 0.7, 'size': 0.45, 'cd': 0.2}),
	_ev('carpet', 'rain', {'blast': 3, 'burn': 3}, 'SATURATION BOMBING',
	    'The sampler stops being random and simply covers everything.',
	    {'dmg': 0.6, 'count': 3, 'cd': 0.25}),
	_ev('runaway', 'flame', {'burn': 3, 'giant': 3}, 'THERMAL RUNAWAY',
	    'The cone stops being a cone. Everything in front of you is already ash.',
	    {'dmg': 0.55, 'size': 0.55, 'count': 4}, {'burn': 1}),
	_ev('sink', 'flame', {'void': 3, 'pierce': 3}, 'ATTENTION SINK',
	    'The jet inhales the field into itself, then burns what it swallowed.',
	    {'dmg': 0.75, 'count': 2, 'speed': 0.3}, {'void': 1}),
]
EVO_BY_EMIT = {}
for _e in EVOS: EVO_BY_EMIT.setdefault(_e['emit'], []).append(_e)


# ============================================================== PASSIVES
PASSIVES = [
	dict(id='power',   name='TENSOR CORES',   glyph='+', desc='+12% damage on everything.',      rare=1),
	dict(id='haste',   name='LOW LATENCY',    glyph='<', desc='-9% cooldown on all processes.',  rare=1),
	dict(id='area',    name='WIDE CONTEXT',   glyph='o', desc='+14% area of effect.',            rare=1),
	dict(id='vel',     name='HIGH THROUGHPUT',glyph='»', desc='+16% projectile speed.',          rare=1),
	dict(id='hp',      name='REDUNDANCY',     glyph='#', desc='+22 max integrity, and heal it.', rare=1),
	dict(id='regen',   name='SELF REPAIR',    glyph='%', desc='+0.6 integrity per second.',      rare=1),
	dict(id='speed',   name='OPTIMIZER',      glyph='»', desc='+9% movement speed.',             rare=1),
	dict(id='magnet',  name='WIDE ATTENTION', glyph='m', desc='+35% token pickup radius.',       rare=1),
	dict(id='xp',      name='GRADIENT BOOST', glyph='^', desc='+16% experience gained.',         rare=1),
	dict(id='armor',   name='HARDENING',      glyph='=', desc='+1 armour: flat damage reduction.',rare=2),
	dict(id='crit',    name='SHARP LOGITS',   glyph='!', desc='+6% critical chance globally.',   rare=2),
	dict(id='luck',    name='TEMPERATURE',    glyph='?', desc='+12% luck: better offers, more drops.', rare=2),
	dict(id='dodge',   name='STOCHASTIC',     glyph='~', desc='+6% chance to phase through a hit.', rare=2),
	dict(id='cool',    name='HEAT SINK',      glyph='v', desc='Overclock heat decays 40% slower.',rare=2),
	dict(id='amount',  name='BATCH SIZE',     glyph='3', desc='+1 projectile to every process.', rare=3),
	dict(id='slot',    name='PARALLELISM',    glyph='[', desc='+1 process slot.',                rare=3),
	dict(id='reroll',  name='RESAMPLE',       glyph='r', desc='+2 rerolls, +1 banish.',          rare=2),
]
PASSIVE_BY_ID = {p['id']: p for p in PASSIVES}


# =============================================================== PROCESS
class Process:
	__slots__ = ('emit', 'rank', 'ops', 'evo', 'syn', 't', 'phase', 'heat', 'heat_max',
	             'heat_dmg', 'heat_decay', 'c', 'dirty', 'name', 'col', 'pending', 'fused',
	             'uid', 'flash', 'ents')

	_uid = 0

	def __init__(self, emit, rank=1, ops=None):
		Process._uid += 1
		self.uid = Process._uid
		self.emit = emit
		self.rank = rank
		self.ops = dict(ops or {})
		self.evo = None
		self.syn = ()
		self.t = 0.15 + random.random() * 0.25
		self.phase = random.random() * TAU
		self.heat = 0.0
		self.heat_max = 0.0
		self.heat_dmg = 0.0
		self.heat_decay = 1.5
		self.pending = []
		self.fused = 0
		self.flash = 0.0
		self.ents = []
		self.c = None
		self.dirty = True
		self.refresh()

	# ---------------------------------------------------------- identity
	def refresh(self):
		self.dirty = True
		syn = []
		for sid, req, _d in SYN:
			ok = True
			for k, v in req.items():
				if self.ops.get(k, 0) < v: ok = False; break
			if ok: syn.append(sid)
		self.syn = tuple(syn)
		em = E[self.emit]
		if self.evo:
			self.name = self.evo['name']
			self.col = GOLD
		else:
			base = em['name']
			pre = suf = ''
			best = 0
			for k, v in self.ops.items():
				if k in PREFIX and v > best: best = v; pre = PREFIX[k]
			best = 0
			for k, v in self.ops.items():
				if k in SUFFIX and v > best: best = v; suf = SUFFIX[k]
			nm = base
			if pre and (len(self.ops) > 1 or best >= 2): nm = pre + ' ' + nm
			if suf and len(self.ops) >= 2: nm = nm + ' ' + suf
			self.name = nm
			self.col = tint(self.ops, em['col'])
		self.heat_max = 0.0
		oc = self.ops.get('overclock', 0)
		if oc:
			self.heat_max = 3.0 + 2.0 * oc
			self.heat_dmg = 0.055 + 0.012 * oc
			self.heat_decay = 1.5 if 'RUNAWAY' not in self.syn else 0.85

	def op_cap(self):
		"""How many ops this process may still be OFFERED. A merge is allowed to
		exceed it -- the union is kept whole -- and then simply stops being offered
		anything new until the ranks catch up."""
		return max(MAX_OPS_PER_PROC + self.fused, len(self.ops))

	def add_op(self, op, n=1):
		self.ops[op] = min(MAX_TRAIT_RK, self.ops.get(op, 0) + n)
		self.refresh()
		return self.check_evo()

	def check_evo(self):
		if self.evo: return None
		for ev in EVO_BY_EMIT.get(self.emit, ()):
			ok = True
			for k, v in ev['req'].items():
				if self.ops.get(k, 0) < v: ok = False; break
			if ok:
				self.evo = ev
				for k, v in ev['grant'].items():
					self.ops[k] = min(MAX_TRAIT_RK + 2, self.ops.get(k, 0) + v)
				self.rank += 2
				self.refresh()
				return ev
		return None

	def evo_progress(self):
		"""Closest unfinished evolution: (evo, missing dict, fraction)."""
		if self.evo: return None
		best = None; bf = -1.0
		for ev in EVO_BY_EMIT.get(self.emit, ()):
			have = 0; need = 0; missing = {}
			for k, v in ev['req'].items():
				h = min(v, self.ops.get(k, 0))
				have += h; need += v
				if h < v: missing[k] = v - h
			f = have / need
			if f > bf: bf = f; best = (ev, missing, f)
		return best

	# ------------------------------------------------------------ stats
	def stats(self, pl):
		if not self.dirty and self.c is not None: return self.c
		em = E[self.emit]
		r = self.rank
		add_dmg = 0.17 * (r - 1)
		add_cd = 0.0; add_size = 0.0; add_speed = 0.0
		add_count = 0.0; crit_c = 0.0; crit_m = 0.0
		for op, rk in self.ops.items():
			m = O[op]['mods']
			if not m: continue
			add_dmg += m.get('dmg', 0.0) * rk
			add_cd += m.get('cd', 0.0) * rk
			add_size += m.get('size', 0.0) * rk
			add_speed += m.get('speed', 0.0) * rk
			add_count += m.get('count', 0.0) * rk
			crit_c += m.get('crit_c', 0.0) * rk
			crit_m += m.get('crit_m', 0.0) * rk
		if self.evo:
			mo = self.evo['mods']
			add_dmg += mo.get('dmg', 0.0)
			add_cd -= mo.get('cd', 0.0)
			add_size += mo.get('size', 0.0)
			add_speed += mo.get('speed', 0.0)
			add_count += mo.get('count', 0.0)
			crit_c += mo.get('crit_c', 0.0)
			crit_m += mo.get('crit_m', 0.0)

		area = (1.0 + add_size) * pl.area_mult
		c = {
			'dmg':   em['dmg'] * (1.0 + add_dmg) * pl.dmg_mult,
			'cd':    max(0.07, em['cd'] * (1.0 + add_cd) * pl.cd_mult),
			'count': max(1, int(round(em['count'] + add_count + pl.amount))),
			'speed': em['speed'] * (1.0 + add_speed) * (pl.pspeed_mult if em['speed'] > 30 else 1.0),
			'size':  em['size'] * (1.0 + add_size * (0.55 if em['size'] > 40 else 1.0)),
			'ttl':   em['ttl'] * pl.dur_mult,
			'area':  area,
			'crit_c': min(0.85, crit_c + pl.crit_c),
			'crit_m': 2.0 + crit_m + pl.crit_m,
			'col':   self.col,
		}
		self.c = c; self.dirty = False
		return c

	def power(self, pl):
		"""Estimated effective damage per second against a crowd.

		This has to model the projectile pipeline, not just the stat block: most
		of the interesting ops -- pierce, chain, split, ignite, corrupt -- carry no
		stat modifier at all, so an estimate built from the stat block alone shows
		the same number before and after taking one, which is exactly backwards on
		a card whose whole job is to say what changes.

		Every coefficient here was fitted against measured damage-per-second from
		tools/dpsfit.py: 24 enemies held alive in a 230px ring for 18 seconds, one
		emitter at a time, each op swept at rank 1/3/5. It is an estimate, not a
		promise -- but it is an estimate that was checked.
		"""
		c = self.stats(pl)
		o = self.ops
		syn = self.syn
		cd = max(0.08, c['cd'])

		# ---- what one projectile is worth, in multiples of its own damage
		hit = 1.0
		p = o.get('pierce', 0) + (2 if 'JUGGERNAUT' in syn else 0)
		if p: hit += 3.2 * p / (p + 2.0)                 # saturates: bodies run out
		hit += 1.02 * o.get('bounce', 0)
		ch = o.get('chain', 0)
		if ch: hit += (0.45 + 0.08 * ch) * ch * 0.9      # the arc, with its falloff
		bl = o.get('blast', 0)
		if bl: hit += (0.28 * bl + 0.24 * bl * bl) * (1.45 if 'IMPLOSION' in syn else 1.0)
		sp = o.get('split', 0)
		if sp:
			k = (1 + sp) * ((0.78 if 'HYDRA' in syn else 0.46) + 0.05 * sp)
			# FRACTAL lets shards split again: the payload stops being linear
			hit += k * (1.0 + k * (1.0 + 0.55 * k)) if ('FRACTAL' in syn or 'HYDRA' in syn) else k
		hit *= 1.0 + c['crit_c'] * (c['crit_m'] - 1.0)

		# How many bodies one cast of THIS emitter touches, measured. A field that
		# ticks for three seconds and a single bolt cannot share a formula.
		# The two do not multiply: an emitter whose crowd factor is already 50 is
		# hitting everything in range, so PIERCE has almost nothing left to add.
		# Only the raw single-target emitters get the op bonus at full value.
		crowd = E[self.emit].get('crowd', 1.0)
		extra = (hit - 1.0) / (1.0 + 1.0 * (crowd - 1.0))
		reach = crowd * (1.0 + extra)
		dps = c['dmg'] * c['count'] * reach / cd

		# ---- damage that is its own source, not a multiple of the weapon's
		bn = o.get('burn', 0)
		if bn:
			lit = min(6.0, 0.55 + 0.28 * (2.2 + 0.5 * bn) * (1.0 + 0.6 * (reach - 1.0)))
			dps += (2.6 + 2.2 * bn) * pl.dmg_mult * (1.5 if 'WILDFIRE' in syn else 1.0) * lit
		cr = o.get('corrupt', 0)
		if cr:
			dps += (4.0 + 3.0 * cr) * (2 + cr) * pl.dmg_mult * 0.20 \
			       * (2.0 if 'CONTAGION' in syn else 1.0) * min(3.0, reach ** 0.5)

		# ---- multipliers on the whole output
		eo = o.get('echo', 0)
		if eo: dps *= 1.42 + 0.005 * eo
		rc = o.get('recursion', 0)
		if rc: dps *= 1.0 + (0.16 + 0.11 * rc) * 0.35    # needs kills, so: modest
		fb = o.get('feedback', 0)
		if fb: dps *= 1.0 + min(0.20, (0.05 + 0.035 * fb) / cd * 0.2)
		oc = o.get('overclock', 0)
		if oc: dps *= 1.0 + 0.32 * (3.0 + 2.0 * oc) * (0.055 + 0.012 * oc)
		fr = o.get('frost', 0)
		if fr:
			dps *= 1.0 + 0.03 * fr
			if 'SHATTER' in syn: dps *= 1.0 + 0.35 * (0.55 + 0.25 * fr)
		# these four do not deal damage; they stop shots being wasted
		if o.get('void'): dps *= 1.0 + 0.010 * o['void']
		if o.get('shock'): dps *= 1.0 + 0.012 * o['shock']
		if o.get('homing'): dps *= 1.0 + 0.020 * o['homing']
		if o.get('orbitize'): dps *= 1.0 + 0.020 * o['orbitize']
		if self.evo: dps *= 1.25
		return dps

	def sustain(self, pl):
		"""Integrity per second this process gives back through DRAIN."""
		dr = self.ops.get('drain', 0)
		if not dr: return 0.0
		c = self.stats(pl)
		hits = c['count'] / max(0.08, c['cd']) * E[self.emit].get('crowd', 1.0)
		return (0.10 + 0.045 * dr) * (0.5 + 0.55 * dr) * min(hits, 20.0)


def fuse_plan(a, b):
	"""What merging b into a produces: (ops, rank, dropped).

	A merge is never a downgrade: nothing is dropped. Every op survives at least at
	the higher of the two ranks and shared ops gain one. The op cap governs what a
	process can still be OFFERED, not what a merge may hand it -- paying a whole
	process for the union is the price, and it has to be worth paying.
	"""
	ops = dict(a.ops)
	for k, v in b.ops.items():
		ops[k] = min(MAX_TRAIT_RK, max(ops.get(k, 0), v) + (1 if k in a.ops else 0))
	return ops, a.rank + max(1, min(6, b.rank)), []


def ghost_process(emit, ops, rank):
	"""A throwaway Process used only to price a hypothetical build for the UI."""
	g = Process(emit, rank, ops)
	g.check_evo()
	return g


def tint(ops, base):
	best = None; br = 0
	for k, v in ops.items():
		c = O[k]['col']
		if c is not None and v > br: br = v; best = c
	if best is None: return base
	return mix(base, best, min(0.62, 0.24 + 0.11 * br))


# ================================================================= FIRING
def aim(w, pr, spread_seed=0):
	pl = w.player
	t = nearest_enemy(w, pl.x, pl.y, 900.0)
	if t is not None: return math.atan2(t.y - pl.y, t.x - pl.x), t
	if pl.fx_ or pl.fy_: return math.atan2(pl.fy_, pl.fx_), None
	return pr.phase, None


def fire(w, pr, mult=1.0, echo=False):
	c = pr.stats(w.player)
	f = globals().get('_fire_' + pr.emit)
	if f: f(w, pr, c, mult)
	pr.flash = 1.0
	if pr.heat_max > 0.0 and not echo:
		# heat was +1 per shot against a decay of 1.5/s, so OVERCLOCK simply did not
		# exist on anything slower than about one shot a second -- which is every
		# emitter LIGHTNING ORACLE and its neighbours are built on. Gain now pays
		# for the wait instead of punishing it.
		gain = 1.0 + 1.6 * c['cd']
		pr.heat = min(pr.heat_max, pr.heat + gain * (2.0 if 'RUNAWAY' in pr.syn else 1.0))
	if not echo:
		eo = pr.ops.get('echo', 0)
		if eo:
			pr.pending.append((w.t + 0.20 + 0.02 * (5 - eo), 0.42 + 0.055 * eo))


def _crit(c, pr):
	cc = c['crit_c']
	if 'OVERDRIVE' in pr.syn and pr.heat > 0: cc += 0.035 * pr.heat
	return min(0.9, cc)


def _shoot(w, pr, c, x, y, a, speed, dmg, size, ttl, kind='shot', **kw):
	return new_proj(w, kind, x, y, math.cos(a) * speed, math.sin(a) * speed, dmg,
	                c['col'], pr, r=size, ttl=ttl, crit_c=_crit(c, pr), crit_m=c['crit_m'],
	                dr=kw.pop('dr', size), **kw)


def _fan(w, pr, c, base_a, n, spread, mult, speed=None, ttl=None, size=None, dmg=None):
	pl = w.player
	sp = speed if speed is not None else c['speed']
	tt = ttl if ttl is not None else c['ttl']
	sz = size if size is not None else c['size']
	dm = (dmg if dmg is not None else c['dmg']) * mult
	vortex = 'VORTEX' in pr.syn
	for i in range(n):
		off = 0.0 if n == 1 else (i - (n - 1) * 0.5) * spread
		if vortex: off *= 0.35
		a = base_a + off
		p = _shoot(w, pr, c, pl.x + math.cos(a) * 14, pl.y + math.sin(a) * 14, a,
		           sp * (1.0 + (0.06 * i if vortex else 0.0)), dm, sz, tt)
		if vortex: p.seed = 0.0
	return n


def _fire_bolt(w, pr, c, mult):
	a, _t = aim(w, pr)
	n = c['count']
	_fan(w, pr, c, a, n, 0.16, mult)
	w.audio.play('fire_bolt', 0.5, 0.05)


def _fire_swarm(w, pr, c, mult):
	a, _t = aim(w, pr)
	n = c['count']
	pl = w.player
	for i in range(n):
		aa = a + w.rng.uniform(-0.85, 0.85)
		sp = c['speed'] * w.rng.uniform(0.8, 1.25)
		_shoot(w, pr, c, pl.x, pl.y, aa, sp, c['dmg'] * mult, c['size'], c['ttl'])
	w.audio.play('fire_swarm', 0.4, 0.06)


def orbit_speed(pr):
	return E['orbit']['speed'] * (1.0 + 0.06 * (pr.rank - 1)) * (1.0 + 0.1 * pr.ops.get('swift', 0))


def _fire_orbit(w, pr, c, mult):
	em = E['orbit']
	n = c['count']
	r = (em['orbit_r'] + 5.0 * (c['size'] - em['size'])) * (0.85 + 0.25 * w.player.area_mult)
	spd = orbit_speed(pr)
	for i in range(n):
		p = new_proj(w, 'orb', w.player.x, w.player.y, 0, 0, c['dmg'] * mult, c['col'], pr,
		             r=c['size'], ttl=c['ttl'], follow=True,
		             a0=pr.phase + i * TAU / n, f0=r, f1=spd,
		             crit_c=_crit(c, pr), crit_m=c['crit_m'])


def _fire_aura(w, pr, c, mult):
	em = E['aura']
	tick = em['tick'] / (1.0 + 0.14 * (pr.rank - 1) + 0.12 * pr.ops.get('swift', 0))
	new_proj(w, 'field', w.player.x, w.player.y, 0, 0, c['dmg'] * mult, c['col'], pr,
	         r=c['size'] * w.player.area_mult, ttl=c['ttl'], follow=True,
	         f1=0.05, f2=tick, crit_c=_crit(c, pr) * 0.5, crit_m=c['crit_m'])


def _fire_nova(w, pr, c, mult):
	pl = w.player
	for i in range(max(1, min(6, int(c['count'])))):
		new_proj(w, 'wave', pl.x, pl.y, 0, 0, c['dmg'] * mult, c['col'], pr,
		         r=10.0, ttl=c['ttl'] + 0.1 * i, follow=True, owner=pl,
		         f0=14.0, f1=c['size'] * w.player.area_mult * (1.0 + 0.12 * i),
		         crit_c=_crit(c, pr), crit_m=c['crit_m'])
	w.audio.play('fire_nova', 0.6, 0.08)
	w.fx.shake(0.05)


def _fire_beam(w, pr, c, mult):
	em = E['beam']
	n = max(1, min(6, int(c['count'])))
	L = em['length'] * (1.0 + 0.10 * (pr.rank - 1)) * w.player.area_mult * (1.0 + 0.22 * pr.ops.get('giant', 0))
	spd = em['speed'] * (1.0 + 0.08 * pr.ops.get('swift', 0)) * (1.0 if w.rng.random() < 0.5 else -1.0)
	for i in range(n):
		new_proj(w, 'beam', w.player.x, w.player.y, 0, 0, c['dmg'] * mult, c['col'], pr,
		         r=c['size'] * 0.5, ttl=c['ttl'], follow=True,
		         a0=pr.phase + i * TAU / n, f0=L, f1=spd, f2=0.1,
		         crit_c=_crit(c, pr) * 0.4, crit_m=c['crit_m'])
	w.audio.play('fire_beam', 0.4, 0.4)


def _fire_mine(w, pr, c, mult):
	em = E['mine']
	pl = w.player
	n = c['count']
	for i in range(n):
		a = w.rng.random() * TAU
		sp = em['speed'] * w.rng.uniform(0.4, 1.0)
		new_proj(w, 'mine', pl.x, pl.y, math.cos(a) * sp, math.sin(a) * sp,
		         c['dmg'] * mult, c['col'], pr, r=c['size'], ttl=c['ttl'],
		         f0=0.45, f1=em['blast_r'] * w.player.area_mult * (1.0 + 0.10 * pr.ops.get('giant', 0)),
		         crit_c=_crit(c, pr), crit_m=c['crit_m'])
	w.audio.play('fire_mine', 0.45, 0.08)


def _fire_arc(w, pr, c, mult):
	from game.combat import chain_arc, nearest_n
	pl = w.player
	n = c['count']
	seen = set()
	# the CHAIN op never reached this emitter: chain_arc is called straight from
	# here, so _hit -- where ops['chain'] is normally read -- is never involved,
	# while CHAIN sits in its affinity list and THUNDER TRANSFORMER wants rank 4
	jumps = E['arc']['jumps'] + pr.rank // 3 + pr.ops.get('chain', 0)
	fired = 0
	for i in range(n):
		tg = nearest_n(w, pl.x, pl.y, 1, 460.0, seen)
		if not tg: break
		crit = w.rng.random() < _crit(c, pr)
		d = c['dmg'] * mult * (c['crit_m'] if crit else 1.0)
		if pr.heat > 0: d *= 1.0 + pr.heat * pr.heat_dmg
		chain_arc(w, pl.x, pl.y, tg[0], d, c['col'], pr, jumps, 200.0, seen)
		fired += 1
	if fired: w.audio.play('fire_arc', 0.5, 0.06)


def _fire_turret(w, pr, c, mult):
	pl = w.player
	rate = E['turret']['rate'] / (1.0 + 0.10 * (pr.rank - 1) + 0.16 * pr.ops.get('swift', 0))
	n = max(1, min(6, int(c['count'])))
	for i in range(n):
		a = w.rng.random() * TAU
		d = 40.0 + w.rng.random() * 60.0
		new_proj(w, 'turret', pl.x + math.cos(a) * d, pl.y + math.sin(a) * d, 0, 0,
		         c['dmg'] * mult, c['col'], pr, r=10.0, ttl=c['ttl'] * w.player.dur_mult,
		         f0=0.3, f1=rate, f2=c['size'],
		         crit_c=_crit(c, pr), crit_m=c['crit_m'])
	w.fx.wave(pl.x, pl.y, 8, 40, 0.3, c['col'], 3)


def _fire_blade(w, pr, c, mult):
	a, _t = aim(w, pr)
	n = c['count']
	pl = w.player
	for i in range(n):
		aa = a + (i - (n - 1) * 0.5) * (TAU / max(3, n + 1))
		new_proj(w, 'blade', pl.x, pl.y, math.cos(aa) * c['speed'], math.sin(aa) * c['speed'],
		         c['dmg'] * mult, c['col'], pr, r=c['size'], ttl=c['ttl'],
		         pierce=E['blade']['pierce'], spin=13.0,
		         f0=c['ttl'] * 0.34 * (1.0 + 0.30 * pr.ops.get('bounce', 0)),
		         crit_c=_crit(c, pr), crit_m=c['crit_m'])
	w.audio.play('fire_boom', 0.45, 0.07)


def _fire_flame(w, pr, c, mult):
	"""A cone of short-lived piercing embers. Fires constantly, so each tongue is
	cheap: the damage lives in the overlap, not in any one particle."""
	em = E['flame']
	pl = w.player
	a, _t = aim(w, pr)
	n = c['count']
	cone = em['cone'] * (1.0 + 0.16 * pr.ops.get('multishot', 0))
	reach = c['ttl'] * (1.0 + 0.12 * pr.ops.get('giant', 0))
	for i in range(n):
		aa = a + w.rng.uniform(-cone, cone) * 0.5
		sp = c['speed'] * w.rng.uniform(0.72, 1.15)
		_shoot(w, pr, c, pl.x + math.cos(a) * 12, pl.y + math.sin(a) * 12, aa, sp,
		       c['dmg'] * mult, c['size'] * w.rng.uniform(0.75, 1.25), reach,
		       pierce=em['pierce'] + pr.ops.get('pierce', 0))
	if w.rng.random() < 0.22:
		w.audio.play('fire_swarm', 0.28, 0.2)


def _fire_spiral(w, pr, c, mult):
	pl = w.player
	n = c['count']
	pr.phase += 0.7
	for i in range(n):
		a = pr.phase + i * TAU / n
		p = _shoot(w, pr, c, pl.x, pl.y, a, c['speed'], c['dmg'] * mult, c['size'], c['ttl'])
		p.seed = 0.0 if (i % 2 == 0 or 'VORTEX' in pr.syn) else 1.0
		if 'orbitize' not in pr.ops:
			# the spiral emitter always curves a little, even without the op
			p.a1 = 1.0
	w.audio.play('fire_orb', 0.4, 0.07)


def _fire_rain(w, pr, c, mult):
	pl = w.player
	n = c['count']
	rad = c['size'] * w.player.area_mult
	for i in range(n):
		e = random_enemy(w, pl.x, pl.y, 520.0)
		if e is not None:
			tx = e.x + w.rng.uniform(-30, 30); ty = e.y + w.rng.uniform(-30, 30)
		else:
			a = w.rng.random() * TAU; d = w.rng.uniform(90, 340)
			tx = pl.x + math.cos(a) * d; ty = pl.y + math.sin(a) * d
		w.timers.append((w.t + 0.18 + 0.09 * i, _mk_strike(w, pr, c, tx, ty, rad, mult)))
		w.fx.wave(tx, ty, rad, rad * 0.3, 0.28, c['col'], 2)


def _mk_strike(w, pr, c, x, y, rad, mult):
	def go():
		from game.combat import explode
		crit = w.rng.random() < _crit(c, pr)
		d = c['dmg'] * mult * (c['crit_m'] if crit else 1.0)
		if pr.heat > 0: d *= 1.0 + pr.heat * pr.heat_dmg
		w.fx.part('spark', x, y - 120, 0, 900, 0.18, 5.0, c['col'], 0.0)
		explode(w, x, y, rad, d, c['col'], pr, 220.0, 0.05, None, crit, status=True)
		bl = pr.ops.get('blast', 0)
		if bl:
			explode(w, x, y, rad * 0.6, d * 0.4, c['col'], pr, 120.0, 0.0, None, crit)
	return go


# ================================================================ ARSENAL
class Arsenal:
	def __init__(self, w, first='bolt'):
		self.w = w
		self.procs = [Process(first)]
		self.slots = 4
		self.log = []

	def add_process(self, emit):
		p = Process(emit)
		self.procs.append(p)
		return p

	def can_add(self): return len(self.procs) < self.slots

	def mark_dirty(self):
		for pr in self.procs: pr.dirty = True

	def update(self, dt, w):
		pl = w.player
		for pr in self.procs:
			c = pr.stats(pl)
			if pr.heat_max > 0.0 and pr.heat > 0.0:
				pr.heat = max(0.0, pr.heat - dt * pr.heat_decay * w.player.cool_mult)
			pr.flash = max(0.0, pr.flash - dt * 4.0)
			pr.phase += dt * (orbit_speed(pr) if pr.emit == 'orbit' else 1.0)
			if pr.pending:
				keep = []
				for tt, m in pr.pending:
					if w.t >= tt: fire(w, pr, m, True)
					else: keep.append((tt, m))
				pr.pending = keep
			pr.t -= dt
			if pr.t <= 0.0:
				pr.t += c['cd']
				if pr.t < 0.0: pr.t = c['cd'] * 0.5
				fire(w, pr)

	def fuse(self, a, b):
		"""Merge b into a. The plan is computed by fuse_plan so the card can show
		exactly this before you commit to it."""
		ops, rank, dropped = fuse_plan(a, b)
		a.ops = ops
		a.rank = rank
		a.fused += 1 + b.fused
		if b in self.procs: self.procs.remove(b)
		a.refresh()
		return a.check_evo()

	def total_power(self, pl):
		return sum(p.power(pl) for p in self.procs)
