# Workshop 2026 Update — Handoff / Working Plan

Status doc for updating the *Exploring Cloud-Native Geospatial Formats* workshop
(3 notebooks: `01` COG, `02` zarr, `03` kerchunk) for 2026 conferences. Written
as a handoff so the work can resume on another machine.

**Last updated:** 2026-07-06 (Phases 3, 4 AND 5 COMPLETE — store live on the
`data` branch; nb02 and nb03 fully rewritten and executing end to end; all
three notebooks done. Next: Phase 6 workshop-branch finalization, and the
Deferred items below are now unblocked)
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

### ✅ Phase 3 — Build & publish the v3 GeoZarr store (DONE: built + live on `data`)
Build our own Zarr **v3** GeoZarr store because no public geospatial v3 store
exists yet (verified: PC Daymet, EOPF Sentinel, NASA POWER are all still v2, and
none embed CRS in the store). Build from the SAME Sentinel-2 scene as nb01/nb03
for continuity (EPSG:32610).

#### ✅ Build script (done; COMMITTED 2026-07-06 as a single squashed commit — see `git log`)
- Built `scripts/build_geozarr.py` — standalone PEP 723 inline-script
  (`# /// script` with `geozarr-toolkit>=0.1.2`, `async-geotiff>=0.5.1`,
  `obstore>=0.11.0`, `zarr>=3.1.3`), run via `uv run scripts/build_geozarr.py
  [--out PATH] [--overwrite]`; deps stay out of the workshop env. Default
  `--out` is scene-scoped: `./S2B_T10TFR_20231223.zarr`.
- **Sparse multi-band scene store, modeled from the scene's STAC item**
  (supersedes the single-band B04 store, which superseded the POI-crop
  design): the store models the ENTIRE scene — every single-band raster asset
  in the Earth Search item (17 bands: the spectral bands plus scl/aot/wvp and
  the cloud/snow masks; multi-band visual/preview, thumbnail, and metadata
  docs skipped) — but materializes chunk DATA only for red (the B04 COG nb01
  and nb03 use, still read in full via `async-geotiff` + obstore range
  reads). The script fetches the item from Earth Search at build time (stdlib
  urllib; collection + item id derived from the COG URL) and takes ALL
  other-band metadata from it — per-asset `proj:shape`/`proj:transform`,
  `raster:bands` (data_type/nodata/scale/offset), `eo:bands` (common_name) —
  the other bands' COGs are never opened. Rationale: a fuller, more realistic
  GeoZarr structure for nb02 to explore, and the sparse bands are a
  deliberate teaching beat — zarr metadata cannot tell you which chunks exist
  (missing chunk = reads as fill_value, silently, no error, no manifest),
  the chunk-level version of "zarr doesn't solve discovery", setting up
  nb03's kerchunk/Icechunk manifests.
- **Structure:** root group → one child group per band → multiscale arrays
  `0..N`. Band groups named by `eo` common_name (B04 → `red`, B02 → `blue`);
  assets with no common_name (scl/aot/wvp/cloud/snow) or an ambiguous one
  (rededge1/2/3 all share `rededge`) use their asset key. Bands sit on their
  native grids (10 m: 10980², 20 m: 5490², 60 m: 1830² — per the item), all
  sharing the exact full-scene bbox. proj:/spatial:/multiscales convention
  attrs live on each BAND group and `validate_group` runs per band group (it
  only checks the attrs of the group it is handed — no recursion into
  children); the root group carries NO attrs at all (a v3 root `zarr.json`
  doesn't even list its children — nb02's first taste of the discovery gap).
- **Pyramids:** red's is the COG's own overview IFDs, read via
  `GeoTIFF.overviews` and copied pixel-for-pixel — base 10980² @ 10 m
  (1024 px tiles) + 4 overviews: 5490² @ 20 m, 2745² @ 40 m, 1373² @
  ~79.97 m, 687² @ ~159.83 m. The metadata-only bands' level structures are
  SYNTHESIZED with the same deterministic rule the real pyramid follows —
  GDAL-style ceil-halving of dims until a level fits within one 1024² chunk,
  pixel sizes rescaled to preserve the exact full-scene extent — and the
  build asserts the rule reproduces red's ACTUAL pyramid (shapes exactly,
  transforms to 1e-9) before trusting it for anyone else. Those pyramids are
  the store's own design, not read from the other COGs: 20 m bands get 4
  levels (5490→2745→1373→687), 60 m bands 2 (1830→915).
  `multiscales.resampling_method` is `average` for the continuous bands (for
  red that's the *producer's* resampling — Element 84's standard S2 COG
  pipeline) and `nearest` for the uint8 class/mask bands (our claim;
  averaging class codes would be meaningless).
- Store: v3, **uniform 1024×1024 chunks on every level of every band** = the
  red COG's full-res tile size (square tiles asserted); levels smaller than
  one chunk get their chunk clamped to the array shape. Codecs per band:
  bands with a declared scale/offset in `raster:bands` (reflectance bands
  scale 1e-4/offset −0.1; aot/wvp scale 1e-3/offset 0) get
  `numcodecs.fixedscaleoffset`→`numcodecs.delta`→`bytes`→`zstd` (level 13,
  plain zstd NOT blosc), `dimension_names=['y','x']`, no sharding — same
  rationale as before: nb01 decodes a COG tile by hand (inflate, reverse TIFF
  predictor 2, apply DN→reflectance from the TIFF tags) and the store
  declares that SAME recipe as explicit v3 codec metadata. Logical dtype
  float32; the scale-offset codec encodes to the source uint16 DNs
  **bit-exactly** (asserted per level for red at build time), then delta,
  then zstd; fill_value = the physical value of the band's nodata DN (−0.1
  reflectance; 0.0 for aot/wvp), so missing chunks and nodata pixels read
  identically. Unscaled uint8 bands (scl classification, cloud/snow masks)
  have no physical transform to declare, so no scaling codec: logical uint8,
  `delta`→`bytes`→`zstd`, fill = nodata code 0. No CF
  `scale_factor`/`add_offset` attrs anywhere — scaling lives in the codec
  chain, and CF attrs on top would make xarray apply it twice. The build also
  cross-checks the item's scale/offset/nodata for red against the COG's own
  TIFF tags (the one band where both are visible — they agree).
- **Ragged edges:** 10980 % 1024 = 740, so the 10 m level-0/1/2 chunk grids
  have partial edge chunks. Zarr v3 stores those as FULL-size chunk buffers
  padded with fill_value — verified by hand: edge chunk `red/0/c/10/10`
  decodes to a full 1024² buffer whose out-of-bounds region is all DN 0 /
  reflectance −0.1.
- Stats: 17 band groups (1 materialized + 16 metadata-only), red = 5 levels
  (base + 4 COG overviews), **171 chunk files — ALL under `red/`
  (121/36/9/4/1 per level) — 201.5 MB total, largest chunk 1.57 MB**; 86
  `zarr.json` files ≈ 186 kB of metadata. Every file far under the GitHub
  100 MB/file limit. Build ≈ 1¾ min (downloads the full ~240 MB red scene via
  range reads; the STAC item fetch is one small GET).
- `geozarr-toolkit` 0.1.2 API worked as advertised — no hand-written fallback
  needed: `create_geozarr_attrs()` (spatial: + proj: attrs + zarr_conventions),
  `create_multiscales_layout()`, `create_zarr_conventions(...)` with the
  `*ConventionMetadata` classes, `validate_group()` (run by the script after
  writing, once per band group). Gotchas: `create_multiscales_layout` returns
  `{'multiscales': ...}` to merge into group attrs, and its `zarr_conventions`
  must be set separately; `proj:code` validation resolves the CRS via pyproj
  (pulled in by async-geotiff anyway); `validate_group` does NOT recurse into
  child groups/arrays — it validates only the attrs of the group it is given,
  hence the per-band-group gate.
- Verified against the built store: raw `zarr.json`s (v3, codecs chain in
  order with the right configs per band — scaled float32 vs plain uint8 —
  dims, chunk grid, proj/spatial/multiscales attrs w/ EPSG:32610 on every
  band group and array; per-level transforms at native 10/20/60 m resolutions
  and bbox [600000, 4990200, 709800, 5100000] identical on every level of
  every band, no leftover CF scaling attrs; empty root attrs); v3 `c/row/col`
  chunk keys on disk, plain files only (no consolidated metadata), chunk
  files ONLY under `red/` — every other band is arrays + attrs with zero
  chunks; **sparse reads behave as designed in the workshop env:** zarr opens
  `green/0` fine and returns fill (−0.1) everywhere with no error, `scl/0`
  reads back uint8 fill 0 through its delta-only chain — nothing in the
  metadata distinguishes a sparse band from a full one; xarray round-trip
  (per-level open works via `drop_variables` on the sibling levels, values
  are reflectance applied exactly once, full-scene red mean ≈ 0.0505); full
  by-hand chunk decode (raw file starts with the zstd magic `28 b5 2f fd`;
  generic zstd decompress → `<u2` → wrapping cumsum → reshape →
  scale/offset) matches the zarr read exactly; red DNs round-trip bit-exactly
  vs fresh COG reads of the base image and overview level 3 (POI DN 3736 →
  reflectance 0.2736 at level-0 full-image pixel (7471, 211) — same pixel
  coords as nb01 on the COG — chunk `red/0/c/7/0` in-chunk (303, 211)).
- Codec import gotchas: the v3 wrappers are re-exported at `zarr.codecs`
  (`Delta`, `FixedScaleOffset` — same classes as `zarr.codecs.numcodecs` /
  `numcodecs.zarr3`), serialized as `numcodecs.delta` /
  `numcodecs.fixedscaleoffset`. zarr ≥ 3.2 also ships a native `scale_offset`
  codec (zarr-extensions spec) but it is dtype-preserving — no `astype`, so it
  can't encode float reflectance to uint16 DNs without a second `cast_value`
  codec whose `cast-value-rs` backend every reader would need; hence
  FixedScaleOffset.
- Rebuild the store anywhere with `uv run scripts/build_geozarr.py --out
  <path>`.

#### ✅ Publish (done 2026-07-06)
- Published to the **`data` orphan branch** (store at the branch root). Live
  base URL:
  `https://raw.githubusercontent.com/jkeifer/cng-raster-formats/data/S2B_T10TFR_20231223.zarr`
- The publish is JUST the store — the previously planned STAC item catalog
  record was dropped. nb02 starts from the known store URL, and that's the
  teaching point: zarr doesn't solve data discovery — you still need an
  external index of what stores exist and what's in them. (The STAC item is
  still used at BUILD time as the metadata source for the sparse bands; it
  just isn't a published deliverable.)
- **Verified live over plain HTTP (2026-07-06):**
  - `GET zarr.json` and `red/0/zarr.json` → 200; contents identical to the
    local build.
  - `Range: bytes=0-3` on `red/0/c/7/0` → **206 Partial Content**, body is the
    zstd magic `28 b5 2f fd`, `Content-Range: bytes 0-3/1548961`.
  - Full by-hand decode from the live URL (fetch `red/0/c/7/0` → numcodecs
    zstd decode → `frombuffer('<u2')` → wrapping cumsum over the flat buffer →
    reshape 1024² → scale/offset): in-chunk (303, 211) = DN 3736 →
    reflectance 0.2736 — matches nb01's read of the same POI pixel from the
    COG.
  - Metadata-only band chunk `green/0/c/0/0` → **404 Not Found** (plain-text
    body `404: Not Found`). This is the sparse-store beat over HTTP: chunk
    absence = 404, which zarr treats as fill_value — silently, no error, and
    nothing in the metadata distinguishes it from a transient miss. nb02
    teaches this.
  - Headers of note: `Accept-Ranges: bytes` on every response; `Content-Type:
    text/plain; charset=utf-8` for `zarr.json` files vs
    `application/octet-stream` for chunk files; `Cache-Control: max-age=300`
    + ETag, served via Fastly (`X-Cache` header) — the 5-minute CDN cache
    should help absorb workshop-room bursts.
- **Risk — raw.githubusercontent.com at workshop scale:** ~20–30 participants,
  typically NAT'd behind one or a few conference-room IPs, all issuing bursts of
  unauthenticated range requests. Probably fine via the CDN, but have a
  fallback: a jsDelivr mirror of the `data` branch (per-file, so unaffected by
  total store size), or "download it locally" — ~201 MB for the whole-scene
  store (still viable on conference Wi-Fi, but heavier than the old 30 MB crop;
  revisit before the workshop if that's a concern).

### ✅ Phase 4 — Rewrite nb02 (Reading Zarr the Hard Way, v3) (DONE 2026-07-06)
`src/02_reading-zarr-the-hard-way.py` fully rewritten against the live store
(the old Planetary Computer Daymet / zarr v2 notebook is gone). What it covers:
- **Starts from the known store URL, no STAC search** — with the discovery
  teaching point up front (zarr solves layout/access, not discovery), and the
  gap demonstrated live at BOTH levels: the root `zarr.json` declares no
  children (and guessed keys — `B04` vs `red` — only answer yes/404), and the
  sparse bands have no chunk manifest. Both halves explicitly set up nb03's
  kerchunk/Icechunk manifests as "the missing inventory".
- **v3 structure hands-on over plain HTTP** (stdlib urllib, matching nb01):
  unified `zarr.json` docs, `c/row/col` chunk keys, `codecs` pipeline,
  `dimension_names`, plus a v2→v3 "decoder ring" table; multi-band group
  hierarchy with the 17-band `BANDS` list and native 10/20/60 m grids.
- **Headline beat:** CRS + geotransform read from the `proj:`/`spatial:`
  convention attrs on the band group — the old "zarr has no geo extension"
  lament rewritten as "the conventions exist now", with the explicit contrast
  to nb01's geo-key/pixel-scale/tie-point tag slog.
- **Declared vs implied recipe:** codec-by-codec table mapping the `codecs`
  chain to where the COG hid the same fact (fixedscaleoffset↔GDAL_METADATA,
  delta↔predictor 2, bytes↔byte-order mark, zstd↔compression tag); the
  canonical-array-semantics beat (float32 reflectance vs uint16 DNs); scl's
  plain uint8 delta→zstd chain as the per-array-recipe contrast.
- **Multiscales used for something real:** level 4 is a single clamped 687²
  chunk → one-GET whole-scene quicklook, decoded stepwise (zstd magic callback
  to nb01's magic numbers, flattened-vs-per-row delta note, wrapping cumsum),
  then displayed on the folium map from `spatial:bbox`.
- **POI flow identical to nb01:** griffine locate-cell on the UTM grid →
  (7471, 211) → chunk `red/0/c/7/0`, in-chunk (303, 211) → DN 3736 →
  reflectance 0.2736 (bit-exact vs the COG, as a Q/A beat), with the
  key/path-vs-byte-offset addressing beat (the COG's tile index was an
  inventory; zarr's computed addressing needs none and provides none) and the
  full-chunk edge-padding note on `read_chunk`'s reshape; chunk/tile 1:1
  correspondence at level 0 only (COG overviews are 512-px tiles) as a Q/A.
- **Sparse beat live:** `green/0/zarr.json` metadata identical to red's, chunk
  GET → 404, then `zarr.open_array` reads the same window as silent fill
  (−0.1).
- **"Open it the easy way" payoff:** `zarr.open_array` one-liner reproduces
  0.2736; then the flip side — `zarr.open_group(...).keys()` returns [] and
  `xarray.open_zarr` yields zero data variables over plain HTTP (no listing,
  no child metadata) — the discovery gap catching even the real tooling.
- **Scrubber coverage:** 16 `#| scrub-note:` cells (nb01 has 13) + 2
  `<!-- scrub-omit -->` answer cells; `notes/02_*.md` now generates with real
  content (it was empty before). Verified no answer leaks in the exercise
  notebook.
- **Verification:** `jupytext --sync` round-trip stable (byte-identical);
  `generate_notebooks.py` produces completed + exercise + notes;
  `uv run jupyter execute` of the completed notebook passes end to end against
  the LIVE store in ~10 s (all key outputs checked: cell/chunk coords, 0.2736,
  zstd magic, B04/green 404s, green fill window, empty group listing);
  `uv run prek run --all-files` passes.

### ✅ Phase 5 — Rewrite nb03 (Kerchunk → v3 + VirtualiZarr/Icechunk coda) (DONE 2026-07-06)
`src/03_free-range-artisanal-grass-fed-kerchunk.py` fully rewritten. The
hand-built reference exercise is kept but emits **v3-shaped** metadata
(`zarr.json` docs, `codecs` pipeline, `dimension_names`, `c/row/col` chunk
keys), framed as the payoff of nb02's discovery thread: the COG's tile offset
tags are an *internal* manifest, kerchunk writes that inventory down
externally. What it covers / what was learned:
- **The old notebook's refs decoded WRONG pixel values** (found while
  modernizing): it declared `numcodecs.delta` for TIFF predictor 2, but
  numcodecs' delta is a *flattened* cumsum while the predictor restarts per
  row. Verified empirically against tile (7, 0): per-row decode gives DN 3736
  (nb01's value), flat decode gives 8869 — every row after row 0 of every
  tile was silently garbage, unnoticed because the old nb never checked a
  value. There is NO stock zarr/numcodecs codec for per-row differencing, so
  the rewrite demonstrates the mismatch on a toy array (new teaching beat,
  pays off nb02's flattened-vs-per-row footnote), then registers a ~25-line
  custom v3 `ArrayArrayCodec` (`tiff.predictor2`, cumsum along axis -1) with
  a loud honesty note: the refs only decode where that codec is registered —
  the fundamental cost of virtualizing bytes encoded without standard codecs,
  and exactly why the Phase 3 store re-encoded instead. Rest of the declared
  chain: `numcodecs.fixedscaleoffset` copied verbatim from the store's
  `red/0` doc, `bytes` little-endian, `numcodecs.zlib` (canonical dtype
  float32 reflectance, fill −0.1, matching nb02's contract).
- **Opening the refs:** fsspec `reference://` + `zarr.storage.FsspecStore`
  (both filesystem layers need `asynchronous=True`; `skip_instance_cache=True`
  retires the old "restart the kernel after editing the json" gripe). Payoffs
  staged against nb02: `zarr.open_group(...).keys()` now returns `['red']`
  (the manifest IS the inventory — and zero HTTP requests for any metadata),
  `xarray.open_zarr` actually finds the data variable, and the POI pixel
  (7471, 211) reads 0.2736 with the logged request being exactly
  `bytes=161151032-162782871` — the tag 324/325 values for tile (7, 0).
- **Byte-range logger refreshed:** aiohttp now deprecates subclassing
  `ClientSession`, so the `LoggingClientSession` device became `TraceConfig`
  request-start hooks injected via the HTTP filesystem's `get_client` kwarg.
  Multi-chunk reads updated honestly: zarr v3 fetches one exact range per
  chunk key, concurrently — no range coalescing like the old fsspec/kerchunk
  engine did (adjacent-tiles and 14-MB-apart-tiles demos both show two exact
  per-chunk ranges).
- **Coda (APIs introspected against installed source, both post-training):**
  VirtualiZarr 2.7's `KerchunkJSONParser` is **v2-refs-only** (expects
  `.zarray` + `_ARRAY_DIMENSIONS`), so the notebook builds the model directly
  from the same refs — `ChunkManifest(entries, shape, separator='/')` +
  `ManifestArray(ArrayV3Metadata.from_dict(<our doc>), ...)` (accepted the
  hand-built doc unchanged, custom codec and all) + `ManifestGroup` +
  `ManifestStore(group, registry=ObjectStoreRegistry({prefix: obstore
  HTTPStore}))` → `to_virtual_dataset()`, with the 482 MB-apparent vs
  few-kB-actual (`vds.vz.nbytes`) beat. Icechunk 2.1:
  `RepositoryConfig.set_virtual_chunk_container(VirtualChunkContainer(prefix,
  icechunk.http_store()))`, `Repository.create(in_memory_storage(), config,
  authorize_virtual_chunk_access={prefix: icechunk.credentials.HttpAccess})`
  (passing `None` is deprecated), `vds.vz.to_icechunk(session.store)` +
  commit, read-back via `readonly_session` + xarray → 0.2736 again, plus
  `all_virtual_chunk_locations()` and `ancestry()` for the
  versioned/transactional beats. Honest caveats in-notebook: icechunk fetches
  virtual chunks with its own client (invisible to the aiohttp logger), the
  custom-codec requirement follows the repo, and virtual refs rot if the
  source COG's bytes ever change.
- **Scrubber coverage:** 16 `#| scrub-note:` cells (nb01 13, nb02 16; old
  nb03 had zero) + 3 `<!-- scrub-omit -->` answer cells; `notes/03_*.md` now
  generates with real content. Exercise notebook verified leak-free (no
  0.2736/3736/tile-index-77/toy-decode answers in unscrubbed cells).
- **Verification:** `jupytext --sync` round-trip stable (all three sources
  unchanged); `generate_notebooks.py` produces completed + exercise + notes;
  `uv run jupyter execute` of the completed notebook passes end to end
  against the live COG in ~8 s, with key outputs programmatically checked
  (toy delta mismatch, 121 chunk refs, group listing, exact byte ranges, POI
  0.2736 via both fsspec and icechunk paths, ancestry); `uv run prek run
  --all-files` passes. Also gitignored the notebook's `kerchunk.json` runtime
  artifact.

### ⏳ Deferred (was gated on Phases 4/5 — that gate is now OPEN; do with Phase 6)
- Trim the `workshop` branch's `pyproject.toml` to runtime-only deps; regen its
  `uv.lock`. (Currently it still has the pre-Phase-2 pyproject with dev tooling.)
- Fix the stale participant README on the `workshop` branch (still has the
  removed pip section, old presentation dates).
- First real `workshop` branch publish commit (`data` was published in
  Phase 3).

---

## Remaining phases

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
  0.17–1.57 MB in the built sparse multi-band store; total ~201 MB across 171
  chunk files, all under `red/`).
- `geozarr-toolkit` (0.1.2), `async-geotiff` (0.5.1), `obstore` (0.11.0) exist on
  PyPI. `geozarr-toolkit` is young — API validated against installed source in
  Phase 3; the helpers (`create_geozarr_attrs`, `create_multiscales_layout`,
  `validate_group`) work as documented (see Phase 3 notes). `validate_group`
  checks only the given group's own attrs — no recursion — so nested band
  groups are validated one at a time.
- The scene's Earth Search STAC item carries everything the sparse bands need
  (verified 2026-07): per-asset `proj:shape`/`proj:transform`, `raster:bands`
  (data_type/nodata/scale/offset), `eo:bands` common_name — no COG-header
  fallback needed. Quirks: rededge1/2/3 share common_name `rededge` (naming
  falls back to asset key), and the item also has single-band `cloud`/`snow`
  uint8 masks (included, same treatment as scl).
- Jupytext round-trip preserves the scrubber's inline markers
  (`#| scrub-note:`, `<!-- scrub-omit -->`); scrubber output is deterministic.
- `ipynb-scrubber scrub-project` has no output-dir override (only
  `--config-file`); `generate_notebooks.py` rebases paths via a temp config.
