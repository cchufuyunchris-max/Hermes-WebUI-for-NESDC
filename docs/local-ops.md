# 本地测试环境运维脚本

这些脚本用于本地测试环境，不替代生产部署系统。默认保留 `.data/` 下的用户数据。

## 启动

```sh
scripts/dev-up.sh
```

它会校验目录结构，自动创建 `configs/local.env`，构建本地镜像，并启动：

- JupyterHub: `http://127.0.0.1:8000`
- Hermes Admin: `http://127.0.0.1:8001/admin.html`

## Smoke Test

```sh
scripts/smoke-test.sh
```

检查内容：

- Docker daemon 是否可用
- `docker-compose.local.yml` 是否有效
- `hermes-jupyterhub`、`hermes-admin` 是否运行
- JupyterHub/Admin 登录页是否可访问
- 使用 `JUPYTERHUB_ADMIN_API_TOKEN` 创建并 Spawn `HERMES_SMOKE_USER`
- 访问 `HERMES_SMOKE_USER` 的 WebUI 页面
- 检查用户容器内中文、light、推荐 Skill 目录等关键环境变量
- 管理端 policy、用户统计、推荐 Skill 是否可读
- 管理端相关 Python/JavaScript 是否通过基础语法检查

如果你修改了本地端口或路径，优先改 `configs/local.env`，不要改 compose 文件。

默认测试用户：

```env
HERMES_SMOKE_USER=smoke
JUPYTERHUB_ADMIN_API_TOKEN=local-jupyterhub-admin-token
```

该用户的数据会保留在 `HERMES_HOST_USER_DATA_ROOT/smoke`，便于后续排查。需要重置时：

```sh
scripts/dev-reset-user.sh smoke
```

## 日志

查看所有服务日志：

```sh
scripts/dev-logs.sh
```

只看某个服务：

```sh
scripts/dev-logs.sh hermes-admin
scripts/dev-logs.sh jupyterhub
```

## 停止

```sh
scripts/dev-down.sh
```

该脚本不会删除 `.data/`，所以用户会话、记忆、workspace、已安装 Skill 会保留。

## 环境配置文件

本地测试使用：

```text
configs/local.env
```

服务器部署参考：

```text
configs/server.env.example
```

`configs/local.env` 和 `configs/server.env` 都不应提交到版本库。需要迁服务器时，复制 `configs/server.env.example`，然后修改：

- 端口和公开 URL
- 宿主机数据目录
- OAuth 参数
- Admin Token / Admin 密码
- 本地模型网关地址
- Dify / ClickHouse 等连接信息

## 重置单个测试用户

```sh
scripts/dev-reset-user.sh alice
```

脚本会要求输入完整用户 ID 二次确认，然后：

- 停止并删除 `jupyter-{user_id}` 测试容器
- 删除 `.data/users/{user_id}`
- 删除 `configs/policies/users/{user_id}.json`

自动化场景可以使用：

```sh
scripts/dev-reset-user.sh alice --yes
```
