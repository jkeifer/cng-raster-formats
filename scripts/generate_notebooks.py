#!/usr/bin/env python3
"""Generate the completed + exercise notebooks (and notes) from the src/ files.

The py:percent files in src/ are the source of truth. This script:

  1. Renders each src/NN_completed.py to a completed .ipynb via Jupytext.
  2. Runs ipynb-scrubber over each completed notebook to produce the exercise
     notebook + notes file.

Both steps write into --output-dir, which is the directory that *contains* the
`notebooks/` and `notes/` subdirectories. It defaults to the repo root (`.`), so
a bare run regenerates the repo's own notebooks in place. Point it at a
worktree to stage a dist branch, e.g.:

    uv run scripts/worktree.py workshop            # -> ./workshop
    uv run scripts/generate_notebooks.py --output-dir ./workshop

Filenames, tags, and clear-text are read from the [tool.ipynb-scrubber] config
in pyproject.toml, so this stays single-sourced with the local `scrub-project`
workflow. The scrubber's own engine is reused (via a rewritten temp config), so
output is identical to `ipynb-scrubber scrub-project`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import tomllib

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / 'src'


def _load_scrubber_config() -> dict:
    with (REPO_ROOT / 'pyproject.toml').open('rb') as f:
        data = tomllib.load(f)
    try:
        return data['tool']['ipynb-scrubber']
    except KeyError:
        raise SystemExit('error: no [tool.ipynb-scrubber] section in pyproject.toml')


def _toml_escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _render_completed(input_ipynb: Path, output_dir: Path) -> Path:
    """Render src/<stem>.py -> <output_dir>/notebooks/<stem>.ipynb via Jupytext."""
    stem = input_ipynb.stem  # e.g. "01_completed"
    src_py = SRC_DIR / f'{stem}.py'
    if not src_py.exists():
        raise SystemExit(f'error: missing source file {src_py}')

    dest = output_dir / 'notebooks' / f'{stem}.ipynb'
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['jupytext', '--to', 'ipynb', '--output', str(dest), str(src_py)],
        check=True,
    )
    return dest


def _write_temp_config(config: dict, output_dir: Path, tmp_dir: Path) -> Path:
    """Write an .ipynb-scrubber.toml with all paths rebased under output_dir."""
    lines: list[str] = []

    options = config.get('options', {})
    if options:
        lines.append('[options]')
        for key, val in options.items():
            lines.append(f'{key} = "{_toml_escape(str(val))}"')
        lines.append('')

    for entry in config.get('files', []):
        stem = Path(entry['input']).stem
        completed = output_dir / 'notebooks' / f'{stem}.ipynb'
        out = output_dir / entry['output']
        lines.append('[[files]]')
        lines.append(f'input = "{_toml_escape(str(completed))}"')
        lines.append(f'output = "{_toml_escape(str(out))}"')
        if 'notes-file' in entry:
            notes = output_dir / entry['notes-file']
            lines.append(f'notes-file = "{_toml_escape(str(notes))}"')
        lines.append('')

    config_path = tmp_dir / '.ipynb-scrubber.toml'
    config_path.write_text('\n'.join(lines))
    return config_path


def generate(output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    config = _load_scrubber_config()

    # 1. Render completed notebooks from src/ into the output dir.
    for entry in config.get('files', []):
        _render_completed(Path(entry['input']), output_dir)

    # 2. Scrub completed -> exercise (+ notes) using the scrubber's own engine,
    #    with a temp config whose paths point into the output dir.
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _write_temp_config(config, output_dir, Path(tmp))
        # Ensure notes output dirs exist.
        for entry in config.get('files', []):
            if 'notes-file' in entry:
                (output_dir / entry['notes-file']).parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
        subprocess.run(
            ['ipynb-scrubber', 'scrub-project', '--config-file', str(config_path)],
            check=True,
        )


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
