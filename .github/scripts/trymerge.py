#!/usr/bin/env python3

import json
import re
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from typing import cast, Any, Callable, Dict, List, Optional, Tuple


GH_GET_PR_INFO_QUERY = """
query ($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      state,
      title,
      body,
      headRefName
      headRepository {
        nameWithOwner
      }
      baseRefName
      changedFiles,
      files(last: 100) {
        nodes {
          path,
        }
      }
      reviews(last: 100) {
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

GH_REMOTE_URL_MATCH = re.compile("^https://.*@?github.com/(.+)/(.+)$")


def _check_output(items: List[str], encoding: str = "utf-8") -> str:
    from subprocess import check_output
    return check_output(items).decode(encoding)


def get_git_remote_name() -> str:
    import os
    return os.getenv("GIT_REMOTE_NAME", "origin")


def get_git_repo_dir() -> str:
    import os
    from pathlib import Path
    return os.getenv("GIT_REPO_DIR", str(Path(__file__).resolve().parent.parent))


def gh_get_repo_owner_and_name() -> Tuple[str, str]:
    remote_name = get_git_remote_name()
    repo_dir = get_git_repo_dir()
    url = _check_output(["git", "-C", repo_dir, "remote", "get-url", remote_name])
    rc = GH_REMOTE_URL_MATCH.match(url)
    if rc is None:
        raise RuntimeError(f"Unexpected url format {url}")
    return cast(Tuple[str, str], rc.groups())


def _fetch_url(url: str, *,
               headers: Optional[Dict[str, str]] = None,
               data: Optional[Dict[str, Any]] = None,
               method: Optional[str] = None,
               reader: Callable = lambda x: x.read()) -> Any:
    import os
    if headers is None:
        headers = {}
    token = os.environ.get("GITHUB_TOKEN")
    if token is not None and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'token {token}'
    if data:
        data = json.dumps(data).encode()
    try:
        with urlopen(Request(url, headers=headers, data=data, method=method)) as conn:
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


def gh_post_comment(org: str, project: str, pr_num: int, comment: str) -> List[Dict[str, Any]]:
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


def gh_graphql(query: str, **kwargs: Any) -> List[Dict[str, Any]]:
    return _fetch_url("https://api.github.com/graphql", data={"query": query, "variables": kwargs}, reader=json.load)


def gh_get_pr_info(org: str, proj: str, pr_no: int) -> Any:
    rc = gh_graphql(GH_GET_PR_INFO_QUERY, name=proj, owner=org, number=pr_no)
    return rc["data"]["repository"]["pullRequest"]


def gh_fetch_pr_diff(org: str, proj: str, pr_no: int) -> str:
    headers = {'Accept': 'application/vnd.github.v3.diff'}
    return _fetch_url(f'https://api.github.com/repos/{org}/{proj}/pulls/{pr_no}', headers).decode("utf-8")


def main() -> None:
    import sys
    if len(sys.argv) != 2:
        print("Unexpected number of arguments")
        sys.exit(-1)

    org, project = gh_get_repo_owner_and_name()
    pr_num = int(sys.argv[1])

    info = gh_get_pr_info(org, project, pr_num)
    if int(info["changedFiles"]) > 100:
        gh_post_comment(org, project, pr_num, "Can't merge: too many files changed")
        sys.exit(-1)

    files_changed = [x["path"] for x in info["files"]["nodes"]]
    print(gh_post_comment(org, project, pr_num, f"argv={sys.argv}\nfiles_changed={files_changed}"))


if __name__ == "__main__":
    main()
