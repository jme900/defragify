"""defragify: what you've been working on, across AI coding sessions and your own hand-coding, as threads on a board.

python worklog.py config                 print the effective config
python worklog.py digest OUT.json        sessions not yet labeled (or continued since)
python worklog.py label FILE             merge {session_id: [{thread, status, note, summary, family, tickets}]} into the cache
python worklog.py board OUT.html         render the board from labels, tracker statuses and session stats
python worklog.py context OUT.json NAME...  everything recorded for the named threads' sessions, for writing a ticket

Sessions come from Claude Code, Codex, Cursor, GitHub Copilot chat, Antigravity, and "manual" days: editor saves
(VS Code family local history) and your own git commits that happened outside every AI session.

Results go to files, never stdout redirection, so the commands behave the same in bash, zsh and PowerShell.
Folders: CLAUDE_CONFIG_DIR (default ~/.claude) holds projects/ and defragify/; DEFRAGIFY_HOME and
DEFRAGIFY_PROJECTS override each one. CODEX_HOME (default ~/.codex) is where Codex keeps its sessions.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from base64 import b64decode
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from functools import cache
from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse

# Spelled out on purpose: datetime.UTC needs Python 3.11 and this runs on 3.9+.
UTC = timezone(timedelta(0))
IDLE = timedelta(minutes=5)
# Saves and commits come further apart than chat turns: a gap under this still counts as working.
MANUAL_IDLE = timedelta(minutes=30)
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()
HOME = Path(os.environ.get("DEFRAGIFY_HOME") or CLAUDE_DIR / "defragify").expanduser()
PROJECTS = Path(os.environ.get("DEFRAGIFY_PROJECTS") or CLAUDE_DIR / "projects").expanduser()
CODEX = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
if sys.platform == "win32":
    APPS = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
elif sys.platform == "darwin":
    APPS = Path.home() / "Library" / "Application Support"
else:
    APPS = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
# VS Code and its forks share one layout: local history, per-window workspaceStorage, Copilot chats.
EDITORS = [APPS / n / "User" for n in ("Code", "Code - Insiders", "VSCodium", "Cursor", "Windsurf", "Antigravity")]
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
    url = git(cwd, "remote", "get-url", "origin")
    return any(re.search(rf"github\.com[:/]{re.escape(org)}/", url, re.I) for org in scope["github_orgs"])


def git(cwd, *args):
    """stdout of a read-only git command, "" on any failure. safe.directory: repos owned by another
    account (WSL, shared drives) are fine to read."""
    try:
        out = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", cwd, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def load(path, default):
    # utf-8-sig: Windows PowerShell saves files with a byte-order mark.
    return json.loads(Path(path).read_text(encoding="utf-8-sig")) if Path(path).exists() else default


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")


def jsonl(path):
    with path.open(encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d


def when(x):
    """Epoch milliseconds or an ISO string -> aware datetime."""
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x / 1000, UTC)
    # fromisoformat on 3.9/3.10 takes neither "Z" nor more than 6 fractional digits.
    x = re.sub(r"(\.\d{6})\d+", r"\1", x.replace("Z", "+00:00"))
    t = datetime.fromisoformat(x)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def uri_path(uri):
    """file:///c%3A/Users/me/repo -> c:/Users/me/repo"""
    path = unquote(urlparse(uri).path)
    return path[1:] if re.match(r"/[A-Za-z]:", path) else path


def clean(text):
    """A typed prompt with injected context stripped, or None when the message is all injection."""
    text = re.sub(r"<(system-reminder|ide_selection|ide_opened_file)>.*?</\1>", "", text, flags=re.S).strip()
    if not text or text.startswith(("<", "# AGENTS.md", "# Context from my IDE")):
        return None
    return " ".join(text.split())


def raw(source, sid, cwd, stamps, prompts, title=None, files=(), committed=False, out_tokens=0, branches=()):
    return {
        "source": source,
        "id": sid,
        "cwd": cwd,
        "stamps": stamps,
        "prompts": prompts,
        "title": title,
        "files": list(dict.fromkeys(re.split(r"[\\/]", f.rstrip("\\/"))[-1] for f in files)),
        "committed": committed,
        "out_tokens": out_tokens,
        "branches": list(dict.fromkeys(branches)),
    }


# Each reader knows one tool's undocumented on-disk format and nothing else.


def read_claude(since):
    for path in PROJECTS.glob("*/*.jsonl"):
        if mtime(path) < since:
            continue
        stamps, prompts, files, branches = [], [], [], []
        title, cwd, out_tokens, committed, seen = None, None, 0, False, set()
        for d in jsonl(path):
            if d.get("type") == "ai-title":
                title = d.get("aiTitle") or title
            if not d.get("timestamp"):
                continue
            stamps.append(when(d["timestamp"]))
            cwd = cwd or d.get("cwd")
            if d.get("gitBranch") not in (None, "", "HEAD"):
                branches.append(d["gitBranch"])
            msg = d.get("message")
            if d.get("type") == "user" and not d.get("isMeta") and not d.get("isSidechain"):
                content = (msg or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if isinstance(content, str) and (text := clean(content)):
                    prompts.append(text)
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
                    files.append(args["file_path"])
                if block.get("name") in ("Bash", "PowerShell") and "git commit" in str(args.get("command", "")):
                    committed = True
        yield raw("claude", path.stem, cwd, stamps, prompts, title, files, committed, out_tokens, branches)


def read_codex(since):
    index = CODEX / "session_index.jsonl"
    titles = {d.get("id"): d.get("thread_name") for d in jsonl(index)} if index.exists() else {}
    for path in [*CODEX.glob("sessions/*/*/*/*.jsonl"), *CODEX.glob("archived_sessions/*.jsonl")]:
        if mtime(path) < since:
            continue
        meta, stamps, prompts, files, out_tokens, committed = {}, [], [], [], 0, False
        for d in jsonl(path):
            p = d.get("payload") or {}
            if d.get("type") == "session_meta":
                meta = p
            if d.get("timestamp"):
                stamps.append(when(d["timestamp"]))
            kind = p.get("type")
            if kind == "message" and p.get("role") == "user":
                text = " ".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
                # The IDE extension wraps each prompt in editor context; the typed request follows this marker.
                if text := clean(text.split("My request for Codex:", 1)[-1]):
                    prompts.append(text)
            elif kind == "token_count":
                out_tokens = ((p.get("info") or {}).get("total_token_usage") or {}).get("output_tokens", out_tokens)
            elif kind == "custom_tool_call" and p.get("name") == "apply_patch":
                files += re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", str(p.get("input")), re.M)
            elif kind == "function_call" and "git commit" in str(p.get("arguments")):
                committed = True
        if isinstance(meta.get("source"), dict):  # a subagent's rollout; its parent session covers the work
            continue
        sid = meta.get("id") or path.stem
        branch = (meta.get("git") or {}).get("branch")
        yield raw(
            "codex",
            f"codex:{sid}",
            meta.get("cwd"),
            stamps,
            prompts,
            titles.get(sid),
            files,
            committed,
            out_tokens,
            [branch] if branch else [],
        )


def sqlite_rows(db, query):
    if not db.exists():
        return []
    con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        return con.execute(query).fetchall()
    except sqlite3.Error:  # an editor without that table or key
        return []
    finally:
        con.close()


def workspace_folders(editor):
    """workspaceStorage/<hash> -> the folder that window had open."""
    out = {}
    for ws in editor.glob("workspaceStorage/*/workspace.json"):
        folder = load(ws, {}).get("folder", "")
        if folder.startswith("file:"):
            out[ws.parent] = uri_path(folder)
    return out


def read_cursor(since):
    for editor in EDITORS:
        db = editor / "globalStorage" / "state.vscdb"
        if not db.exists() or mtime(db) < since:
            continue
        cwd_of = {}
        for ws, folder in workspace_folders(editor).items():
            for (value,) in sqlite_rows(
                ws / "state.vscdb", "select value from ItemTable where key = 'composer.composerData'"
            ):
                for c in json.loads(value).get("allComposers", []):
                    cwd_of[c.get("composerId")] = folder
        bubbles = dict(
            sqlite_rows(db, "select key, value from cursorDiskKV where key like 'bubbleId:%' and value is not null")
        )
        composers = sqlite_rows(
            db, "select key, value from cursorDiskKV where key like 'composerData:%' and value is not null"
        )
        for key, value in composers:
            c = json.loads(value)
            cid = key.split(":", 1)[1]
            stamps = [when(c[k]) for k in ("createdAt", "lastUpdatedAt") if c.get(k)]
            prompts = []
            for h in c.get("fullConversationHeadersOnly") or []:
                b = json.loads(bubbles.get(f"bubbleId:{cid}:{h.get('bubbleId')}") or "{}")
                if b.get("createdAt"):
                    stamps.append(when(b["createdAt"]))
                if h.get("type") == 1 and (text := clean(b.get("text") or "")):
                    prompts.append(text)
            files = [uri_path(u) for u in c.get("codeBlockData") or {} if u.startswith("file:")]
            yield raw("cursor", f"cursor:{cid}", cwd_of.get(cid), stamps, prompts, c.get("name"), files)


def read_copilot(since):
    for editor in EDITORS:
        for ws, folder in workspace_folders(editor).items():
            for path in ws.glob("chatSessions/*.json*"):
                if mtime(path) < since:
                    continue
                if path.suffix == ".json":
                    snap = load(path, {})
                    requests, title = snap.get("requests") or [], snap.get("customTitle")
                else:
                    # Event log: kind 0 = snapshot, 1 = set the value at key path k, 2 = append to the list at k.
                    requests, title = [], None
                    for d in jsonl(path):
                        v = d.get("v")
                        if d.get("kind") == 0 and isinstance(v, dict):
                            requests, title = list(v.get("requests") or []), v.get("customTitle")
                        elif d.get("kind") == 2 and d.get("k") == ["requests"] and isinstance(v, list):
                            requests += v
                        elif d.get("kind") == 1 and d.get("k") == ["customTitle"]:
                            title = v
                requests = [r for r in requests if isinstance(r, dict)]
                stamps = [when(r["timestamp"]) for r in requests if r.get("timestamp")]
                prompts = [t for r in requests if (t := clean((r.get("message") or {}).get("text") or ""))]
                yield raw("copilot", f"copilot:{path.stem}", folder, stamps, prompts, title)


def varint(b):
    return sum((byte & 0x7F) << (7 * i) for i, byte in enumerate(b))


def read_antigravity(since):
    """Antigravity encrypts its transcripts. Its trajectory index is plain protobuf holding, per conversation,
    a title, the workspace URI, step timestamps and the agent's task summaries, but not the typed prompts."""
    db = APPS / "Antigravity" / "User" / "globalStorage" / "state.vscdb"
    if not db.exists() or mtime(db) < since:
        return
    key = "antigravityUnifiedStateSync.trajectorySummaries"
    for (value,) in sqlite_rows(db, f"select value from ItemTable where key = '{key}'"):
        # Each entry: field 1 = conversation id, then a wrapper whose field 1 is the summary, base64 again.
        for cid, blob in re.findall(
            rb"\x0a\x24([0-9a-f-]{36})\x12[\x80-\xff]*[\x00-\x7f]\x0a[\x80-\xff]*[\x00-\x7f]([A-Za-z0-9+/=]+)",
            b64decode(value),
        ):
            inner = b64decode(blob + b"=" * (-len(blob) % 4))
            title = inner[2 : 2 + inner[1]].decode("utf-8", "ignore") if inner[:1] == b"\x0a" else ""
            ws = re.search(rb"file:///[^\x00-\x20\"']+", inner)
            # google.protobuf.Timestamp: field 1 = seconds (a 5-byte varint for any date this decade), field 2 = nanos.
            stamps = [
                datetime.fromtimestamp(varint(m), UTC)
                for m in re.findall(rb"\x08([\x80-\xff]{4}[\x00-\x7f])\x10", inner)
            ]
            tasks = [json.loads(b'"' + t + b'"') for t in re.findall(rb'"TaskSummary":"((?:[^"\\]|\\.)*)"', inner)]
            prompts = list(dict.fromkeys(t for t in (title, *tasks) if t))
            cwd = uri_path(ws.group().decode()) if ws else None
            yield raw(
                "antigravity",
                f"antigravity:{cid.decode()}",
                cwd,
                [t for t in stamps if t.year >= 2024],
                prompts,
                title or None,
            )


@cache
def repo_root(folder):
    root = git(folder, "rev-parse", "--show-toplevel")
    return os.path.normcase(os.path.abspath(root)) if root else None


def read_manual(since, ai):
    """Coding without an AI session: editor saves (VS Code family local history) and your own commits,
    one session per repo per day. Anything within IDLE of any AI session's activity, in any repo, is left
    out: agents commit across repos, and their time is already counted."""
    busy = sorted(t for r in ai for t in r["stamps"])
    roots = {root for r in ai if r["cwd"] and (root := repo_root(r["cwd"]))}
    saves = defaultdict(list)
    for editor in EDITORS:
        for entries in editor.glob("History/*/entries.json"):
            if mtime(entries) < since:
                continue
            h = load(entries, {})
            if not str(h.get("resource", "")).startswith("file:"):
                continue
            file = uri_path(h["resource"])
            if root := repo_root(os.path.dirname(file)):
                saves[root] += [(when(e["timestamp"]), file) for e in h.get("entries", []) if e.get("timestamp")]
    days = defaultdict(lambda: {"stamps": [], "files": [], "commits": []})

    def add(root, t, **item):
        i = bisect_left(busy, t)
        if t < since or any(abs(t - busy[j]) < IDLE for j in (i - 1, i) if 0 <= j < len(busy)):
            return
        day = days[root, t.astimezone().date().isoformat()]
        day["stamps"].append(t)
        for k, v in item.items():
            day[k].append(v)

    for root in {*saves, *roots}:
        for t, file in saves.get(root, []):
            add(root, t, files=file)
        if email := git(root, "config", "user.email"):
            log = git(root, "log", "--all", f"--author={email}", f"--since={since.isoformat()}", "--format=%aI%x09%s")
            for line in log.splitlines():
                stamp, _, subject = line.partition("\t")
                add(root, when(stamp), commits=subject)
    for (root, date), day in days.items():
        files = [re.split(r"[\\/]", f)[-1] for f in dict.fromkeys(day["files"])]
        prompts = day["commits"] or [f"Edited {', '.join(files[:6])}"]
        sid = f"manual:{os.path.basename(root)}:{date}"
        yield raw("manual", sid, root, day["stamps"], prompts, None, day["files"], bool(day["commits"]))


def finish(r, since):
    stamps = sorted(t for t in r["stamps"] if t >= since)
    if not stamps or not r["prompts"] or not in_scope(r["cwd"]):
        return None
    idle = MANUAL_IDLE if r["source"] == "manual" else IDLE
    active = sum((b - a for a, b in zip(stamps, stamps[1:]) if b - a < idle), timedelta())
    return {
        "id": r["id"],
        "source": r["source"],
        "project": re.split(r"[\\/]", (r["cwd"] or "unknown").rstrip("\\/"))[-1],
        "branches": r["branches"],
        "title": r["title"],
        "start": stamps[0].isoformat(),
        "last": stamps[-1].isoformat(),
        "active_min": round(active.total_seconds() / 60),
        "out_tokens": r["out_tokens"],
        "days": sorted({t.astimezone().date().isoformat() for t in stamps}),
        "prompts": r["prompts"],
        "files": r["files"],
        "committed": r["committed"],
    }


@cache
def all_sessions():
    since = datetime.now(UTC) - timedelta(days=config()["window_days"])
    ai = []
    for reader in (read_claude, read_codex, read_cursor, read_copilot, read_antigravity):
        try:
            ai += list(reader(since))
        except Exception as e:  # one tool changing its format must not cost the board every other source
            print(f"skipped {reader.__name__}: {e!r}", file=sys.stderr)
    found = (finish(r, since) for r in [*ai, *read_manual(since, ai)])
    return tuple(s for s in found if s)


def sessions():
    # Fresh copies: digest mutates what it gets.
    return [dict(s) for s in all_sessions()]


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
                    "source": s["source"],
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
