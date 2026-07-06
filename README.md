# cng-raster-formats — Contributor Guide

This is the **source/development branch** for the *Exploring Cloud-Native
Geospatial Formats* workshop. If you are here to **take the workshop**, you want
the [`workshop` branch](https://github.com/jkeifer/cng-raster-formats/tree/workshop)
instead — it contains the ready-to-run notebooks and setup instructions.

This document is for people editing the workshop content.

## Repository model

The workshop is authored here on `main` and published to two long-lived
branches. Keeping generated artifacts off `main` keeps its history clean and
diffable.

| Branch     | Contents                                                        | Audience     |
| ---------- | --------------------------------------------------------------- | ------------ |
| `main`     | Source: `src/*.py`, `scripts/`, config, this README             | Contributors |
| `workshop` | Runnable notebooks + participant README, LICENSE, notes, run env | Participants  |
| `data`     | Orphan branch holding the self-hosted GeoZarr store              | (data host)  |

Notebooks are **never committed on `main`** — they are generated on demand into a
worktree of the target branch and committed there.

## Notebook sources

The source of truth for each notebook is a
[Jupytext](https://jupytext.readthedocs.io/) `py:percent` file under `src/`:

* `src/NN_<name>.py` — the full, working notebook, as readable Python with
  `# %%` cell markers (clean diffs, no JSON noise, no cell outputs). Each file
  is named for its exercise (e.g. `src/01_reading-cogs-the-hard-way.py`).

From each `src/` file we generate:

* `notebooks/completed/NN_<name>.ipynb` — the completed notebook (Jupytext
  render of the `.py`). Keeping the completed renders under
  `notebooks/completed/` avoids colliding with the exercise notebooks and, on
  the `workshop` branch, gives a tidy "answers live here" separation.
* `notebooks/NN_<name>.ipynb` — the **exercise** notebook handed to attendees,
  produced by
  [`ipynb-scrubber`](https://pypi.org/project/ipynb-scrubber/), which clears
  designated cells and omits answer cells.
* `notes/NN_<name>.md` — notes extracted from cells tagged for note-taking.

Both generation steps are configured by `[tool.ipynb-scrubber]` in
`pyproject.toml` (input/output paths, tags) and `jupytext.toml` (the `src/` ↔
`notebooks/completed/` pairing).

### Editing

Edit `src/NN_<name>.py` directly, or edit a completed notebook in Jupyter and
sync it back to the `.py`:

```commandline
# after editing a notebook in Jupyter, sync it back to src/:
uv run jupytext --sync src/*.py
```

## Building & publishing

Two small, composable scripts handle staging content onto the dist branches. The
generic `worktree.py` prepares (or reuses) a worktree for a branch; you then
generate content into it, review, and commit yourself. Nothing is committed or
pushed automatically.

### Publishing the workshop notebooks

```commandline
# 1. Check out the workshop branch as a worktree at ./workshop
uv run scripts/worktree.py workshop

# 2. Generate the notebooks + notes into that worktree
uv run scripts/generate_notebooks.py --output-dir ./workshop

# 3. Review, then commit/push from the worktree
cd workshop
git add -A && git commit -m "Update notebooks" && git push
```

`generate_notebooks.py` defaults `--output-dir` to the repo root, so a bare
`uv run scripts/generate_notebooks.py` regenerates the notebooks in place (handy
for a quick local check). The generated notebooks are gitignored on `main`.

The `workshop` branch maintains its **own** participant-facing README, LICENSE,
notes, and runtime environment (a trimmed `pyproject.toml` with runtime deps
only, plus its `uv.lock`, Dockerfile, `compose.yml`, and `.devcontainer`). Those
are edited on the `workshop` branch, not copied from `main`; the stage script
only writes the notebooks and notes.

### The `data` branch (GeoZarr store)

The `data` branch is an orphan branch that hosts a self-built Zarr v3 GeoZarr
store, served to the notebooks over HTTP byte-range requests via
`raw.githubusercontent.com`. The store is built from the same Sentinel-2 COG
the notebooks use, by `scripts/build_geozarr.py` — a standalone PEP 723 script
(its deps are declared inline and resolved by `uv run`; they are deliberately
not part of the project environment).

Publishing follows the same worktree flow as the `workshop` branch:

```commandline
# 1. Check out the data branch as a worktree at ./data
uv run scripts/worktree.py data

# 2. Build the store into the worktree (~200 MB; downloads the full scene)
uv run scripts/build_geozarr.py --out ./data/S2B_T10TFR_20231223_B04.zarr

# 3. Review, then commit/push from the worktree
cd data
git add -A && git commit -m "Rebuild GeoZarr store" && git push
```

The store is then served per-file at
`https://raw.githubusercontent.com/<owner>/<repo>/data/<store>.zarr/...`,
which honors HTTP Range requests, so the notebooks can do byte-range chunk
reads with no extra infrastructure.

## Development environment

```commandline
uv sync
```

installs everything, including the dev tooling (Jupytext, ipynb-scrubber). Run
Jupyter with `uv run jupyter lab`.

After syncing, install the git hooks with `uv run prek install`. The hooks run
ruff lint and format, with the tools coming from the dev dependency group; run
them manually with `uv run prek run --all-files`.

## Checks / CI

CI (`.github/workflows/ci.yml`) runs on pull requests and on pushes to `main`.
It runs the prek hooks, then generates all notebooks from `src/` and executes
each completed notebook end to end (this hits the public data services the
notebooks use, so no credentials are needed). The local equivalents:

```commandline
uv run prek run --all-files
uv run scripts/generate_notebooks.py
uv run jupyter execute notebooks/completed/NN_<name>.ipynb   # for each of 01, 02, 03
```
