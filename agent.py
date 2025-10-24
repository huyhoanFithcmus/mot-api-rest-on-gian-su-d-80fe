Dưới đây là mã nguồn đã được sửa đổi dựa trên các nhận xét chi tiết của bạn. Các thay đổi tập trung vào việc khắc phục lỗi logic, cải thiện xử lý ngoại lệ bằng cách sử dụng các ngoại lệ cụ thể hơn, tích hợp logging, tách biệt rõ ràng các trách nhiệm của phương thức `apply_edits` và `commit_and_push`, và sử dụng `pathlib.Path` nhất quán hơn.

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
import shutil  # For potential cleanup of invalid repos
from pathlib import Path
from typing import Dict, Iterable, Optional, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from git import Repo, GitCommandError, InvalidGitRepositoryError
except ImportError:
    logger.warning("GitPython not found. Agent functionality will be limited (no commit/push).")
    Repo = None  # type: ignore
    # Define dummy exceptions for type hinting and to avoid NameError if GitPython is missing
    GitCommandError = type('GitCommandError', (Exception,), {})  # type: ignore
    InvalidGitRepositoryError = type('InvalidGitRepositoryError', (Exception,), {})  # type: ignore

try:
    # reuse helper from tools if available
    from tools.git_operations import clone_repo
    from tools.file_system import get_code_files
except ImportError:
    logger.warning("tools.git_operations or tools.file_system not found. Using fallback implementations.")

    # Helper for fallback clone_repo to check if a path is a git repo
    def _is_git_repo_static(path: str) -> bool:
        """Checks if a given path is a valid Git repository."""
        if Repo is None:
            return False
        try:
            _ = Repo(path)
            return True
        except InvalidGitRepositoryError:
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking if {path} is a git repo: {e}")
            return False

    def clone_repo(repo_url: str, branch: str, local_path: str) -> Optional[str]:
        """Fallback: Clones a Git repository using GitPython if available.
        If local_path exists and is not a valid repo, it will be removed.
        """
        if Repo is None:
            raise RuntimeError("GitPython not available and tools.git_operations not found")

        path_obj = Path(local_path)
        if path_obj.exists():
            if _is_git_repo_static(local_path):
                try:
                    repo = Repo(local_path)
                    repo.git.checkout(branch)
                    logger.info(f"Repository at {local_path} already exists and is valid. Checked out branch {branch}.")
                    return local_path
                except GitCommandError as e:
                    logger.error(f"Git command error during checkout in existing repo {local_path}: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Error accessing existing repository at {local_path}: {e}")
                    return None
            else:
                logger.warning(f"Path {local_path} exists but is not a valid Git repository. Removing and re-cloning.")
                try:
                    shutil.rmtree(local_path)
                except OSError as e:
                    logger.error(f"Failed to remove existing non-Git directory {local_path}: {e}")
                    raise RuntimeError(f"Failed to clean up {local_path} for cloning.")

        try:
            repo = Repo.clone_from(repo_url, local_path)
            repo.git.checkout(branch)
            logger.info(f"Successfully cloned {repo_url} to {local_path} and checked out branch {branch}.")
            return local_path
        except GitCommandError as e:
            logger.error(f"Failed to clone {repo_url} to {local_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during cloning {repo_url} to {local_path}: {e}")
            return None

    def get_code_files(repo_path: str) -> Dict[str, str]:
        """Fallback: Simple wrapper scanning for .py files."""
        result: Dict[str, str] = {}
        repo_path_obj = Path(repo_path)
        for p in repo_path_obj.rglob('*.py'):  # Use rglob for efficiency
            if p.is_file():
                try:
                    result[str(p)] = p.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode file {p} with utf-8. Skipping.")
                except OSError as e:
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
        # Generic API Key is very broad and may produce false positives.
        # Use with caution and consider more specific patterns if possible.
        ("Generic API Key", re.compile(r"[A-Za-z0-9]{32,}")),
    ]

    def __init__(self, repo_url: str, branch: str = 'main', local_path: str | Path = './temp_repo', auto_push: bool = False) -> None:
        self.repo_url = repo_url
        self.branch = branch
        self.local_path: Path = Path(local_path)  # Store as Path object
        self._repo: Optional[Repo] = None
        # track files most recently written by apply_edits for preview/dry-run
        self._last_written_paths: List[Path] = []  # Store as Path objects
        # if True, apply_edits will automatically commit and push (use with caution)
        self.auto_push = bool(auto_push)

    def _is_git_repo(self, path: Path) -> bool:
        """Checks if a given path is a valid Git repository."""
        if Repo is None:
            return False
        try:
            _ = Repo(path)
            return True
        except InvalidGitRepositoryError:
            return False
        except Exception as e:
            logger.debug(f"Unexpected error checking if {path} is a git repo: {e}")
            return False

    def ensure_repo(self) -> Path:
        """Ensure repository is cloned locally and set self._repo.

        Returns the local path of the repository.
        Raises RuntimeError if cloning or repository access fails.
        """
        # if local path exists and is a git repo, open it
        if self.local_path.exists():
            if self._is_git_repo(self.local_path):
                try:
                    # _is_git_repo already checked Repo is not None
                    self._repo = Repo(self.local_path)
                    # try checkout
                    try:
                        self._repo.git.checkout(self.branch)
                        logger.info(f"Repository at {self.local_path} already exists and is valid. Checked out branch {self.branch}.")
                        return self.local_path
                    except GitCommandError:
                        # branch may not exist locally; try fetch + checkout
                        logger.info(f"Branch {self.branch} not found locally. Attempting to fetch and checkout.")
                        try:
                            origin = self._repo.remote(name='origin')
                            origin.fetch()
                            self._repo.git.checkout(self.branch)
                            logger.info(f"Successfully fetched and checked out branch {self.branch}.")
                            return self.local_path
                        except GitCommandError as e:
                            logger.error(f"Failed to fetch and checkout branch {self.branch}: {e}")
                            raise RuntimeError(f"Failed to checkout branch {self.branch} in {self.local_path}.")
                        except Exception as e:
                            logger.error(f"An unexpected error occurred during fetch/checkout: {e}")
                            raise RuntimeError(f"An unexpected error occurred during fetch/checkout in {self.local_path}.")
                except InvalidGitRepositoryError:
                    # This should ideally not happen if _is_git_repo returned True, but for safety
                    logger.warning(f"Path {self.local_path} was identified as a repo but GitPython failed to open it. Attempting re-clone.")
                    # Fall through to re-clone logic
                except Exception as e:
                    logger.error(f"An unexpected error occurred while opening existing repository {self.local_path}: {e}")
                    # Fall through to re-clone logic
            else:
                logger.warning(f"Path {self.local_path} exists but is not a valid Git repository. Removing and re-cloning.")
                try:
                    shutil.rmtree(self.local_path)
                except OSError as e:
                    logger.error(f"Failed to remove existing non-Git directory {self.local_path}: {e}")
                    raise RuntimeError(f"Failed to clean up {self.local_path} for cloning.")

        # If we reach here, either local_path didn't exist, or it was invalid and removed.
        path_str = clone_repo(self.repo_url, self.branch, str(self.local_path))  # clone_repo expects str
        if not path_str:
            raise RuntimeError(f"Failed to clone {self.repo_url} (branch={self.branch})")

        self.local_path = Path(path_str)  # Ensure self.local_path is updated if clone_repo changed it
        if Repo is not None:
            try:
                self._repo = Repo(self.local_path)
            except InvalidGitRepositoryError as e:
                logger.error(f"Cloned repository at {self.local_path} is not a valid Git repo: {e}")
                raise RuntimeError(f"Cloned repository at {self.local_path} is not a valid Git repo.")
            except Exception as e:
                logger.error(f"An unexpected error occurred while opening cloned repository {self.local_path}: {e}")
                raise RuntimeError(f"An unexpected error occurred while opening cloned repository {self.local_path}.")

        logger.info(f"Repository {self.repo_url} successfully ensured at {self.local_path}.")
        return self.local_path

    def read_code_files(self) -> Dict[Path, str]:  # Changed key type to Path
        """Return a mapping of absolute file paths -> file contents for code files."""
        # Ensure repo is cloned before reading files
        self.ensure_repo()
        files_dict = get_code_files(str(self.local_path))
        # Convert keys to Path objects for consistency
        return {Path(k): v for k, v in files_dict.items()}

    def ensure_clean_worktree(self, allow_untracked: bool = True) -> bool:
        """Return True if working tree is clean (or only allowed untracked files).

        If GitPython is not available, this will return True (cannot check).
        """
        if Repo is None:
            logger.warning("GitPython not available, cannot check for clean worktree. Assuming clean.")
            return True

        # Ensure _repo is initialized
        if self._repo is None:
            try:
                self.ensure_repo()  # This will initialize self._repo
            except RuntimeError as e:
                logger.error(f"Could not ensure repository for clean worktree check: {e}. Assuming clean.")
                return True  # If we can't even get the repo, we can't check.

        repo = self._repo
        if repo is None:  # Should not happen after ensure_repo, but for type safety
            return True

        dirty = repo.is_dirty(untracked_files=not allow_untracked)
        if dirty:
            logger.warning(f"Working tree at {self.local_path} is dirty.")
        return not dirty

    def secret_scan(self, content: str) -> List[str]:
        """Scan a string for likely secrets. Returns a list of issue messages."""
        issues: List[str] = []
        for name, pattern in self.SECRET_PATTERNS:
            if pattern.search(content):
                issues.append(name)
        return issues

    def preview_edits(self, edits: Dict[str | Path, str]) -> Dict[Path, str]:  # Changed key type to Path
        """Return unified diffs for the given edits (no files are changed by this call).

        Inputs:
        - edits: mapping of repo-relative or absolute paths -> new content

        Returns mapping path -> unified diff string (empty string if new file with no old content).
        """
        diffs: Dict[Path, str] = {}

        # Ensure repo is available for reading HEAD
        if Repo is not None and self._repo is None:
            try:
                self.ensure_repo()
            except RuntimeError as e:
                logger.warning(f"Could not ensure repository for previewing edits: {e}. Diffs might be less accurate.")
                # Continue without _repo, will try to read from disk

        for path_key, new_content in edits.items():
            p = Path(path_key)
            if not p.is_absolute():
                abs_path = self.local_path / p
            else:
                abs_path = p

            # determine old content from HEAD if present
            old_content = ''
            if Repo is not None and self._repo is not None:
                try:
                    repo_root = Path(self._repo.working_tree_dir)
                    rel_to_root = str(abs_path.relative_to(repo_root))
                    # try to get file content at HEAD
                    try:
                        old_content = self._repo.git.show(f'HEAD:{rel_to_root}')
                    except GitCommandError:
                        # File might be new or not in HEAD
                        old_content = ''
                    except Exception as e:
                        logger.debug(f"Unexpected error getting HEAD content for {rel_to_root}: {e}")
                        old_content = ''
                except ValueError:  # abs_path not relative to repo_root
                    logger.debug(f"Path {abs_path} is not relative to repo root {repo_root}. Cannot get HEAD content.")
                    old_content = ''
                except Exception as e:
                    logger.debug(f"Unexpected error determining repo_root or relative path: {e}")
                    old_content = ''

            # If no git available or HEAD content failed, try reading file from disk as old content (before edits)
            if not old_content and abs_path.exists():
                try:
                    old_content = abs_path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode existing file {abs_path} with utf-8 for diff. Skipping old content.")
                    old_content = ''
                except OSError as e:
                    logger.warning(f"Could not read existing file {abs_path} for diff: {e}. Skipping old content.")
                    old_content = ''

            # produce unified diff
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            fromfile = str(abs_path)
            tofile = str(abs_path)
            ud = ''.join(difflib.unified_diff(old_lines, new_lines, fromfile=fromfile, tofile=tofile))
            diffs[abs_path] = ud

        return diffs

    def apply_edits(self, edits: Dict[str | Path, str]) -> List[Path]:
        """Apply edits to files in the working tree.

        Edits keys are paths relative to repository root (or absolute paths). Values
        are the file content to write. Directories will be created if missing.

        This method only applies changes to the file system and stages them in Git
        if GitPython is available. It does NOT commit or push.

        Returns a list of absolute paths to files that were written.
        """
        written_paths: List[Path] = []
        for path_key, content in edits.items():
            # permit both absolute and relative paths
            p = Path(path_key)
            if not p.is_absolute():
                p = self.local_path / p

            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                p.write_text(content, encoding='utf-8')
                written_paths.append(p)
                logger.debug(f"Wrote content to {p}")
            except OSError as e:
                logger.error(f"Failed to write content to {p}: {e}")
                raise RuntimeError(f"Failed to write content to {p}: {e}")

        # remember written files for preview/dry-run
        self._last_written_paths = written_paths

        # stage changes in Git index if Repo available
        if Repo is not None:
            if self._repo is None:
                try:
                    self.ensure_repo()
                except RuntimeError as e:
                    logger.warning(f"Could not ensure repository for staging changes: {e}. Changes will not be staged.")
                    return written_paths  # Cannot stage if repo not available

            if self._repo is not None:  # Check again after ensure_repo
                try:
                    # Convert Path list to str list for GitPython
                    self._repo.index.add([str(p) for p in written_paths])
                    logger.info(f"Staged {len(written_paths)} files.")
                except GitCommandError as e:
                    logger.warning(f"Failed to stage changes for {written_paths}: {e}. Commit might still work if changes are detected.")
                except Exception as e:
                    logger.warning(f"An unexpected error occurred during staging changes: {e}. Commit might still work.")
        else:
            logger.debug("GitPython not available, skipping staging changes.")

        return written_paths

    def apply_and_push(self, edits: Dict[str | Path, str], message: str = 'Automated edits by agent', dry_run: bool = False) -> Dict[str, Any]:
        """Convenience: apply edits then commit and push (or dry-run)."""
        self.apply_edits(edits)  # This now only applies and stages
        # If dry_run, commit_and_push will generate diffs based on current worktree state
        # which includes the just-applied edits.
        return self.commit_and_push(message=message, push=True, dry_run=dry_run)

    def _paths_changed_by_worktree(self) -> List[Path]:
        """Return a list of paths that are changed in working tree (modified or untracked).

        Uses the repo status if available; otherwise returns last_written_paths.
        """
        if Repo is None or self._repo is None:
            # Fallback to last written paths if GitPython not available or repo not initialized
            if not self._last_written_paths:
                logger.warning("GitPython not available or repo not initialized, and no recent written paths. Cannot determine changed files.")
            return list(self._last_written_paths)

        repo = self._repo
        changed: List[Path] = []
        try:
            # porcelain gives lines like ' M file' or '?? file'
            status = repo.git.status('--porcelain')
            for line in status.splitlines():
                if not line.strip():
                    continue
                # file path starts at position 3
                path_str = line[3:].strip()  # .strip() to remove potential leading/trailing whitespace
                abs_path = Path(repo.working_tree_dir) / path_str
                changed.append(abs_path)
            logger.debug(f"Detected {len(changed)} changed files via git status.")
        except GitCommandError as e:
            logger.warning(f"Failed to get git status: {e}. Falling back to last written paths.")
            changed = list(self._last_written_paths)
        except Exception as e:
            logger.warning(f"An unexpected error occurred getting git status: {e}. Falling back to last written paths.")
            changed = list(self._last_written_paths)
        return changed

    def commit_and_push(self, message: str = 'Automated edits by agent', push: bool = False, author: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Create a commit with current staged/unstaged changes and optionally push.

        If dry_run is True, do NOT create a commit or push. Instead, return a
        dictionary with previews (unified diffs) for the changed files.

        Returns a dictionary with keys:
          - dry_run: bool
          - diffs: mapping path -> unified diff (keys are Path objects)
          - files: list of affected files (Path objects)
          - commit: commit hash (only present when not dry_run and commit created)
        """
        if Repo is None:
            raise RuntimeError('GitPython required for commit_and_push')

        if self._repo is None:
            try:
                self.ensure_repo()
            except RuntimeError as e:
                raise RuntimeError(f"Failed to initialize repository for commit_and_push: {e}")

        repo = self._repo
        if repo is None:  # Should not happen after ensure_repo, but for type safety
            raise RuntimeError("Repository object is None after ensure_repo.")

        # compute affected paths
        affected_paths = self._paths_changed_by_worktree()
        if not affected_paths and not dry_run:
            logger.info("No changes detected in the working tree. Skipping commit.")
            return {"dry_run": False, "diffs": {}, "files": [], "commit": None}

        if dry_run:
            # generate diffs for affected paths
            edits_for_preview: Dict[Path, str] = {}
            for p in affected_paths:
                try:
                    new_text = p.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"Could not decode file {p} for dry-run diff. Skipping.")
                    new_text = ''
                except OSError as e:
                    logger.warning(f"Could not read file {p} for dry-run diff: {e}. Skipping.")
                    new_text = ''
                edits_for_preview[p] = new_text

            # preview_edits expects Dict[str | Path, str] and returns Dict[Path, str]
            diffs = self.preview_edits(edits_for_preview)
            # Convert Path keys/values to str for consistency with original output format
            return {"dry_run": True, "diffs": {str(k): v for k, v in diffs.items()}, "files": [str(p) for p in affected_paths]}

        # non-dry run: run basic safety checks
        # ensure working tree is not dirty from unrelated changes
        if not self.ensure_clean_worktree(allow_untracked=True):
            raise RuntimeError('Working tree is dirty. Please commit or stash local changes before running the agent.')

        # scan for secrets in the new content of affected files
        secret_issues: Dict[Path, List[str]] = {}
        for p in affected_paths:
            try:
                content = p.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                logger.warning(f"Could not decode file {p} for secret scan. Skipping.")
                content = ''
            except OSError as e:
                logger.warning(f"Could not read file {p} for secret scan: {e}. Skipping.")
                content = ''
            issues = self.secret_scan(content)
            if issues:
                secret_issues[p] = issues
        if secret_issues:
            raise RuntimeError(f'Secret patterns detected in files: {secret_issues}')

        try:
            # add all changes (staged and unstaged)
            repo.git.add(all=True)
            logger.info("Staged all changes in the repository.")

            # quick check: nothing to commit
            # After `add(all=True)`, we only need to check `repo.index.diff('HEAD')`.
            if not repo.index.diff('HEAD'):
                logger.info("No changes to commit after staging.")
                return {"dry_run": False, "diffs": {}, "files": [str(p) for p in affected_paths], "commit": None}
        except GitCommandError as e:
            logger.error(f"Git command error during staging changes: {e}")
            raise RuntimeError(f"Failed to stage changes for commit: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during staging changes: {e}")
            raise RuntimeError(f"An unexpected error occurred during staging changes: {e}")

        try:
            if author:
                c = repo.index.commit(message, author=author)
            else:
                c = repo.index.commit(message)
            logger.info(f"Successfully created commit: {c.hexsha}")
        except GitCommandError as e:
            logger.error(f'Failed to create commit: {e}')
            raise RuntimeError(f'Failed to create commit: {e}')
        except Exception as e:
            logger.error(f'An unexpected error occurred while creating commit: {e}')
            raise RuntimeError(f'An unexpected error occurred while creating commit: {e}')

        commit_hash = str(c.hexsha) if c is not None else None

        if push:
            try:
                origin = repo.remote(name='origin')
                origin.push(refspec=f'{self.branch}:{self.branch}')
                logger.info(f"Successfully pushed commit {commit_hash} to origin/{self.branch}.")
            except GitCommandError as e:
                logger.error(f'Failed to push to remote: {e}')
                raise RuntimeError(f'Failed to push to remote: {e}')
            except Exception as e:
                logger.error(f'An unexpected error occurred while pushing to remote: {e}')
                raise RuntimeError(f'An unexpected error occurred while pushing to remote: {e}')

        return {"dry_run": False, "diffs": {}, "files": [str(p) for p in affected_paths], "commit": commit_hash}


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

    # Initialize agent
    agent = Agent(args.repo, args.branch, args.local, auto_push=args.auto_push)

    # Ensure repo is ready
    try:
        agent.ensure_repo()
    except RuntimeError as e:
        logger.critical(f"Agent initialization failed: {e}")
        exit(1)

    edits: Dict[Path, str] = {}  # Changed key type to Path
    if args.edit:
        for relpath_str, localfile_str in args.edit:
            try:
                edits[Path(relpath_str)] = Path(localfile_str).read_text(encoding='utf-8')
            except FileNotFoundError:
                logger.error(f"Local file '{localfile_str}' not found for edit path '{relpath_str}'. Skipping.")
                exit(1)
            except UnicodeDecodeError:
                logger.error(f"Could not decode local file '{localfile_str}' with utf-8. Skipping.")
                exit(1)
            except OSError as e:
                logger.error(f"Error reading local file '{localfile_str}': {e}. Skipping.")
                exit(1)

    if edits:
        # If auto_push is enabled or --push is explicitly given, use apply_and_push
        if agent.auto_push or args.push:
            logger.info("Applying edits and committing/pushing (due to auto_push or --push flag).")
            res = agent.apply_and_push(edits, message=args.message, dry_run=args.dry_run)
        else:
            # Otherwise, just apply edits (stage them)
            logger.info("Applying edits (will be staged, not committed/pushed automatically).")
            agent.apply_edits(edits)
            # If dry_run is requested, we still need to show diffs for the applied (staged) changes
            if args.dry_run:
                logger.info("Dry-run requested after applying edits. Generating diffs for current worktree state.")
                res = agent.commit_and_push(message=args.message, push=False, dry_run=True)
            else:
                res = None  # No commit/push, no dry-run output

        if res is not None and res.get('dry_run'):
            print('Dry-run diffs:')
            for p_str, d in res['diffs'].items():  # res['diffs'] keys are str
                print('---', p_str)
                print(d)
        elif res is not None and res.get('commit'):
            logger.info(f"Commit created: {res['commit']}")
            if args.push:
                logger.info("Push was also performed.")
        elif res is not None:
            logger.info("Edits applied, but no commit/push action taken (or no changes to commit).")
    else:
        # No edits provided, just perform a commit/push action if requested
        logger.info("No edits provided. Performing commit/push action if requested.")
        result = agent.commit_and_push(args.message, push=args.push, dry_run=args.dry_run)
        if result.get('dry_run'):
            print('Dry-run diffs:')
            for p_str, d in result['diffs'].items():  # result['diffs'] keys are str
                print('---', p_str)
                print(d)
        elif result.get('commit'):
            logger.info(f"Commit created: {result['commit']}")
            if args.push:
                logger.info("Push was also performed.")
        else:
            logger.info("No changes to commit or push action taken.")
    logger.info('Done')
```