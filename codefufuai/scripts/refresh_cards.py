#!/usr/bin/env python3
"""Refresh all of codefufuai's cards from live GitHub data — her daemon.

The operator runs token-stats locally as a daemon; she lives on GitHub, so
her daemon is this script on a cron. Steps:

1. fetch her contribution wall (GraphQL contributionsCollection) →
   data/contribs.json — the snake card's meal, literally 她自己的提交墙
2. count her authored PRs (search API) → data/stats.json — feeds the
   profile card's "PRs opened" line
3. regenerate the snake card and the profile card (all theme/language
   variants) into assets/
4. bump the README ?v= cache-bust params

Git commit/push is the caller's job (the workflow does it); this script
only writes files. Runs locally too (any authenticated gh).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HERE = Path(__file__).resolve().parent

CALENDAR_QUERY = (
    "query($l:String!){user(login:$l){createdAt "
    "contributionsCollection{contributionCalendar{totalContributions "
    "weeks{contributionDays{date contributionCount color}}}}}}"
)


def gh(*args):
    r = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return r.stdout


def main():
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "codefufuai")
    DATA.mkdir(parents=True, exist_ok=True)

    cal = gh("api", "graphql", "-f", f"query={CALENDAR_QUERY}", "-f", f"l={owner}")
    (DATA / "contribs.json").write_text(cal)

    # search API: PRs she authored, any state (防限流：单请求取 total_count)
    res = json.loads(gh("api", f"search/issues?q=author:{owner}+type:pr&per_page=1"))
    stats = {"prs_opened": res["total_count"]}
    (DATA / "stats.json").write_text(json.dumps(stats) + "\n")

    subprocess.run([sys.executable, str(HERE / "gen_snake_card.py")], check=True)
    subprocess.run([sys.executable, str(HERE / "gen_codefufuai_card.py"),
                    "--stats-json", str(DATA / "stats.json")], check=True)

    v = int(time.time())
    for name in ("README.md", "README.zh-CN.md"):
        p = ROOT / name
        if p.exists():
            p.write_text(re.sub(r"\?v=\d+", f"?v={v}", p.read_text()))
    print(f"refreshed: wall total="
          f"{json.loads(cal)['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']}"
          f", prs_opened={stats['prs_opened']}, README v={v}")


if __name__ == "__main__":
    main()
