# Code map

A navigation file for whoever picks this up cold — including me, from a blank
conversation. It says where things live and which invariants are load-bearing.
It is not a tutorial and not an API reference; read the modules for that.

Python 3.10, pygame 2.1.2, numpy. No assets: every shape is drawn from vectors
and every sound is synthesised at boot. Tabs for indentation, code in English.

---

## Shape of the thing

```
main.py                  the Game object: display, scenes, event routing, save file
core/    settings.py     constants, palette, resolution; VERSION lives here
         utils.py        math, spatial hash, cached surface factories, text, agent_shape
         fx.py           particles, damage numbers, shockwaves, shake, hitstop
         audio.py        the synth rack and the sequencer; nothing is loaded from disk
         pace.py         the four training schedules (difficulty presets)
game/    world.py        owns every entity list, ticks the sim, draws the scene
         player.py       the agent: movement, dash/blink, stats, levelling
         weapons.py      emitters, ops, synergies, evolutions, the Process, firing
         projectiles.py  projectile entities and the hit-resolution pipeline
         combat.py       targeting, damage, status effects, explosions, chains
         enemies.py      archetypes, AI, enemy projectiles
         bosses.py       one telegraphed multi-phase boss per biome
         director.py     pressure curve, wave composition, events, biome pacing
         levels.py       biomes: palettes, procedural backdrops, ambient hazards
         pickups.py      xp tokens, integrity, caches
         offers.py       what the level-up screen is allowed to offer, and previews
         transition.py   the biome change, rendered as a matrix multiply
         sandbox.py      the bench: install anything into a live run
         ui.py           HUD, level-up cards, pause, options, codex, tree, menus
tools/                   headless harnesses; none of them are shipped
```

`ui.py` is the biggest file by a wide margin and it is mostly drawing code with
no state. `weapons.py` is the design surface. Those two are where most work lands.

---

## The scene machine

`Game.scene` is a string. Every scene routes its own events in
`Game.handle_events` and draws in `Game.draw`:

`title` `select` `codex` `options` `play` `pause` `tree` `levelup` `sandbox` `end`

Only `play` and `sandbox` tick the world. `levelup` owns its own class
(`ui.LevelUp`) because it holds selection state across frames; every other scene
is a pure draw call plus a rect list the router hit-tests.

Two of them are overlays drawn on top of a live world frame: `pause` and `tree`.
`tree` remembers where it was opened from in `Game.tree_back`.

---

## Weapons: the model

Everything is built from a handful of tables in `weapons.py`, all filled by
helper functions at import time:

| table | built by | what it is |
|---|---|---|
| `E` | `_em()` | 13 **emitters** — the weapon itself. Each names a `_fire_*` function. |
| `O` | `_op()` | 22 **ops** — modifiers installed onto one process, rank 1..5 |
| `SYN` | literal | op **thresholds** that unlock a named behaviour |
| `EVOS` | `_ev()` | **evolutions**: emitter + op ranks → a new named weapon |
| `PASSIVES` | literal | global stat upgrades, not attached to a process |
| `BOOTS` | literal | the seven playable units |

A **`Process`** is one installed weapon: an emitter, a rank, and a dict of ops.
`Process.stats(pl)` folds the emitter's base numbers, its rank, its ops' `mods`,
its evolution's `mods` and the player's global multipliers into one stat block.
Cached, invalidated by `mark_dirty()`.

`Process.power(pl)` is the **estimated dps** shown on cards and in the pause
screen. It is a hand-fitted model of the projectile pipeline, not a stat sum —
most interesting ops (pierce, chain, split, burn, corrupt) carry no stat
modifier at all, so a stat-sum estimate shows the same number before and after
taking one, which is exactly backwards on a card whose job is to say what
changes. Every coefficient in it was fitted against measured damage. The `crowd`
factor on each emitter is measured, and ops are compressed against it: an
emitter already hitting everything in range has little left for PIERCE to add.

**If you change how an emitter fires, check `power()` still tracks it.** The
harness pattern: 24 enemies pinned in a ring, 18 seconds, one op swept at ranks
1/3/5, compare `power()` against `world.stats['dmg'] / seconds`.

---

## Weapons: firing, and where ops actually get spent

`fire()` → `_fire_<emit>()` → usually `new_proj()`. Each projectile has a
**kind**, and the kind decides which hit path it takes. Two emitters make no
projectile at all. This is the single most important thing to know here:

| kind | emitters | update fn | hit path | ops available |
|---|---|---|---|---|
| `shot` | bolt, swarm, spiral, flame | `_upd_shot` → `_collide_point` | **`_hit`** | everything |
| `orb` | orbit | `_upd_orb` → `_collide_persist` | `_apply` | elements only |
| `field` | aura | `_upd_field` | `_apply` | elements only |
| `wave` | nova | `_upd_wave` | `_apply` | elements only |
| `beam` | beam | `_upd_beam` | `_apply` | elements only |
| `blade` | blade | `_upd_blade` → `_collide_persist` | `_apply` | elements only |
| `turret` | turret | `_upd_turret`, which spawns `shot`s | via its shots | everything |
| `mine` | mine | `_upd_mine` → `_detonate_mine` | `explode()` | spent by hand |
| *none* | arc | fires instantly from `_fire_arc` | `combat.chain_arc` | spent by hand |
| *none* | rain | a timer running `_mk_strike` | `combat.explode` | spent by hand |

`_hit` is the full pipeline: blast, chain, split, void, pierce, bounce.
`_apply` only carries the elemental payload: burn, frost, shock, corrupt, crit,
drain. `explode()` reaches `damage_enemy` and carries no ops of its own.

So **an op named in an emitter's `affinity`, or required by one of its
evolutions, can silently do nothing** if that emitter's kind never reaches the
code that spends it. Seven evolution recipes shipped in exactly that state once.
The repairs are: `_detonate_mine` spending blast/split/chain/void explicitly, a
rate-limited impact-op block inside `_apply` for non-`shot` kinds, and
`combat.apply_status` for paths that skip `_apply` entirely.

Same trap in the arithmetic: `_fire_beam`, `_fire_nova` and `_fire_turret` all
divided `count` by two against a base count of 1, so MULTISHOT I and II were
worth nothing while `power()` — linear in `count` — happily raised the estimate.

When adding an op or an evolution, the check is: *pick the weakest enemy type,
measure dps with the op at rank 0 and rank 5, and confirm the number moves.*
Measuring against tanky enemies hides every kill-gated op (recursion, corrupt).

---

## The level-up screen

`offers.build_offers(w)` decides what is offerable; `ui.LevelUp` renders and
routes it. Offer kinds: `op`, `new` (a new emitter), `passive`, `fuse`, `heal`.

`offers.attach_preview()` builds the before/after data onto the offer, using
**ghost objects** — `weapons.ghost_process()` and `player.passive_preview()` —
so nothing mutates the run in order to price a hypothetical.

`ui._weapon_scene()` draws the little animated diagram. Every op decoration in it
**must be a function of the op's rank**, or the before and after panels render
byte-identical pixels and the card lies. Same for the target lane: it grows with
`max(pierce, chain)`, because a shot that runs out of bodies before it runs out
of ranks draws the previous rank's picture.

Points **bank** in `player.banked`. The screen spends one per pick and deals a
fresh hand while any remain (`LevelUp.spend`). `Game.lvl_hold` stops it
re-opening after the player leaves with points still owed; a new level clears it.
`opts['defer']` turns off auto-opening entirely.

`fuse_plan(a, b)` merges two processes. It is deliberately lossless — it must
never drop an op, because a fusion that reads as a downgrade is worse than no
fusion at all. `Process.op_cap()` widens to accommodate it.

---

## Options and the save file

`main.OPTIONS` is the single table: id, display name, hotkey, real values,
labels, description. `Game.opt_get / opt_cycle / persist_opts` read and write the
live state, the function keys route through the same `opt_cycle`, and
`ui.draw_options` renders it. Adding an option means adding one row, plus a
branch in `opt_get`/`opt_cycle` if it does not live in `Game.opts`.

`save.json` sits next to the exe, falling back to `%APPDATA%` if that folder is
read-only. It holds the options, the best run, and one score board per schedule.

---

## Traps that have already cost time

- **`_hit` vs `_apply`.** See the table above. First thing to check when an op
  "does nothing".
- **Measuring op strength against tanky enemies.** Kill-gated ops never fire, so
  they read as inert when they are not.
- **Fixed-size decorations in `_weapon_scene`.** They make the comparison panels
  identical and the card dishonest.
- **CRLF.** git normalises on commit, so patch scripts that match exact strings
  break right after a `commit` or `checkout`. Normalise before patching.
- **Stdlib shadowing.** A scratch file named `select.py` on `sys.path[0]`
  re-executes on any transitive `import select`. Name scratch scripts `zz_*.py`.
- **Batching enemy blits** was tried and reverted: 276k→108k calls, zero net gain.
- **Explosion rings** are capped in `fx.wave` (`WAVE_SOFT` / `WAVE_CAP`) for
  readability, not for speed — `draw.circle` is about 1% of the frame.
- **A locked exe.** `tools/build.py` fails with `PermissionError` if the game is
  still running from `dist/`.

---

## Harnesses

```
python tools/smoke.py       every scene, a real run, the sandbox
python tools/bosstest.py    all five bosses through every phase
python tools/bench.py       frame budget, bloom on and off
python tools/simulate.py    a long headless run, prints the build it grew
python tools/audition.py    every sound, once
python tools/shots.py       the README images
python tools/build.py --zip PyInstaller, one file, windowed
```

All of them set `SDL_VIDEODRIVER=dummy`. Run smoke, bosstest and bench before
committing anything that touches the world, the pipeline or the UI.
