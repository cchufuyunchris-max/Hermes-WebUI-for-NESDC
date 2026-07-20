# 配置外置化说明

Hermes 测试环境和服务器环境都通过 env 文件驱动，避免把路径、端口、密钥写死在 compose 或代码里。

## 配置文件

```text
configs/.env.example          通用默认值，不放真实密钥
configs/local.env.example     本地测试模板
configs/local.env             本地真实配置，不提交
configs/server.env.example    服务器模板
configs/server.env            服务器真实配置，不提交
```

本地初始化：

```sh
scripts/ensure-local-env.sh
```

服务器初始化：

```sh
cp configs/server.env.example configs/server.env
```

## Compose 用法

本地：

```sh
docker compose --env-file configs/local.env -f docker-compose.local.yml up -d
```

服务器：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml up -d --build
```

服务器 24h 常驻、Docker 开机自启、systemd 托管 Compose、日志、更新和备份流程见
[server-ops.md](server-ops.md)。

## 迁移服务器前检查

- `HERMES_HOST_USER_DATA_ROOT` 指向服务器持久用户目录。
- `HERMES_HOST_PROVISIONED_SKILLS_ROOT` 指向推荐 Skill 目录。
- `HERMES_HOST_POLICY_ROOT` 指向管理员策略目录。
- `HERMES_ADMIN_API_TOKEN` 和 `HERMES_ADMIN_PASSWORD` 已替换。
- `JUPYTERHUB_AUTH_MODE=oauth` 时，OAuth URL 和 callback URL 已配置。
- `JUPYTERHUB_ADMIN_API_TOKEN` 已设置时，smoke test 可以自动 Spawn 测试用户。
- `MODEL_BASE_URL` 指向本地模型网关或内部模型服务。
- Dify / ClickHouse 等连接优先在管理后台策略里配置。
- 反向代理允许 iframe 时，需要在上层平台和 Hermes 服务同时配置。

## 原则

- 代码和 compose 只保留变量名和默认值。
- 真实密钥只放 `configs/local.env` / `configs/server.env` 或更安全的 secret 管理系统。
- 管理后台生成和保存的策略文件位于 `HERMES_HOST_POLICY_ROOT`。
- 用户会话、记忆、workspace、已安装 Skill 位于 `HERMES_HOST_USER_DATA_ROOT`。
