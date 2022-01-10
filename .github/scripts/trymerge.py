#!/usr/bin/env python3

import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from typing import Any, Callable, Dict, List, Optional


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
                      data= {"body": comment})


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

def main() -> None:
    import sys
    if len(sys.argv) != 3:
        print("Unexpected number of arguments")
        sys.exit(-1)
    org, project = sys.argv[1].split('/', 1)
    pr_num = int(sys.argv[2])
    print(gh_post_comment(org, project, pr_num, f"argv={sys.argv}"))


if __name__ == "__main__":
    main()
