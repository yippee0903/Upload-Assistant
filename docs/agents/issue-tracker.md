# Issue Tracker

Issues for this repo are managed with **Beads** (`bd` CLI) — a lightweight local issue tracker with first-class dependency support. Issues are stored in `.beads/` and prefixed `Upload-Assistant-*`.

## Key commands

```bash
bd create "Title" -d "Description"   # create an issue
bd list                               # list open issues
bd show <id>                          # show issue details
bd close <id>                         # close an issue
bd label <id> <label>                 # apply a label
bd tag <id> <label>                   # alias for bd label
bd comment <id> "text"                # add a comment
bd link <id> --deps <other-id>        # add a dependency
bd set-state <id> <state>             # update operational state
bd query '<expr>'                     # query issues with a filter expression
```

## Workflow for skills

- **Creating issues** — use `bd create` with a clear title and `-d` for description. Add `--label needs-triage` on creation unless the triage state is already known.
- **Triaging** — use `bd label <id> <triage-label>` to move an issue through the triage state machine (see `triage-labels.md`).
- **Closing** — use `bd close <id>` when resolved.
- **Linking related issues** — use `bd link` to express dependencies between issues.

## Notes

- External PRs are **not** a triage surface for this repo.
- `.beads/` is excluded locally (`.git/info/exclude`) — issues are local to this machine only and never reach GitHub.
- Use `bd --help` or `bd <command> --help` for full flag reference.
