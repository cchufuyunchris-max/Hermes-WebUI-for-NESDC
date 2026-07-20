# 服务器迁移完整流程

这份文档从一台新服务器开始，把本地已经提交到 GitHub 的 Hermes WebUI 部署成 24h 常驻服务。

当前仓库：

```text
https://github.com/cchufuyunchris-max/Hermes-WebUI-for-NESDC.git
```

## 0. 服务器要求

推荐配置：

```text
CPU: 4 核起步，8 核更稳
Memory: 16 GB 起步，32 GB 更稳
Storage: 100 GB 起步，推荐 200 GB SSD
OS: Ubuntu 22.04/24.04、Debian 12、Rocky Linux 9、AlmaLinux 9
```

不推荐新部署使用 CentOS 7.6。Docker 官方当前 CentOS 文档面向 CentOS Stream 9/10，CentOS 7.6 生命周期和软件源兼容性都比较差。如果服务器供应商只能给 CentOS 7.6，需要先确认 Docker Engine、Compose plugin、containerd 可以稳定安装。

服务器需要能访问：

- GitHub，拉取代码。
- Docker registry，构建或拉取基础镜像。
- 模型网关，例如 `MODEL_BASE_URL` 指向的内网或公网地址。
- 主平台 OAuth 地址，如果生产环境接入统一登录。

## 1. 安装基础工具

Ubuntu / Debian：

```sh
sudo apt-get update
sudo apt-get install -y git curl ca-certificates gnupg
```

Rocky / Alma / CentOS Stream：

```sh
sudo dnf install -y git curl ca-certificates dnf-plugins-core
```

## 2. 安装 Docker Engine 和 Compose

服务器必须安装 Docker。这个项目依赖：

- Docker daemon，负责长期运行容器。
- Docker Compose v2，也就是 `docker compose` 命令。
- Docker socket，Admin WebUI 用它重建用户容器。

### Ubuntu / Debian

建议按 Docker 官方仓库安装。简化流程：

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

如果是 Debian，把上面仓库地址中的 `linux/ubuntu` 改为 `linux/debian`。

### Rocky / Alma / CentOS Stream

```sh
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

验证：

```sh
sudo docker run hello-world
docker compose version
```

如果普通用户需要直接执行 Docker 命令：

```sh
sudo usermod -aG docker "$USER"
```

然后重新登录 SSH。生产服务器也可以继续用 `sudo docker ...`，权限边界更清晰。

## 3. 拉取项目代码

建议部署到固定目录：

```sh
sudo mkdir -p /srv/hermes
sudo chown -R "$USER":"$USER" /srv/hermes
cd /srv/hermes
git clone https://github.com/cchufuyunchris-max/Hermes-WebUI-for-NESDC.git app
cd /srv/hermes/app
```

检查当前版本：

```sh
git status
git log --oneline -1
```

## 4. 准备生产配置

复制模板：

```sh
cp configs/server.env.example configs/server.env
```

编辑：

```sh
nano configs/server.env
```

至少修改：

```env
JUPYTERHUB_URL=https://hermes.example.com
HERMES_ADMIN_URL=https://hermes-admin.example.com
HERMES_ADMIN_PASSWORD=replace-with-strong-password
HERMES_ADMIN_API_TOKEN=replace-with-random-token
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://your-model-gateway.example.com/v1
MODEL_API_KEY=
MODEL_DEFAULT=your-default-model
```

如果暂时没有 OAuth，可以先用测试登录模式：

```env
JUPYTERHUB_AUTH_MODE=native
JUPYTERHUB_OPEN_SIGNUP=false
JUPYTERHUB_ADMIN_USERS=admin
```

如果已经接入主平台 OAuth，再填：

```env
JUPYTERHUB_AUTH_MODE=oauth
OAUTH_CLIENT_ID=...
OAUTH_CLIENT_SECRET=...
OAUTH_AUTHORIZE_URL=...
OAUTH_TOKEN_URL=...
OAUTH_USERDATA_URL=...
OAUTH_CALLBACK_URL=https://hermes.example.com/hub/oauth_callback
```

真实的 `configs/server.env` 不要提交到 Git。

## 5. 创建持久目录

这些目录保存用户数据、JupyterHub 数据、Admin 数据和策略文件：

```sh
sudo mkdir -p /srv/hermes/users
sudo mkdir -p /srv/hermes/jupyterhub
sudo mkdir -p /srv/hermes/admin
sudo mkdir -p /srv/hermes/policies/users
sudo chown -R "$USER":"$USER" /srv/hermes
```

默认推荐 Skill 使用仓库内目录：

```env
HERMES_HOST_PROVISIONED_SKILLS_ROOT=/srv/hermes/app/skills
```

## 6. 首次启动

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml up -d --build
```

查看状态：

```sh
docker compose --env-file configs/server.env -f docker-compose.server.yml ps
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f hermes-admin
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f jupyterhub
```

默认本机端口：

```text
JupyterHub: 127.0.0.1:8000
Admin WebUI: 127.0.0.1:8001
```

如果还没有反向代理，但需要直接测试，可以临时把 `configs/server.env` 改成：

```env
HERMES_JUPYTERHUB_BIND=0.0.0.0
HERMES_ADMIN_BIND=0.0.0.0
```

生产环境建议保持 `127.0.0.1`，由 Nginx/Caddy 对外暴露 HTTPS。

## 7. 配置反向代理

推荐两个域名：

```text
https://hermes.example.com        -> 127.0.0.1:8000
https://hermes-admin.example.com  -> 127.0.0.1:8001
```

Nginx 需要支持 WebSocket：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Admin 域名同理，把 `proxy_pass` 改成 `http://127.0.0.1:8001`。

## 8. 配置全局模型

登录 Admin WebUI：

```text
https://hermes-admin.example.com
```

进入全局策略/模型配置，填写：

```text
model.provider
model.default
model.base_url
model.api_key
```

保存后点击“应用到所有用户”。这会重建用户 runtime 容器，让新策略写入每个用户容器里的：

```text
/home/hermes/data/hermes/config.yaml
```

如果只是保存配置但没有重建用户容器，已经运行的用户容器不会马上读取新模型配置。

## 9. 设置开机自启

`docker-compose.server.yml` 已经设置 `restart: unless-stopped`，容器异常退出会自动重启。

为了让服务器重启后自动执行 Compose，创建 systemd service：

```sh
sudo nano /etc/systemd/system/hermes-webui.service
```

写入：

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

## 10. 更新代码

以后本地修改并 push 后，服务器更新：

```sh
cd /srv/hermes/app
git pull
docker compose --env-file configs/server.env -f docker-compose.server.yml up -d --build
```

## 11. 备份

至少备份：

```text
/srv/hermes/users
/srv/hermes/jupyterhub
/srv/hermes/admin
/srv/hermes/policies
/srv/hermes/app/configs/server.env
```

`configs/server.env` 包含密钥，不要放入 GitHub。

## 12. 常见检查命令

```sh
docker ps
docker compose --env-file configs/server.env -f docker-compose.server.yml ps
docker compose --env-file configs/server.env -f docker-compose.server.yml logs -f
docker logs hermes-admin
docker logs hermes-jupyterhub
```

检查 Docker 是否开机自启：

```sh
systemctl is-enabled docker
systemctl status docker
```

检查 Hermes 是否开机自启：

```sh
systemctl is-enabled hermes-webui
systemctl status hermes-webui
```

