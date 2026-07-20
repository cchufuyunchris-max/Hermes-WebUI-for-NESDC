# Hermes 后台管理页面

## 入口

后台页面地址：

```text
/admin.html
```

本地开发推荐使用独立管理服务：

```bash
docker compose -f docker-compose.local.yml up -d hermes-admin
```

然后打开：

```text
http://127.0.0.1:8001/admin.html
```

本地默认 Admin Token：

```text
local-admin
```

本地管理服务也启用了 WebUI 密码，默认密码同样是：

```text
local-admin
```

所以访问时先登录 WebUI，再在后台页右上角输入 Admin Token 后刷新或保存。

在 JupyterHub 用户路径下访问时也是同一个页面，例如：

```text
http://127.0.0.1:8000/user/test/admin.html
```

但工程化部署时，不建议通过普通用户容器管理全局策略。推荐单独部署管理员服务，并把策略目录以可写方式挂载给管理员服务；JupyterHub 和用户容器只读取策略。

页面当前管理的是 Hermes Runtime 的策略文件，包括模型档位、通用数据连接、MCP、审计和用户容器资源配额。

## 启用方式

本地开发环境默认启用后台页面。生产环境建议显式配置：

```bash
HERMES_ADMIN_UI_ENABLED=true
HERMES_ADMIN_API_TOKEN=change-me
HERMES_ADMIN_POLICY_PATH=/srv/hermes/policies/global.json
```

如果不设置 `HERMES_ADMIN_POLICY_PATH`，系统会按顺序使用：

```text
HERMES_POLICY_ROOT/global.json
configs/policies/global.json
```

后台页面只适合放在受控的管理员服务里。不要把可写全局策略的后台入口暴露给普通用户容器。

## 管理能力

当前页面支持：

```text
1. 启用或关闭 Hermes Runtime。
2. 配置 safe / quality / fast 三个模型档位。
3. 控制用户是否能配置自己的在线模型 API Key。
4. 配置通用数据连接，包括 Dify、ClickHouse、Postgres、MySQL、SQLite、DuckDB、Mongo、Redis、MCP 和其他类型。
5. 强制数据库类连接只读。
6. 管理数据工具审计开关和审计日志路径。
7. 设置用户容器 CPU、内存和磁盘配额。
8. 为单个用户创建资源覆盖策略，用于针对性扩容或禁用访问。
9. 查看最近的数据工具审计事件。
10. 直接编辑原始 JSON。
```

## 通用数据连接

以后数据库不只 ClickHouse，所以统一使用 `data_connectors.connectors[]`。

数据库类连接必须满足只读条件之一：

```text
access_mode = read-only / readonly / read / ro / select-only
readonly = true
```

示例：

```json
{
  "id": "warehouse-readonly",
  "type": "postgres",
  "enabled": true,
  "host": "postgres.internal",
  "port": 5432,
  "database": "analytics",
  "user": "readonly",
  "password": "change-me",
  "privacy_level": "private",
  "access_mode": "read-only",
  "readonly": true,
  "mcp": {
    "enabled": true,
    "server_name": "warehouse-readonly",
    "command": "postgres-mcp-server",
    "args": [],
    "env": {
      "POSTGRES_READONLY": "1"
    }
  }
}
```

保存时，页面显示的 `********` 会被后端合并回原密钥，避免管理员只是改普通字段时把密码清空。

## API

后台页面使用三个接口：

```text
GET  /api/admin/policy
POST /api/admin/policy/save
GET  /api/admin/audit?limit=100
```

如果配置了 `HERMES_ADMIN_API_TOKEN`，请求需要带：

```text
X-Hermes-Admin-Token: change-me
```

如果 WebUI 自身启用了登录，页面会自动带 `X-Hermes-CSRF-Token`。

## 生效方式

后台保存的是策略文件。已经启动的用户容器不会自动改变环境变量和 MCP 配置，需要重新 Spawn 后生效。

## 用户扩容

全局默认资源写在：

```text
configs/policies/global.json
```

单个用户扩容写在：

```text
configs/policies/users/{user_id}.json
```

例如给 `alice` 扩容：

```json
{
  "enabled": true,
  "resources": {
    "cpu_limit": 4,
    "memory_limit": "8g",
    "disk_quota_bytes": 53687091200
  }
}
```

JupyterHub 会在 Spawn 前自动把 `global.json` 和用户覆盖文件合并。用户覆盖只影响该用户，删除覆盖后会回到全局默认配置。

管理后台的「用户与资源」会同时读取：

- `configs/policies/users/{user_id}.json`：单个用户的扩容/禁用覆盖策略。
- `.data/users/{user_id}`：该用户的 Hermes 持久目录，也就是会话、记忆、workspace、已安装 skill 等用户数据。

因此，即使某个用户没有单独扩容覆盖，只要已经登录并产生过数据，也会显示在用户列表里。后台会计算每个用户目录的当前占用，并按有效磁盘配额显示状态：

- 低于 80%：正常。
- 80% 及以上：接近配额，需要关注。
- 90% 及以上：高风险，建议扩容或清理。

「删除覆盖」只删除该用户的资源覆盖 JSON，不删除用户数据。「删除用户及数据」会要求输入完整用户 ID 二次确认，然后删除该用户的 Hermes 持久目录和覆盖配置。执行这个操作前，应先在 JupyterHub 停止该用户正在运行的服务，避免任务中断或数据写入到一半。

本地开发的 `hermes-admin` 服务需要可写挂载用户目录：

```yaml
./.data/users:/srv/hermes/users
```

生产环境中，平台账号仍建议由主系统管理；Hermes 管理后台只负责 Hermes 侧容器资源和用户持久数据。
