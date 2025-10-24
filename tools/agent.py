"""tools.agent

Provides an Agent class that can:
- clone a GitHub repository (uses existing clone_repo helper)
- read project code files
- write or create files in the repo working tree
- commit and push changes back to the remote

This improved implementation adds:
- preview_edits(edits) to get unified diffs without committing
- commit_and_push(..., dry_run=True) to preview diffs instead of committing
- ensure_clean_worktree() to detect dirty working trees
- secret_scan(content) basic guard against common secrets
- tracking of the last applied edits so dry-run can preview those files
- auto_push option and convenience apply_and_push method
"""
from __future__ import annotations

import os
import difflib
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, List, Any

try:
    from git import Repo, GitCommandError
except Exception:
    Repo = None  # type: ignore

try:
    # reuse helper from tools if available
    from tools.git_operations import clone_repo
    from tools.file_system import get_code_files
except Exception:
    # fallback: simple local implementations
    def clone_repo(repo_url: str, branch: str, local_path: str) -> Optional[str]:
        # naive fallback: attempt using GitPython if available
        if Repo is None:
            raise RuntimeError("GitPython not available and tools.git_operations not found")
        if os.path.exists(local_path):
            # do not remove existing path
            repo = Repo(local_path)
            try:
                repo.git.checkout(branch)
                return local_path
            except Exception:
                return None
        repo = Repo.clone_from(repo_url, local_path)
        repo.git.checkout(branch)
        return local_path

    def get_code_files(repo_path: str) -> Dict[str, str]:
        # simple wrapper scanning for .py files (fallback)
        result: Dict[str, str] = {}
        for root, dirs, files in os.walk(repo_path):
            for f in files:
                if f.endswith('.py'):
                    p = Path(root) / f
                    try:
                        result[str(p)] = p.read_text(encoding='utf-8')
                    except Exception:
                        pass
        return result


class Agent:
    """Agent for cloning, editing, previewing and committing code changes.

    Notes:
    - Commit/push operations require GitPython present in the environment.
    - Push is opt-in by default, but can be enabled with auto_push=True.
    """

    SECRET_PATTERNS = [
        ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
        ("AWS Secret Key", re.compile(r"(?i)aws(.{0,20})?(secret|secret_key)[\\s:=]+[A-Za-z0-9/+=]{40}")),
        ("Private Key PEM", re.compile(r"-----BEGIN PRIVATE KEY-----")),
        ("RSA PRIVATE KEY", re.compile(r"-----BEGIN RSA PRIVATE KEY-----")),
        ("JWT token", re.compile(r"eyJ[0-9A-Za-z_\\-]+\.[0-9A-Za-z_\\-]+\.[0-9A-Za-z_\\-]+")),
        ("Generic API Key", re.compile(r"[A-Za-z0-9]{32,}")),
    ]

    def __init__(self, repo_url: str, branch: str = 'main', local_path: str | Path = './temp_repo', auto_push: bool = False) -> None:
        self.repo_url = repo_url
        self.branch = branch
        self.local_path = str(local_path)
        self._repo = None
        # track files most recently written by apply_edits for preview/dry-run
        self._last_written_paths: List[str] = []
        # if True, apply_edits will automatically commit and push (use with caution)
        self.auto_push = bool(auto_push)

    def ensure_repo(self) -> str:
        """Ensure repository is cloned locally and set self._repo.

        Returns the local path of the repository.
        """
        # if local path exists and is a git repo, open it
        if os.path.exists(self.local_path):
            try:
                if Repo is None:
                    # still ok: rely on clone_repo
                    clone_repo(self.repo_url, self.branch, self.local_path)
                else:
                    self._repo = Repo(self.local_path)
                    # try checkout
                    try:
                        self._repo.git.checkout(self.branch)
                    except Exception:
                        # branch may not exist locally; try fetch + checkout
                        try:
                            origin = self._repo.remote(name='origin')
                            origin.fetch()
                            self._repo.git.checkout(self.branch)
                        except Exception:
                            pass
                return self.local_path
            except Exception:
                # fallback to re-clone
                pass

        path = clone_repo(self.repo_url, self.branch, self.local_path)
        if not path:
            raise RuntimeError(f"Failed to clone {self.repo_url} (branch={self.branch})")
        if Repo is not None:
            self._repo = Repo(self.local_path)
        return self.local_path

    def read_code_files(self) -> Dict[str, str]:
        """Return a mapping of absolute file paths -> file contents for code files."""
        return get_code_files(self.local_path)

    def ensure_clean_worktree(self, allow_untracked: bool = True) -> bool:
        """Return True if working tree is clean (or only allowed untracked files).

        If Repo is not available this will return True (can't check).
        """
        if Repo is None:
            return True
        if self._repo is None:
            self._repo = Repo(self.local_path)
        repo = self._repo
        dirty = repo.is_dirty(untracked_files=not allow_untracked)
        return not dirty

    def secret_scan(self, content: str) -> List[str]:
        """Scan a string for likely secrets. Returns a list of issue messages."""
        issues: List[str] = []
        for name, pattern in self.SECRET_PATTERNS:
            if pattern.search(content):
                issues.append(name)
        return issues

    def preview_edits(self, edits: Dict[str, str]) -> Dict[str, str]:
        """Return unified diffs for the given edits (no files are changed by this call).

        Inputs:
        - edits: mapping of repo-relative or absolute paths -> new content

        Returns mapping path -> unified diff string (empty string if new file with no old content).
        """
        diffs: Dict[str, str] = {}
        # ensure repo is available for reading HEAD
        if Repo is not None and self._repo is None and os.path.exists(self.local_path):
            try:
                self._repo = Repo(self.local_path)
            except Exception:
                self._repo = None

        for rel_path, new_content in edits.items():
            p = Path(rel_path)
            if not p.is_absolute():
                abs_path = Path(self.local_path) / rel_path
            else:
                abs_path = p

            # determine old content from HEAD if present
            old_content = ''
            if Repo is not None and self._repo is not None:
                # compute path relative to repo root for git show
                try:
                    repo_root = Path(self._repo.working_tree_dir)
                    rel_to_root = str(abs_path.relative_to(repo_root))
                    # try to get file content at HEAD
                    try:
                        old_content = self._repo.git.show(f'HEAD:{rel_to_root}')
                    except Exception:
                        old_content = ''
                except Exception:
                    old_content = ''
            else:
                # if no git available, try reading file from disk as old content (before edits)
                if abs_path.exists():
                    try:
                        old_content = abs_path.read_text(encoding='utf-8')
                    except Exception:
                        old_content = ''

            # produce unified diff
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            fromfile = str(abs_path)
            tofile = str(abs_path)
            ud = ''.join(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile))
            diffs[str(abs_path)] = ud

        return diffs

    def apply_edits(self, edits: Dict[str, str], commit_message: Optional[str] = None, push: Optional[bool] = None, dry_run: bool = False) -> Optional[Dict[str, Any]]:
        """Apply edits to files in the working tree.

        Edits keys are paths relative to repository root (or absolute paths). Values
        are the file content to write. Directories will be created if missing.

        If the Agent is configured with auto_push or `push=True` is provided, this
        method will attempt to commit and push the changes automatically after applying.

        If dry_run=True, no commit/push will be performed and a preview diffs dict
        will be returned (same shape as commit_and_push dry_run output).
        """
        written_paths: List[str] = []
        for rel_path, content in edits.items():
            # permit both absolute and relative paths
            p = Path(rel_path)
            if not p.is_absolute():
                p = Path(self.local_path) / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            written_paths.append(str(p))

        # remember written files for preview/dry-run
        self._last_written_paths = written_paths

        # stage changes in Git index if Repo available
        if Repo is not None:
            if self._repo is None:
                self._repo = Repo(self.local_path)
            try:
                self._repo.index.add(written_paths)
            except Exception:
                # fallback: ignore staging here; commit will find changes
                pass

        # determine effective push behavior
        push_effective = self.auto_push if push is None else bool(push)

        if push_effective:
            # commit_message fallback
            msg = commit_message or 'Automated edits by agent'
            return self.commit_and_push(message=msg, push=True, dry_run=dry_run)

        return None

    def apply_and_push(self, edits: Dict[str, str], message: str = 'Automated edits by agent', dry_run: bool = False) -> Dict[str, Any]:
        """Convenience: apply edits then commit and push (or dry-run)."""
        self.apply_edits(edits)
        return self.commit_and_push(message=message, push=True, dry_run=dry_run)

    def _paths_changed_by_worktree(self) -> List[str]:
        """Return a list of paths that are changed in working tree (modified or untracked).

        Uses the repo status if available; otherwise returns last_written_paths.
        """
        if Repo is None or self._repo is None:
            return list(self._last_written_paths)

        repo = self._repo
        changed: List[str] = []
        try:
            # porcelain gives lines like ' M file' or '?? file'
            status = repo.git.status('--porcelain')
            for line in status.splitlines():
                if not line.strip():
                    continue
                # file path starts at position 3
                path = line[3:]
                abs_path = str(Path(repo.working_tree_dir) / path)
                changed.append(abs_path)
        except Exception:
            # fallback to last written
            changed = list(self._last_written_paths)
        return changed

    def commit_and_push(self, message: str = 'Automated edits by agent', push: bool = False, author: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Create a commit with current staged/unstaged changes and optionally push.

        If dry_run is True, do NOT create a commit or push. Instead, return a
        dictionary with previews (unified diffs) for the changed files.

        Returns a dictionary with keys:
          - dry_run: bool
          - diffs: mapping path -> unified diff
          - files: list of affected files
          - commit: commit hash (only present when not dry_run and commit created)
        """
        if Repo is None:
            raise RuntimeError('GitPython required for commit_and_push')

        if self._repo is None:
            self._repo = Repo(self.local_path)

        repo = self._repo

        # compute affected paths
        affected = self._paths_changed_by_worktree()

        if dry_run:
            # generate diffs for affected paths
            edits: Dict[str, str] = {}
            for p in affected:
                try:
                    new_text = Path(p).read_text(encoding='utf-8')
                except Exception:
                    new_text = ''
                # provide repo-relative keys in preview_edits for nicer diffs
                rel = os.path.relpath(p, repo.working_tree_dir)
                edits[rel] = new_text

            diffs = self.preview_edits(edits)
            return {"dry_run": True, "diffs": diffs, "files": affected}

        # non-dry run: run basic safety checks
        # ensure working tree is not dirty from unrelated changes
        if not self.ensure_clean_worktree(allow_untracked=True):
            raise RuntimeError('Working tree is dirty. Please commit or stash local changes before running the agent.')

        # scan for secrets in the new content of affected files
        secret_issues: Dict[str, List[str]] = {}
        for p in affected:
            try:
                content = Path(p).read_text(encoding='utf-8')
            except Exception:
                content = ''
            issues = self.secret_scan(content)
            if issues:
                secret_issues[p] = issues
        if secret_issues:
            raise RuntimeError(f'Secret patterns detected in files: {secret_issues}')

        try:
            # add all changes
            repo.git.add(all=True)
            # quick check: nothing to commit
            try:
                if not repo.index.diff('HEAD') and not repo.untracked_files:
                    return {"dry_run": False, "files": affected, "commit": None}
            except Exception:
                # ignore diff check issues
                pass
        except Exception:
            # continue; repo.index.commit may still work
            pass

        try:
            if author:
                c = repo.index.commit(message, author=author)
            else:
                c = repo.index.commit(message)
        except Exception as e:
            raise RuntimeError(f'Failed to create commit: {e}')

        commit_hash = None
        try:
            commit_hash = str(c.hexsha) if c is not None else None
        except Exception:
            commit_hash = None

        if push:
            try:
                origin = repo.remote(name='origin')
                origin.push(refspec=f'{self.branch}:{self.branch}')
            except GitCommandError as e:
                raise RuntimeError(f'Failed to push to remote: {e}')

        return {"dry_run": False, "files": affected, "commit": commit_hash}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Agent helper to clone, edit, commit and optionally push.')
    parser.add_argument('repo', help='Repository URL to clone')
    parser.add_argument('--branch', default='main', help='Branch to checkout')
    parser.add_argument('--local', default='./temp_repo', help='Local path to clone into')
    parser.add_argument('--edit', nargs=2, action='append', metavar=('PATH','FILE'),
                        help='Apply edit: PATH (relative path in repo) and FILE (local file with new content)')
    parser.add_argument('--push', action='store_true', help='If set, push commit to origin')
    parser.add_argument('--dry-run', action='store_true', help='If set, show diffs only and do not commit')
    parser.add_argument('--message', default='Automated edits by agent', help='Commit message')
    parser.add_argument('--auto-push', action='store_true', help='If set, enable agent.auto_push to commit+push automatically after apply_edits')

    args = parser.parse_args()
    agent = Agent(args.repo, args.branch, args.local, auto_push=args.auto_push)
    agent.ensure_repo()
    edits: Dict[str,str] = {}
    if args.edit:
        for relpath, localfile in args.edit:
            edits[relpath] = Path(localfile).read_text(encoding='utf-8')

    if edits:
        res = agent.apply_edits(edits, commit_message=args.message, push=args.push or args.auto_push, dry_run=args.dry_run)
        if res is not None and res.get('dry_run'):
            print('Dry-run diffs:')
            for p, d in res['diffs'].items():
                print('---', p)
                print(d)
    else:
        result = agent.commit_and_push(args.message, push=args.push, dry_run=args.dry_run)
        if result.get('dry_run'):
            print('Dry-run diffs:')
            for p, d in result['diffs'].items():
                print('---', p)
                print(d)
    print('Done')