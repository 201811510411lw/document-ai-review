# document-ai-review deployment config

本目录保存镜像构建和 UAT/生产部署相关文件，参考同组项目的 `config/` 目录约定。

## 文件

- `Dockerfile`：单镜像构建，先构建 `web-console`，再把静态产物复制到 FastAPI 镜像，由 `ai-service` 同时提供 API 和前端页面。
- `Jenkinsfile`：使用 Jenkins Kubernetes agent + Kaniko 构建并推送镜像。
- `deployment.yaml` / `service.yaml` / `ingress.yaml`：Kubernetes 部署清单。
- `configmap.yaml`：非敏感运行时配置。
- `secret.example.env`：敏感配置示例，实际部署时创建 Kubernetes Secret，不要提交真实密钥。

## Jenkins 参数

默认参数：

```text
GIT_REPO=https://git.lsym.cn/datacenter/data-development/document-ai-review.git
GIT_BRANCH=fix/qc-review-closure-followup
IMAGE_REGISTRY=prod-mirror-cn-beijing.cr.volces.com/metadata
IMAGE_TAG=v1.${BUILD_NUMBER}
```

构建出的镜像：

```text
prod-mirror-cn-beijing.cr.volces.com/metadata/document-ai-review:<IMAGE_TAG>
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

## 部署顺序

```bash
kubectl -n ds-api create secret generic document-ai-review-secret --from-env-file=config/secret.example.env
kubectl apply -f config/configmap.yaml
kubectl apply -f config/deployment.yaml
kubectl apply -f config/service.yaml
kubectl apply -f config/ingress.yaml
```

实际部署前请先复制 `secret.example.env` 并替换真实密钥，不要把真实 secret 提交到仓库。
