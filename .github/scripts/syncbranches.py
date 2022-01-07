#!/usr/bin/env python3

from typing import cast, Any, Dict, List, Tuple, Union
from collections import defaultdict
import os


def _check_output(items: List[str], encoding:str = "utf-8") -> str:
    from subprocess import check_output
    return check_output(items).decode(encoding)


def fuzzy_list_to_dict(items: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Converts list to dict preserving elements with duplicate keys
    """
    rc: Dict[str, List[str]] = defaultdict(lambda:[])
    for (key, val) in items:
        rc[key].append(val)
    return dict(rc)


class GitRepo:
    def __init__(self, path: str, remote:str = "origin") -> None:
        self.repo_dir = path
        self.remote = remote

    def _run_git(self, *args: Any) -> str:
        return _check_output(["git", "-C", self.repo_dir] + list(args))

    def revlist(self, revision_range: str) -> List[str]:
        rc = self._run_git("rev-list", revision_range, "--", ".").strip()
        return rc.split("\n") if len(rc) > 0 else []

    def current_branch(self) -> str:
        return self._run_git("symbolic-ref", "--short", "HEAD").strip()

    def checkout(self, branch: str) -> None:
        self._run_git('checkout', branch)

    def show_ref(self, name: str) -> str:
        refs = self._run_git('show-ref', '-s', name).strip().split('\n')
        if not all(refs[i] == refs[0] for i in range(1, len(refs))):
            raise RuntimeError(f"referce {name} is ambigous")
        return refs[0]

    def rev_parse(self, name: str) -> str:
        return self._run_git('rev-parse', '--verify', name).strip()

    def get_merge_base(self, from_ref: str, to_ref: str) -> str:
        return self._run_git('merge-base', from_ref, to_ref).strip()

    def patch_id(self, ref: Union[str, List[str]]) -> List[Tuple[str, str]]:
        is_list = isinstance(ref, list)
        if is_list:
            if len(ref) == 0:
                return []
            ref = " ".join(ref)
        rc = _check_output(['sh', '-c', f'git -C {self.repo_dir} show {ref}|git patch-id --stable']).strip()
        return [cast(Tuple[str, str], x.split(" ", 1)) for x in rc.split("\n")]

    def cherry_pick(self, ref: str) -> None:
        self._run_git('cherry-pick', '-x', ref)

    def compute_branch_diffs(self, from_branch: str, to_branch: str) -> Tuple[List[str], List[str]]:
        """
        Returns list of commmits that are missing in each other branch since their merge base
        Might be slow if merge base is between two branches is pretty far off
        """
        from_ref = self.rev_parse(from_branch)
        to_ref = self.rev_parse(to_branch)
        merge_base = self.get_merge_base(from_ref, to_ref)
        from_commits = self.revlist(f'{merge_base}..{from_ref}')
        to_commits = self.revlist(f'{merge_base}..{to_ref}')
        from_ids = fuzzy_list_to_dict(self.patch_id(from_commits))
        to_ids = fuzzy_list_to_dict(self.patch_id(to_commits))
        for patch_id in set(from_ids).intersection(set(to_ids)):
            if len(from_ids[patch_id]) != len(to_ids[patch_id]):
                # TODO: This is likely an indication of apply-revert-apply sequence on one branch
                # but just apply on another, need to investigate further
                raise RuntimeError("Number of commits with identical patch_ids do not match")
            for commit in from_ids[patch_id]:
                from_commits.remove(commit)
            for commit in to_ids[patch_id]:
                to_commits.remove(commit)
        return (from_commits, to_commits)

    def cherry_pick_commits(self, from_branch: str, to_branch: str) -> None:
        orig_branch = self.current_branch()
        self.checkout(to_branch)
        from_commits, to_commits = self.compute_branch_diffs(from_branch, to_branch)
        if len(from_commits) == 0:
            print("Nothing to do")
            self.checkout(orig_branch)
            return
        for commit in reversed(from_commits):
            self.cherry_pick(commit)
        self.checkout(orig_branch)

    def push(self, branch: str) -> None:
        self._run_git("push", self.remote, branch)


if __name__ == '__main__':
    repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    default_branch = 'main'
    sync_branch = 'sync'
    repo = GitRepo(repo_dir)
    repo.cherry_pick_commits(sync_branch, default_branch)
    repo.push(default_branch)
