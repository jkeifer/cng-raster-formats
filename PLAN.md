# Workshop 2026 Update — Handoff / Working Plan

Status doc for updating the *Exploring Cloud-Native Geospatial Formats* workshop
(3 notebooks: `01` COG, `02` zarr, `03` kerchunk) for 2026 conferences. Written
as a handoff so the work can resume on another machine.

**Last updated:** 2026-07-06 (Phase 3 build half done; build script rewritten
as a whole-scene converter — pyramid from the COG's own overviews)
**Working branch:** `jak/2026` (merges to `main`)

---

## Machine setup

After cloning on a new machine:

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

- **Source of truth:** `src/NN_<name>.py` (Jupytext `py:percent`), named for
  its exercise (e.g. `src/01_reading-cogs-the-hard-way.py`).
- **Generated (never committed on `main`):**
  `notebooks/completed/NN_<name>.ipynb` (Jupytext render),
  `notebooks/NN_<name>.ipynb` (exercise, via ipynb-scrubber),
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
(the `src/` ↔ `notebooks/completed/` pairing).

---

## Progress

### ✅ Phase 1 — nb01 fixes (COMMITTED, pushed: `fc12b51`)
- Fixed bare `except:` in `extract_geo_keys` → `except Exception as e: ... from e`.
- Removed the broken `Tag.pack` stub from the appendix parser.
- Spellcheck pass on markdown (unit16→uint16, many typos).

### ✅ Phase 2 — Tooling, hygiene, delivery model (COMMITTED, pushed: `51e6ee8`)
- **`src/` layout + Jupytext:** `src/*.py` are the source of truth;
  `jupytext.toml` pairs `src/` ↔ `notebooks/completed/`. Verified byte-clean
  round-trip.
- **Rename (post-2.5):** sources renamed for their exercises
  (`src/NN_completed.py` → `src/NN_<name>.py`); completed renders now land in
  `notebooks/completed/`, avoiding filename collisions with the exercise
  notebooks.
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
- **CI:** back IN scope — but as ordinary tests, not a cron canary. See
  Phase 2.5 below.

### ✅ Phase 2.5 — Pre-commit hooks + CI (COMMITTED: `151fa27` hooks, `867e02a` CI; rename `4c1a3cc`)
CI came back in scope after all — as ordinary tests, not a cron canary.
Runnable locally, on PRs, and on pushes to `main`. Both parts done:
- **prek-managed pre-commit hooks** (`.pre-commit-config.yaml`) —
  system-language local hooks running ruff check/format via `uv run`, with prek
  + ruff in the uv dev dependency group. `uv run prek run --all-files` passes.
- **GitHub Actions workflow** (`.github/workflows/ci.yml`) — `lint` job runs
  the same prek hooks; `notebooks` job generates all notebooks from `src/` and
  executes each completed notebook (`uv run jupyter execute ...`), one step per
  notebook, 30-min job timeout, concurrency-cancels superseded runs. Verified
  locally: all three notebooks executed cleanly (01 ~13s, 02 ~82s, 03 ~7s; one
  transient S3 connection reset on a first 01 attempt — the notebooks do real
  network I/O, so occasional flakes are possible).

### ⏳ Deferred (do after Phases 4/5, so deps aren't curated twice)
- Trim the `workshop` branch's `pyproject.toml` to runtime-only deps; regen its
  `uv.lock`. (Currently it still has the pre-Phase-2 pyproject with dev tooling.)
- Fix the stale participant README on the `workshop` branch (still has the
  removed pip section, old presentation dates).
- First real `workshop` / `data` branch publish commits.

---

## Remaining phases

### 🚧 Phase 3 — Build & publish the v3 GeoZarr store  (build half DONE)
Build our own Zarr **v3** GeoZarr store because no public geospatial v3 store
exists yet (verified: PC Daymet, EOPF Sentinel, NASA POWER are all still v2, and
none embed CRS in the store). Build from the SAME Sentinel-2 scene as nb01/nb03
for continuity (EPSG:32610).

#### ✅ Build script (done; COMMITTED 2026-07-06 as a single squashed commit — see `git log`)
- Built `scripts/build_geozarr.py` — standalone PEP 723 inline-script
  (`# /// script` with `geozarr-toolkit>=0.1.2`, `async-geotiff>=0.5.1`,
  `obstore>=0.11.0`, `zarr>=3.1.3`), run via `uv run scripts/build_geozarr.py
  [--out PATH] [--overwrite]`; deps stay out of the workshop env. Default
  `--out` is scene-derived: `./S2B_T10TFR_20231223_B04.zarr`.
- **Pure whole-scene COG→GeoZarr converter** (supersedes the earlier POI-crop
  design — no POI, no cropping, no local resampling): everything about the
  store is driven by the source COG's own metadata/structure, and a full-scene
  store makes nb02's locate-the-POI-pixel math line up exactly with nb01's
  work on the full COG (same grid, same pixel coordinates — locating the POI
  is notebook work, not build-script work). Reads the same B04 COG nb03
  hardcodes via `async-geotiff` + obstore `HTTPStore` (range reads only).
- **Pyramid = the COG's own overview IFDs**, read via `GeoTIFF.overviews`
  (async-geotiff 0.5.x exposes each overview as an `Overview` with full
  `.read()`, `.transform`, `.shape`, tile sizes — no local-downsample fallback
  needed). This COG: base 10980×10980 @ 10 m (1024 px tiles) + 4 overviews —
  5490² @ 20 m, 2745² @ 40 m, 1373² @ ~79.97 m, 687² @ ~159.83 m, all 512 px
  tiles, deflate. Overviews are copied pixel-for-pixel; per-level transforms/
  shapes come from the IFDs. GDAL ceil-halves overview dims, so the coarsest
  two levels are 2× only nominally, and their non-integer pixel sizes preserve
  the exact full-scene extent (every level's bbox is identical).
  `multiscales.resampling_method='average'` is the *producer's* resampling
  (Element 84's standard S2 COG pipeline), not ours.
- Store: v3, **uniform 1024×1024 chunks on every level** = the COG's full-res
  tile size (square tiles asserted). The overview IFDs use 512 px tiles, but
  one uniform chunk size is a simpler story for nb02 and means fewer chunk
  files; each level's chunk grid is declared in its own `zarr.json` anyway.
  The coarsest level (687²) is smaller than one chunk, so its chunk is clamped
  to the array shape. Codec pipeline
  `numcodecs.fixedscaleoffset`→`numcodecs.delta`→`bytes`→`zstd` (level 13,
  plain zstd NOT blosc), `dimension_names=['y','x']`, no sharding. Rationale
  (supersedes the earlier "plain zstd only" pipeline): nb01 decodes a COG tile
  by hand — inflate, reverse TIFF predictor 2, apply the DN→reflectance
  scale/offset from the TIFF tags — and the store declares that SAME recipe as
  explicit v3 codec metadata, so nb02 can say "same operations as the COG, but
  here the store *tells you* the recipe". Logical dtype is float32 reflectance;
  the scale-offset codec (offset −0.1, scale 10000, derived from the COG's
  `scales`/`offsets`) encodes to the COG's uint16 DNs **bit-exactly** (asserted
  per level at build time), then delta differences the DNs, then zstd. No CF
  `scale_factor`/`add_offset` attrs — scaling lives in the codec chain, and CF
  attrs on top would make xarray apply it twice. fill_value −0.1 (float32) =
  the reflectance of the COG's nodata DN 0, so missing chunks and nodata
  pixels read identically.
- **Ragged edges:** 10980 % 1024 = 740, so the level-0/1/2 chunk grids have
  partial edge chunks. Zarr v3 stores those as FULL-size chunk buffers padded
  with fill_value — verified by hand: edge chunk `0/c/10/10` decodes to a full
  1024² buffer whose out-of-bounds region is all DN 0 / reflectance −0.1.
- Stats: 5 levels (base + 4 COG overviews), **171 chunk files, 201.4 MB
  total, largest chunk 1.57 MB** — every file far under the GitHub 100 MB/file
  limit. Build ≈ 1¾ min (downloads the full ~240 MB scene via range reads).
- `geozarr-toolkit` 0.1.2 API worked as advertised — no hand-written fallback
  needed: `create_geozarr_attrs()` (spatial: + proj: attrs + zarr_conventions),
  `create_multiscales_layout()`, `create_zarr_conventions(...)` with the
  `*ConventionMetadata` classes, `validate_group()` (run by the script after
  writing). Gotchas: `create_multiscales_layout` returns `{'multiscales': ...}`
  to merge into group attrs, and its `zarr_conventions` must be set separately;
  `proj:code` validation resolves the CRS via pyproj (pulled in by
  async-geotiff anyway).
- Verified against the built store: raw `zarr.json`s (v3, codecs chain in
  order with the right configs, dims, chunk grid, proj/spatial/multiscales
  attrs w/ EPSG:32610 + per-level transforms/bboxes covering the FULL scene —
  origin (600000, 5100000) UTM 10N, bbox [600000, 4990200, 709800, 5100000] on
  every level, no leftover CF scaling attrs); v3 `c/row/col` chunk keys on
  disk, plain files only (no consolidated metadata); xarray round-trip
  (per-level open works via `drop_variables` on the other levels, values are
  reflectance applied exactly once, full-scene mean ≈ 0.0505; opening ALL
  levels from the root at once conflicts since levels share dim names —
  expected multiscales behavior, and nb02 reads by hand anyway); full by-hand
  chunk decode (raw file starts with the zstd magic `28 b5 2f fd`; generic
  zstd decompress → `<u2` → wrapping cumsum → reshape → scale/offset) matches
  the zarr read exactly for POI, interior, and edge chunks; DNs round-trip
  bit-exactly vs fresh COG reads of the base image AND of overviews 0 and 3
  (POI DN 3736 → reflectance 0.2736 at level-0 full-image pixel (7471, 211) —
  same pixel coords as nb01 on the COG — chunk `0/c/7/0` in-chunk (303, 211)).
- Codec import gotchas: the v3 wrappers are re-exported at `zarr.codecs`
  (`Delta`, `FixedScaleOffset` — same classes as `zarr.codecs.numcodecs` /
  `numcodecs.zarr3`), serialized as `numcodecs.delta` /
  `numcodecs.fixedscaleoffset`. zarr ≥ 3.2 also ships a native `scale_offset`
  codec (zarr-extensions spec) but it is dtype-preserving — no `astype`, so it
  can't encode float reflectance to uint16 DNs without a second `cast_value`
  codec whose `cast-value-rs` backend every reader would need; hence
  FixedScaleOffset.
- Store currently staged outside the repo (not committed); rebuild anywhere
  with `uv run scripts/build_geozarr.py --out <path>`.

#### ⏳ Publish + STAC item (remaining)
- Publish to the **`data` orphan branch** via `worktree.py data` +
  `build_geozarr.py --out ./data/<store>.zarr`, then review + commit + push.
  Served at `raw.githubusercontent.com/<owner>/<repo>/data/<store>.zarr/...`
  (raw honors HTTP Range → 206; verified).
- STAC item using modern **proj + raster** extensions, asset href → the
  `data`-branch raw URL. Reference guide:
  https://developmentseed.org/geozarr-examples/examples/cog-to-zarr/
- **Risk — raw.githubusercontent.com at workshop scale:** ~20–30 participants,
  typically NAT'd behind one or a few conference-room IPs, all issuing bursts of
  unauthenticated range requests. Probably fine via the CDN, but have a
  fallback: a jsDelivr mirror of the `data` branch (per-file, so unaffected by
  total store size), or "download it locally" — now ~201 MB for the whole-scene
  store (still viable on conference Wi-Fi, but heavier than the old 30 MB crop;
  revisit at publish time if that's a concern).

### Phase 4 — Rewrite nb02 (Reading Zarr the Hard Way, v3)
Re-point at the self-hosted v3 store; teach v3 structure:
- unified `zarr.json` (vs `.zgroup`/`.zarray`/`.zattrs`/`.zmetadata`)
- `c/0/0` chunk keys (vs `0.0`); `codecs` pipeline (vs `compressor`+`filters`);
  `dimension_names` (vs `_ARRAY_DIMENSIONS`)
- **Headline:** read the CRS from the store's proj/spatial convention metadata —
  rewrite the outdated cell-44 lament ("zarr has no geo extension") into "the
  conventions exist now, here's how to read them"; show STAC proj as the
  catalog-level counterpart.
- Keep the by-hand decode → locate-cell flow with `griffine` on the projected
  UTM grid (like nb01). The store is the FULL scene on the COG's own grid, so
  the locate-the-POI math gives the SAME pixel coordinates as nb01 on the COG
  (POI → level-0 pixel (7471, 211) → chunk `c/7/0`, in-chunk (303, 211), DN
  3736 → reflectance 0.2736). The full recipe, straight from the `codecs`
  metadata: generic zstd decompress (`numcodecs` has a decoder and is already
  a workshop dep) → `np.frombuffer('<u2')` → undo the delta filter with a
  wrapping cumsum (`np.cumsum(...).astype('<u2')`; NOTE numcodecs delta
  differences the *flattened* chunk — it does NOT reset per row like TIFF
  predictor 2, so it's one cumsum, not one per row) → reshape → apply the
  scale-offset codec's DN→reflectance (`dn / scale + offset`). Same operations
  nb01 did by hand on the COG — but here the store declares them. NOTE for the
  reshape step: a decoded chunk buffer is ALWAYS the full chunk shape from
  `zarr.json` (1024²), even for the ragged edge chunks (10980 isn't a multiple
  of 1024) — zarr v3 pads partial chunks with fill_value (−0.1 / DN 0) beyond
  the array bounds. Optional: sharding stretch.
- Source edit lands in `src/02_reading-zarr-the-hard-way.py`.

### Phase 5 — Rewrite nb03 (Kerchunk → v3 + VirtualiZarr coda)
- Keep the hand-built reference exercise, but emit **v3-shaped** metadata
  (`zarr.json`, `codecs`, `dimension_names`, `c/` keys) matching nb02.
- Add a coda re-opening the same refs via **VirtualiZarr**, and writing to
  **Icechunk** as the modern preferred store. Refresh the `LoggingClientSession`
  byte-range demo. Source edit in
  `src/03_free-range-artisanal-grass-fed-kerchunk.py`.

### Phase 6 — Finalize workshop branch + docs
- Do the deferred `workshop` pyproject trim + participant README refresh (incl.
  2026 presentation-history rows).
- Publish `workshop` (via the stage flow) and `data` branches.
- **End-to-end validation gate before publishing:** fresh clone of the
  `workshop` branch, `uv sync`, execute all three completed notebooks top to
  bottom.
- Set `workshop` as the GitHub **default branch** so attendees land on it.
- After the default-branch switch, new PRs will default-target `workshop`; add
  a line to the contributor README telling contributors to retarget `main`.
- Delete PLAN.md itself once the plan is complete (it graduates into the
  READMEs).

---

## Verified facts / gotchas (so you don't re-investigate)

- EOPF Sentinel & NASA POWER public zarr are **still v2** (checked their stores
  directly, 2026-07); neither embeds CRS. Hence self-hosting a v3 store.
- `raw.githubusercontent.com` **does** honor `Range` requests (`Accept-Ranges:
  bytes`, returns `206`) — so byte-range reads from the `data` branch work with
  zero extra infra. 100 MB/file limit is fine (compressed chunks are
  0.17–1.57 MB in the built whole-scene store; total ~201 MB across 171 chunk
  files).
- `geozarr-toolkit` (0.1.2), `async-geotiff` (0.5.1), `obstore` (0.11.0) exist on
  PyPI. `geozarr-toolkit` is young — API validated against installed source in
  Phase 3; the helpers (`create_geozarr_attrs`, `create_multiscales_layout`,
  `validate_group`) work as documented (see Phase 3 notes).
- Jupytext round-trip preserves the scrubber's inline markers
  (`#| scrub-note:`, `<!-- scrub-omit -->`); scrubber output is deterministic.
- `ipynb-scrubber scrub-project` has no output-dir override (only
  `--config-file`); `generate_notebooks.py` rebases paths via a temp config.
