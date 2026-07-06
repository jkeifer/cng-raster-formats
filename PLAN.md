# Workshop 2026 Update — Handoff / Working Plan

Status doc for updating the *Exploring Cloud-Native Geospatial Formats* workshop
(3 notebooks: `01` COG, `02` zarr, `03` kerchunk) for 2026 conferences. Written
as a handoff so the work can resume on another machine.

**Last updated:** 2026-07-06
**Working branch:** `jak/2026` (merges to `main`)

---

## ⚠️ Before moving machines — READ THIS FIRST

The Phase 2 work is **committed nowhere**. It is entirely uncommitted in the
working tree of `jak/2026`, and the `workshop`/`data` branches exist **only
locally** (not on `origin`). If you switch machines without acting, you lose it.

What IS safe on `origin/jak/2026`:
- **Phase 1** (notebook 01 fixes) — commit `fc12b51 "revise 01 COG notebook"`.

What is NOT pushed / NOT committed:
- **All of Phase 2** — uncommitted working-tree changes on `jak/2026` (see
  `git status` below).
- **`workshop` branch** — local only, 1 commit `830c5d3 "create workshop branch"`.
- **`data` branch** — local only, orphan, 1 commit `def0074 "create data branch"`.

### To carry the work to another machine

Commit and push everything first (from this machine):

```commandline
# 1. Commit the Phase 2 working-tree changes on jak/2026
git add -A
git commit -m "Phase 2: src/ layout, jupytext, delivery tooling, hygiene"
git push origin jak/2026

# 2. Push the dist branches (they are local-only right now)
git push -u origin workshop
git push -u origin data
```

Then on the new machine:

```commandline
git clone <repo> && cd cng-raster-formats
git checkout jak/2026
uv sync
# Recreate the worktrees (they are machine-local, not stored in git):
uv run scripts/worktree.py workshop   # -> ./workshop  (from origin/workshop)
uv run scripts/worktree.py data       # -> ./data      (from origin/data)
```

Worktrees are **not** portable — they are local checkouts. Recreate them with
`scripts/worktree.py` after cloning. `./workshop` and `./data` are gitignored.

---

## Repository / delivery model

Authored on `main`; published to two long-lived branches. Generated artifacts
are kept off `main`.

| Branch     | Contents                                                          | Audience     |
| ---------- | ---------------------------------------------------------------- | ------------ |
| `main`     | Source: `src/*.py`, `scripts/`, config, contributor README        | Contributors |
| `workshop` | Runnable notebooks + participant README, LICENSE, notes, run env  | Participants  |
| `data`     | Orphan branch hosting the self-built GeoZarr v3 store (byte-range) | (data host)  |

- **Source of truth:** `src/NN_completed.py` (Jupytext `py:percent`).
- **Generated (never committed on `main`):** `notebooks/NN_completed.ipynb`
  (Jupytext render), `notebooks/NN_<name>.ipynb` (exercise, via ipynb-scrubber),
  `notes/NN_<name>.md`. All gitignored on `main`.
- **`workshop` maintains its OWN runtime-only `pyproject.toml` + lock, README,
  LICENSE, Dockerfile, compose, .devcontainer.** The stage step writes ONLY
  notebooks + notes into it — never env files. No cross-branch env sync.

### Tooling (built, tested, working)

- `scripts/worktree.py <branch> [--path P] [--orphan]` — generic: ensure branch
  exists, check out as a worktree (default `./<branch>`), print the path. Prunes
  stale registrations; errors clearly on conflicts. Does not generate or commit.
- `scripts/generate_notebooks.py [--output-dir DIR]` — renders `src/` →
  completed `.ipynb` (Jupytext) → exercise `.ipynb` + notes (reuses
  ipynb-scrubber via a rebased temp config). Default `--output-dir` = repo root;
  point at `./workshop` to stage the dist branch. Produces clean, output-free
  notebooks.

### Publishing the workshop (the flow)

```commandline
uv run scripts/worktree.py workshop                         # -> ./workshop
uv run scripts/generate_notebooks.py --output-dir ./workshop
cd workshop && git add -A && git commit -m "..." && git push  # you review + commit
```

Config lives in `pyproject.toml` (`[tool.ipynb-scrubber]`) and `jupytext.toml`
(the `src/` ↔ `notebooks/` pairing).

---

## Progress

### ✅ Phase 1 — nb01 fixes (COMMITTED, pushed: `fc12b51`)
- Fixed bare `except:` in `extract_geo_keys` → `except Exception as e: ... from e`.
- Removed the broken `Tag.pack` stub from the appendix parser.
- Spellcheck pass on markdown (unit16→uint16, many typos).

### ✅ Phase 2 — Tooling, hygiene, delivery model (DONE, **UNCOMMITTED**)
- **`src/` layout + Jupytext:** `src/*_completed.py` are the source of truth;
  `jupytext.toml` pairs `src/` ↔ `notebooks/`. Verified byte-clean round-trip.
- **Deps:** deleted committed `requirements.txt` (+ README pip section); added
  `virtualizarr` + `icechunk` (zarr → 3.2.1). Dockerfile unaffected (exports
  from lock at build).
- **`.gitignore`:** replaced fragile `notebooks/*`+typo pattern; now ignores
  `/notebooks/`, `/notes/`, runtime cruft, and `/workshop/` `/data/` worktrees.
- **Notebooks untracked on `main`** (`git rm --cached`), now generated on demand.
  Verified a source-only tree rebuilds every notebook.
- **Delivery tooling:** `worktree.py` + `generate_notebooks.py` built and tested
  end-to-end (staged notebooks into `./workshop`).
- **README split:** `main/README.md` rewritten as contributor guide; participant
  README stays on `workshop`.
- **CI:** intentionally dropped (notebooks depend only on Earth Search + AWS S3 +
  the self-hosted `data` branch — all reliable; no upstream canary needed).

Uncommitted change set on `jak/2026` (as of writing):
```
 M .gitignore   M README.md   M pyproject.toml   M uv.lock
 D requirements.txt
 D notebooks/*.ipynb   D notes/*.md   (untracked now, still on disk)
?? PLAN.md   ?? jupytext.toml   ?? scripts/   ?? src/
```

### ⏳ Deferred (do after Phases 4/5, so deps aren't curated twice)
- Trim the `workshop` branch's `pyproject.toml` to runtime-only deps; regen its
  `uv.lock`. (Currently it still has the pre-Phase-2 pyproject with dev tooling.)
- Fix the stale participant README on the `workshop` branch (still has the
  removed pip section, old presentation dates).
- First real `workshop` / `data` branch publish commits.

---

## Remaining phases

### Phase 3 — Build & publish the v3 GeoZarr store  (NEXT)
Build our own Zarr **v3** GeoZarr store because no public geospatial v3 store
exists yet (verified: PC Daymet, EOPF Sentinel, NASA POWER are all still v2, and
none embed CRS in the store). Build from the SAME Sentinel-2 scene as nb01/nb03
for continuity (EPSG:32610).

- `scripts/build_geozarr.py` — **standalone PEP 723 inline-script**
  (`# /// script` block with `geozarr-toolkit>=0.1.2`, `async-geotiff>=0.5.1`,
  `obstore>=0.11.0`, `zarr>=3.1.3`), run via `uv run`, isolated from the workshop
  env. Reads the Sentinel-2 COG via `async-geotiff` (no full download), crops
  around the POI, writes a v3 store: **1024×1024 chunks**, blosc/zstd codec
  pipeline, `dimension_names`, multiscale child arrays. Attaches geo metadata via
  `geozarr-toolkit`: **proj + spatial + multiscales conventions** (NOT CF
  grid_mapping). No sharding in the main store (keeps by-hand reads simple).
  Verify chunk sizes < GitHub's ~100 MB/file limit; round-trip with xarray.
- Publish to the **`data` orphan branch** via `worktree.py data` +
  `build_geozarr.py --out ./data/<store>.zarr`, then review + commit + push.
  Served at `raw.githubusercontent.com/<owner>/<repo>/data/<store>.zarr/...`
  (raw honors HTTP Range → 206; verified).
- STAC item using modern **proj + raster** extensions, asset href → the
  `data`-branch raw URL. Reference guide:
  https://developmentseed.org/geozarr-examples/examples/cog-to-zarr/

### Phase 4 — Rewrite nb02 (Reading Zarr the Hard Way, v3)
Re-point at the self-hosted v3 store; teach v3 structure:
- unified `zarr.json` (vs `.zgroup`/`.zarray`/`.zattrs`/`.zmetadata`)
- `c/0/0` chunk keys (vs `0.0`); `codecs` pipeline (vs `compressor`+`filters`);
  `dimension_names` (vs `_ARRAY_DIMENSIONS`)
- **Headline:** read the CRS from the store's proj/spatial convention metadata —
  rewrite the outdated cell-44 lament ("zarr has no geo extension") into "the
  conventions exist now, here's how to read them"; show STAC proj as the
  catalog-level counterpart.
- Keep the by-hand decompress → `np.frombuffer` → reshape → locate-cell flow with
  `griffine` on the projected UTM grid (like nb01). Optional: sharding stretch.
- Source edit lands in `src/02_completed.py`.

### Phase 5 — Rewrite nb03 (Kerchunk → v3 + VirtualiZarr coda)
- Keep the hand-built reference exercise, but emit **v3-shaped** metadata
  (`zarr.json`, `codecs`, `dimension_names`, `c/` keys) matching nb02.
- Add a coda re-opening the same refs via **VirtualiZarr**, and writing to
  **Icechunk** as the modern preferred store. Refresh the `LoggingClientSession`
  byte-range demo. Source edit in `src/03_completed.py`.

### Phase 6 — Finalize workshop branch + docs
- Do the deferred `workshop` pyproject trim + participant README refresh (incl.
  2026 presentation-history rows).
- Publish `workshop` (via the stage flow) and `data` branches.
- Set `workshop` as the GitHub **default branch** so attendees land on it.

---

## Verified facts / gotchas (so you don't re-investigate)

- EOPF Sentinel & NASA POWER public zarr are **still v2** (checked their stores
  directly, 2026-07); neither embeds CRS. Hence self-hosting a v3 store.
- `raw.githubusercontent.com` **does** honor `Range` requests (`Accept-Ranges:
  bytes`, returns `206`) — so byte-range reads from the `data` branch work with
  zero extra infra. 100 MB/file limit is fine (compressed 1024² chunks ~1–1.5 MB).
- `geozarr-toolkit` (0.1.2), `async-geotiff` (0.5.1), `obstore` (0.11.0) exist on
  PyPI. `geozarr-toolkit` is young — validate its API against source in Phase 3.
- Jupytext round-trip preserves the scrubber's inline markers
  (`#| scrub-note:`, `<!-- scrub-omit -->`); scrubber output is deterministic.
- `ipynb-scrubber scrub-project` has no output-dir override (only
  `--config-file`); `generate_notebooks.py` rebases paths via a temp config.
