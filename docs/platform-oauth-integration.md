# 平台 OAuth 接入说明

Hermes 建议作为独立 Docker 服务运行，不要和 Java + Vue 主平台合并代码。

Java + Vue 主平台负责：

- 用户注册、登录、退出
- 权限、套餐、支付
- Dify / 模型平台入口
- 统一导航和页面框架

Hermes 服务负责：

- JupyterHub 用户调度
- DockerSpawner 按用户启动容器
- Hermes WebUI
- Hermes Agent
- 每个用户独立的持久目录、会话、文件和 skill

## 推荐部署方式

主平台和 Hermes 可以部署在两台不同服务器上，也就是两个 IP：

```text
主平台服务器
  IP: 服务器 A
  域名: https://platform.example.com
  技术: Java + Vue

Hermes 服务器
  IP: 服务器 B
  域名: https://hermes.example.com
  技术: JupyterHub + DockerSpawner + Hermes WebUI
```

线上建议都使用域名和 HTTPS，不建议在正式 iframe/OAuth 场景里直接使用 IP。

## 目标登录流程

```text
用户登录 Java + Vue 主平台
-> Vue 页面用 iframe 打开 Hermes
-> 如果 Hermes 侧还没有登录态，JupyterHub 跳转到主平台 OAuth 授权地址
-> 主平台授权后回调到 JupyterHub
-> JupyterHub 读取 userinfo.id
-> DockerSpawner 启动 jupyter-{id}
-> 用户数据挂载到 /srv/hermes/users/{id}
```

主平台用户的 `id` 是 Hermes 的稳定用户边界。

不要使用昵称、手机号、邮箱作为 Docker 目录名，因为这些字段可能变化，也可能包含不适合作为路径的字符。

## Hermes 环境变量

本地开发继续使用 NativeAuthenticator：

```env
JUPYTERHUB_AUTH_MODE=native
JUPYTERHUB_OPEN_SIGNUP=true
```

服务器接入主平台 OAuth 时切换为：

```env
JUPYTERHUB_AUTH_MODE=oauth
JUPYTERHUB_OPEN_SIGNUP=false
JUPYTERHUB_ALLOW_ALL=true

OAUTH_CLIENT_ID=...
OAUTH_CLIENT_SECRET=...
OAUTH_AUTHORIZE_URL=https://platform.example.com/oauth/authorize
OAUTH_TOKEN_URL=https://platform.example.com/oauth/token
OAUTH_USERDATA_URL=https://platform.example.com/oauth/userinfo
OAUTH_USERDATA_METHOD=GET
OAUTH_USERNAME_KEY=id
OAUTH_LOGIN_SERVICE=主平台
OAUTH_SCOPE=openid,profile
OAUTH_CALLBACK_URL=https://hermes.example.com/hub/oauth_callback
```

其中：

- `OAUTH_AUTHORIZE_URL`、`OAUTH_TOKEN_URL`、`OAUTH_USERDATA_URL` 指向主平台服务器。
- `OAUTH_CALLBACK_URL` 指向 Hermes 服务器。
- `OAUTH_USERNAME_KEY=id` 表示从主平台 userinfo 响应里读取 `id` 作为 Hermes 用户名。

主平台的 userinfo 接口至少需要返回：

```json
{
  "id": "stable-platform-user-id"
}
```

其他字段如 `name`、`avatar`、`email` 可以后续再接，不是第一阶段必需。

## Vue iframe 入口

Vue 主平台可以 iframe 嵌入：

```text
https://hermes.example.com/hub/user-redirect/
```

或者：

```text
https://hermes.example.com/hub/spawn
```

优先推荐 `/hub/user-redirect/`，因为它会把当前已登录用户送到自己的 Hermes server，不需要主平台知道 JupyterHub 内部的 `/user/{id}/` 路径。

示例：

```html
<iframe
  src="https://hermes.example.com/hub/user-redirect/"
  style="width: 100%; height: 100vh; border: 0;"
></iframe>
```

## 两台服务器时的关键点

### 1. 必须使用 HTTPS

主平台和 Hermes 都建议使用 HTTPS：

```text
https://platform.example.com
https://hermes.example.com
```

如果一个是 HTTP、一个是 HTTPS，浏览器可能拦截 iframe、Cookie 或 OAuth 跳转。

### 2. iframe 允许源

Hermes 服务器需要允许主平台页面嵌入。

生产环境不要使用通配符，应该只允许主平台域名：

```text
frame-ancestors https://platform.example.com
```

如果浏览器报 CSP / frame-ancestors / X-Frame-Options 相关错误，需要在 Hermes 服务器的反向代理或 JupyterHub header 配置里调整。

### 3. Cookie / SameSite

跨域 iframe 场景下，浏览器对 Cookie 更严格。

如果 iframe 里登录态不能保持，通常需要检查：

```text
SameSite=None
Secure=true
```

也就是说，Hermes 必须走 HTTPS，Cookie 才能安全地在跨站 iframe 中使用。

### 4. OAuth 回调地址

主平台 OAuth 后台必须登记 Hermes 的 callback：

```text
https://hermes.example.com/hub/oauth_callback
```

这个地址必须和 `OAUTH_CALLBACK_URL` 完全一致。

### 5. 网络连通性

Hermes 服务器需要能访问主平台的：

```text
OAUTH_TOKEN_URL
OAUTH_USERDATA_URL
```

用户浏览器需要能访问：

```text
主平台域名
Hermes 域名
```

## 用户持久目录

生产环境把用户数据放在 Hermes 服务器的持久磁盘路径：

```env
HERMES_HOST_USER_DATA_ROOT=/srv/hermes/users
HERMES_USER_DATA_ROOT=/srv/hermes/users
```

每个主平台用户会得到：

```text
/srv/hermes/users/{id}/webui
/srv/hermes/users/{id}/hermes
/srv/hermes/users/{id}/workspace
/srv/hermes/users/{id}/skills
/srv/hermes/users/{id}/sessions
```

需要定期备份：

```text
/srv/hermes/users
```

## 不需要合并代码

主平台和 Hermes 不需要放在同一个代码仓库，也不需要部署在同一台服务器。

二者只通过这些边界协作：

- iframe：主平台展示 Hermes 页面
- OAuth：主平台告诉 Hermes 当前用户是谁
- userinfo.id：Hermes 用它创建用户容器和持久目录
- HTTPS / Cookie / CSP：保证浏览器侧 iframe 正常工作

这样两边可以独立开发、独立部署、独立升级。

