---
name: defragify
description: Defragments your brain. A board of everything you've been working on across Claude Code sessions. Sorts the last 30 days of sessions into threads (features, ideas, fixes, research), groups related threads into families, shows hours worked, what's going cold, and what is or isn't tracked in your issue tracker (Linear, GitHub Issues, Jira, Asana or none), and publishes it as a private "Work in Flight" artifact you can rearrange. Use for "/defragify", "defragify", "what am I working on", "what's in flight", "what's going cold", "update my board", "how long have I spent on X", and when a board comment asks for a ticket.
---

# defragify

Sorts the person's recent Claude Code sessions into threads and keeps a private board of them, titled "Work in Flight", so many parallel sessions stop being clutter: what they're in, what's going cold, what's linked, what's tracked, and where the hours went.

Paths:
- `<skill dir>` is this skill's base directory. Run the script with `python3 "<skill dir>/worklog.py" <command>` (`python` where that's the name). It needs only the standard library.
- `<home>` is `~/.claude/defragify/`: `config.json`, `labels.json`, `tracker.json`, `board_url.txt`. `python3 "<skill dir>/worklog.py" config` prints the effective config and whether it exists.
- `<scratch>` is your scratchpad (or a temp folder).

Board database (the board artifact's db, read and written with the artifact data tool on the board URL):
- `state/<slug>`: the person's edits, `{name, status, removed, note, mergedInto, ticketsAdded, ticketsRemoved, at}`. Never write these. Never put a ticket from `ticketsRemoved` back in a label.
- `requests/<slug>`: ticket requests from the board, `{name, status: pending|done|failed, via, ticket, message, at}`. You write these when you handle one.
- `<slug>` is the thread name lowercased, runs of non-alphanumerics turned into `-`, trimmed of `-`.

## Before anything: Python

The script needs Python 3.9 or newer. Check with `python3 --version` (then `python --version`). On Windows, a `python3` that opens the Microsoft Store or prints nothing means Python isn't really installed. If neither works, say in one plain sentence that this needs Python, a free one-time install (add the actual error for anyone who wants it), and offer to install it for them (`winget install Python.Python.3.12` on Windows, `brew install python` on a Mac with Homebrew, otherwise point them to python.org). Install only once they say yes, then carry on.

## First run: setup

Match the person: some write no code, many are engineers. Default to everyday words ("Should this count every project you've worked on, or only some folders?"), and switch to the precise terms (GitHub orgs, paths, config fields) as soon as they talk that way or ask. Never hide an option to keep it simple. If `config` says the file doesn't exist, ask these four questions in one round (use the ask-user tool where there is one), then write `<home>/config.json`:

1. **Which sessions count?** Every repo (default), only repos under certain GitHub orgs, or only certain folders. Maps to `scope.github_orgs` / `scope.paths`; both empty means everything.
2. **Issue tracker?** Linear, GitHub Issues, Jira, Asana, or none. Maps to `tracker.kind`. For anything but none, read `trackers/<kind>.md` and fill in what it says (link pattern, where new tickets go). Check the connector or CLI it needs is available and say so if not.
3. **How should new tickets be written?** Optional free text saved as `tracker.ticket_style` (for example "to-do list with acceptance criteria, always an estimate"). Skip for none.
4. **Window?** 30 days unless they want shorter or longer (`window_days`).

```json
{
  "window_days": 30,
  "scope": { "github_orgs": [], "paths": [] },
  "tracker": {
    "kind": "linear",
    "link": "https://linear.app/<workspace>/issue/{id}",
    "create_in": { "team": "<team>", "assignee": "me" },
    "columns": {},
    "ticket_style": ""
  }
}
```

`tracker.columns` maps a tracker status name to a board column (`idea`, `building`, `waiting`, `shipped`, `dropped`) and only lists overrides of the tracker page's defaults. Then do a normal run.

## Run

1. `python3 "<skill dir>/worklog.py" digest > <scratch>/digest.json`
   Gives `known_threads` (name -> status, summary, family) and every session not yet labeled or continued since: title, project, branches, active minutes, first and last prompts, files edited, whether it committed, and `ticket_mentions`.
   If a board exists (`<home>/board_url.txt`), read its `state` and `requests` collections. The person's `state` edits outrank your labels: a thread they moved to Done or Dropped (or removed) stays there unless a new session clearly reopens the work, and then it reappears by itself because the session is newer than the edit. `mergedInto` is the slug of the thread they folded this one into: label new sessions for that work with the target's name. A `note` is their own wording; keep its intent if the thread moves on.
2. Label each session into one or more threads. Write `<scratch>/labels.json` as
   `{"<full session id>": [{"thread": "...", "status": "...", "note": "...", "summary": "...", "family": "...", "tickets": ["..."]}]}`
   - **thread**: reuse a `known_threads` name whenever the session continues that work. A new name only for genuinely new work. Short and recognisable ("Checkout retries", "Pricing page idea"), never a ticket number alone.
   - **status** as of the end of that session: `idea` (explored, nothing built), `building`, `waiting` (blocked on review, merge, deploy or someone else), `shipped`, `dropped`.
   - **note**: where it was left, one concrete line ("committed on main, unpushed; next = deploy"). This is what they read to pick it back up.
   - **summary**: 2-3 plain sentences on the whole thread so far: what it is, what's done, where it stands. Update the thread's current summary.
   - **family**: the larger effort this thread belongs to ("Checkout revamp", "Research"). Reuse existing family names; a handful per board, not one per thread.
   - **tickets**: ids from the configured tracker that this session actually worked on or created for the thread, in the tracker's id format. Leave out passing mentions. Empty for tracker none.
   - Quick questions and machine setup go in one "Setup & admin" thread as `shipped`. A session touching two threads gets two entries.
   **Work in batches.** A first run can find hundreds of sessions. Never read the whole digest at once: take about 30 sessions at a time (oldest first), label them, and run step 3 for that batch before reading the next. Each saved batch drops out of the next `digest`, so an interrupted run picks up where it stopped. Tell the person how many sessions there are and that the first run takes a while; later runs only see what's new.
3. `python3 "<skill dir>/worklog.py" label <scratch>/labels.json` (once per batch)
4. If the tracker isn't none: handle every `requests` doc still `pending` (see Ticket requests), then refresh statuses as `trackers/<kind>.md` describes and write `<home>/tracker.json`:
   `{"<id>": {"state": "<status name>", "column": "idea|building|waiting|shipped|dropped", "updated": "<ISO time>", "url": "<optional>", "label": "<optional short name>"}}`
   for every linked ticket: every label `tickets` entry, every `state` doc's `ticketsAdded`, every `done` request's `ticket`. Map `state` to `column` with the tracker page's defaults plus `tracker.columns`. The board moves each card to its least-advanced open ticket (dropped ones ignored), so this file keeps cards in step with the tracker.
5. `python3 "<skill dir>/worklog.py" board <scratch>/work_in_flight.html`
6. Publish it with the artifact tool. With a URL in `board_url.txt`, read that artifact first if this conversation hasn't, then publish to it without `capabilities` so the stored ones carry forward. Without one, publish a new artifact with icon `board` and `capabilities: {db: {rules: [{path: "", read: "view", write: "owner"}]}, user: {}, comments: {}}`, and save its URL to `board_url.txt`.

Then reply with the link and what's going cold (name, days left, note), skipping anything they moved or removed. Nothing else unless asked.

## Ticket requests

Arrive as a comment sent to Claude on the board ("defragify ticket request: ... requests/<slug>"), or as a `pending` doc found during a run. Same steps either way:

1. Read `requests/<slug>` for the thread name, plus every thread whose `state` doc has `mergedInto` equal to that slug.
2. `python3 "<skill dir>/worklog.py" context "<name>" ["<merged name>" ...]` for every session's prompts, files and commits. Check your memory notes for anything about the thread.
3. Find an existing ticket that already covers it (`trackers/<kind>.md`, "Find"). If one does, link it instead of creating.
4. Otherwise create one ("Create"): where `tracker.create_in` says, written per `tracker.ticket_style` (default: what it's for, a to-do checklist with what the sessions already did ticked, and acceptance criteria). Status follows the card: idea -> backlog or todo, building -> in progress, shipped -> done.
5. Write back: set `requests/<slug>` to `{name, status: "done", ticket: "<id>", via, at}`, pinned to the version you read. On a real failure set `status: "failed"` with a one-line `message`. Add the ticket to the thread's latest session label (`label` with a `tickets` entry), add it to `tracker.json`, then rebuild and republish the board.
6. If it came as a comment: reply in the thread with the ticket and its link, then resolve the thread.

## All-day session

To have board requests handled within a minute, run `/defragify` once in a session that stays open. Its publish arms comment replies for that session, and the board's Create new button sends requests there. With no session listening, the request waits for the next run.

## Questions

For "how long have I spent on X" or "what did I do this week", run steps 1-3 if anything is unlabeled, then answer from the board data (`threads[].hours`, `sessions`, `last`) without publishing. To fix a thread's status or rename one, relabel the affected sessions with `label` (it overwrites per session) and rebuild.
