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

# Distinct from 1 (errors) and 2 (argparse usage) so a caller can tell "the tree
# has drifted" apart from "the run failed": generation still succeeded.
EXIT_STALE = 3


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


def _entry_paths(entry: FileEntry) -> tuple[Path, ...]:
    """Every path one config entry owns."""
    paths = (entry.input, entry.output, entry.notes_file)
    return tuple(p for p in paths if p is not None)


def _stale_paths(
    entries: list[FileEntry], output_dir: Path, roots: set[str]
) -> list[Path]:
    """Files under the managed trees that the config doesn't claim.

    Everything below notebooks/ and notes/ is generated, so a file we aren't
    about to write is a leftover from an older config -- a renamed notebook, or
    a notes-file for a notebook that no longer has any notes. Nothing removes
    those otherwise, and when the output dir is a published worktree they ship.
    """
    expected = {p.resolve() for entry in entries for p in _entry_paths(entry)}
    return [
        path
        for root in sorted(roots)
        if (output_dir / root).is_dir()
        for path in sorted((output_dir / root).rglob('*'))
        if path.is_file() and path.resolve() not in expected
    ]


def _prune_stale(stale: list[Path], output_dir: Path, roots: set[str]) -> None:
    """Delete stale files, and any directory the deletions leave empty.

    Pruning rather than wiping the tree is deliberate: `jupytext --update` needs
    the previous notebook to still be there to keep its cell ids stable.
    """
    for path in stale:
        path.unlink()
        print(f'removed stale {path.relative_to(output_dir)}', file=sys.stderr)

    for root in sorted(roots):
        base = output_dir / root
        if not base.is_dir():
            continue
        # Deepest first, so a directory emptied by its children's removal goes too.
        for path in sorted(base.rglob('*'), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()


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


def generate(output_dir: Path, prune: bool = False) -> bool:
    """Generate the notebooks. Returns True if stale output was left in place."""
    output_dir = output_dir.resolve()
    try:
        config = ProjectConfig.from_file(PYPROJECT)
    except ScrubberError as e:
        raise SystemExit(f'error: {e}') from e

    # The top-level directory of each configured path (notebooks/, notes/) is a
    # tree we own end to end, so we get to say what does and doesn't belong.
    roots = {
        p.parts[0]
        for configured in config.files
        for p in _entry_paths(configured)
        if not p.is_absolute() and p.parts
    }
    entries = [_rebase(configured, output_dir) for configured in config.files]

    stale = _stale_paths(entries, output_dir, roots)
    if stale and prune:
        _prune_stale(stale, output_dir, roots)
        stale = []
    elif stale:
        # Deleting is opt-in: report, and say how to act on it.
        for path in stale:
            print(f'stale {path.relative_to(output_dir)}', file=sys.stderr)
        print(
            f'{len(stale)} stale file(s) the config no longer claims; '
            're-run with --prune to delete them',
            file=sys.stderr,
        )

    for entry in entries:
        _render_completed(entry.input)
        _scrub(entry, entry.get_options(config.global_options))

    return bool(stale)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=REPO_ROOT,
        help='directory containing notebooks/ and notes/ (default: repo root)',
    )
    parser.add_argument(
        '--prune',
        action='store_true',
        help='delete generated files the config no longer claims; without it '
        f'they are only reported, and the run exits {EXIT_STALE}',
    )
    args = parser.parse_args()
    stale = generate(args.output_dir, prune=args.prune)
    return EXIT_STALE if stale else 0


if __name__ == '__main__':
    sys.exit(main())
