# Linear

Needs the Linear connector (claude.ai connector or the Linear MCP server).

**Setup.** Ids look like `ENG-123`. Find the workspace slug from any issue's `url` (`https://linear.app/<workspace>/issue/ENG-123/...`) and set `tracker.link` to `https://linear.app/<workspace>/issue/{id}`. Ask which team new tickets go to; `create_in: {"team": "<team>", "assignee": "me"}`.

**Find.** `list_issues` with `team` and a keyword `query` from the thread name and summary. Check `list_issues` with `assignee: "me"` too. A match covers the same work, not just the same area.

**Create.** `save_issue` with `team`, `title`, `description` (markdown, real newlines), `assignee: "me"`, the status that matches the card (check `list_issue_statuses` for the team's names), and any estimate or labels `ticket_style` asks for. Long agent detail goes at the end in a collapsible `+++ Agent notes` ... `+++` section.

**Refresh statuses.** One call: `list_issues` with `team`, `updatedAt: "-P60D"`, `fields: ["id", "status", "statusType", "updatedAt"]`, `limit: 250`, following `cursor` while `hasNextPage`. `get_issue` for any linked id not in that list. Each entry: `state` = `status`, `updated` = `updatedAt`, `column` from:

| `statusType` | column |
|---|---|
| `triage`, `backlog`, `unstarted` | `idea` |
| `started` | `building`; `waiting` when the name says review, ready, release, QA or blocked |
| `completed` | `shipped` |
| `canceled`, `duplicate` | `dropped` |

`tracker.columns` overrides by status name.
