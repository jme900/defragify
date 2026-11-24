# Jira

Best effort: written against the Atlassian connector (Atlassian Remote MCP) but not yet run against a real Jira site. Tool names below are the connector's usual ones; use whatever its equivalents are called in your session.

Needs the Atlassian connector with Jira access.

**Setup.** Ids look like `PROJ-123`. Find the site with `getAccessibleAtlassianResources` (gives the `cloudId` and the site URL) and set `tracker.link` to `https://<site>.atlassian.net/browse/{id}`. Ask which project new tickets go to and the issue type: `create_in: {"cloudId": "<id>", "project": "PROJ", "issue_type": "Task", "assignee": "me"}`.

**Find.** `searchJiraIssuesUsingJql` with JQL like `project = PROJ AND text ~ "<keywords>" ORDER BY updated DESC`, and `assignee = currentUser()` for your own. A match covers the same work, not just the same area.

**Create.** `createJiraIssue` with the project, issue type, summary and description (Jira takes markdown through the connector). Assign to yourself via `lookupJiraAccountId` if the create call needs an account id. If the card isn't an idea, move the issue with `getTransitionsForJiraIssue` then `transitionJiraIssue`.

**Refresh statuses.** One JQL search for all linked ids: `key in (PROJ-1, PROJ-2, ...)` with fields `status,updated` (split into batches of 50). Each entry: `state` = `status.name`, `updated` = `updated`, `column` from the status category:

| `status.statusCategory.key` | column |
|---|---|
| `new` (To Do) | `idea` |
| `indeterminate` (In Progress) | `building`; `waiting` when the name says review, QA, blocked or ready |
| `done` | `shipped`; `dropped` when the name or resolution says won't do, cancelled or duplicate |

`tracker.columns` overrides by status name.
