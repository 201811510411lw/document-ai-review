# Issue tracker：GitLab

本项目的 issues 和 PRD 目标上使用 GitLab Issues 管理。在 GitLab remote 和认证配置完成后，使用 `glab` CLI 执行 issue 和 merge request 相关操作。

## 当前 remote 状态

配置本文档时，本地仓库仍然指向 GitHub：

```text
https://github.com/201811510411lw/document-ai-review.git
```

目标工作流仍然是 GitLab Issues + `glab` CLI，但在以下两个条件同时满足之前，不要实际创建 GitLab issue：

- `git remote -v` 指向目标 GitLab 项目。
- `glab auth status` 确认已经登录目标 GitLab host。

任何 skill 在发布内容到 issue tracker 之前，都必须先运行：

```bash
git remote -v
glab auth status
```

如果任一检查失败，停止创建 issue，并要求用户先配置 GitLab remote 或完成 `glab` 认证。

## 操作约定

- 创建 issue：`glab issue create --title "..." --description "..."`
- 查看 issue：`glab issue view <number> --comments`
- 列出 issues：`glab issue list -F json`，并按需使用 `--label` 过滤
- 评论 issue：`glab issue note <number> --message "..."`
- 添加或移除 labels：`glab issue update <number> --label "..."` / `--unlabel "..."`
- 关闭 issue：先用 `glab issue note` 写明关闭原因，再运行 `glab issue close <number>`
- Merge requests：使用 `glab mr create`、`glab mr view`、`glab mr note` 以及相关 `glab mr` 命令

GitLab remote 配置完成后，`glab` 会根据 `git remote -v` 推断目标仓库。

## 当 skill 要求 "publish to the issue tracker"

先检查 `git remote -v` 和 `glab auth status`。

如果仓库已经指向目标 GitLab 项目，并且 `glab` 已认证，则创建 GitLab issue。

否则不要创建 issue，先要求用户配置 GitLab remote 并完成 `glab auth`。

## 当 skill 要求 "fetch the relevant ticket"

先检查 `git remote -v` 和 `glab auth status`，再运行：

```bash
glab issue view <number> --comments
```
