## Agent skills

### Issue tracker

Issues are tracked locally using the `bd` CLI (Beads). External PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

Every bug or feature request raised in conversation gets a `bd create "<title>" -d "<description>" --label needs-triage` before any code is touched; close it with `bd close <id>` in the same turn as the commit that resolves it. Do this without being asked.

### Triage labels

Default label vocabulary — `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
