#!/usr/bin/env python3

import json
import os
import re
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from typing import cast, Any, Callable, Dict, List, Optional, Tuple
from gitutils import get_git_remote_name, get_git_repo_dir, GitRepo


GH_GET_PR_INFO_QUERY = """
query ($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closed
      isCrossRepository
      author {
        login
      }
      title
      body
      headRefName
      headRepository {
        nameWithOwner
      }
      baseRefName
      baseRepository {
        nameWithOwner
        defaultBranchRef {
          name
        }
      }
      commits(first: 100) {
        nodes {
          commit {
            author {
              user {
                login
              }
              email
              name
            }
            oid
          }
        }
        totalCount
      }
      changedFiles,
      files(last: 100) {
        nodes {
          path
        }
      }
      latestReviews(last: 100) {
        nodes {
          author {
            login
          },
          state
        },
        totalCount
      }
    }
  }
}
"""

RE_GHSTACK_HEAD_REF = re.compile(r"^(gh/[^/]+/[0-9]+/)head$")
RE_GHSTACK_SOURCE_ID = re.compile(r'^ghstack-source-id: (.+)\n?', re.MULTILINE)
RE_PULL_REQUEST_RESOLVED = re.compile(
    r'Pull Request resolved: '
    r'https://github.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>[0-9]+)',
    re.MULTILINE
)


def _fetch_url(url: str, *,
               headers: Optional[Dict[str, str]] = None,
               data: Optional[Dict[str, Any]] = None,
               method: Optional[str] = None,
               reader: Callable = lambda x: x.read()) -> Any:
    if headers is None:
        headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token is not None and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'token {token}'
    data_ = json.dumps(data).encode() if data is not None else None
    try:
        with urlopen(Request(url, headers=headers, data=data_, method=method)) as conn:
            return reader(conn)
    except HTTPError as err:
        if err.code == 403 and all(key in err.headers for key in ['X-RateLimit-Limit', 'X-RateLimit-Used']):
            print(f"Rate limit exceeded: {err.headers['X-RateLimit-Used']}/{err.headers['X-RateLimit-Limit']}")
        raise


def fetch_json(url: str,
               params: Optional[Dict[str, Any]] = None,
               data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if params is not None and len(params) > 0:
        url += '?' + '&'.join(f"{name}={val}" for name, val in params.items())
    return _fetch_url(url, headers=headers, data=data, reader=json.load)


def gh_post_comment(org: str, project: str, pr_num: int, comment: str, dry_run: bool = False) -> List[Dict[str, Any]]:
    if dry_run:
        print(comment)
        return []
    return fetch_json(f'https://api.github.com/repos/{org}/{project}/issues/{pr_num}/comments',
                      data={"body": comment})


def gh_update_pr(org: str, project: str, pr_num: int, *,
                 base: Optional[str] = None,
                 state: Optional[str] = None,
                 title: Optional[str] = None,
                 body: Optional[str] = None,
                 ) -> List[Dict[str, Any]]:
    data = {}
    if base is not None:
        data["base"] = base
    if body is not None:
        data["body"] = body
    if state is not None:
        data["state"] = state
    if title is not None:
        data["title"] = title
    return _fetch_url(f'https://api.github.com/repos/{org}/{project}/issues/{pr_num}',
                      headers={'Accept': 'application/vnd.github.v3+json'},
                      data=data,
                      method="PATCH",
                      reader=json.load)


def gh_graphql(query: str, **kwargs: Any) -> Dict[str, Any]:
    return _fetch_url("https://api.github.com/graphql", data={"query": query, "variables": kwargs}, reader=json.load)


def gh_get_pr_info(org: str, proj: str, pr_no: int) -> Any:
    rc = gh_graphql(GH_GET_PR_INFO_QUERY, name=proj, owner=org, number=pr_no)
    return rc["data"]["repository"]["pullRequest"]


def gh_fetch_pr_diff(org: str, proj: str, pr_no: int) -> str:
    headers = {'Accept': 'application/vnd.github.v3.diff'}
    return _fetch_url(f'https://api.github.com/repos/{org}/{proj}/pulls/{pr_no}', headers=headers).decode("utf-8")


def parse_args() -> Any:
    from argparse import ArgumentParser
    parser = ArgumentParser("Merge PR into default branch")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("pr_num", type=int)
    return parser.parse_args()


class GitHubPR:
    def __init__(self, org: str, project: str, pr_num: int) -> None:
        assert isinstance(pr_num, int)
        self.org = org
        self.project = project
        self.pr_num = pr_num
        self.info = gh_get_pr_info(org, project, pr_num)

    def is_closed(self) -> bool:
        return bool(self.info["closed"])

    def is_cross_repo(self) -> bool:
        return bool(self.info["isCrossRepository"])

    def base_ref(self) -> str:
        return self.info["baseRefName"]

    def default_branch(self) -> str:
        return self.info["baseRepository"]["defaultBranchRef"]["name"]

    def head_ref(self) -> str:
        return self.info["headRefName"]

    def is_ghstack_pr(self) -> bool:
        return RE_GHSTACK_HEAD_REF.match(self.head_ref()) is not None

    def get_changed_files_count(self) -> int:
        return int(self.info["changedFiles"])

    def get_changed_files(self) -> List[str]:
        rc = [x["path"] for x in self.info["files"]["nodes"]]
        if len(rc) != self.get_changed_files_count():
            raise RuntimeError("Changed file count mismatch")
        return rc

    def _get_reviewers(self) -> List[Tuple[str, bool]]:
        reviews_count = int(self.info["latestReviews"]["totalCount"])
        if len(self.info["latestReviews"]["nodes"]) != reviews_count:
            raise RuntimeError("Can't fetch all PR reviews")
        return [(x["author"]["login"], x["state"]) for x in self.info["latestReviews"]["nodes"]]

    def get_approved_by(self) -> List[str]:
        return [login for (login, state) in self._get_reviewers() if state == "APPROVED"]

    def get_commit_count(self) -> int:
        return int(self.info["commits"]["totalCount"])

    def get_pr_creator_login(self) -> str:
        return self.info["author"]["login"]

    def get_committer_login(self, num: int = 0) -> str:
        return self.info["commits"]["nodes"][num]["commit"]["author"]["user"]["login"]

    def get_committer_author(self, num: int = 0) -> str:
        node = self.info["commits"]["nodes"][num]["commit"]["author"]
        return f"{node['name']} <{node['email']}>"

    def get_authors(self) -> Dict[str, str]:
        rc = {}
        for idx in range(self.get_commit_count()):
            rc[self.get_committer_login(idx)] = self.get_committer_author(idx)

        return rc

    def get_author(self) -> str:
        authors = self.get_authors()
        if len(authors) == 1:
            return next(iter(authors.values()))
        return self.get_authors()[self.get_pr_creator_login()]

    def get_title(self) -> str:
        return self.info["title"]

    def get_body(self) -> str:
        return self.info["body"]

    def get_pr_url(self) -> str:
        return f"https://github.com/{self.org}/{self.project}/pull/{self.pr_num}"

    def merge_ghstack_into(self, repo: GitRepo) -> None:
        assert self.is_ghstack_pr()
        # For ghstack, cherry-pick commits based from origin
        orig_ref = f"{repo.remote}/{re.sub(r'/head$', '/orig', self.head_ref())}"
        rev_list = repo.revlist(f"{self.default_branch()}..{orig_ref}")
        for idx, rev in enumerate(reversed(rev_list)):
            msg = repo.commit_message(rev)
            m = RE_PULL_REQUEST_RESOLVED.search(msg)
            assert self.org == m.group('owner') and self.project == m.group('repo')
            pr_num = int(m.group('number'))
            if pr_num != self.pr_num:
                pr = GitHubPR(self.org, self.project, pr_num)
                if pr.is_closed():
                    print(f"Skipping {idx+1} of {len(rev_list)} PR (#{pr_num}) as its already been merged")
                    continue
                check_if_should_be_merged(pr, repo)
            repo.cherry_pick(rev)
            repo.amend_commit_message(re.sub(RE_GHSTACK_SOURCE_ID, "", msg))

    def merge_into(self, repo: GitRepo, dry_run: bool = False) -> None:
        check_if_should_be_merged(self, repo)
        if repo.current_branch() != self.default_branch():
            repo.checkout(self.default_branch())
        if not self.is_ghstack_pr():
            msg = self.get_body()
            msg += f"\nPull Request resolved: {self.get_pr_url()}\n"
            repo._run_git("merge", "--squash", f"{repo.remote}/{self.head_ref()}")
            repo._run_git("commit", f"--author=\"{self.get_author()}\"", "-m", msg)
        else:
            self.merge_ghstack_into(repo)

        if not dry_run:
            repo.push(self.default_branch())


def check_if_should_be_merged(pr: GitHubPR, repo: GitRepo) -> None:
    changed_files = pr.get_changed_files()
    approved_by = pr.get_approved_by()
    author = pr.get_author()


def main() -> None:
    import sys
    args = parse_args()
    repo = GitRepo(get_git_repo_dir(), get_git_remote_name())
    org, project = repo.gh_owner_and_name()

    pr = GitHubPR(org, project, args.pr_num)
    if pr.is_closed():
        print(gh_post_comment(org, project, args.pr_num, f"Can't merge closed PR #{args.pr_num}", dry_run=args.dry_run))
        sys.exit(-1)

    if pr.is_cross_repo():
        print(gh_post_comment(org, project, args.pr_num, "Cross-repo merges are not supported at the moment", dry_run=args.dry_run))
        sys.exit(-1)

    try:
        pr.merge_into(repo, dry_run=args.dry_run)
    except Exception as e:
        gh_post_comment(org, project, args.pr_num, f"Merge failed due to {e}", dry_run=args.dry_run)


if __name__ == "__main__":
    main()
