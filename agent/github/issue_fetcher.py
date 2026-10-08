import re
from dataclasses import dataclass, field

import requests

URL_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


@dataclass
class Issue:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    comments: list = field(default_factory=list)

    def to_text(self) -> str:
        parts = [f"Title: {self.title}", "", self.body or "(no description)"]
        for i, c in enumerate(self.comments, 1):
            parts += ["", f"--- Comment {i} ---", c]
        return "\n".join(parts)


def parse_issue_url(url: str) -> tuple[str, str, int]:
    m = URL_RE.search(url)
    if not m:
        raise ValueError(f"Not a GitHub issue URL: {url}")
    return m.group(1), m.group(2), int(m.group(3))


def fetch_issue(url: str, token: str = "", max_comments: int = 20) -> Issue:
    owner, repo, number = parse_issue_url(url)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    api = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    r = requests.get(api, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    c = requests.get(f"{api}/comments", headers=headers, params={"per_page": max_comments}, timeout=30)
    c.raise_for_status()
    comments = [f"{x['user']['login']}: {x['body'][:2000]}" for x in c.json()]

    return Issue(owner, repo, number, data["title"], data.get("body") or "", comments)