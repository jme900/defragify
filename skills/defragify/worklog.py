"""defragify: what you've been working on across Claude Code sessions, as threads on a board.

python worklog.py config                 print the effective config
python worklog.py digest OUT.json        sessions not yet labeled (or continued since)
python worklog.py label FILE             merge {session_id: [{thread, status, note, summary, family, tickets}]} into the cache
python worklog.py board OUT.html         render the board from labels, tracker statuses and session stats
python worklog.py context OUT.json NAME...  everything recorded for the named threads' sessions, for writing a ticket

Results go to files, never stdout redirection, so the commands behave the same in bash, zsh and PowerShell.
Folders: CLAUDE_CONFIG_DIR (default ~/.claude) holds projects/ and defragify/; DEFRAGIFY_HOME and
DEFRAGIFY_PROJECTS override each one.
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from functools import cache
from pathlib import Path

# Spelled out on purpose: datetime.UTC needs Python 3.11 and this runs on 3.9+.
UTC = timezone(timedelta(0))
IDLE = timedelta(minutes=5)
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
HOME = Path(os.environ.get("DEFRAGIFY_HOME") or CLAUDE_DIR / "defragify").expanduser()
PROJECTS = Path(os.environ.get("DEFRAGIFY_PROJECTS") or CLAUDE_DIR / "projects").expanduser()
CONFIG = HOME / "config.json"
LABELS = HOME / "labels.json"
TRACKER = HOME / "tracker.json"
TEMPLATE = Path(__file__).with_name("board.html")
STATUSES = ("idea", "building", "waiting", "shipped", "dropped")
ID_PATTERNS = {
    "linear": r"\b[A-Z][A-Z0-9]{1,9}-\d+\b",
    "jira": r"\b[A-Z][A-Z0-9]{1,9}-\d+\b",
    "github": r"\b[\w.-]+/[\w.-]+#\d+\b",
    "asana": r"app\.asana\.com/[\w/]+",
    "none": r"(?!)",
}


@cache
def config():
    cfg = load(CONFIG, {})
    tracker = {"kind": "none", **cfg.get("tracker", {})}
    tracker.setdefault("id_pattern", ID_PATTERNS.get(tracker["kind"], ID_PATTERNS["none"]))
    return {
        "window_days": cfg.get("window_days", 30),
        "scope": {"github_orgs": [], "paths": [], **cfg.get("scope", {})},
        "tracker": tracker,
    }


@cache
def in_scope(cwd):
    """Empty scope = every session. Otherwise the session's folder must sit under a listed path
    or be a git repo whose origin is on one of the listed GitHub orgs."""
    scope = config()["scope"]
    if not scope["github_orgs"] and not scope["paths"]:
        return True
    if not cwd:
        return False
    here = os.path.normcase(os.path.abspath(cwd))
    for p in scope["paths"]:
        root = os.path.normcase(os.path.abspath(os.path.expanduser(p)))
        if here == root or here.startswith(root.rstrip("\\/") + os.sep):
            return True
    if not scope["github_orgs"]:
        return False
    # safe.directory: read-only lookup; repos owned by another account (WSL, shared drives) are fine.
    try:
        url = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", cwd, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return any(re.search(rf"github\.com[:/]{re.escape(org)}/", url, re.I) for org in scope["github_orgs"])


def load(path, default):
    # utf-8-sig: Windows PowerShell saves files with a byte-order mark.
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) if Path(path).exists() else default


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")


def prompt_text(d):
    if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
        return None
    content = (d.get("message") or {}).get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    content = re.sub(r"<(system-reminder|ide_selection|ide_opened_file)>.*?</\1>", "", content, flags=re.S).strip()
    if not content or content.startswith("<"):
        return None
    return " ".join(content.split())


def scan(path, since):
    """Read one Claude Code transcript. Its format is undocumented, so all knowledge of it lives here."""
    stamps, prompts, files, branches = [], [], {}, {}
    title, project, cwd, out_tokens, committed, seen = None, None, None, 0, False, set()
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("type") == "ai-title":
                title = d.get("aiTitle") or title
            if not d.get("timestamp"):
                continue
            stamps.append(datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")))
            if d.get("cwd") and not cwd:
                cwd = d["cwd"]
                project = re.split(r"[\\/]", cwd.rstrip("\\/"))[-1]
            if d.get("gitBranch") not in (None, "", "HEAD"):
                branches[d["gitBranch"]] = 1
            if text := prompt_text(d):
                prompts.append(text)
            msg = d.get("message")
            if d.get("type") != "assistant" or not isinstance(msg, dict):
                continue
            if msg.get("id") not in seen:
                seen.add(msg.get("id"))
                out_tokens += (msg.get("usage") or {}).get("output_tokens", 0)
            for block in msg.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                args = block.get("input") or {}
                if block.get("name") in ("Edit", "Write", "NotebookEdit") and args.get("file_path"):
                    files[re.split(r"[\\/]", args["file_path"])[-1]] = 1
                if block.get("name") in ("Bash", "PowerShell") and "git commit" in str(args.get("command", "")):
                    committed = True
    stamps = sorted(t for t in stamps if t >= since)
    if not stamps or not prompts or not in_scope(cwd):
        return None
    active = sum((b - a for a, b in zip(stamps, stamps[1:]) if b - a < IDLE), timedelta())
    return {
        "id": path.stem,
        "project": project or path.parent.name,
        "branches": list(branches),
        "title": title,
        "start": stamps[0].isoformat(),
        "last": stamps[-1].isoformat(),
        "active_min": round(active.total_seconds() / 60),
        "out_tokens": out_tokens,
        "days": sorted({t.astimezone().date().isoformat() for t in stamps}),
        "prompts": prompts,
        "files": list(files),
        "committed": committed,
    }


def sessions():
    since = datetime.now(UTC) - timedelta(days=config()["window_days"])
    for path in PROJECTS.glob("*/*.jsonl"):
        if datetime.fromtimestamp(path.stat().st_mtime, UTC) < since:
            continue
        if s := scan(path, since):
            yield s


def digest(out):
    labels = load(LABELS, {})
    ticket_id = re.compile(config()["tracker"]["id_pattern"])
    todo = []
    for s in sessions():
        seen = labels.get(s["id"])
        if seen and seen["labeled_at"] >= s["last"]:
            continue
        p = s.pop("prompts")
        s["ticket_mentions"] = sorted(set(ticket_id.findall(" ".join([*p, s["title"] or ""]))))
        s["prompts"] = [x[:220] for x in (p[:3] + p[-2:] if len(p) > 5 else p)]
        s["files"] = s["files"][:12]
        del s["days"]
        todo.append(s)
    known = {}
    for entry in sorted(labels.values(), key=lambda e: e["labeled_at"]):
        for t in entry["threads"]:
            k = known.setdefault(t["thread"], {})
            k["status"] = t["status"]
            for field in ("summary", "family"):
                if t.get(field):
                    k[field] = t[field]
    save(out, {"known_threads": known, "sessions": sorted(todo, key=lambda s: s["start"])})
    print(f"{len(todo)} sessions to label, {len(known)} known threads -> {out}")


def label(file):
    new = load(file, {})
    labels = load(LABELS, {})
    now = datetime.now(UTC)
    for sid, threads in new.items():
        bad = [t for t in threads if t.get("status") not in STATUSES or not t.get("thread")]
        if bad:
            sys.exit(f"{sid}: each thread needs a name and a status in {STATUSES}: {bad}")
        labels[sid] = {"labeled_at": now.isoformat(), "threads": threads}
    cutoff = (now - timedelta(days=config()["window_days"] + 5)).isoformat()
    labels = {k: v for k, v in labels.items() if v["labeled_at"] >= cutoff}
    HOME.mkdir(parents=True, exist_ok=True)
    save(LABELS, labels)
    print(f"{len(new)} sessions labeled, {len(labels)} in cache")


def board(out):
    labels = load(LABELS, {})
    threads = defaultdict(
        lambda: {"hours": 0.0, "tokens": 0, "sessions": [], "days": set(), "projects": set(), "tickets": set()}
    )
    unlabeled, count = 0, 0
    for s in sessions():
        count += 1
        entry = labels.get(s["id"])
        if not entry or not entry["threads"]:
            unlabeled += 1
            continue
        share = 1 / len(entry["threads"])
        for t in entry["threads"]:
            th = threads[t["thread"]]
            th["hours"] += s["active_min"] / 60 * share
            th["tokens"] += round(s["out_tokens"] * share)
            th["days"].update(s["days"])
            th["projects"].add(s["project"])
            th["tickets"].update(t.get("tickets", []))
            th["sessions"].append(
                {
                    "last": s["last"],
                    "title": s["title"] or s["prompts"][0][:80],
                    "min": s["active_min"],
                    "share_min": round(s["active_min"] * share, 1),
                    "share_tok": round(s["out_tokens"] * share),
                }
            )
            if s["last"] >= th.get("last", ""):
                th.update(last=s["last"], status=t["status"], note=t.get("note", ""))
            for field in ("summary", "family"):
                if t.get(field) and s["last"] >= th.get(f"{field}_at", ""):
                    th.update({field: t[field], f"{field}_at": s["last"]})
    rows = []
    for name, th in threads.items():
        th["sessions"].sort(key=lambda x: x["last"], reverse=True)
        rows.append(
            {
                **th,
                "name": name,
                "hours": round(th["hours"], 1),
                "days": sorted(th["days"]),
                "projects": sorted(th["projects"]),
                "tickets": sorted(th["tickets"]),
            }
        )
    tracker = config()["tracker"]
    data = {
        "generated": datetime.now(UTC).isoformat(),
        "window_days": config()["window_days"],
        "session_count": count,
        "unlabeled": unlabeled,
        "threads": rows,
        "tracker": {
            "kind": tracker["kind"],
            "link": tracker.get("link", ""),
            "id_pattern": tracker["id_pattern"],
            "entries": load(TRACKER, {}),
        },
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    Path(out).write_text(html, encoding="utf-8", newline="\n")
    print(f"{len(rows)} threads, {count} sessions ({unlabeled} unlabeled) -> {out}")


def context(out_file, names):
    labels = load(LABELS, {})
    wanted = {n.lower() for n in names}
    found = []
    for s in sessions():
        match = [t for t in (labels.get(s["id"]) or {}).get("threads", []) if t["thread"].lower() in wanted]
        if match:
            found.append({**s, "labels": match, "prompts": [x[:1500] for x in s["prompts"]]})
    save(out_file, sorted(found, key=lambda s: s["start"]))
    print(f"{len(found)} sessions -> {out_file}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "config":
        print(json.dumps({**config(), "home": str(HOME), "exists": CONFIG.exists()}, indent=1))
    elif cmd == "digest":
        digest(sys.argv[2])
    elif cmd == "label":
        label(sys.argv[2])
    elif cmd == "board":
        board(sys.argv[2])
    elif cmd == "context":
        context(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(__doc__)
