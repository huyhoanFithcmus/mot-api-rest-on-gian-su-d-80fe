```python
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
import logging
import sys  # For logging fallback if logging module isn't configured for console output
from pathlib import Path
from typing import Dict, Iterable, Optional, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from git import Repo, GitCommandError, InvalidGitRepositoryError
except ImportError:  # Changed from Exception to ImportError for more specificity
    Repo = None  # type: ignore
    # Define dummy classes for type hinting when GitPython is not available
    GitCommandError = type('GitCommandError', (Exception,), {})
    InvalidGitRepositoryError = type('InvalidGitRepositoryError', (Exception,), {})
    logger.warning("GitPython not available. Some functionalities (commit, push, advanced repo checks) will be disabled.")

try:
    # reuse helper from tools if available
    from tools.git_operations import clone_repo
    from tools.file_system import get_code_files
except ImportError:  # Changed from Exception to ImportError
    logger.warning("tools.git_operations or tools.file_system not found. Using fallback implementations.")
    # fallback: simple local implementations
    def clone_repo(repo_url: str, branch: str, local_path: str) -> Optional[str]:
        # naive fallback: attempt using GitPython if available
        if Repo is None:
            raise RuntimeError("GitPython not available and tools.git_operations not found")
        if os.path.exists(local_path):
            # do not remove existing path
            try:
                repo = Repo(local_path)
                repo.git.checkout(branch)
                logger.info(f"Successfully checked out branch '{branch}' in existing repo at {local_path}")
                return local_path
            except (GitCommandError, InvalidGitRepositoryError) as e:  # Specific exceptions
                logger.warning(f"Failed to checkout branch or open existing repo at {local_path}: {e}. Attempting re-clone.")
                # Fallback to re-clone logic below if existing repo is problematic
                pass  # Continue to cloning logic

        try:
            logger.info(f"Cloning {repo_url} (branch={branch}) to {local_path}")
            repo = Repo.clone_from(repo_url, local_path)
            repo.git.checkout(branch)
            logger.info(f"Successfully cloned {repo_url} to {local_path}")
            return local_path
        except GitCommandError as e:  # Specific exception
            logger.error(f"Failed to clone {repo_url} (branch={branch}) to {local_path}: {e}")
            return None

    def get_code_files(repo_path: str) -> Dict[str, str]:
        # simple wrapper scanning for common code/text files (fallback)
        result: Dict[str, str] = {}
        # Define common file extensions to include
        CODE_FILE_EXTENSIONS = (
            '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs', '.rb', '.php',
            '.html', '.css', '.json', '.yaml', '.yml', '.md', '.txt', '.xml', '.sh', '.bash', '.zsh'
        )
        # Define common directories to exclude
        EXCLUDE_DIRS = ('.git', '.venv', '__pycache__', 'node_modules', 'build', 'dist', '.idea', '.vscode')

        for root, dirs, files in os.walk(repo_path):
            # Modify dirs in-place to skip excluded directories for os.walk
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

            for f in files:
                if f.endswith(CODE_FILE_EXTENSIONS):
                    p = Path(root) / f
                    try:
                        result[str(p)] = p.read_text(encoding='utf-8')
                    except UnicodeDecodeError:  # Specific exception for file content issues
                        logger.warning(f"Could not decode file {p} with utf-8. Skipping.")
                    except IOError as e:  # Catch other IO errors
                        logger.warning(f"Could not read file {p}: {e}. Skipping.")
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
        self._repo: Optional[Repo] = None  # Explicitly type _repo
        # track files most recently written by apply_edits for preview/dry-run
        self._last_written_paths: List[str] = []
        # if True, apply_edits will automatically commit and push (use with caution)
        self.auto_push = bool(auto_push)

    def _get_git_repo(self) -> Repo:
        """Ensures self._repo is initialized and returns it. Raises RuntimeError if GitPython is not available or repo is invalid."""
        if Repo is None:
            raise RuntimeError('GitPython is not available. Cannot perform Git operations.')
        if self._repo is None:
            try:
                self._repo = Repo(self.local_path)
            except InvalidGitRepositoryError:
                raise RuntimeError(f"Path '{self.local_path}' is not a valid Git repository.")
            except Exception as e:  # Catch other potential issues during Repo initialization
                raise RuntimeError(f"Failed to initialize Git repository at '{self.local_path}': {e}")
        return self._repo

    def ensure_repo(self) -> str:
        """Ensure repository is cloned locally and set self._repo.

        Returns the local path of the repository.
        """
        # If local path exists, try to open it as a git repo
        if os.path.exists(self.local_path):
            try:
                if Repo is None:
                    # If GitPython is not available, rely on clone_repo fallback
                    path = clone_repo(self.repo_url, self.branch, self.local_path)
                    if not path:
                        raise RuntimeError(f"Failed to clone {self.repo_url} (branch={self.branch}) without GitPython.")
                    return path
                else:
                    # GitPython is available, try to open existing repo
                    repo = self._get_git_repo()  # Use the helper to get repo
                    try:
                        repo.git.checkout(self.branch)
                        logger.info(f"Checked out branch '{self.branch}' in existing repo at '{self.local_path}'")
                        return self.local_path
                    except GitCommandError as e:
                        logger.warning(f"Branch '{self.branch}' not found locally or checkout failed: {e}. Attempting fetch and checkout.")
                        try:
                            origin = repo.remote(name='origin')
                            origin.fetch()
                            repo.git.checkout(self.branch)
                            logger.info(f"Fetched and checked out branch '{self.branch}' in existing repo at '{self.local_path}'")
                            return self.local_path
                        except GitCommandError as fetch_e:
                            logger.error(f"Failed to fetch and checkout branch '{self.branch}': {fetch_e}. Attempting re-clone.")
                            # Fall through to re-clone logic
                        except Exception as other_e:  # Catch other unexpected errors during fetch/checkout
                            logger.error(f"An unexpected error occurred during fetch/checkout: {other_e}. Attempting re-clone.")
                            # Fall through to re-clone logic
            except RuntimeError as e:  # Catch errors from _get_git_repo or clone_repo
                logger.warning(f"Problem with existing repository at '{self.local_path}': {e}. Attempting re-clone.")
            except Exception as e:  # Catch any other unexpected errors before re-clone
                logger.warning(f"An unexpected error occurred while trying to use existing repo: {e}. Attempting re-clone.")

        # If we reach here, either local_path didn't exist, or there was an issue with the existing repo.
        logger.info(f"Cloning {self.repo_url} (branch={self.branch}) to '{self.local_path}'")
        path = clone_repo(self.repo_url, self.branch, self.local_path)
        if not path:
            raise RuntimeError(f"Failed to clone {self.repo_url} (branch={self.branch})")

        # Ensure _repo is set if GitPython is available and clone was successful
        if Repo is not None:
            self._repo = Repo(self.local_path)
        return self.local_path

    def read_code_files(self) -> Dict[str, str]:
        """Return a mapping of absolute file paths -> file contents for code files."""
        self.ensure_repo()  # Ensure repo is cloned before reading files
        return get_code_files(self.local_path)

    def ensure_clean_worktree(self, allow_untracked: bool = True) -> bool:
        """Return True if working tree is clean (or only allowed untracked files).

        If Repo is not available this will return True (can't check).
        """
        if Repo is None:
            logger.warning("GitPython not available, cannot check for clean worktree. Assuming clean.")
            return True

        repo = self._get_git_repo()
        dirty = repo.is_dirty(untracked_files=not allow_untracked)
        if dirty:
            logger.warning(f"Working tree is dirty. Status:\n{repo.git.status('--porcelain')}")
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

        repo: Optional[Repo] = None
        if Repo is not None:
            try:
                repo = self._get_git_repo()
            except RuntimeError as e:
                logger.warning(f"Could not initialize Git repo for preview_edits: {e}. Will use file system for old content.")

        for rel_path, new_content in edits.items():
            p = Path(rel_path)
            if not p.is_absolute():
                abs_path = Path(self.local_path) / rel_path
            else:
                abs_path = p

            old_content = ''
            if repo is not None:
                # compute path relative to repo root for git show
                try:
                    repo_root = Path(repo.working_tree_dir)
                    rel_to_root = str(abs_path.relative_to(repo_root))
                    # try to get file content at HEAD
                    try:
                        old_content = repo.git.show(f'HEAD:{rel_to_root}')
                    except GitCommandError:  # File might be new or not in HEAD
                        old_content = ''
                except ValueError:  # abs_path is not relative to repo_root
                    logger.warning(f"Path '{abs_path}' is outside repository root '{repo_root}'. Cannot get HEAD content.")
                    # Fallback to reading from disk if not in repo
                    if abs_path.exists():
                        try:
                            old_content = abs_path.read_text(encoding='utf-8')
                        except UnicodeDecodeError:
                            logger.warning(f"Could not decode existing file '{abs_path}' for diff. Using empty content.")
                        except IOError as e:
                            logger.warning(f"Could not read existing file '{abs_path}' for diff: {e}. Using empty content.")
            else:
                # if no git available, try reading file from disk as old content (before edits)
                if abs_path.exists():
                    try:
                        old_content = abs_path.read_text(encoding='utf-8')
                    except UnicodeDecodeError:
                        logger.warning(f"Could not decode existing file '{abs_path}' for diff. Using empty content.")
                    except IOError as e:
                        logger.warning(f"Could not read existing file '{abs_path}' for diff: {e}. Using empty content.")

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

            # Ensure parent directories exist
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create parent directories for '{p}': {e}")
                raise

            # Write file content
            try:
                p.write_text(content, encoding='utf-8')
                written_paths.append(str(p))
            except IOError as e:
                logger.error(f"Failed to write content to file '{p}': {e}")
                raise

        # remember written files for preview/dry-run
        self._last_written_paths = written_paths

        # stage changes in Git index if Repo available
        if Repo is not None:
            try:
                repo = self._get_git_repo()
                # Stage only the files that were explicitly written by this agent.
                # This is more precise than repo.git.add(all=True) for apply_edits.
                # If commit_and_push is called later, it will handle staging all relevant changes.
                repo.index.add(written_paths)
                logger.info(f"Staged {len(written_paths)} files written by agent.")
            except GitCommandError as e:
                logger.warning(f"Failed to stage files {written_paths}: {e}. Commit might still work if changes are detected.")
            except RuntimeError as e:  # From _get_git_repo
                logger.warning(f"GitPython repo not available for staging: {e}. Skipping staging.")

        # determine effective push behavior
        push_effective = self.auto_push if push is None else bool(push)

        if push_effective:
            # commit_message fallback
            msg = commit_message or 'Automated edits by agent'
            return self.commit_and_push(message=msg, push=True, dry_run=dry_run)

        return None

    def apply_and_push(self, edits: Dict[str, str], message: str = 'Automated edits by agent', dry_run: bool = False) -> Dict[str, Any]:
        """Convenience: apply edits then commit and push (or dry-run)."""
        # This method now correctly delegates to apply_edits, which handles the commit/push logic.
        result = self.apply_edits(edits, commit_message=message, push=True, dry_run=dry_run)
        if result is None:
            # This should not happen if push=True is passed and dry_run is handled within apply_edits.
            # If apply_edits returns None, it means no push/dry_run happened, which contradicts apply_and_push's intent.
            raise RuntimeError("apply_edits did not return a result when push was expected in apply_and_push.")
        return result

    def _paths_changed_by_worktree(self) -> List[str]:
        """Return a list of paths that are changed in working tree (modified or untracked).

        Uses the repo status if available; otherwise returns last_written_paths.
        """
        if Repo is None:
            logger.warning("GitPython not available, cannot get changed paths from worktree. Returning last written paths.")
            return list(self._last_written_paths)

        try:
            repo = self._get_git_repo()
            changed: List[str] = []
            # porcelain gives lines like ' M file' or '?? file'
            status = repo.git.status('--porcelain')
            for line in status.splitlines():
                if not line.strip():
                    continue
                # file path starts at position 3, strip any leading/trailing whitespace
                path = line[3:].strip()
                abs_path = str(Path(repo.working_tree_dir) / path)
                changed.append(abs_path)
            return changed
        except (GitCommandError, RuntimeError) as e:  # RuntimeError from _get_git_repo
            logger.warning(f"Failed to get git status: {e}. Falling back to last written paths.")
            return list(self._last_written_paths)

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

        repo = self._get_git_repo()

        # compute affected paths
        affected = self._paths_changed_by_worktree()

        if dry_run:
            # generate diffs for affected paths
            edits: Dict[str, str] = {}
            for p in affected:
                try:
                    new_text = Path(p).read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode file '{p}' for dry-run diff. Using empty content.")
                    new_text = ''
                except IOError as e:
                    logger.warning(f"Could not read file '{p}' for dry-run diff: {e}. Using empty content.")
                    new_text = ''
                # provide repo-relative keys in preview_edits for nicer diffs
                try:
                    rel = os.path.relpath(p, repo.working_tree_dir)
                    edits[rel] = new_text
                except ValueError:  # Path not relative to repo_working_tree_dir
                    logger.warning(f"Path '{p}' is outside repository root. Using absolute path for diff.")
                    edits[p] = new_text

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
            except UnicodeDecodeError:
                logger.error(f"Could not decode file '{p}' for secret scan. Skipping.")
                content = ''
            except IOError as e:
                logger.error(f"Could not read file '{p}' for secret scan: {e}. Skipping.")
                content = ''
            issues = self.secret_scan(content)
            if issues:
                secret_issues[p] = issues
        if secret_issues:
            raise RuntimeError(f'Secret patterns detected in files: {secret_issues}')

        try:
            # Add all changes (staged, modified, untracked) to the index.
            # This ensures that all changes detected by _paths_changed_by_worktree
            # are included in the commit.
            repo.git.add(all=True)
            logger.info("Staged all changes in the repository.")
        except GitCommandError as e:
            logger.error(f"Failed to stage all changes: {e}")
            raise RuntimeError(f'Failed to stage changes for commit: {e}')

        # quick check: nothing to commit
        try:
            # Check if there are any changes in the index compared to HEAD
            # After `add(all=True)`, `repo.index.diff('HEAD')` should capture all changes.
            if not repo.index.diff('HEAD'):
                logger.info("No changes to commit after staging.")
                return {"dry_run": False, "files": affected, "commit": None}
        except GitCommandError as e:
            logger.warning(f"Failed to check for changes to commit: {e}. Proceeding with commit attempt.")
        except Exception as e:  # Catch other unexpected errors during diff check
            logger.warning(f"An unexpected error occurred during diff check: {e}. Proceeding with commit attempt.")

        try:
            if author:
                c = repo.index.commit(message, author=author)
            else:
                c = repo.index.commit(message)
            logger.info(f"Created commit: {c.hexsha}")
        except GitCommandError as e:
            raise RuntimeError(f'Failed to create commit: {e}')
        except Exception as e:  # Catch other unexpected errors during commit
            raise RuntimeError(f'An unexpected error occurred during commit: {e}')

        commit_hash = str(c.hexsha) if c is not None else None

        if push:
            try:
                origin = repo.remote(name='origin')
                # Push to the current branch
                origin.push(self.branch)
                logger.info(f"Pushed commit to origin/{self.branch}")
            except GitCommandError as e:
                raise RuntimeError(f'Failed to push to remote: {e}')
            except Exception as e:  # Catch other unexpected errors during push
                raise RuntimeError(f'An unexpected error occurred during push: {e}')

        return {"dry_run": False, "files": affected, "commit": commit_hash}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Agent helper to clone, edit, commit and optionally push.')
    parser.add_argument('repo', help='Repository URL to clone')
    parser.add_argument('--branch', default='main', help='Branch to checkout')
    parser.add_argument('--local', default='./temp_repo', help='Local path to clone into')
    parser.add_argument('--edit', nargs=2, action='append', metavar=('PATH', 'FILE'),
                        help='Apply edit: PATH (relative path in repo) and FILE (local file with new content)')
    parser.add_argument('--push', action='store_true', help='If set, push commit to origin')
    parser.add_argument('--dry-run', action='store_true', help='If set, show diffs only and do not commit')
    parser.add_argument('--message', default='Automated edits by agent', help='Commit message')
    parser.add_argument('--auto-push', action='store_true', help='If set, enable agent.auto_push to commit+push automatically after apply_edits')

    args = parser.parse_args()

    # Configure logging for console output in __main__ if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    agent = Agent(args.repo, args.branch, args.local, auto_push=args.auto_push)

    try:
        agent.ensure_repo()
        edits: Dict[str, str] = {}
        if args.edit:
            for relpath, localfile in args.edit:
                try:
                    edits[relpath] = Path(localfile).read_text(encoding='utf-8')
                except FileNotFoundError:
                    logger.error(f"Local file '{localfile}' not found for edit path '{relpath}'. Exiting.")
                    sys.exit(1)  # Exit if a specified edit file is missing
                except UnicodeDecodeError:
                    logger.error(f"Could not decode local file '{localfile}' for edit path '{relpath}'. Exiting.")
                    sys.exit(1)
                except IOError as e:
                    logger.error(f"Error reading local file '{localfile}' for edit path '{relpath}': {e}. Exiting.")
                    sys.exit(1)

        if edits:
            # Pass args.push directly. apply_edits will handle auto_push logic.
            res = agent.apply_edits(edits, commit_message=args.message, push=args.push, dry_run=args.dry_run)
            if res is not None and res.get('dry_run'):
                print('Dry-run diffs:')
                for p, d in res['diffs'].items():
                    print('---', p)
                    print(d)
            elif res is not None and res.get('commit'):
                print(f"Changes committed with hash: {res['commit']}")
            elif res is not None:
                print("Changes applied, but no commit/push performed (e.g., dry-run or push not enabled).")
        else:
            # If no edits, just perform commit_and_push based on current worktree state
            result = agent.commit_and_push(args.message, push=args.push, dry_run=args.dry_run)
            if result.get('dry_run'):
                print('Dry-run diffs:')
                for p, d in result['diffs'].items():
                    print('---', p)
                    print(d)
            elif result.get('commit'):
                print(f"Changes committed with hash: {result['commit']}")
            else:
                print("No changes to commit or push.")
        logger.info('Done')

    except RuntimeError as e:
        logger.error(f"Agent operation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        sys.exit(1)

```