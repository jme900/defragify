"""Build the README demo board from made-up sessions, through the real pipeline.

python demo/make_demo.py   writes demo/out/ (fake transcripts, config, labels, tracker) and demo/out/board.html
"""

import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
SKILL = ROOT.parent / "skills" / "work-in-flight" / "worklog.py"
NOW = datetime.now(UTC).replace(second=0, microsecond=0)

# name, family, status, note, summary, tickets [(id, state, column)], sessions [(days_ago, minutes, repo, title)]
THREADS = [
    (
        "Saved cards",
        "Checkout revamp",
        "building",
        "Tokenising done; next = retry on a declined card",
        "Lets returning guests pay with a saved card. Card tokenising and the wallet table are in; the retry flow on declines is next.",
        [("TW-141", "In Progress", "building")],
        [
            (0, 95, "web", "Saved cards: tokenise on first payment"),
            (2, 70, "api", "Wallet table and migration"),
            (6, 40, "api", "Saved cards spike"),
        ],
    ),
    (
        "Apple Pay",
        "Checkout revamp",
        "waiting",
        "PR up; waiting on review from payments",
        "Adds Apple Pay to the booking checkout on web and iOS. Built and tested on sandbox; the PR is in review.",
        [("TW-138", "In Review", "waiting")],
        [(1, 85, "web", "Apple Pay button and merchant validation"), (4, 60, "mobile", "Apple Pay on iOS checkout")],
    ),
    (
        "Address autocomplete",
        "Checkout revamp",
        "idea",
        "Picked the provider; nothing built",
        "Autocompletes the billing address to cut checkout errors. Compared three providers and picked one; no code yet.",
        [],
        [(3, 35, "web", "Compare address autocomplete providers")],
    ),
    (
        "Checkout error copy",
        "Checkout revamp",
        "shipped",
        "Shipped with the new decline messages",
        "Rewrote every checkout error so guests know what to fix. Shipped.",
        [("TW-129", "Done", "shipped")],
        [(9, 45, "web", "Rewrite checkout error messages")],
    ),
    (
        "Faster search results",
        "Search & discovery",
        "building",
        "Index rebuilt; p95 down from 900ms to 310ms",
        "Cuts search latency for the listings page. The listings index was rebuilt and cached; filters are next.",
        [("TW-150", "In Progress", "building"), ("TW-151", "In Progress", "building")],
        [
            (0, 120, "api", "Rebuild listings search index"),
            (1, 75, "api", "Cache popular searches"),
            (5, 50, "api", "Profile slow search queries"),
        ],
    ),
    (
        "Map view",
        "Search & discovery",
        "idea",
        "Sketched it; waiting to see if search speed lands first",
        "Shows search results on a map. Only a sketch and a library comparison so far.",
        [],
        [(11, 30, "web", "Map view sketch")],
    ),
    (
        "Price filter bug",
        "Search & discovery",
        "shipped",
        "Fixed rounding on nightly prices",
        "The price filter dropped listings priced on the boundary. Fixed and released.",
        [("TW-133", "Done", "shipped")],
        [(8, 40, "api", "Price filter boundary bug")],
    ),
    (
        "Offline trips",
        "Mobile app",
        "building",
        "Trips cache works; sync conflicts still open",
        "Lets guests open their upcoming trips with no signal. Caching works; resolving edits made offline is the open part.",
        [],
        [(0, 65, "mobile", "Offline trips cache"), (3, 80, "mobile", "Sync trips after reconnecting")],
    ),
    (
        "Push reminders",
        "Mobile app",
        "waiting",
        "Waiting on the copy from marketing",
        "Reminds guests of check-in times. Built behind a flag; waiting for final copy.",
        [("TW-145", "Blocked", "waiting")],
        [(7, 55, "mobile", "Check-in push reminders")],
    ),
    (
        "Dark mode",
        "Mobile app",
        "dropped",
        "Dropped for now; design wants a full refresh first",
        "Dark theme for the app. Paused until the design refresh.",
        [("TW-120", "Canceled", "dropped")],
        [(16, 30, "mobile", "Dark mode tokens")],
    ),
    (
        "Flaky booking tests",
        "Infra & reliability",
        "building",
        "Two of five flaky tests fixed",
        "The booking test suite fails about one run in five. Found the shared-clock cause; two tests fixed.",
        [],
        [(2, 60, "api", "Track down flaky booking tests")],
    ),
    (
        "Postgres upgrade",
        "Infra & reliability",
        "waiting",
        "Staging upgraded; prod window booked for Thursday",
        "Moves the database to a supported Postgres version. Staging is done; prod waits on the maintenance window.",
        [("TW-142", "Ready for release", "waiting")],
        [(5, 90, "api", "Postgres upgrade on staging"), (12, 45, "api", "Postgres upgrade plan")],
    ),
    (
        "Error alert noise",
        "Infra & reliability",
        "idea",
        "Counted alerts: 70% are one retrying job",
        "Too many pager alerts. Found that most come from one retrying job; no change made yet.",
        [],
        [(24, 25, "api", "Why is the pager so noisy")],
    ),
    (
        "Host payouts research",
        "Research",
        "idea",
        "Notes on three payout providers; no decision",
        "Looking at paying hosts out faster. Compared three providers on fees and countries.",
        [],
        [(25, 40, "api", "Host payout providers")],
    ),
    (
        "Reviews summary idea",
        "Research",
        "idea",
        "Prototype summarised 50 reviews well; cost unclear",
        "Summarise a listing's reviews into a few lines. A quick prototype read well; running cost not checked.",
        [],
        [(13, 55, "api", "Prototype review summaries")],
    ),
    (
        "Onboarding checklist",
        "Team & admin",
        "shipped",
        "Merged; new starters use it from Monday",
        "A first-week checklist for new engineers. Merged into the handbook.",
        [],
        [(10, 30, "web", "New starter checklist")],
    ),
    (
        "Setup & admin",
        "Team & admin",
        "shipped",
        "Answered where the staging keys live",
        "Small questions and machine setup.",
        [],
        [(1, 10, "web", "Where do staging keys live"), (6, 8, "api", "Node version mismatch")],
    ),
    (
        "Weekly metrics email",
        "Team & admin",
        "building",
        "Query done; email template next",
        "A Monday email with bookings, conversion and refunds. The numbers query is written.",
        [],
        [(4, 45, "api", "Weekly metrics query")],
    ),
]


def write_session(sid, repo, branch, title, start, minutes, tokens):
    folder = OUT / "projects" / f"demo-{repo}"
    folder.mkdir(parents=True, exist_ok=True)
    cwd = f"/home/dev/tidewater/{repo}"
    lines = [{"type": "ai-title", "aiTitle": title, "sessionId": sid}]
    for i in range(0, minutes + 1, 2):
        ts = (start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        if i == 0:
            lines.append(
                {
                    "type": "user",
                    "timestamp": ts,
                    "cwd": cwd,
                    "gitBranch": branch,
                    "message": {"role": "user", "content": title},
                }
            )
        else:
            lines.append(
                {
                    "type": "assistant",
                    "timestamp": ts,
                    "cwd": cwd,
                    "gitBranch": branch,
                    "message": {
                        "id": f"{sid}-{i}",
                        "role": "assistant",
                        "content": [],
                        "usage": {"output_tokens": tokens},
                    },
                }
            )
    path = folder / f"{sid}.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8", newline="\n")
    os.utime(path, (start.timestamp() + minutes * 60,) * 2)


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    home = OUT / "home"
    home.mkdir(parents=True)
    labels, tracker = {}, {}
    for name, family, status, note, summary, tickets, sessions in THREADS:
        for i, (days_ago, minutes, repo, title) in enumerate(sorted(sessions)):
            sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"work-in-flight-demo/{name}/{i}"))
            start = NOW - timedelta(days=days_ago, minutes=minutes + 30 * i)
            write_session(sid, repo, f"feature/{name.lower().replace(' ', '-')}", title, start, minutes, 900)
            latest = i == 0
            labels[sid] = {
                "labeled_at": NOW.isoformat(),
                "threads": [
                    {
                        "thread": name,
                        "family": family,
                        "summary": summary,
                        "status": status if latest else ("idea" if status == "idea" else "building"),
                        "note": note if latest else title,
                        "tickets": [t[0] for t in tickets],
                    }
                ],
            }
        for tid, state, column in tickets:
            tracker[tid] = {"state": state, "column": column, "updated": (NOW - timedelta(days=1)).isoformat()}
    config = {"window_days": 30, "scope": {"github_orgs": [], "paths": []}, "tracker": {"kind": "linear", "link": ""}}
    (home / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    (home / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    (home / "tracker.json").write_text(json.dumps(tracker, indent=1), encoding="utf-8")
    env = {**os.environ, "WIF_HOME": str(home), "WIF_PROJECTS": str(OUT / "projects")}
    subprocess.run([sys.executable, str(SKILL), "board", str(OUT / "board.html")], env=env, check=True)


if __name__ == "__main__":
    main()
