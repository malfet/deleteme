#!/usr/bin/env python3

from collections import defaultdict
from typing import Dict, List, Tuple
import os


def get_git_remote_name() -> str:
    return os.getenv("GIT_REMOTE_NAME", "origin")


def get_git_repo_dir() -> str:
    from pathlib import Path
    return os.getenv("GIT_REPO_DIR", str(Path(__file__).resolve().parent.parent))


def fuzzy_list_to_dict(items: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Converts list to dict preserving elements with duplicate keys
    """
    rc: Dict[str, List[str]] = defaultdict(lambda: [])
    for (key, val) in items:
        rc[key].append(val)
    return dict(rc)
