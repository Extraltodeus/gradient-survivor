"""Level-up offer generation.

The point of this module is that offers are not random noise: they are biased
toward whatever would make the player's current build *cohere* -- ops that finish
an evolution, ops that light up a synergy, fusions that free a slot.
"""

import math, random
from core.settings import *
from core.utils import *
from game.weapons import (E, O, SYN, SYN_BY_ID, EVO_BY_EMIT, PASSIVES, PASSIVE_BY_ID,
                          Process, MAX_OPS_PER_PROC, EMIT_ORDER, STARTERS,
                          fuse_plan, ghost_process)
from game.player import passive_preview


class Offer:
	__slots__ = ('kind', 'key', 'title', 'sub', 'desc', 'col', 'rarity', 'glyph',
	             'note', 'note_col', 'apply', 'proc', 'ops_preview', 'weight', 'pv', 'pair')


def _mk(kind, key, title, sub, desc, col, rarity, glyph, apply, proc=None,
        note=None, note_col=GOLD, weight=1.0):
	o = Offer()
	o.kind = kind; o.key = key; o.title = title; o.sub = sub; o.desc = desc
	o.col = col; o.rarity = rarity; o.glyph = glyph; o.apply = apply
	o.proc = proc; o.note = note; o.note_col = note_col; o.weight = weight
	o.ops_preview = None
	o.pv = None
	o.pair = None
	return o


# ===================================================== PREVIEW (what it does)
# Every card gets a before/after it can actually show. Built only for the cards
# that make it onto the table -- pricing the whole pool would cost far more.

_STAT_ROWS = (
	('damage',     lambda p: p.dmg_mult * 100.0,        '%.0f%%',  1),
	('cooldown',   lambda p: p.cd_mult * 100.0,         '%.0f%%', -1),
	('area',       lambda p: p.area_mult * 100.0,       '%.0f%%',  1),
	('proj speed', lambda p: p.pspeed_mult * 100.0,     '%.0f%%',  1),
	('amount',     lambda p: p.amount,                  '+%.0f',   1),
	('max hp',     lambda p: p.maxhp,                   '%.0f',    1),
	('regen',      lambda p: p.regen,                   '%.1f/s',  1),
	('move',       lambda p: p.move_mult * 100.0,       '%.0f%%',  1),
	('pickup',     lambda p: p.magnet,                  '%.0f',    1),
	('xp gain',    lambda p: p.xp_mult * 100.0,         '%.0f%%',  1),
	('armour',     lambda p: p.armor,                   '%.0f',    1),
	('crit',       lambda p: p.crit_c * 100.0,          '%.0f%%',  1),
	('crit dmg',   lambda p: (2.0 + p.crit_m) * 100.0,  '%.0f%%',  1),
	('luck',       lambda p: p.luck * 100.0,            '%.0f%%',  1),
	('dodge',      lambda p: p.dodge * 100.0,           '%.0f%%',  1),
	('heat decay', lambda p: p.cool_mult * 100.0,       '%.0f%%', -1),
	('rerolls',    lambda p: p.rerolls,                 '%.0f',    1),
	('banishes',   lambda p: p.banishes,                '%.0f',    1),
)


# passives whose effect is visible on a weapon rather than on the agent
WEAPON_PASSIVES = ('power', 'haste', 'area', 'vel', 'crit', 'amount', 'cool')


def _rows_player(a, b):
	out = []
	for label, get, fmt, sign in _STAT_ROWS:
		va = get(a); vb = get(b)
		if abs(vb - va) < 1e-6: continue
		out.append((label, fmt % va, fmt % vb, (1 if vb > va else -1) * sign))
	return out


def _rows_proc(pl, a, b):
	"""Numbers for one process, before vs after. Unchanged lines are dropped: a
	table of identical values teaches nothing."""
	ca = a.stats(pl); cb = b.stats(pl)
	raw = [('damage',  '%.0f' % ca['dmg'],   '%.0f' % cb['dmg'],   cb['dmg'] - ca['dmg']),
	       ('shots',   'x%d' % ca['count'],  'x%d' % cb['count'],  cb['count'] - ca['count']),
	       ('cadence', '%.2fs' % ca['cd'],   '%.2fs' % cb['cd'],   ca['cd'] - cb['cd']),
	       ('size',    '%.0f' % ca['size'],  '%.0f' % cb['size'],  cb['size'] - ca['size']),
	       ('crit',    '%.0f%%' % (ca['crit_c'] * 100), '%.0f%%' % (cb['crit_c'] * 100),
	        cb['crit_c'] - ca['crit_c'])]
	out = [(l, x, y, 1 if d > 0 else -1) for l, x, y, d in raw if abs(d) > 1e-6]
	pa = a.power(pl); pb = b.power(pl)
	out.append(('est. dps', '%d' % pa, '%d' % pb, 1 if pb >= pa else -1))
	return out


def _mods(ops):
	"""Ranked ops, as the weapon scenes want them: rank drives how loud each
	effect is drawn, so III does not look like I."""
	return dict(ops)


def attach_preview(w, o):
	pl = w.player
	if o.kind == 'op' and o.proc is not None:
		op = o.key[3:]
		pr = o.proc
		nxt = dict(pr.ops)
		nxt[op] = min(MAX_TRAIT_RK, nxt.get(op, 0) + 1)
		g = ghost_process(pr.emit, nxt, pr.rank)
		o.pv = dict(mode='ab', emit=pr.emit, before=_mods(pr.ops), after=_mods(nxt),
		            evo_a=pr.evo, evo_b=g.evo, name_a=pr.name, name_b=g.name,
		            rows=_rows_proc(pl, pr, g), focus=op, ghost=g)
	elif o.kind == 'new':
		k = o.key.split(':', 1)[1]
		g = ghost_process(k, {}, 1)
		em = E[k]
		o.pv = dict(mode='solo', emit=k, after=set(), evo_b=None, name_b=em['name'],
		            rows=[('damage', '-', '%.0f' % em['dmg'], 1),
		                  ('shots', '-', 'x%d' % em['count'], 1),
		                  ('cadence', '-', '%.2fs' % em['cd'], 1),
		                  ('est. dps', '0', '%d' % g.power(pl), 1)],
		            ghost=g)
	elif o.kind == 'passive':
		pid = o.key.split(':', 1)[1]
		g = passive_preview(pl, pid, w.arsenal.slots)
		rows = _rows_player(pl, g)
		if pid == 'slot':
			rows.insert(0, ('process slots', '%d' % w.arsenal.slots, '%d' % (w.arsenal.slots + 1), 1))
		o.pv = dict(mode='passive', pid=pid, rows=rows, ghost=g)
		# a global multiplier is abstract until you see it land on the weapon you
		# are actually running, so show it there
		if pid in WEAPON_PASSIVES and w.arsenal.procs:
			pr = max(w.arsenal.procs, key=lambda p: p.power(pl))
			gp = ghost_process(pr.emit, pr.ops, pr.rank)
			o.pv.update(emit=pr.emit, ops=dict(pr.ops), st_a=dict(pr.stats(pl)),
			            st_b=dict(gp.stats(g)), name_a=pr.name)
	elif o.kind == 'fuse' and o.pair is not None:
		a, b = o.pair
		ops, rank, dropped = fuse_plan(a, b)
		g = ghost_process(a.emit, ops, rank)
		o.pv = dict(mode='fuse', a=a, b=b, ghost=g, dropped=dropped,
		            emit=a.emit, emit_b=b.emit, after=_mods(ops),
		            name_b=g.name, evo_b=g.evo, rows=_rows_proc(pl, a, g),
		            rows_b=_rows_proc(pl, b, g))
	elif o.kind == 'heal':
		o.pv = dict(mode='heal', rows=[('integrity', '%d' % int(pl.hp), '%d' % int(pl.maxhp), 1)])
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
		room = len(pr.ops) < pr.op_cap()
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
			# ops that only move a number the global passives already move are the
			# ones that read as filler; they still exist, they just stop crowding
			# out the ones that change what the weapon DOES
			if d['tag'] == 'stat': wgt *= 0.66
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
	# A free process slot with no weapon on the table is the single worst hand the
	# game can deal: the slot is visible in the HUD and there is nothing to do with
	# it. These are kept apart so one can be forced onto the table below.
	news = []
	if ar.can_add():
		have = set(p.emit for p in ar.procs)
		for k in EMIT_ORDER:
			if k in have: continue
			key = 'new:' + k
			if key in banned: continue
			em = E[k]
			wgt = 13.0 / (1.0 + em['tier'] * 0.55)
			if len(ar.procs) < 3: wgt *= 1.7
			news.append(_mk('new', key, em['name'], 'NEW PROCESS', em['desc'], em['col'], 2,
			                em['glyph'], _apply_new(w, k), None,
			                'fills process slot %d of %d' % (len(ar.procs) + 1, ar.slots),
			                INK_DIM, wgt))
		pool.extend(news)

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
		         'Two processes become one. No op is lost, shared ops gain a rank, '
		         'the ranks add, and a process slot is freed.',
		         MAGENTA, 3, '&', _apply_fuse(w, a, b), a,
		         b.name + ' stops existing', RED, 11.0)
		fo.ops_preview = (a.emit, b.emit)
		fo.pair = (a, b)
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

	def take(o):
		pool.remove(o)
		seen.add(o.key)
		kinds[o.kind] = kinds.get(o.kind, 0) + 1
		if o.proc is not None: procs[id(o.proc)] = procs.get(id(o.proc), 0) + 1
		out.append(o)

	# a free slot always gets something to put in it, before anything else rolls
	avail = [x for x in news if x in pool]
	if avail:
		pick = [x for x in avail if x.key not in avoid] or avail
		take(weighted(rng, [(x, x.weight) for x in pick]))

	while len(out) < n and pool and guard < 400:
		guard += 1
		o = weighted(rng, [(x, _w(x)) for x in pool])
		if o is None: break
		if o.key in seen:
			pool.remove(o); continue
		take(o)
	if not out:
		out.append(_mk('heal', 'heal', 'DEFRAGMENT', 'SYSTEM',
		               'Restore every point of integrity you are missing.',
		               HP_COL, 1, '+', _apply_heal(w, None)))
	for o in out: attach_preview(w, o)
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


def _apply_heal(w, n=None):
	"""n=None is a full repair -- the fallback card and the skip both use it."""
	def go(): w.player.heal(w.player.maxhp if n is None else n)
	return go
