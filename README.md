<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo-light.svg">
    <img alt="defragify logo: scattered green pixels defragment into a pixel-art brain" src="docs/logo-light.svg" width="220">
  </picture>
</p>

<h1 align="center">defragify</h1>

<p align="center">
  <b>Defragment your brain.</b><br>
  A board of everything you've been working on with Claude Code, Codex, Cursor and friends, plus what you coded by hand.
</p>

<p align="center">
  <a href="#install"><img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-D97757"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-2f8a55"></a>
  <img alt="Python 3.9 or newer" src="https://img.shields.io/badge/python-3.9%2B-3776AB">
  <img alt="Runs on macOS, Linux and Windows" src="https://img.shields.io/badge/macOS_%7C_Linux_%7C_Windows-supported-555">
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#what-it-shows">What it shows</a> ·
  <a href="#using-the-board">Using the board</a> ·
  <a href="#trackers">Trackers</a> ·
  <a href="#what-it-reads-and-where-it-goes">Privacy</a>
</p>

---

With Claude you can run ten sessions across three repos and chase a dozen ideas in a week. Most of that is fine to forget. Some of it isn't, and it gets lost in the clutter: the idea you'd half-explored, the fix waiting on a review, the feature that was never ticketed. defragify reads your recent sessions, sorts them into threads, and keeps them on one private board, so you can see where you're at and let the rest go.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/board-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/board-light.png">
  <img alt="The defragify board: hours worked per day as a defrag map, what's going cold, and open threads in Ideas, Building and Waiting columns" src="docs/board-light.png">
</picture>

## Quick start

No coding needed. In Claude Code:

1. Type `/plugin marketplace add jme900/defragify` and press Enter.
2. Type `/plugin install defragify@defragify` and press Enter. (Using Claude Code inside VS Code? See [Install](#install) below.)
3. Start a new session and type `/defragify`. Answer four quick questions, and Claude builds your board and gives you the link.

The first run reads up to a month of your sessions, so give it a few minutes. If you don't have Python, Claude will say so and offer to install it. After that, run `/defragify` whenever you want the board brought up to date.

## What it shows

- **Where your time went.** One sentence up top says what you worked on and for how long ("This week you worked on 9 things for 14.2h"), with a bar chart of hours worked per day. Hours are active time: gaps of more than five minutes don't count.
- **What's still open.** Ideas, Building and Waiting fill the board. Finished and dropped work folds into one line at the bottom.
- **What's going cold.** Anything you haven't worked on in a while fades, and a "Going cold" band lists what's about to drop off the 30-day window. Pick it back up or let it go.
- **What's linked.** Claude groups related threads into families ("Checkout revamp") and shows the family on each card. Group the board by family from the View menu.
- **What's tracked.** If you use an issue tracker, each card shows its tickets and moves with them: a card is only as far along as its least-advanced ticket. Open work with no ticket gets an "untracked" tag.

## Install

In Claude Code:

```
/plugin marketplace add jme900/defragify
/plugin install defragify@defragify
```

In the VS Code extension, where `/plugin` isn't available, run the same two steps in a terminal:

```
claude plugin marketplace add jme900/defragify
claude plugin install defragify@defragify
```

Start a new session afterwards so the skill loads.

Then run `/defragify`. The first run asks four questions: which sessions count, which tracker you use, how new tickets should be written, and how many days to keep. It then sorts your sessions and publishes your board as a private artifact on claude.ai. Run it again whenever you want the board brought up to date.

## Using the board

Click a card to open it: a short summary of the thread, its tickets, hours, sessions, and its controls.

| To | Do |
|---|---|
| Move a card | Drag it to another column, or use its status menu |
| Merge two threads | Drag one onto the other and hold until it says "Release to merge" |
| Change the note | Click the pen next to it |
| Remove a card | Trash icon, top right. Removed cards stay under View → Removed cards |
| Link a ticket | `+` beside the tickets, then paste ids or links |
| Get a new ticket written | `+`, then Create new. Claude reads every session in the thread and writes it |
| Unlink a ticket | `×` on the ticket |
| Narrow the time range | Today, 3 days, Week, 2 weeks or 30 days |
| Undo | Every change shows a toast with Undo |

Your changes stick. A card you move stays put until you work on that thread again or its tickets change. Merges and ticket links stay until you undo them.

**Keep a session open** and run `/defragify` in it once a day. That session then handles Create new within a minute. With no session open, the request waits for your next run.

## Trackers

Claude does all tracker work through the connector or CLI you already have.

| Tracker | Needs | Status |
|---|---|---|
| Linear | Linear connector | Tested |
| GitHub Issues | `gh` CLI | Tested |
| Jira | Atlassian connector | Best effort, not yet run against a real site |
| Asana | Asana connector | Best effort, not yet run against a real workspace |
| None | Nothing | Tested. Ticket controls are hidden |

Each tracker's details are in [`skills/defragify/trackers/`](skills/defragify/trackers/). Reports from Jira and Asana users are welcome.

## What it reads and where it goes

- It reads the session history each AI tool keeps on your machine, wherever it finds one: Claude Code (`~/.claude/projects/`), Codex (`~/.codex/sessions/`), Cursor chats, GitHub Copilot chats in VS Code and its forks, and Antigravity's conversation index (its transcripts are encrypted, so only titles, times and task summaries).
- It also counts coding you did by hand: file saves from VS Code-family editors' local history and your own git commits, when no AI session was running. These show up as `manual` sessions, one per repo per day.
- Claude labels new sessions in your own Claude Code session, the same way it works on anything else you ask.
- Your settings and labels stay in `~/.claude/defragify/`.
- `~/.claude` is `%USERPROFILE%\.claude` on Windows. If you've moved it with `CLAUDE_CONFIG_DIR`, defragify follows.
- The board is a private artifact in your claude.ai account. It holds thread names, notes, summaries and session titles, not your code.

## Requirements and limits

- Claude Code signed in with a claude.ai account, which publishing artifacts needs. API-key-only setups can't publish the board.
- macOS, Linux or Windows, with Python 3.9 or newer (standard library only). Claude finds it as `python3`, `python` or the Windows `py` launcher, and offers to install it if it's missing.
- Claude Code deletes transcripts after 30 days by default (`cleanupPeriodDays`), so the board can't look back further than that unless you raise it.
- None of these formats are documented and any could change in a release. Each tool has its own `read_*()` function in `worklog.py`; one that breaks is skipped with a warning, so the rest still build the board, and a fix is small.
- Hand-coding time comes from saves and commits, so it's a floor: time spent reading or thinking between saves isn't counted, and edits made while an AI session is running count toward that session.

## License

MIT
