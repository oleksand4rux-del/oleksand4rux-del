"""Fetch the contribution calendar and the featured repos from the GitHub GraphQL API.

Writes data/contributions.json and data/repos.json, which scripts/render_readme_cards.py reads.
Needs a token in GITHUB_TOKEN (the Action's built-in token is enough for public activity; a
personal token with read:user also counts private contributions).

Run: GITHUB_TOKEN=... python scripts/fetch_github_data.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGIN = "oleksand4rux-del"
FEATURED = ["cursor-lab"]  # repos that get a card, in order
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

REPO_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    name
    description
    url
    homepageUrl
    stargazerCount
    forkCount
    pushedAt
    primaryLanguage { name color }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.load(res)
    if body.get("errors"):
        sys.exit(f"GitHub API error: {body['errors']}")
    return body["data"]


def main() -> None:
    DATA.mkdir(exist_ok=True)
    cal = graphql(QUERY, {"login": LOGIN})["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for week in cal["weeks"]
        for d in week["contributionDays"]
    ]
    contributions = {
        "login": LOGIN,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": cal["totalContributions"],
        "days": days,
    }
    (DATA / "contributions.json").write_text(json.dumps(contributions, indent=1) + "\n", encoding="utf-8")

    repos = []
    for name in FEATURED:
        repo = graphql(REPO_QUERY, {"owner": LOGIN, "name": name})["repository"]
        if repo:
            repos.append(repo)
    (DATA / "repos.json").write_text(json.dumps(repos, indent=1) + "\n", encoding="utf-8")
    print(f"{len(days)} days, {cal['totalContributions']} contributions, {len(repos)} repos")


if __name__ == "__main__":
    main()
