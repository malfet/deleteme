#!/usr/bin/env python3

from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib import parse
import os
import sys
import json

if __name__ == "__main__":
    token = os.environ.get("GITHUB_TOKEN")
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token is not None:
        headers['Authorization'] = f'token {token}'
    data=json.dumps({"body":f"body " + " ".join(sys.argv)}).encode()
    req = Request("https://api.github.com/repos/malfet/deleteme/issues/1/comments", headers=headers, data=data, method='POST')
    with urlopen(req) as reply:
        print(reply.read())
