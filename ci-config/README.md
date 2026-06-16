# document-ai-review deployment config

本目录保存应用仓库内的镜像构建相关文件。

Kubernetes 发布清单不放在应用仓库内，统一放在 GitOps 仓库：

```text
/home/lsym005226/project/lsym-gitops/document-ai-review/
```

## 文件

- `Dockerfile`：单镜像构建，先构建 `web-console`，再把静态产物复制到 FastAPI 镜像，由 `ai-service` 同时提供 API 和前端页面。
- `Jenkinsfile`：使用 Jenkins Kubernetes agent + Kaniko 构建并推送镜像。

Kubernetes 相关文件：

- `deployment.yaml`
- `service.yaml`
- `ingress.yaml`
- `configmap.yaml`
- `secret.example.env`

这些文件由 `/home/lsym005226/project/lsym-gitops/document-ai-review/` 管理。

## Jenkins 参数

默认参数：

```text
GIT_REPO=https://git.lsym.cn/datacenter/data-development/document-ai-review.git
GIT_BRANCH=fix/qc-review-closure-followup
IMAGE_REGISTRY=prod-mirror-cn-beijing.cr.volces.com/metadata
IMAGE_TAG=v1
PYTHON_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review-python-runtime:3.12-slim
NODE_IMAGE=prod-mirror-cn-beijing.cr.volces.com/metadata/node:22-bookworm-slim-pnpm11.5.1
```

构建出的镜像：

```text
prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review:v1
```

## Python 运行基础镜像

基础镜像基于：

```text
python:3.12-slim
```

需要安装的系统包：

```text
ca-certificates
libglib2.0-0
libjpeg62-turbo
libpng16-16
poppler-utils
```

其中 `poppler-utils` 提供 `pdftoppm`，用于 `pdf2image` 处理 PDF；`libjpeg62-turbo`、`libpng16-16` 是 Pillow 常见图片运行依赖；`libglib2.0-0` 作为图片/PDF 处理的保守运行依赖保留。

当前已推送到私有镜像仓库：

```text
prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review-python-runtime:3.12-slim
```

## 域名和企微

当前清单默认域名：

```text
https://ai-review.lsym.cn
```

企业微信后台需要配置：

```text
OAuth 回调域名：ai-review.lsym.cn
工作台入口：https://ai-review.lsym.cn/reviews
回调地址：https://ai-review.lsym.cn/api/v1/auth/sso/callback?provider=wecom
```

部署顺序见 GitOps 仓库对应目录 README。
