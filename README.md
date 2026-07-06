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

* `src/NN_completed.py` — the full, working notebook, as readable Python with
  `# %%` cell markers (clean diffs, no JSON noise, no cell outputs).

From each `src/` file we generate:

* `NN_completed.ipynb` — the completed notebook (Jupytext render of the `.py`).
* `NN_<name>.ipynb` — the **exercise** notebook handed to attendees, produced by
  [`ipynb-scrubber`](https://pypi.org/project/ipynb-scrubber/), which clears
  designated cells and omits answer cells.
* `notes/NN_<name>.md` — notes extracted from cells tagged for note-taking.

Both generation steps are configured by `[tool.ipynb-scrubber]` in
`pyproject.toml` (input/output paths, tags) and `jupytext.toml` (the `src/` ↔
`notebooks/` pairing).

### Editing

Edit `src/NN_completed.py` directly, or edit a notebook in Jupyter and sync it
back to the `.py`:

```commandline
# after editing a notebook in Jupyter, sync it back to src/:
uv run jupytext --sync src/*_completed.py
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
`raw.githubusercontent.com`. See `scripts/` for the build/stage tooling.

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
uv run jupyter execute notebooks/NN_completed.ipynb   # for each of 01, 02, 03
```
