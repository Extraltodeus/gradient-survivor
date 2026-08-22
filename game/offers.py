"""Level-up offer generation.

The point of this module is that offers are not random noise: they are biased
toward whatever would make the player's current build *cohere* -- ops that finish
an evolution, ops that light up a synergy, fusions that free a slot.
"""

import math, random
from core.settings import *
from core.utils import *
from game.weapons import (E, O, SYN, SYN_BY_ID, EVO_BY_EMIT, PASSIVES, PASSIVE_BY_ID,
                          Process, MAX_OPS_PER_PROC, EMIT_ORDER, STARTERS)


class Offer:
	__slots__ = ('kind', 'key', 'title', 'sub', 'desc', 'col', 'rarity', 'glyph',
	             'note', 'note_col', 'apply', 'proc', 'ops_preview', 'weight')


def _mk(kind, key, title, sub, desc, col, rarity, glyph, apply, proc=None,
        note=None, note_col=GOLD, weight=1.0):
	o = Offer()
	o.kind = kind; o.key = key; o.title = title; o.sub = sub; o.desc = desc
	o.col = col; o.rarity = rarity; o.glyph = glyph; o.apply = apply
	o.proc = proc; o.note = note; o.note_col = note_col; o.weight = weight
	o.ops_preview = None
	return o


def _syn_gain(proc, op):
	"""Which synergies would light up if we added one rank of `op`?"""
	out = []
	nxt = dict(proc.ops)
	nxt[op] = min(MAX_TRAIT_RK, nxt.get(op, 0) + 1)
	for sid, req, _d in SYN:
		if sid in proc.syn: continue
		ok = True
		for k, v in req.items():
			if nxt.get(k, 0) < v: ok = False; break
		if ok: out.append(sid)
	return out


def _evo_gain(proc, op):
	if proc.evo: return None
	nxt = dict(proc.ops)
	nxt[op] = min(MAX_TRAIT_RK + 2, nxt.get(op, 0) + 1)
	for ev in EVO_BY_EMIT.get(proc.emit, ()):
		ok = True
		for k, v in ev['req'].items():
			if nxt.get(k, 0) < v: ok = False; break
		if ok: return ev
	return None


def _evo_step(proc, op):
	"""True if this op is part of the closest evolution recipe."""
	p = proc.evo_progress()
	if not p: return None
	ev, missing, frac = p
	if op in missing: return (ev, frac)
	return None


def build_offers(w, n=None, avoid=None):
	pl = w.player
	ar = w.arsenal
	rng = w.rng
	banned = w.banned
	luck = pl.luck
	if n is None:
		n = 4 + (1 if rng.random() < 0.16 + luck * 0.8 else 0)
	avoid = avoid or ()

	pool = []

	# ---------------------------------------------------------- op upgrades
	for pr in ar.procs:
		em = E[pr.emit]
		room = len(pr.ops) < MAX_OPS_PER_PROC
		for op in O:
			cur = pr.ops.get(op, 0)
			if cur >= MAX_TRAIT_RK: continue
			if cur == 0 and not room: continue
			d = O[op]
			key = 'op:' + op
			if key in banned: continue
			wgt = 10.0 / (1.0 + 0.35 * (d['rare'] - 1))
			# bias toward deepening what already exists: that is where combos live
			if cur == 0: wgt *= 0.78
			else: wgt *= 1.0 + 0.30 * cur
			if op in em['affinity']: wgt *= 1.55
			note = None; note_col = GOLD
			ev = _evo_gain(pr, op)
			st = _evo_step(pr, op)
			syn = _syn_gain(pr, op)
			if ev is not None:
				wgt *= 4.2
				note = '>> EVOLVES INTO ' + ev['name']
				note_col = GOLD
			elif st is not None:
				wgt *= 1.0 + 1.9 * st[1]
				note = '-> toward ' + st[0]['name']
				note_col = (200, 170, 120)
			if syn:
				wgt *= 2.0
				note = '+ SYNERGY: ' + ', '.join(syn)
				note_col = VIOLET
			rar = 1 if d['rare'] == 1 else 2
			if ev is not None: rar = 3
			pool.append(_mk('op', key,
			                d['name'] + (' ' + 'I' * (cur + 1) if cur + 1 <= 3 else ' ' + str(cur + 1)),
			                pr.name, d['desc'], d['col'] or E[pr.emit]['col'], rar, d['glyph'],
			                _apply_op(w, pr, op), pr, note, note_col, wgt))

	# --------------------------------------------------------- new processes
	if ar.can_add():
		have = set(p.emit for p in ar.procs)
		for k in EMIT_ORDER:
			if k in have: continue
			key = 'new:' + k
			if key in banned: continue
			em = E[k]
			wgt = 13.0 / (1.0 + em['tier'] * 0.55)
			if len(ar.procs) < 3: wgt *= 1.7
			pool.append(_mk('new', key, em['name'], 'NEW PROCESS', em['desc'], em['col'], 2,
			                em['glyph'], _apply_new(w, k), None,
			                'occupies a process slot', INK_DIM, wgt))

	# ----------------------------------------------------------- rank ups
	for pr in ar.procs:
		key = 'rank:%d' % pr.uid
		wgt = 7.0 + 1.5 * len(pr.ops)
		pool.append(_mk('rank', key, 'AMPLIFY', pr.name,
		                'Rank %d -> %d: +20%% damage on this process.' % (pr.rank, pr.rank + 1),
		                pr.col, 1, '+', _apply_rank(w, pr), pr, None, GOLD, wgt))

	# ------------------------------------------------------------- passives
	for p in PASSIVES:
		key = 'passive:' + p['id']
		if key in banned: continue
		if p['id'] == 'slot' and w.arsenal.slots >= MAX_PROCESSES: continue
		lvl = pl.passives.get(p['id'], 0)
		if lvl >= (2 if p['rare'] == 3 else (8 if p['rare'] == 2 else 12)): continue
		wgt = 9.0 / (1.0 + 0.8 * (p['rare'] - 1))
		wgt *= 1.0 / (1.0 + 0.25 * lvl)
		if p['rare'] == 3: wgt *= (1.0 + luck * 2.0)
		pool.append(_mk('passive', key, p['name'] + ('' if lvl == 0 else ' +%d' % lvl), 'SYSTEM',
		                p['desc'], INK if p['rare'] == 1 else (VIOLET if p['rare'] == 2 else GOLD),
		                p['rare'], p['glyph'], _apply_passive(w, p['id']), None, None, GOLD, wgt))

	# ---------------------------------------------------------------- fusion
	cands = [p for p in ar.procs if len(p.ops) >= 3 and not p.evo]
	if len(ar.procs) >= 3 and len(cands) >= 2 and pl.level - w.last_fuse_lv >= 4:
		cands.sort(key=lambda p: -p.power(pl))
		a, b = cands[0], cands[1]
		key = 'fuse:%d:%d' % (a.uid, b.uid)
		fo = _mk('fuse', key, 'MERGE', a.name + '  <-  ' + b.name,
		         'Fuse both processes: union of every op (ranked up), ranks added, one slot freed.',
		         MAGENTA, 3, '&', _apply_fuse(w, a, b), a,
		         'destroys ' + b.name, RED, 11.0)
		fo.ops_preview = (a.emit, b.emit)
		pool.append(fo)

	# ------------------------------------------------------------- selection
	# Two pressures on top of the raw weights: whatever was just rerolled away is
	# pushed out of the way, and each kind (and each process) gets progressively
	# cheaper to skip once it is already on the table -- four op cards for the same
	# process is technically a roll of the dice and practically a non-choice.
	out = []
	seen = set()
	guard = 0
	kinds = {}
	procs = {}
	fresh = [x for x in pool if x.key not in avoid]
	if len(fresh) >= n: pool = fresh

	def _w(x):
		f = x.weight * (0.30 ** kinds.get(x.kind, 0))
		if x.proc is not None:
			f *= 0.5 ** procs.get(id(x.proc), 0)
		return f

	while len(out) < n and pool and guard < 400:
		guard += 1
		o = weighted(rng, [(x, _w(x)) for x in pool])
		if o is None: break
		pool.remove(o)
		if o.key in seen: continue
		if o.kind == 'op' and any(x.kind == 'op' and x.proc is o.proc and x.key == o.key for x in out):
			continue
		seen.add(o.key)
		kinds[o.kind] = kinds.get(o.kind, 0) + 1
		if o.proc is not None: procs[id(o.proc)] = procs.get(id(o.proc), 0) + 1
		out.append(o)
	if not out:
		out.append(_mk('heal', 'heal', 'DEFRAGMENT', 'SYSTEM', 'Restore 40 integrity.',
		               HP_COL, 1, '+', _apply_heal(w, 40)))
	return out


# ----------------------------------------------------------------- appliers
def _evo_burst(w, pr, ev):
	w.stats['evos'] += 1
	w.evo_log.append(ev['name'])
	w.audio.play('evolve', 1.0)
	w.fx.screen_flash(GOLD, 0.7)
	w.fx.shake(0.5)
	pl = w.player
	w.fx.wave(pl.x, pl.y, 10, 420, 0.9, GOLD, 7)
	w.fx.burst(pl.x, pl.y, 48, GOLD, 420, 1.0, 4.0)
	w.fx.glyphs(pl.x, pl.y, 16, GOLD, 200, 1.4)
	w.banner(ev['name'], ev['desc'], GOLD)


def _apply_op(w, pr, op):
	def go():
		ev = pr.add_op(op)
		w.arsenal.mark_dirty()
		if ev: _evo_burst(w, pr, ev)
	return go


def _apply_new(w, k):
	def go():
		pr = w.arsenal.add_process(k)
		w.fx.wave(w.player.x, w.player.y, 8, 160, 0.6, E[k]['col'], 4)
	return go


def _apply_rank(w, pr):
	def go():
		pr.rank += 1
		pr.refresh()
		ev = pr.check_evo()
		if ev: _evo_burst(w, pr, ev)
	return go


def _apply_passive(w, pid):
	def go():
		w.player.apply_passive(pid)
	return go


def _apply_fuse(w, a, b):
	def go():
		ev = w.arsenal.fuse(a, b)
		w.stats['fuses'] += 1
		w.last_fuse_lv = w.player.level
		w.audio.play('merge', 1.0)
		w.fx.screen_flash(MAGENTA, 0.5)
		w.fx.wave(w.player.x, w.player.y, 8, 300, 0.7, MAGENTA, 6)
		w.fx.shake(0.35)
		if ev: _evo_burst(w, a, ev)
	return go


def _apply_heal(w, n):
	def go(): w.player.heal(n)
	return go
