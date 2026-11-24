# GitHub Issues

Needs the `gh` CLI, signed in (`gh auth status`).

**Setup.** Ids are `owner/repo#123`; the board links them to `https://github.com/owner/repo/issues/123` by itself, so leave `tracker.link` empty. Ask which repo new tickets go to: `create_in: {"repo": "owner/repo", "assignee": "@me"}`. Labels for new issues can go in `create_in.labels`.

**Find.** `gh search issues "<keywords>" --repo <owner/repo> --json number,title,state,url --limit 20` (or `--owner <org>` to search an org). A match covers the same work, not just the same area. The session's own branch or PR often names the issue (`#123`), and `ticket_mentions` catches `owner/repo#123`.

**Create.** Write the body to a file, then `gh issue create --repo <owner/repo> --title "<title>" --body-file <file> --assignee @me` plus `--label` for each configured label. The command prints the new issue's URL; the id is `owner/repo#<number>`.

**Refresh statuses.** For each linked id: `gh issue view <number> --repo <owner/repo> --json state,stateReason,updatedAt,title,url,assignees,labels`. Each entry: `state` = `state` (plus `stateReason` when closed), `updated` = `updatedAt`, `url` = `url`, `column` from:

| GitHub | column |
|---|---|
| open, no assignee | `idea` |
| open, assigned | `building`; `waiting` when a label says review, blocked or waiting |
| closed, `COMPLETED`; or `MERGED` (issue and pull request numbers share one sequence, so a linked id can be a PR) | `shipped` |
| closed, `NOT_PLANNED` or `DUPLICATE` | `dropped` |

`tracker.columns` overrides by label or state name.
