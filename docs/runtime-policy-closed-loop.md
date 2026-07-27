# Runtime Policy 闭环

## 目标

第一版不做管理页面，先打通这个闭环：

```text
Admin Service / 管理脚本
  ↓ 写入策略 JSON
JupyterHub pre_spawn_hook
  ↓ 读取策略 JSON
DockerSpawner
  ↓ 按策略启动用户容器
Hermes Runtime
  ↓ 获得模型、数据源、资源限制等环境变量
```

本地开发中，策略文件放在：

```text
configs/policies/global.json
configs/policies/users/{username}.json
```

生产环境建议放在：

```text
/srv/hermes/policies/global.json
/srv/hermes/policies/users/{platform_user_id}.json
```

## 已接入字段

JupyterHub 当前会读取并应用：

```text
enabled
resources.cpu_limit
resources.memory_limit
resources.disk_quota_bytes
model_policy.allow_user_model_settings
model_policy.allow_user_online_model_api_key
model_policy.runtime_privacy_guard_enabled
model_policy.online_allowed_toolsets
model_policy.private_tool_names
model_policy.public_mcp_tool_prefixes
model_policy.allow_terminal_network
model_policy.allow_code_network
model_policy.mode
model_policy.default_tier
model_policy.allowed_tiers
model_policy.gateway_provider
model_policy.tiers.safe
model_policy.tiers.quality
model_policy.tiers.fast
data_connectors.audit.enabled
data_connectors.audit.log_path
data_connectors.enforce_managed_mcp_servers
data_connectors.connectors[]
dify_knowledge.enabled
dify_knowledge.base_url
dify_knowledge.api_key
dify_knowledge.top_k
dify_knowledge.stations[]
recommended_skills_root
```

兼容说明：旧版 `data_sources`、`dify.*`、`clickhouse.*` 仍会被读取，并转换成
`data_connectors.connectors[]`。新配置建议统一使用 `data_connectors`。

## Global Policy

示例：

```json
{
  "enabled": true,
  "resources": {
    "cpu_limit": 2,
    "memory_limit": "4g",
    "disk_quota_bytes": 21474836480
  },
  "model_policy": {
    "allow_user_model_settings": false,
    "allow_user_online_model_api_key": false,
    "runtime_privacy_guard_enabled": true,
    "online_allowed_toolsets": ["web", "vision", "clarify", "todo", "image_gen"],
    "private_tool_names": ["terminal", "process", "execute_code", "read_file", "write_file", "patch", "search_files"],
    "public_mcp_tool_prefixes": [],
    "allow_terminal_network": false,
    "allow_code_network": false,
    "mode": "local-only",
    "default_tier": "safe",
    "allowed_tiers": ["safe", "quality", "fast"],
    "gateway_provider": "",
    "tiers": {
      "safe": "local-private-default",
      "quality": "local-private-default",
      "fast": "local-private-default"
    }
  }
}
```

## Managed Data Connectors

数据库、知识库和 MCP 连接统一放在管理员策略中：

```json
{
  "data_connectors": {
    "audit": {
      "enabled": true,
      "log_path": "/home/hermes/data/audit/data-tools.jsonl"
    },
    "enforce_managed_mcp_servers": true,
    "connectors": [
      {
        "id": "dify-public",
        "type": "dify",
        "enabled": true,
        "base_url": "http://dify.internal",
        "app_id": "change-me",
        "api_key": "change-me",
        "privacy_level": "public",
        "access_mode": "read-only"
      },
      {
        "id": "clickhouse-readonly",
        "type": "clickhouse",
        "enabled": true,
        "host": "clickhouse.internal",
        "port": 8123,
        "database": "default",
        "user": "readonly",
        "password": "change-me",
        "privacy_level": "private",
        "access_mode": "read-only",
        "readonly": true,
        "mcp": {
          "enabled": true,
          "server_name": "clickhouse-readonly",
          "command": "clickhouse-mcp-server",
          "args": [],
          "env": {
            "CLICKHOUSE_HOST": "${CLICKHOUSE_HOST}",
            "CLICKHOUSE_PORT": "${CLICKHOUSE_PORT}",
            "CLICKHOUSE_DATABASE": "${CLICKHOUSE_DATABASE}",
            "CLICKHOUSE_USER": "${CLICKHOUSE_USER}",
            "CLICKHOUSE_PASSWORD": "${CLICKHOUSE_PASSWORD}",
            "CLICKHOUSE_READONLY": "1"
          }
        }
      }
    ]
  }
}
```

JupyterHub 会在 spawn 前做三件事：

```text
1. 校验数据库类 connector 必须是 read-only，否则拒绝启动用户容器。
2. 注入 HERMES_DATA_CONNECTORS_JSON、HERMES_ALLOWED_DATA_CONNECTORS 等环境变量。
3. 把 connector.mcp 转成 HERMES_HOME/config.yaml 里的 mcp_servers。
```

`enforce_managed_mcp_servers=true` 时，容器每次启动都会用管理员策略覆盖
`config.yaml` 里的 `mcp_servers`。这样 MCP 连接不会由用户目录里的手工配置决定。

## Agent 原生模型配置同步

管理员在 Admin WebUI 保存的模型配置不是最终执行入口。Hermes Agent 实际读取的是每个
用户容器内的：

```text
${HERMES_HOME}/config.yaml
```

其中模型字段位于：

```yaml
model:
  provider: deepseek
  default: deepseek-v4-flash
  base_url: https://api.deepseek.com/v1
  api_key: ...
```

Admin WebUI 的“全局 Hermes Agent 模型”表单使用同名字段：

```text
model.provider
model.default
model.base_url
model.api_key
```

后台保存时仍落在全局策略文件的 `model_policy.local_model` 中：

```json
{
  "model_policy": {
    "local_model": {
      "provider": "deepseek",
      "model": "deepseek-v4-flash",
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "..."
    }
  }
}
```

也就是说，管理员不需要登录某个普通用户的 Hermes WebUI，也不需要进入容器手工运行
CLI。全局配置入口是 Hermes Admin WebUI，最终生效入口是每个用户容器的
`HERMES_HOME/config.yaml`。

因此 runtime 启动时会执行 `policy-init.py`，按以下优先级生成用户自己的
`HERMES_HOME/config.yaml`：

```text
1. /srv/hermes/policies/global.json 和 users/{user}.json 中的 model_policy.local_model
2. JupyterHub 注入的 MODEL_PROVIDER / MODEL_BASE_URL / MODEL_API_KEY / MODEL_DEFAULT
3. 用户既有 config.yaml 中非 model 的其它配置
```

JupyterHub 会把宿主机策略目录只读挂载到用户容器：

```text
宿主机 HERMES_HOST_POLICY_ROOT -> 容器 /srv/hermes/policies:ro
```

这样即使 Docker 环境变量是容器创建时固定的，用户容器在下次启动时仍会读取最新
Admin policy，并把 `model.provider`、`model.default`、`model.base_url`、
`model.api_key` 写入 Hermes Agent 原生配置。

注意：正在运行中的用户进程不会自动重新执行 `policy-init.py`。管理员修改模型后，
已运行用户需要重启 runtime；如果是旧版本创建的用户容器，还需要重建一次容器以获得
`/srv/hermes/policies` 挂载。

Admin WebUI 提供两个应用入口：

```text
应用到所有用户       删除所有 jupyter-{user} runtime 容器，保留用户数据
重建该用户容器       只删除指定用户的 jupyter-{user} runtime 容器，保留用户数据
```

这两个操作不会删除 `/srv/hermes/users/{user}` 或本地 `.data/users/{user}`。用户下次
Launch/Spawn 时，JupyterHub 会按最新 policy 新建容器，runtime 会重新生成
`HERMES_HOME/config.yaml`。

## 数据工具审计

Runtime 会对命中的数据工具写 JSONL 审计：

```text
/home/hermes/data/audit/data-tools.jsonl
```

记录字段包括：

```text
user_id
session_id
turn_id
tool_call_id
tool_name
status
model
model_tier
data_profile.category
data_profile.connector_ids
data_profile.intent
duration_ms
```

审计不会记录 SQL 全文、代码全文、文件正文或 API Key。敏感参数只记录长度和 SHA256。

当前会被审计的调用包括：

```text
mcp_* 数据工具
ClickHouse/Postgres/MySQL/SQLite/DuckDB/Mongo/Redis 等数据库工具
Dify/knowledge/retrieval/RAG 等知识库工具
终端或 execute_code 中出现数据库连接/查询痕迹的调用
```

## User Override

给单个用户覆盖：

```text
configs/policies/users/alice.json
```

示例：

```json
{
  "resources": {
    "cpu_limit": 4,
    "memory_limit": "8g",
    "disk_quota_bytes": 53687091200
  },
  "model_policy": {
    "allow_user_online_model_api_key": true,
    "mode": "privacy-router",
    "tiers": {
      "quality": "online-quality",
      "fast": "online-fast"
    }
  }
}
```

用户策略会覆盖全局策略。嵌套对象会做深度合并。

## Runtime Privacy Guard

Runtime Privacy Guard 是用户容器里的硬约束层，不依赖模型“自觉”遵守。

当前行为：

```text
1. 用户选择“高质量 / 快速”时，Runtime 会收窄工具集，只保留 online_allowed_toolsets。
2. 如果在线档位仍试图调用 private_tool_names 或 mcp_* 工具，会在执行前被阻止。
3. “本地安全”档位可以使用 private 工具，但终端/代码执行/MCP 数据工具仍会阻止数据库写 SQL、交互式数据库客户端和默认网络外传命令。
4. 数据库写权限必须在基础设施侧继续用只读账号和网络 ACL 保证。
```

示例策略：

```json
{
  "model_policy": {
    "runtime_privacy_guard_enabled": true,
    "online_allowed_toolsets": ["web", "vision", "clarify", "todo", "image_gen"],
    "private_tool_names": [
      "terminal",
      "process",
      "execute_code",
      "read_file",
      "write_file",
      "patch",
      "search_files",
      "memory",
      "session_search",
      "skill_manage"
    ],
    "public_mcp_tool_prefixes": [],
    "allow_terminal_network": false,
    "allow_code_network": false
  }
}
```

生产建议：

```text
ClickHouse/Postgres/MySQL 只给 readonly 用户
用户 runtime 容器不挂载管理员写账号
用户 runtime 默认禁止公网 egress，只允许模型网关、Dify、只读 MCP 等必要地址
上传文件、用户工作区文件、会话记忆默认视为 private
审计日志记录 tool、tier、blocked_by、reason，不记录 SQL 全文、文件全文或 API Key
```

## 用户自带在线模型 Key

可以允许用户自己配置在线模型 API Key，但必须遵守两个规则：

```text
1. 管理员显式允许
2. private 数据不能走用户自己的在线 Key
```

策略字段：

```json
{
  "model_policy": {
    "allow_user_online_model_api_key": true
  }
}
```

含义：

- 用户可以为“高质量 / 快速”这类 public 档位提供自己的在线模型 Key。
- “本地安全”档位仍然走管理员配置的本地模型。
- ClickHouse、private Dify、private 文件内容不能发送到用户在线模型。
- 在线 Key 不应该写入 JupyterHub 配置，也不应该进入 Admin Service 明文日志。

后续实现用户 Key 时，建议：
当前 Runtime 已经实现了第一版用户 Key 存储和读取：

```text
用户 Key 存在用户自己的 Hermes 数据目录
只在“高质量 / 快速”档位读取
private 工具调用时强制忽略用户 Key
审计日志只记录 key_ref，不记录明文
```

接口：

```text
GET  /api/user-online-model-keys/status
POST /api/user-online-model-keys/save
POST /api/user-online-model-keys/delete
```

保存内容只允许：

```text
tier=quality
tier=fast
```

`tier=safe` 会被拒绝。“本地安全”档位运行时也不会读取用户 Key。

## JupyterHub 应用方式

当前 `docker/jupyterhub/jupyterhub_config.py` 会：

```text
1. 读取 HERMES_POLICY_ROOT/global.json
2. 读取 HERMES_POLICY_ROOT/users/{username}.json
3. 合并策略
4. 如果 enabled=false，拒绝启动用户容器
5. 设置 spawner.cpu_limit / spawner.mem_limit
6. 注入模型策略、托管 data_connectors、Dify、ClickHouse 等环境变量
7. 校验数据库 connector 只读，并托管 MCP servers
8. 可选覆盖 recommended_skills_root 挂载
```

## Dify Knowledge 站点映射

Admin WebUI 的“数据连接 -> Dify Knowledge 管理”用于维护野外站知识库映射。
推荐把 Dify 当作知识库检索层，把 Hermes 当作对话、分析、制图和文件生成层。

全局策略保存为：

```json
{
  "dify_knowledge": {
    "enabled": true,
    "base_url": "http://dify.internal/v1",
    "api_key": "********",
    "privacy_level": "public",
    "access_mode": "read-only",
    "top_k": 5,
    "stations": [
      {
        "enabled": true,
        "station_id": "changbaishan",
        "station_name": "长白山站",
        "dataset_id": "00000000-0000-0000-0000-000000000000",
        "tags": ["文献", "标准", "专著"]
      }
    ]
  }
}
```

用户容器 Spawn 时会注入：

```text
DIFY_KNOWLEDGE_BASE_URL
DIFY_KNOWLEDGE_API_KEY
DIFY_KNOWLEDGE_PRIVACY_LEVEL
DIFY_KNOWLEDGE_ACCESS_MODE
DIFY_KNOWLEDGE_TOP_K
DIFY_KNOWLEDGE_STATIONS_JSON
HERMES_APPROVED_CONNECTOR_BASE_URLS
```

Dify Knowledge 不强制要求 MCP。管理员在 Admin WebUI 填入 `base_url` 和
`api_key` 后，Runtime 会把该 Dify 地址登记为管理员批准的只读知识源：

```text
dify_knowledge.privacy_level=public
dify_knowledge.access_mode=read-only
```

在运行时隐私保护开启的情况下，终端/代码里的未知网络访问仍会被拦截；但如果访问的是
`DIFY_KNOWLEDGE_BASE_URL` 或 `HERMES_APPROVED_CONNECTOR_BASE_URLS` 中的地址，
会被视为已批准的 Dify Knowledge API 调用。数据库写入、交互式数据库客户端、未知外联、
低层 socket/ssh 等仍然保持拦截。

WebUI 会把站点映射作为临时运行提示注入给 Agent。用户询问某个站点的文献、标准、
专著或知识库内容时，Agent 应优先查找 `DIFY_KNOWLEDGE_STATIONS_JSON` 中的站点映射，
并使用匹配的 `dataset_id` 调用 Dify Knowledge API，而不是要求用户再次提供地址、Key
或 dataset_id。常用只读接口：

```text
POST {DIFY_KNOWLEDGE_BASE_URL}/datasets/{dataset_id}/retrieve
GET  {DIFY_KNOWLEDGE_BASE_URL}/datasets/{dataset_id}/documents
```

Dify 官方建议 API Key 只在服务端保存，不要放到浏览器前端。当前内测方案把 Key
注入用户 runtime 容器，适合小范围可信内测；正式上线更推荐由 Admin/内部 proxy
持有 Dify Key，用户容器只调用受控的检索工具。

## 本地验证

修改：

```text
configs/policies/global.json
```

或者新增：

```text
configs/policies/users/alice.json
```

然后重启对应用户 server。用户容器重新 spawn 后策略生效。

## 和未来 Admin Service 的关系

现在的 JSON 文件就是未来 Admin Service 的输出格式。

第一阶段可以手写 JSON 验证闭环；第二阶段 Admin Service 只需要把数据库里的配置渲染
成同样的 JSON 文件即可。
