# cng-raster-formats — Contributor Guide

> [!IMPORTANT]
> This is the **source/development branch** for *Exploring Cloud-Native
> Geospatial Formats: A Hands-on Workshop for Raster Data*. If you are here to
> **run the workshop**, you want the
> [`workshop` branch](https://github.com/jkeifer/cng-raster-formats/tree/workshop)
> instead: it contains the ready-to-run notebooks and setup instructions.

This document is for people editing the workshop content.

## About the workshop

The workshop digs into geospatial raster formats, including COG, Zarr, and
reference files like Kerchunk, using Python to see in detail how raster data is
stored in each format and to understand what cloud-native means for rasters.  A
strong goal is to be as hands-on with these formats as possible by working with
them in Python without any specific geospatial data format libraries, building
up a working understanding of what common higher-level tooling does under the
hood.

## Repository model

The workshop is authored here on `main` and published to two long-lived
branches. Keeping generated artifacts off `main` keeps its history clean and
diffable.

| Branch     | Contents                                                         | Audience     |
| ---------- | ---------------------------------------------------------------- | ------------ |
| `main`     | Source: `src/*.py`, `static/`, `scripts/`, config, this README   | Contributors |
| `workshop` | Runnable notebooks + participant README, LICENSE, notes, run env | Participants |
| `data`     | Orphan branch holding the self-hosted GeoZarr store              | n/a          |

Notebooks are **never committed on `main`**: tooling generates themon demand
into the `workshop` branch and committed there.

The `workshop` branch is a **pure build artifact**: every file on it is
reproducible from `main`, and nothing on it is edited by hand. Its participant
README and `.gitignore` are authored on `main` under `static/`; its
`Dockerfile`, `compose.yml`, `.devcontainer/` and `LICENSE` are copied from
`main` verbatim; and its `pyproject.toml` and `uv.lock` are derived from this
branch's own. Editing a file directly on `workshop` means losing that edit on
the next build.

## Notebook sources

The source of truth for each notebook is a
[Jupytext](https://jupytext.readthedocs.io/) `py:percent` file under `src/`:

* `src/NN_<name>.py`: the full, working notebook, as readable Python with
  `# %%` cell markers (clean diffs, no JSON noise, no cell outputs). Each file
  is named for its exercise (e.g. `src/01_reading-cogs-the-hard-way.py`).

From each `src/` file we generate:

* `notebooks/completed/NN_<name>.ipynb`: the completed notebook (Jupytext
  render of the `.py`). Keeping the completed renders under
  `notebooks/completed/` avoids colliding with the exercise notebooks and, on
  the `workshop` branch, gives a tidy "answers live here" separation.
* `notebooks/NN_<name>.ipynb`: the **exercise** notebook handed to attendees,
  produced by [`ipynb-scrubber`](https://pypi.org/project/ipynb-scrubber/),
  which clears designated cells and omits answer cells.
* `notes/NN_<name>.md`:  notes extracted from cells tagged as such, used to
  provide a cheat sheet for participants, in case they fall behind or mistype
  something.

Both generation steps are configured in `pyproject.toml`:
`[tool.ipynb-scrubber]` (input/output paths, markers) and `[tool.jupytext]`
(the `src/` ↔ `notebooks/completed/` pairing). The build around them, i.e.,
which branch is published and what else ships on it, is
`[tool.workshopify]`.

### Editing

Edit `src/NN_<name>.py` directly, or edit a completed notebook in Jupyter and
sync it back to the `.py`:

```commandline
# after editing a notebook in Jupyter, sync it back to src/:
uv run jupytext --sync src/*.py
```

## Building & publishing

[`workshopify`](https://pypi.org/project/workshopify/) drives the build. It
reads the `[tool.workshopify]` tables in `pyproject.toml`, assembles the whole
published tree, and writes it into a worktree of the target branch. It commits
and pushes nothing. Review the worktree and land it yourself.

### Publishing the workshop notebooks

```commandline
# 1. Assemble the workshop branch into a worktree at ./workshop
#    (prepares the worktree itself if it isn't there yet)
uv run workshopify build

# 2. Review, then commit/push from the worktree
git -C ./workshop status
git -C ./workshop add -A
PREK_ALLOW_NO_CONFIG=1 git -C ./workshop commit -m "Update notebooks"
git -C ./workshop push
```

`PREK_ALLOW_NO_CONFIG=1` is required on the commit: git hooks are shared across
all worktrees, and the `workshop` branch intentionally carries no pre-commit
config.

`build` refuses to run against a worktree with uncommitted changes, since those
may be an unpublished build or notebook edits made in Jupyter that are not yet
synced back to `src/`. Commit them, or pass `--overwrite-dirty`.

Afterwards it reports any **tracked file on the branch that this build did not
write**: a renamed exercise still shipping its old notebook shows up as
nothing at all in `git status`, because it is unchanged. Pass `--clean` to
remove them.

To regenerate the notebooks in place for a quick local check, without touching
the worktree:

```commandline
uv run workshopify generate
```

The generated `notebooks/` and `notes/` are gitignored on `main`.

### What gets published, and from where

| Published file | Comes from |
| --- | --- |
| `notebooks/`, `notes/` | generated from `src/*.py` |
| `README.md`, `.gitignore` | `static/` on `main` |
| `Dockerfile`, `compose.yml`, `.devcontainer/`, `LICENSE` | copied from `main` verbatim (`[tool.workshopify.build] include`) |
| `pyproject.toml`, `uv.lock` | derived from `main`'s, keeping `[project]` and `[tool.uv]` |

A published path has exactly one source: listing a file in both `include` and
`static/` is a build error, not a race. Anything participants should see that
differs from `main`'s version goes in `static/`; anything identical goes in
`include`.

### The `data` branch (GeoZarr store)

The `data` branch is an orphan branch that hosts a self-built Zarr v3 GeoZarr
store, served to the notebooks over HTTP byte-range requests via
`raw.githubusercontent.com`. The store models the same Sentinel-2 scene the
notebooks use (all bands from its STAC item; only the red band's chunk data is
materialized), built by `scripts/build_geozarr.py` — a standalone PEP 723 script
(its deps are declared inline and resolved by `uv run`; they are deliberately
not part of the project environment).

Publishing uses the same worktree helper, but builds its content itself — the
store is not something `workshopify build` knows how to assemble:

```commandline
# 1. Check out the data branch as a worktree at ./data
uv run workshopify worktree data --orphan

# 2. Build the store into the worktree (~200 MB; downloads the full scene)
uv run scripts/build_geozarr.py --out ./data/S2B_T10TFR_20231223.zarr

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

installs everything, including the dev tooling (workshopify, Jupytext,
ipynb-scrubber). Run Jupyter with `uv run jupyter lab`.

After syncing, install the git hooks with `uv run prek install`. The hooks run
ruff lint and format, with the tools coming from the dev dependency group; run
them manually with `uv run prek run --all-files`.

## Checks / CI

CI (`.github/workflows/ci.yml`) runs on pull requests and on pushes to `main`.
It runs the prek hooks and `workshopify check`, then generates all notebooks
from `src/` and executes each completed notebook end to end (this hits the
public data services the notebooks use, so no credentials are needed). The
local equivalents:

```commandline
uv run prek run --all-files
uv run workshopify check
uv run workshopify generate
# for each of 01, 02, 03
uv run jupyter execute notebooks/completed/NN_<name>.ipynb
```

`workshopify check` reports any templated value or declared asset in `src/`
that has drifted from what the context module would regenerate. Nothing is
templated in this workshop yet, so today it always passes.
