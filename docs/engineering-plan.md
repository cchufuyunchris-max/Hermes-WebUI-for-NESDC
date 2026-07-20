# Hermes WebUI 工程化开发计划

## 1. 目标

把当前个人可用的 Hermes WebUI + Hermes Agent 项目工程化，形成可在本地开发、服务器部署、后续接入已有大模型平台的多用户系统。

阶段目标：

1. 本地先跑通单用户 Docker 化版本。
2. 引入 JupyterHub + DockerSpawner，实现每个用户独立 Hermes Runtime 容器。
3. 为每个用户挂载独立持久目录，保存会话、记忆、产物和工作区。
4. 迁移到服务器时只改配置，不改业务代码。
5. 最后接入已有系统的登录、权限、Dify/模型平台能力。

## 2. 总体架构

```text
已有平台前端 / 独立入口
        |
        v
JupyterHub / Gateway
        |
        +-- 用户 A: hermes-runtime 容器
        |       +-- Hermes WebUI
        |       +-- Hermes Agent
        |       +-- /data/users/alice 持久目录
        |
        +-- 用户 B: hermes-runtime 容器
                +-- Hermes WebUI
                +-- Hermes Agent
                +-- /data/users/bob 持久目录
```

后续接入已有系统后：

```text
已有大模型平台
  - 登录页
  - 用户体系
  - Dify / 模型服务
        |
        v
SSO / OAuth / OIDC / 反向代理鉴权
        |
        v
JupyterHub + DockerSpawner
        |
        v
每用户 Hermes Runtime
```

## 3. 推荐技术选型

### 3.1 多用户容器管理

优先使用：

- JupyterHub
- DockerSpawner
- Configurable HTTP Proxy

原因：

- 已经解决用户登录、按用户创建容器、路径代理、容器生命周期管理。
- 每个用户可获得独立 URL，如 `/user/alice/`。
- 支持给每个用户挂载独立 volume。
- 后续可替换 Authenticator 接入已有系统登录。

### 3.2 Hermes Runtime 镜像

每个用户容器中包含：

- 当前 Hermes WebUI
- Hermes Agent
- 项目 skill
- 用户 workspace
- 用户 memory/session/artifact 目录

容器职责：

- 提供 WebUI 服务。
- 调用 Hermes Agent。
- 读写用户自己的持久目录。

容器不应直接获得宿主机 Docker socket。需要 sandbox 时，应通过后续单独的受控 sandbox 服务创建短生命周期容器。

## 4. 目录规划

建议仓库结构：

```text
Hermes WebUI/
  apps/
    webui/
      src/
      public/
      package.json
      Dockerfile
  docker/
    jupyterhub/
      jupyterhub_config.py
      Dockerfile
    hermes-runtime/
      Dockerfile
      entrypoint.sh
  skills/
    eco-stations-climate-report/
  scripts/
    dev.sh
    build-runtime.sh
    migrate-check.sh
  configs/
    .env.example
    local.env.example
    server.env.example
  docs/
    engineering-plan.md
    deployment.md
    integration.md
  docker-compose.local.yml
  docker-compose.server.yml
```

当前已有的 `eco-stations-climate-report` 后续建议移动或复制到 `skills/eco-stations-climate-report`，这样 Hermes Runtime 镜像可以稳定打包它。

## 5. 必须预留的配置项

所有环境相关信息都必须通过环境变量或配置文件注入，避免写死在代码里。

### 5.1 基础服务配置

```env
APP_ENV=local
APP_BASE_URL=http://localhost:8000
PUBLIC_BASE_PATH=/
PORT=8080
```

说明：

- `APP_ENV`：`local`、`staging`、`production`。
- `APP_BASE_URL`：当前服务外部访问地址。
- `PUBLIC_BASE_PATH`：WebUI 被挂载的路径。接入 JupyterHub 后可能是 `/user/{username}/`。
- `PORT`：容器内 WebUI 监听端口。

### 5.2 用户与数据目录

```env
HERMES_USER_ID=local-user
HERMES_USER_NAME=Local User
HERMES_DATA_DIR=/home/hermes/data
HERMES_WORKSPACE_DIR=/home/hermes/data/workspace
HERMES_MEMORY_DIR=/home/hermes/data/memory
HERMES_SESSION_DIR=/home/hermes/data/sessions
HERMES_ARTIFACT_DIR=/home/hermes/data/artifacts
```

迁移到服务器后，宿主机路径由 Docker volume 挂载决定，容器内路径保持不变。

### 5.3 模型与 Dify 配置

```env
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=http://host.docker.internal:3001/v1
MODEL_API_KEY=change-me
MODEL_DEFAULT=default-model

DIFY_BASE_URL=http://host.docker.internal:5001
DIFY_API_KEY=change-me
DIFY_APP_ID=change-me
```

本地、服务器、正式平台只替换这些变量，不改 WebUI 代码。

### 5.4 JupyterHub 配置

```env
JUPYTERHUB_BASE_URL=/
JUPYTERHUB_COOKIE_SECRET_FILE=/srv/jupyterhub/jupyterhub_cookie_secret
DOCKER_NETWORK_NAME=hermes-net
HERMES_RUNTIME_IMAGE=hermes-runtime:local
HERMES_USER_DATA_ROOT=/srv/hermes/users
HERMES_CONTAINER_MEMORY_LIMIT=4g
HERMES_CONTAINER_CPU_LIMIT=2
```

### 5.5 安全配置

```env
TRUSTED_ORIGINS=http://localhost:8000,https://your-domain.com
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
ENABLE_SANDBOX=false
SANDBOX_API_URL=http://sandbox-controller:9000
```

服务器上：

```env
SESSION_COOKIE_SECURE=true
```

## 6. WebUI 改造要求

### 6.1 支持子路径部署

WebUI 不要写死：

```text
/api/xxx
/assets/xxx
http://localhost:8080
```

应统一基于：

```text
PUBLIC_BASE_PATH
```

或使用相对路径：

```text
./api/xxx
./assets/xxx
```

原因：JupyterHub 下用户路径通常是：

```text
/user/alice/
```

如果前端写死 `/api`，请求会跑到根路径，导致多用户代理失效。

### 6.2 API 和 WebSocket 路径

需要统一封装：

```js
const basePath = window.__APP_CONFIG__?.basePath || "/";
const apiUrl = new URL("api/chat", window.location.origin + basePath);
```

WebSocket 也要支持 base path：

```text
wss://domain/user/alice/ws
```

### 6.3 不信任前端传入的用户身份

前端可以展示用户名，但不能决定用户是谁。

用户身份来源顺序：

1. JupyterHub 注入的用户环境变量。
2. 后端鉴权 session。
3. 后续已有平台的 SSO/OIDC claims。

## 7. Docker 化计划

### 7.1 单用户 Runtime 镜像

镜像目标：

```text
hermes-runtime:local
```

容器启动后：

1. 读取环境变量。
2. 确认用户数据目录存在。
3. 启动 Hermes Agent。
4. 启动 WebUI。
5. 监听 `0.0.0.0:8080`。

### 7.2 本地 docker-compose

本地 compose 包含：

- jupyterhub
- docker proxy / DockerSpawner 所需网络
- hermes-runtime 镜像
- 可选 mock model service

本地访问：

```text
http://localhost:8000
```

### 7.3 数据卷

本地：

```text
./.data/users/{username}:/home/hermes/data
```

服务器：

```text
/srv/hermes/users/{username}:/home/hermes/data
```

容器内路径不变，降低迁移风险。

## 8. JupyterHub 配置计划

### 8.1 第一阶段认证

先使用简单认证方式：

- DummyAuthenticator
- NativeAuthenticator

目的：快速验证多用户容器隔离。

### 8.2 第二阶段认证

接入已有平台：

- OAuth2
- OIDC
- 共享反向代理鉴权

推荐 OIDC，因为用户信息、组织信息、权限 claims 更标准。

### 8.3 DockerSpawner 关键配置

需要配置：

- runtime 镜像名
- 容器网络
- 用户数据 volume
- 内存限制
- CPU 限制
- 环境变量注入
- idle timeout

重点是把用户名映射到独立 volume：

```python
c.DockerSpawner.volumes = {
    "/srv/hermes/users/{username}": "/home/hermes/data"
}
```

实际配置时要处理用户名转义，避免路径注入问题。

## 9. Sandbox 安全计划

### 9.1 不推荐方案

不推荐把 Docker socket 直接挂到用户 Hermes 容器：

```text
/var/run/docker.sock:/var/run/docker.sock
```

原因：拥有 Docker socket 基本等价于拥有宿主机 root 权限。

### 9.2 推荐方案

新增 sandbox-controller：

```text
Hermes Runtime
      |
      v
Sandbox Controller
      |
      v
短生命周期 sandbox 容器
```

sandbox-controller 负责：

- 校验用户身份。
- 限制可运行镜像。
- 限制 CPU/内存/网络。
- 限制挂载目录。
- 记录审计日志。
- 定时清理任务容器。

第一阶段可以先关闭 sandbox：

```env
ENABLE_SANDBOX=false
```

等 WebUI + Hermes Runtime 多用户跑通后再加。

## 10. 本地开发阶段计划

### 阶段 A：项目结构整理

产出：

- 标准仓库目录。
- `.env.example`。
- README。
- 单用户启动脚本。

验收：

- 本地不用 Docker 可以跑 WebUI + Hermes Agent。
- 所有路径、端口、模型地址都来自配置。

### 阶段 B：单用户 Docker 化

产出：

- `hermes-runtime` Dockerfile。
- `entrypoint.sh`。
- 本地 volume 挂载。

验收：

- `docker run` 后能访问 WebUI。
- 重启容器后历史会话仍在。
- 修改模型 API 地址不需要重新构建镜像。

### 阶段 C：JupyterHub + DockerSpawner

产出：

- `docker-compose.local.yml`。
- `jupyterhub_config.py`。
- 用户 volume 映射。

验收：

- 用户 A 登录进入自己的 WebUI。
- 用户 B 登录进入自己的 WebUI。
- A/B 容器不同，数据目录不同。
- A 无法访问 B 的数据。

### 阶段 D：服务器迁移演练

产出：

- `docker-compose.server.yml`。
- `server.env.example`。
- `deployment.md`。

验收：

- 服务器只改 env 和域名即可启动。
- HTTPS 可用。
- 用户数据写入 `/srv/hermes/users`。
- 反向代理路径正确。

### 阶段 E：已有系统接入

产出：

- OIDC/OAuth 接入说明。
- iframe 或路由嵌入方案。
- 用户 claims 到 Hermes 用户目录的映射规则。

验收：

- 已有平台登录后可进入自己的 Hermes WebUI。
- 用户退出后 session 失效。
- iframe 下 cookie、跨域、base path 正常。

### 阶段 F：Sandbox Controller

产出：

- sandbox-controller 服务。
- sandbox job API。
- 资源限制与审计日志。

验收：

- Hermes Runtime 不能直接控制 Docker。
- sandbox job 可运行、可超时、可清理。
- 用户只能访问自己的 workspace 挂载。

## 11. 迁移前检查清单

迁移到服务器前必须确认：

- 没有写死 `localhost`。
- 没有写死绝对路径，如 `/Users/...`。
- 前端 API 支持 base path。
- WebSocket 支持反向代理。
- 所有密钥来自环境变量。
- 用户数据目录在容器外持久化。
- 容器内进程不依赖本机 GUI。
- 日志输出到 stdout/stderr。
- 文件上传大小可配置。
- 模型 API 地址可配置。
- Dify API 地址可配置。
- cookie secure/samesite 可配置。
- 服务健康检查可用。

## 12. 后续接入已有平台的两种方式

### 12.1 iframe 嵌入

已有平台页面中嵌入：

```text
https://your-domain.com/user/{username}/
```

优点：

- 改造少。
- JupyterHub 继续负责路由。

注意：

- cookie SameSite 设置。
- X-Frame-Options / CSP 配置。
- 登录态打通。

### 12.2 路由级集成

已有平台反代：

```text
/apps/hermes -> JupyterHub
```

优点：

- 用户体验更完整。
- 可以统一域名、统一权限、统一导航。

注意：

- base path 更复杂。
- WebSocket 转发必须正确。

推荐顺序：

1. 先 iframe 验证。
2. 再做路由级集成。

## 13. 关键风险

### 13.1 Docker socket 风险

不要把 Docker socket 暴露给用户容器。需要 sandbox 时，通过受控服务创建。

### 13.2 子路径部署风险

WebUI 若写死 `/api`，在 JupyterHub `/user/{username}/` 路径下会失败。开发早期就要修掉。

### 13.3 用户名路径风险

不要直接把原始用户名拼进宿主机路径。需要做 slug/escape：

```text
alice@example.com -> alice-example-com
```

同时保存用户 ID 到用户名映射。

### 13.4 状态散落风险

Hermes 的记忆、会话、导出文件、临时文件必须统一落到 `HERMES_DATA_DIR` 下。否则容器重建后会丢状态。

## 14. MVP 验收标准

第一版工程化 MVP 达到以下标准即可：

1. 本地 `docker compose up` 启动 JupyterHub。
2. 两个用户登录后进入各自 Hermes WebUI。
3. 每个用户有独立容器。
4. 每个用户有独立持久目录。
5. 容器重启后会话和产物不丢。
6. WebUI 在 `/user/{username}/` 下资源加载正常。
7. 模型地址、Dify 地址、端口、base path 都来自配置。
8. 不给用户容器挂 Docker socket。

达到这个标准后，再考虑正式 SSO、Dify 深度集成、sandbox-controller 和服务器高可用。

## 15. 建议实施顺序

```text
1. 整理仓库结构
2. 提取配置项
3. 修 WebUI base path
4. 打 hermes-runtime 镜像
5. 单用户 Docker 验证
6. 加 JupyterHub + DockerSpawner
7. 验证多用户 volume 隔离
8. 写服务器 compose 和部署文档
9. 接入已有平台登录
10. 增加 sandbox-controller
```

不要一开始就做完整平台接入。先把“每用户容器 + 每用户持久目录 + WebUI 子路径运行”打稳，这三个是后面所有集成的地基。

## 16. 推荐 Skill 生命周期设计

Hermes WebUI 已经有自己的 skill 面板，平台侧第一版不再额外开发“我的技能”
同步。平台只负责一件事：提供管理员维护的推荐 skill 源，用户侧的安装、查看、
编辑仍然交给 Hermes WebUI / Hermes Agent 原生能力。

推荐把 skill 分为两层：

```text
1. builtin / agent skills
   - 随 Hermes Runtime 镜像发布
   - 只读
   - 用于系统基础能力

2. recommended provisioned skills
   - 管理员维护
   - 出现在平台“推荐 skill”语义下
   - 默认不自动安装给新用户
   - 可由镜像内置、宿主机挂载或 Git 同步
```

推荐容器内目录：

```text
/home/hermes/app
/home/hermes/builtin-skills
/home/hermes/provisioned-skills
/home/hermes/data
  /skills
  /skill-state.json
  /memory
  /sessions
  /artifacts
  /workspace
```

其中：

- `/home/hermes/app`：WebUI 和 Hermes Agent。
- `/home/hermes/builtin-skills`：镜像内置系统 skill，只读。
- `/home/hermes/provisioned-skills`：管理员推荐 skill 来源，只读挂载或镜像内置；默认只作为目录源。
- `/home/hermes/data/skills`：Hermes 原生 skill 面板使用的用户实际 skill 目录，持久化。
- `/home/hermes/data/skill-state.json`：记录每个 skill 的来源、版本、安装时间、是否被用户修改。

### 16.1 初始化规则

新用户第一次启动容器时：

```text
1. 创建 /home/hermes/data 目录结构
2. 不自动复制推荐 skill
3. 启动 Hermes Agent
```

老用户再次启动容器时：

```text
1. 读取 skill-state.json
2. 推荐 skill 更新由后续 Skill Hub 安装/升级流程处理
3. 不在启动阶段覆盖用户 skill 目录
```

### 16.2 Skill 状态文件

建议格式：

```json
{
  "skills": {
    "eco-stations-climate-report": {
      "source": "provisioned",
      "installed_version": "2026.06.24",
      "available_version": "2026.06.24",
      "installed_at": "2026-06-24T00:00:00Z",
      "user_modified": false,
      "update_policy": "manual"
    }
  }
}
```

### 16.3 更新策略

建议第一版使用手动更新：

```env
PROJECT_SKILLS_UPDATE_POLICY=manual
```

可选值：

```text
manual    只提示有更新，不自动覆盖
safe      用户未修改时自动更新
force     强制覆盖，通常只用于测试环境
```

第一版不要默认使用 `force`。用户目录里的 skill 是用户资产，覆盖必须谨慎。

### 16.4 第一版落地方式

MVP 推荐：

```text
本地开发：宿主机只读挂载 skills/ 到 provisioned-skills
生产环境：/srv/hermes/recommended-skills 只读挂载到 provisioned-skills
默认不自动安装到用户 data/skills
后续由 Skill Hub 执行按需安装
```

这个方案不需要开发“我的技能”同步，也不需要替换 Hermes WebUI 原有 skill 面板。
管理员只维护推荐源。后续如果要做管理端页面，它只需要操作
`/srv/hermes/recommended-skills` 这一个目录，或者把该目录背后换成 Git 同步流程。

## 17. 管理后端

Hermes 工程化后需要独立的管理后端，作为平台控制面。

管理后端负责：

```text
1. 推荐 skill 的上传、删除、版本发布
2. 模型档位和模型路由策略
3. Dify、ClickHouse 等知识库/数据库连接
4. 用户管理、容器 CPU/内存/磁盘配额
```

详细设计见：

```text
docs/admin-backend-plan.md
```

MVP 推荐先做：

```text
Admin Service 保存策略
生成 /srv/hermes/policies/*.json
JupyterHub pre_spawn_hook 读取策略
Hermes Runtime 按策略启动
```

这样主平台、管理后端、JupyterHub、用户 Runtime 的边界会比较清楚。
