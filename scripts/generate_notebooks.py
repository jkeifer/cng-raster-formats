#!/usr/bin/env python3
"""Generate the completed + exercise notebooks (and notes) from the src/ files.

The py:percent files in src/ are the source of truth. This script:

  1. Renders each src/NN_<name>.py to a completed .ipynb under
     notebooks/completed/ via Jupytext.
  2. Runs ipynb-scrubber over each completed notebook to produce the exercise
     notebook (notebooks/NN_<name>.ipynb) + notes file (notes/NN_<name>.md).

Both steps write into --output-dir, which is the directory that *contains* the
`notebooks/` and `notes/` subdirectories. It defaults to the repo root (`.`), so
a bare run regenerates the repo's own notebooks in place. Point it at a
worktree to stage a dist branch, e.g.:

    uv run scripts/worktree.py workshop            # -> ./workshop
    uv run scripts/generate_notebooks.py --output-dir ./workshop

Filenames, tags, and clear-text are read from the [tool.ipynb-scrubber] config
in pyproject.toml, so this stays single-sourced with the local `scrub-project`
workflow. We drive the scrubber through its Python API with each config entry's
paths rebased under --output-dir, which is what `scrub-project` itself does
internally -- so the output is identical, without a rewritten temp config.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from dataclasses import replace
from pathlib import Path

from ipynb_scrubber.config import FileEntry, ProjectConfig, ScrubbingOptions
from ipynb_scrubber.exceptions import ScrubberError
from ipynb_scrubber.processor import process_notebook, write_notes_file

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / 'src'
PYPROJECT = REPO_ROOT / 'pyproject.toml'


def _rebase(entry: FileEntry, output_dir: Path) -> FileEntry:
    """Repoint one config entry's paths at output_dir.

    Config paths are relative to the repo root; --output-dir may be a worktree.
    """
    return replace(
        entry,
        input=output_dir / entry.input,
        output=output_dir / entry.output,
        notes_file=output_dir / entry.notes_file if entry.notes_file else None,
    )


def _render_completed(dest: Path) -> None:
    """Render src/<stem>.py -> dest via Jupytext.

    The scrubber input paths (e.g. notebooks/completed/01_<name>.ipynb) share
    their stem with the src/ file they are rendered from.
    """
    src_py = SRC_DIR / f'{dest.stem}.py'
    if not src_py.exists():
        raise SystemExit(f'error: missing source file {src_py}')

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Cell ids are random (nbformat mints uuid4 hex), so a plain render assigns
    # fresh ones every time and rewrites every cell of every notebook. --update
    # merges into the existing file instead, keeping the ids stable; it only
    # applies when there is something to merge into.
    update = ['--update'] if dest.exists() else []
    subprocess.run(
        ['jupytext', '--to', 'ipynb', *update, '--output', str(dest), str(src_py)],
        check=True,
    )


def _scrub(entry: FileEntry, options: ScrubbingOptions) -> None:
    """Completed notebook -> exercise notebook (+ notes), via the scrubber API."""
    notebook = json.loads(entry.input.read_text())
    processed, notes = process_notebook(notebook, options)

    if notes:
        if entry.notes_file is None:
            raise SystemExit(
                f'error: {entry.input} has {len(notes)} cell(s) tagged '
                f'"{options.note_tag}" but no notes-file is configured',
            )
        write_notes_file(notes, entry.notes_file)

    entry.output.parent.mkdir(parents=True, exist_ok=True)
    # indent=1 matches what `ipynb-scrubber scrub-project` writes.
    entry.output.write_text(json.dumps(processed, indent=1))
    print(f'✓ {entry.input} → {entry.output}', file=sys.stderr)


def generate(output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    try:
        config = ProjectConfig.from_file(PYPROJECT)
    except ScrubberError as e:
        raise SystemExit(f'error: {e}') from e

    for configured in config.files:
        entry = _rebase(configured, output_dir)
        _render_completed(entry.input)
        _scrub(entry, entry.get_options(config.global_options))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=REPO_ROOT,
        help='directory containing notebooks/ and notes/ (default: repo root)',
    )
    args = parser.parse_args()
    generate(args.output_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
