# 服务器 24h 常驻运维

这份文档用于把 Hermes WebUI 测试环境迁移成服务器常驻服务。目标是：

- Docker daemon 随服务器开机自启。
- JupyterHub 和 Hermes Admin 由 Docker Compose 常驻运行。
- 容器异常退出后自动重启。
- 服务器重启后自动恢复服务。
- 用户数据、JupyterHub 数据、Admin 数据、策略文件都落在宿主机持久目录。

## 1. 准备服务器

建议部署路径：

```sh
/srv/hermes/app
```

服务器需要提前安装：

- Docker Engine
- Docker Compose v2
- 一个反向代理，例如 Nginx 或 Caddy

启用 Docker 开机自启：

```sh
sudo systemctl enable docker
sudo systemctl start docker
sudo systemctl status docker
```

## 2. 准备配置

进入项目目录：

```sh
cd /srv/hermes/app
cp configs/server.env.example configs/server.env
```

必须修改：

```env
JUPYTERHUB_URL=https://hermes.example.com
HERMES_ADMIN_URL=https://hermes-admin.example.com
HERMES_ADMIN_PASSWORD=change-me
HERMES_ADMIN_API_TOKEN=change-me
MODEL_BASE_URL=http://model-gateway.internal:3001/v1
MODEL_DEFAULT=local-private-default
```

如果 OAuth 尚未接好，可以先用服务器测试模式：

```env
JUPYTERHUB_AUTH_MODE=native
JUPYTERHUB_OPEN_SIGNUP=false
```

接入平台登录后再切换：

```env
JUPYTERHUB_AUTH_MODE=oauth
OAUTH_CLIENT_ID=...
OAUTH_CLIENT_SECRET=...
OAUTH_AUTHORIZE_URL=...
OAUTH_TOKEN_URL=...
OAUTH_USERDATA_URL=...
OAUTH_CALLBACK_URL=https://hermes.example.com/hub/oauth_callback
```

默认 `docker-compose.server.yml` 只绑定本机端口：

```env
HERMES_JUPYTERHUB_BIND=127.0.0.1
HERMES_ADMIN_BIND=127.0.0.1
```

生产环境应由反向代理对外提供 HTTPS。如果需要直接暴露端口，可以改成 `0.0.0.0`。

## 3. 创建持久目录

按 `configs/server.env` 中的路径创建目录：

```sh
sudo mkdir -p /srv/hermes/users
sudo mkdir -p /srv/hermes/jupyterhub
sudo mkdir -p /srv/hermes/admin
sudo mkdir -p /srv/hermes/policies/users
```

推荐 Skill 可以直接使用仓库里的 `skills/`：

```env
HERMES_HOST_PROVISIONED_SKILLS_ROOT=/srv/hermes/app/skills
```

如果想把推荐 Skill 独立于代码更新，也可以使用：

```sh
sudo mkdir -p /srv/hermes/recommended-skills
```

然后把 `skills/` 内容同步到 `/srv/hermes/recommended-skills`，并在 `server.env` 中指向该目录。

## 4. 首次启动

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml up -d --build
```

检查服务：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml ps
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f jupyterhub
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f hermes-admin
```

`docker-compose.server.yml` 已经为 `jupyterhub` 和 `hermes-admin` 设置：

```yaml
restart: unless-stopped
```

因此容器异常退出后会自动重启，除非管理员显式停止它们。

## 5. systemd 托管 Compose

为了让服务器重启后自动执行 `docker compose up -d`，创建 systemd service：

```sh
sudo nano /etc/systemd/system/hermes-webui.service
```

内容：

```ini
[Unit]
Description=Hermes WebUI Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/srv/hermes/app
ExecStart=/usr/bin/docker compose --env-file configs/server.env -f docker-compose.server.yml up -d
ExecStop=/usr/bin/docker compose --env-file configs/server.env -f docker-compose.server.yml stop
RemainAfterExit=yes
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

启用：

```sh
sudo systemctl daemon-reload
sudo systemctl enable hermes-webui
sudo systemctl start hermes-webui
sudo systemctl status hermes-webui
```

之后服务器重启流程是：

```text
服务器开机
  -> systemd 启动 docker
  -> systemd 启动 hermes-webui
  -> docker compose 恢复 JupyterHub / Admin
  -> JupyterHub 按用户启动或恢复 runtime 容器
```

## 6. 日常操作

查看状态：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml ps
```

查看日志：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f
```

重启主服务：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml restart jupyterhub hermes-admin
```

更新代码和镜像：

```sh
git pull
docker compose --env-file configs/server.env -f docker-compose.server.yml up -d --build
```

停止服务但保留数据：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml stop
```

停止并删除主服务容器但保留宿主机数据：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml down
```

不要删除这些目录，除非明确要清空用户数据：

```text
/srv/hermes/users
/srv/hermes/jupyterhub
/srv/hermes/admin
/srv/hermes/policies
```

## 7. 备份建议

至少备份：

```text
/srv/hermes/users
/srv/hermes/jupyterhub
/srv/hermes/admin
/srv/hermes/policies
/srv/hermes/app/configs/server.env
```

其中 `server.env` 包含密钥，应进入安全备份系统，不应提交到 Git。
