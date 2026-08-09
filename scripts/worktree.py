#!/usr/bin/env python3
"""Prepare a git worktree for a branch, creating the branch if needed.

Generic worktree lifecycle helper: given a branch name (and optional path), this
ensures the branch exists and is checked out as a git worktree, then prints the
worktree path. It does *not* run any generation or commit anything -- compose it
with whatever produces content into the worktree, review the result, and commit
yourself.

Typical use in this repo:

    # Prepare the workshop branch worktree, then generate notebooks into it:
    uv run scripts/worktree.py workshop                          # -> ./workshop
    uv run scripts/generate_notebooks.py --output-dir ./workshop
    # ...review ./workshop, then `git -C ./workshop add/commit/push`.

The same tool works for the data branch (or anything else) that needs content
staged into a worktree for review.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from pathlib import Path


def _git(*args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ['git', *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return (result.stdout or '').strip()


def _branch_exists(branch: str) -> bool:
    return (
        subprocess.run(
            ['git', 'show-ref', '--verify', '--quiet', f'refs/heads/{branch}'],
            check=False,
        ).returncode
        == 0
    )


def _remotes_with_branch(branch: str) -> list[str]:
    """Remotes that have a tracking ref for `branch`, e.g. ['origin'].

    A fresh clone has no local `workshop` branch, only `origin/workshop`. Without
    this the branch looks nonexistent and we would branch off HEAD instead --
    quietly producing a worktree with the wrong content.
    """
    refs = _git(
        'for-each-ref',
        '--format=%(refname)',
        f'refs/remotes/*/{branch}',
        capture=True,
    )
    return [
        ref[len('refs/remotes/') :].removesuffix(f'/{branch}')
        for ref in refs.splitlines()
        if ref
    ]


def _worktrees() -> dict[Path, str]:
    """Map each worktree path -> its checked-out branch (bare-checkout aside)."""
    result: dict[Path, str] = {}
    current: Path | None = None
    for line in _git('worktree', 'list', '--porcelain', capture=True).splitlines():
        if line.startswith('worktree '):
            current = Path(line[len('worktree ') :]).resolve()
        elif line.startswith('branch ') and current is not None:
            # e.g. "branch refs/heads/workshop"
            result[current] = line[len('branch ') :].removeprefix('refs/heads/')
    return result


def prepare_worktree(branch: str, path: Path, orphan: bool) -> Path:
    path = path.resolve()

    # Prune stale registrations (e.g. a worktree dir that was deleted) so we
    # don't trip over "branch already used by worktree" for a gone location.
    _git('worktree', 'prune')

    worktrees = _worktrees()

    # A branch can only be checked out in one worktree. If it already is, reuse
    # that -- but insist it matches the requested path to avoid surprises.
    for existing_path, existing_branch in worktrees.items():
        if existing_branch == branch:
            if existing_path != path:
                raise SystemExit(
                    f'error: branch {branch!r} is already checked out at '
                    f'{existing_path} (requested {path}). Reuse that path or '
                    f'remove it with `git worktree remove`.',
                )
            return path

    # Nothing checked out `branch` yet. The target path must be free.
    if path in worktrees:
        raise SystemExit(
            f'error: {path} is already a worktree for branch '
            f'{worktrees[path]!r}, not {branch!r}',
        )
    if path.exists() and any(path.iterdir()):
        raise SystemExit(f'error: {path} exists and is not empty')

    if _branch_exists(branch):
        _git('worktree', 'add', str(path), branch)
        return path

    # No local branch. Before inventing one, check whether it already exists on
    # a remote -- on a fresh clone that is the normal case for `workshop`.
    remotes = _remotes_with_branch(branch)
    if len(remotes) > 1:
        raise SystemExit(
            f'error: branch {branch!r} exists on multiple remotes '
            f'({", ".join(sorted(remotes))}) and no local branch resolves the '
            f'ambiguity. Create it locally first, e.g. `git branch {branch} '
            f'{min(remotes)}/{branch}`.',
        )
    if remotes:
        remote = remotes[0]
        print(f'creating {branch!r} tracking {remote}/{branch}', file=sys.stderr)
        _git(
            'worktree', 'add', '--track', '-b', branch, str(path), f'{remote}/{branch}'
        )
    elif orphan:
        # New orphan branch (no shared history) materialized in the worktree.
        _git('worktree', 'add', '--orphan', '-b', branch, str(path))
    else:
        # Genuinely new branch off the current HEAD. Say so -- if the user meant
        # to check out an existing remote branch, this is where it goes wrong.
        head = _git('rev-parse', '--abbrev-ref', 'HEAD', capture=True)
        print(
            f'note: no local or remote branch {branch!r}; creating it from {head}',
            file=sys.stderr,
        )
        _git('worktree', 'add', '-b', branch, str(path))

    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('branch', help='branch to check out as a worktree')
    parser.add_argument(
        '--path',
        type=Path,
        help='worktree path (default: ./<branch>)',
    )
    parser.add_argument(
        '--orphan',
        action='store_true',
        help='if the branch does not exist, create it as an orphan branch '
        '(no shared history) rather than branching from HEAD',
    )
    args = parser.parse_args()

    path = args.path or Path(f'./{args.branch}')
    result = prepare_worktree(args.branch, path, args.orphan)
    print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
