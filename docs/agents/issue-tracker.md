# Issue tracker: GitLab

Issues and PRDs for this repo should live as GitLab Issues. Use the `glab` CLI for issue and merge request operations after GitLab remote and authentication are configured.

## Current remote status

At setup time, this local clone still pointed at GitHub:

```text
https://github.com/201811510411lw/document-ai-review.git
```

Target workflow is still GitLab Issues + `glab` CLI, but do not actually create GitLab issues until both conditions are true:

- `git remote -v` points to the intended GitLab project.
- `glab auth status` confirms authentication for the target GitLab host.

Before any skill publishes to the issue tracker, run:

```bash
git remote -v
glab auth status
```

If either check fails, stop and ask the user to configure the GitLab remote or authenticate `glab`.

## Conventions

- Create an issue: `glab issue create --title "..." --description "..."`
- Read an issue: `glab issue view <number> --comments`
- List issues: `glab issue list -F json` with appropriate `--label` filters
- Comment on an issue: `glab issue note <number> --message "..."`
- Apply or remove labels: `glab issue update <number> --label "..."` / `--unlabel "..."`
- Close an issue: post the closing explanation first with `glab issue note`, then run `glab issue close <number>`
- Merge requests: use `glab mr create`, `glab mr view`, `glab mr note`, and related `glab mr` commands

Infer the repo from `git remote -v` once the GitLab remote is configured.

## When a skill says "publish to the issue tracker"

First check `git remote -v` and `glab auth status`.

If the repo points to the intended GitLab project and `glab` is authenticated, create a GitLab issue.

If not, do not create the issue yet; ask the user to configure GitLab remote and `glab auth`.

## When a skill says "fetch the relevant ticket"

First check `git remote -v` and `glab auth status`, then run:

```bash
glab issue view <number> --comments
```
