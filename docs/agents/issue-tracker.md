# Issue Tracker：GitHub

本项目当前实际使用 GitHub Issues 和 GitHub Pull Requests 管理工作项与代码合入。

## 当前 remote 状态

当前 remote 指向 GitHub：

```text
https://github.com/201811510411lw/document-ai-review.git
```

本机如安装 `gh` 且已认证，优先使用 GitHub CLI。若 `gh` 不可用，可以使用 GitHub REST API，但不得打印访问令牌。

任何 skill 在发布内容到 issue tracker 之前，都必须先运行：

```bash
git remote -v
gh auth status
```

如果 `gh` 不存在但 git credential helper 中有 GitHub 凭据，可以通过 GitHub REST API 执行同等操作；如果没有可用认证，停止发布并要求用户完成 GitHub 认证。

## 操作约定

```bash
gh issue create --title "..." --body "..."
gh issue view <number> --comments
gh issue list --json number,title,state,labels
gh issue edit <number> --add-label "ready-for-agent"
gh pr create --title "..." --body "..." --base main --head <branch>
gh pr view <number>
gh pr merge <number>
```

## 当 skill 要求 "publish to the issue tracker"

先检查 `git remote -v` 和 GitHub 认证状态。

如果仓库指向当前 GitHub 项目，并且 GitHub 认证可用，则创建 GitHub issue。

否则不要创建 issue，先要求用户配置 GitHub remote 或完成认证。

## 当 skill 要求 "fetch the relevant ticket"

先检查 `git remote -v` 和 GitHub 认证状态，再运行：

```bash
gh issue view <number> --comments
```
