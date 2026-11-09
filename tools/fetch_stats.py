"""Fetch comprehensive GitHub telemetry into cache/stats.json and cache/calendar.json.

Expanded metrics:
- Repos, Contributed Repos, Total Stars, Total Forks, Followers
- All-time Commits, Pull Requests (PRs), Issues
- Net Lines of Code (LOC), Additions (++), Deletions (--) cached per repo OID
- Flagship `oferchen/rsync` (`oc-rsync`) live stars, forks, and latest release version
- Current & Longest contribution streaks
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
STATS_OUT = CACHE / "stats.json"
LOC_CACHE = CACHE / "loc.json"
CALENDAR_OUT = CACHE / "calendar.json"

LOGIN = os.environ.get("GH_LOGIN", "oferchen")
ENDPOINT = "https://api.github.com/graphql"
TOKEN = os.environ.get("GITHUB_TOKEN")

session = requests.Session()


def fetch_linkedin_stats() -> dict:
    """Fetch live public profile telemetry & category stats from LinkedIn."""
    url = "https://il.linkedin.com/in/0ferchen"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    stats = {
        "followers": "3,232",
        "connections": "500+",
        "headline": "Sr. DevOps, Platform & AI Infra",
        "top_certs": ["CKA", "CKAD", "Vault", "Terraform", "AWS-SAA", "PCAP"],
    }
    try:
        import urllib.request
        import re
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html_text = resp.read().decode("utf-8", errors="ignore")

        # Extract from JSON-LD schema
        m = re.findall(r'<script type="application/ld\+json">\s*({.*?})\s*</script>', html_text, re.DOTALL)
        for raw in m:
            try:
                data = json.loads(raw)
                for item in data.get("@graph", []):
                    if item.get("@type") == "Person":
                        inter = item.get("interactionStatistic", {})
                        if inter.get("userInteractionCount"):
                            count = inter["userInteractionCount"]
                            stats["followers"] = f"{count:,}"
                        if item.get("description"):
                            stats["headline"] = item["description"].split("…")[0].strip()
            except Exception:
                pass

        # Extract connection count from meta
        meta_m = re.search(r'<meta\s+property="og:description"\s+content="(.*?)"', html_text)
        if meta_m:
            desc = meta_m.group(1)
            conn_m = re.search(r'(\d+\+?)\s*(?:חיבורים|connections)', desc)
            if conn_m:
                stats["connections"] = conn_m.group(1)

        # Extract certifications from profile H3 headings
        all_h3 = re.findall(r'<h3[^>]*>\s*(.*?)\s*</h3>', html_text, re.DOTALL)
        found_certs = []
        for h in all_h3:
            clean = re.sub(r'<[^>]+>', '', h).strip()
            if "CKA:" in clean:
                found_certs.append("CKA")
            elif "CKAD:" in clean:
                found_certs.append("CKAD")
            elif "Vault" in clean:
                found_certs.append("Vault")
            elif "Terraform" in clean:
                found_certs.append("Terraform")
            elif "AWS Certified" in clean or "Solutions Architect" in clean:
                found_certs.append("AWS-SAA")
            elif "PCAP" in clean:
                found_certs.append("PCAP")
        if found_certs:
            stats["top_certs"] = list(dict.fromkeys(found_certs))

        print(f"  linkedin: {stats['followers']} followers | {stats['connections']} connections | {len(stats['top_certs'])} certs")
    except Exception as exc:
        print(f"  warning: could not fetch live LinkedIn data: {exc}", file=sys.stderr)

    return stats


def query(document: str, variables: dict, attempt: int = 0) -> dict:
    resp = session.post(
        ENDPOINT,
        json={"query": document, "variables": variables},
        headers={"Authorization": f"bearer {TOKEN}"},
        timeout=30,
    )
    if resp.status_code in (403, 429, 502, 503, 504) and attempt < 3:
        wait = int(resp.headers.get("Retry-After", 15 * (attempt + 1)))
        print(f"  HTTP {resp.status_code}, sleeping {wait}s", file=sys.stderr)
        time.sleep(wait)
        return query(document, variables, attempt + 1)

    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(f"GraphQL error: {json.dumps(payload['errors'], indent=2)}")
    return payload["data"]


REPOS_Q = """
query($login:String!, $after:String) {
  user(login:$login) {
    id
    createdAt
    avatarUrl(size:460)
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, after:$after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        nameWithOwner
        stargazerCount
        forkCount
        releases(first:1, orderBy:{field:CREATED_AT, direction:DESC}) {
          nodes { tagName }
        }
        defaultBranchRef { target { ... on Commit { oid } } }
      }
    }
  }
}
"""

CALENDAR_Q = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date weekday contributionCount contributionLevel }
        }
      }
    }
  }
}
"""

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

CONTRIB_Q = """
query($login:String!) {
  user(login:$login) {
    repositoriesContributedTo(
      first:1,
      contributionTypes:[COMMIT, PULL_REQUEST, REPOSITORY]
    ) { totalCount }
  }
}
"""

COMMITS_Q = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

HISTORY_Q = """
query($owner:String!, $name:String!, $authorId:ID!, $after:String) {
  repository(owner:$owner, name:$name) {
    defaultBranchRef {
      target { ... on Commit {
        history(first:100, after:$after, author:{id:$authorId}) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes { additions deletions }
        }
      }}
    }
  }
}
"""


def fetch_repos() -> tuple[dict, list[dict]]:
    repos: list[dict] = []
    meta: dict = {}
    after = None
    while True:
        data = query(REPOS_Q, {"login": LOGIN, "after": after})["user"]
        if not meta:
            meta = {
                "id": data["id"],
                "createdAt": data["createdAt"],
                "avatarUrl": data.get("avatarUrl", f"https://github.com/{LOGIN}.png?size=460"),
                "followers": data["followers"]["totalCount"],
                "prs": (data.get("pullRequests") or {}).get("totalCount", 0),
                "issues": (data.get("issues") or {}).get("totalCount", 0),
                "repos": data["repositories"]["totalCount"],
            }
        repos.extend(data["repositories"]["nodes"])
        page = data["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            return meta, repos
        after = page["endCursor"]


def fetch_commit_total(created_at: str) -> int:
    start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    total = 0
    cursor = start
    while cursor < now:
        try:
            next_year = cursor.replace(year=cursor.year + 1)
        except ValueError:
            next_year = cursor.replace(year=cursor.year + 1, day=28)
        end = min(next_year, now)
        c = query(COMMITS_Q, {
            "login": LOGIN,
            "from": cursor.isoformat().replace("+00:00", "Z"),
            "to": end.isoformat().replace("+00:00", "Z"),
        })["user"]["contributionsCollection"]
        total += c["totalCommitContributions"] + c["restrictedContributionsCount"]
        cursor = end
    return total


def fetch_loc(repos: list[dict], author_id: str) -> tuple[int, int]:
    cache = json.loads(LOC_CACHE.read_text(encoding="utf-8")) if LOC_CACHE.exists() else {}
    added = deleted = 0
    walked = reused = 0

    for repo in repos:
        name = repo["nameWithOwner"]
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        head = target.get("oid")
        if not head:
            continue

        hit = cache.get(name)
        if hit and hit.get("oid") == head:
            added += hit["added"]
            deleted += hit["deleted"]
            reused += 1
            continue

        owner, short = name.split("/", 1)
        r_add = r_del = 0
        after = None
        try:
            while True:
                repo_data = query(HISTORY_Q, {
                    "owner": owner, "name": short,
                    "authorId": author_id, "after": after,
                }).get("repository") or {}
                branch_ref = repo_data.get("defaultBranchRef") or {}
                target_obj = branch_ref.get("target") or {}
                hist = target_obj.get("history")
                if not hist:
                    break
                for node in hist.get("nodes") or []:
                    if node:
                        r_add += node.get("additions") or 0
                        r_del += node.get("deletions") or 0
                if not hist["pageInfo"]["hasNextPage"]:
                    break
                after = hist["pageInfo"]["endCursor"]
        except Exception as exc:
            print(f"  skipping LOC walk on {name}: {exc}", file=sys.stderr)
            continue

        cache[name] = {"oid": head, "added": r_add, "deleted": r_del}
        added += r_add
        deleted += r_del
        walked += 1
        print(f"  walked {name}: +{r_add:,} -{r_del:,}")

    CACHE.mkdir(exist_ok=True)
    LOC_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    print(f"  loc cache: {walked} walked, {reused} reused")
    return added, deleted


def fetch_calendar() -> tuple[dict, int, int]:
    cal = query(CALENDAR_Q, {"login": LOGIN})["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = []
    flat_days = []
    for week in cal["weeks"]:
        slots: list[dict | None] = [None] * 7
        for day in week["contributionDays"]:
            entry = {
                "date": day["date"],
                "count": day["contributionCount"],
                "level": LEVELS[day["contributionLevel"]],
            }
            slots[day["weekday"]] = entry
            flat_days.append(entry)
        weeks.append(slots)

    # Calculate longest and current streaks within the 53-week window
    longest = cur = 0
    for d in flat_days:
        if d["count"] > 0:
            cur += 1
            if cur > longest:
                longest = cur
        else:
            cur = 0
    # If today has 0 commits so far, check if yesterday had an active streak
    if cur == 0 and len(flat_days) >= 2 and flat_days[-2]["count"] > 0:
        idx = len(flat_days) - 2
        while idx >= 0 and flat_days[idx]["count"] > 0:
            cur += 1
            idx -= 1

    return {"total": cal["totalContributions"], "weeks": weeks}, cur, longest


def main() -> None:
    if not TOKEN:
        raise SystemExit("GITHUB_TOKEN is not set")

    print(f"fetching stats for {LOGIN}")
    meta, repos = fetch_repos()
    print(f"  repos: {meta['repos']} | followers: {meta['followers']}")

    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r.get("forkCount", 0) for r in repos)

    # Extract flagship oc-rsync metrics
    rsync_stars, rsync_forks, rsync_ver = 113, 5, "v0.4.2"
    for r in repos:
        if r.get("name") == "rsync":
            rsync_stars = r.get("stargazerCount", rsync_stars)
            rsync_forks = r.get("forkCount", rsync_forks)
            rel_nodes = ((r.get("releases") or {}).get("nodes")) or []
            if rel_nodes and rel_nodes[0].get("tagName"):
                rsync_ver = rel_nodes[0]["tagName"]
            break

    contrib = query(CONTRIB_Q, {"login": LOGIN})["user"]["repositoriesContributedTo"]["totalCount"]
    commits = fetch_commit_total(meta["createdAt"])
    added, deleted = fetch_loc(repos, meta["id"])
    calendar, streak_cur, streak_max = fetch_calendar()
    li_stats = fetch_linkedin_stats()

    stats = {
        "repos": meta["repos"],
        "contrib": contrib,
        "stars": stars,
        "forks": forks,
        "commits": commits,
        "prs": meta["prs"],
        "issues": meta["issues"],
        "followers": meta["followers"],
        "loc": added - deleted,
        "added": added,
        "deleted": deleted,
        "rsync_stars": rsync_stars,
        "rsync_forks": rsync_forks,
        "rsync_ver": rsync_ver,
        "streak_current": streak_cur,
        "streak_longest": streak_max,
        "linkedin_followers": li_stats.get("followers", "3,232"),
        "linkedin_connections": li_stats.get("connections", "500+"),
        "linkedin_certs": ", ".join(li_stats.get("top_certs", ["CKA", "CKAD", "Vault", "Terraform", "AWS-SAA", "PCAP"])),
        "linkedin_headline": li_stats.get("headline", "Sr. DevOps, Platform & AI Infra"),
        "avatar_url": meta.get("avatarUrl", f"https://github.com/{LOGIN}.png?size=460"),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    CACHE.mkdir(exist_ok=True)
    STATS_OUT.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))

    CALENDAR_OUT.write_text(json.dumps(calendar, indent=1), encoding="utf-8")
    print(f"  calendar: {len(calendar['weeks'])} weeks, {calendar['total']} contributions")


if __name__ == "__main__":
    main()
