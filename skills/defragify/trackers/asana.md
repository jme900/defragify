# Asana

Best effort: written against the Asana connector (Asana MCP server) but not yet run against a real workspace. Tool names below are the connector's usual ones; use whatever its equivalents are called in your session.

Needs the Asana connector.

**Setup.** Asana tasks have numeric ids (gids) and no short key, so the board shows each task's name on its chip instead (`label` in `tracker.json`). Set `tracker.link` to `https://app.asana.com/0/0/{id}`; a task's own `permalink_url` is used when known. Find the workspace with `asana_list_workspaces`, then ask which project new tasks go to: `create_in: {"workspace": "<gid>", "project": "<gid>", "assignee": "me"}`.

**Find.** `asana_search_tasks` (or `asana_typeahead_search` for tasks) in the workspace with keywords from the thread name and summary, `assignee.any: me` for your own. A match covers the same work, not just the same area. In session prompts, task links look like `app.asana.com/0/<project>/<task gid>`; the gid is the last number.

**Create.** `asana_create_task` with `name`, `notes` (or `html_notes`), the project, and `assignee: "me"`. If the project's sections mirror stages ("Doing", "Review"), add the task to the section matching the card.

**Refresh statuses.** `asana_get_task` per linked gid with `opt_fields: completed,completed_at,modified_at,name,permalink_url,memberships.section.name`. Each entry: `state` = the section name (or "Completed"), `updated` = `modified_at`, `url` = `permalink_url`, `label` = the task name cut to about 30 characters, `column` from:

| Asana | column |
|---|---|
| completed | `shipped` |
| incomplete, section names review, waiting or blocked | `waiting` |
| incomplete, section names doing, in progress or active | `building` |
| incomplete, anything else | `idea` |

`tracker.columns` overrides by section name.
