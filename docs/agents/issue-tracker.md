# Issue tracker: GitHub

Issues and PRDs for this repo live in GitHub Issues for `201811510411lw/document-ai-review`.

## Conventions

- Use GitHub REST API for issue operations.
- Do not use `gh` CLI in this repo.
- When credentials are needed, obtain them through the existing Git credential helper during the actual API call.
- Do not print tokens or `Authorization` headers.

## Operations

- Create an issue with `POST /repos/201811510411lw/document-ai-review/issues`.
- Read an issue with `GET /repos/201811510411lw/document-ai-review/issues/{issue_number}` and `GET /repos/201811510411lw/document-ai-review/issues/{issue_number}/comments`.
- List issues with `GET /repos/201811510411lw/document-ai-review/issues`.
- Comment with `POST /repos/201811510411lw/document-ai-review/issues/{issue_number}/comments`.
- Apply labels with `POST /repos/201811510411lw/document-ai-review/issues/{issue_number}/labels`.
- Close with `PATCH /repos/201811510411lw/document-ai-review/issues/{issue_number}` and `state=closed`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue using the REST API. For PRDs, create one issue whose body is the generated PRD. For implementation slices, create one issue per approved vertical slice.
