# 管理员模型与数据路由方案

## 目标

生产环境里，模型配置应该由管理员统一控制，而不是让用户随意连接外网模型。

核心要求：

- 涉及隐私数据的任务必须走本地模型。
- 非隐私任务可以走性能更好的在线模型。
- 用户容器里不保存在线模型的真实 API Key。
- 数据库和知识库工具要有明确的数据分级。

当前数据源分级建议：

```text
ClickHouse / 数据库      private
Dify / 本地知识库        public 或 private，取决于知识库内容
普通写作/总结/格式化     public
```

## 推荐架构

不要让 Hermes 直接配置多个模型供应商。推荐加一个管理员控制的 OpenAI-compatible
模型网关：

```text
Hermes 用户容器
  ↓
Admin Model Gateway 统一模型网关
  ├─ local-private-model  本地模型
  └─ online-public-model  在线模型
```

Hermes Runtime 只看到一个模型地址：

```env
MODEL_PROVIDER=openai-compatible
MODEL_BASE_URL=https://model-gateway.example.com/v1
MODEL_API_KEY=网关签发的内部 token
MODEL_DEFAULT=local-private-default
```

在线模型的真实 Key 只存在模型网关服务器，不进入用户容器。

## 路由策略

第一版先用保守策略：

```env
HERMES_MODEL_POLICY_MODE=local-only
```

这表示所有任务都走本地模型。等系统稳定后，再切到：

```env
HERMES_MODEL_POLICY_MODE=privacy-router
```

路由规则：

```text
如果请求调用了 private 工具：
  使用 local-private-model

如果请求包含 private 数据源结果：
  使用 local-private-model

如果请求只涉及 public 工具或普通对话：
  允许使用 online-public-model
```

建议环境变量：

```env
HERMES_PRIVATE_MODEL_ID=local-private-default
HERMES_PUBLIC_MODEL_ID=online-public-default
HERMES_MODEL_TIER_SAFE_MODEL=local-private-default
HERMES_MODEL_TIER_QUALITY_MODEL=local-private-default
HERMES_MODEL_TIER_FAST_MODEL=local-private-default
HERMES_MODEL_GATEWAY_PROVIDER=
HERMES_PRIVACY_TOOL_NAMES=clickhouse,postgres,sqlite,database,mcp_clickhouse
HERMES_ALLOW_USER_MODEL_SETTINGS=false
HERMES_ALLOW_USER_ONLINE_MODEL_API_KEY=false
HERMES_RUNTIME_PRIVACY_GUARD_ENABLED=true
HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS=web,vision,clarify,todo,image_gen
HERMES_ALLOW_TERMINAL_NETWORK=false
HERMES_ALLOW_CODE_NETWORK=false
HERMES_ALLOWED_DATA_CONNECTORS=dify-public,clickhouse-readonly
HERMES_DATA_AUDIT_ENABLED=true
HERMES_DATA_AUDIT_LOG_PATH=/home/hermes/data/audit/data-tools.jsonl
```

用户看到的不是供应商名，而是三个档位：

```text
本地安全  -> HERMES_MODEL_TIER_SAFE_MODEL
高质量    -> HERMES_MODEL_TIER_QUALITY_MODEL
快速      -> HERMES_MODEL_TIER_FAST_MODEL
```

第一阶段可以三个档位全部指向本地模型。第二阶段接入模型网关后，再让高质量和快速
指向网关里的在线模型别名。

## Runtime 隐私安全闭环

当前 WebUI Runtime 已经做了第一版硬约束：

```text
高质量 / 快速：
  只保留 public 工具集
  默认允许 web、vision、clarify、todo、image_gen
  禁止 terminal、file、MCP、memory、session_search、browser automation 等 private 工具

本地安全：
  可以使用 private 数据工具
  终端和代码执行仍会拦截数据库写入、交互式数据库客户端、常见网络外传命令
```

对应配置：

```env
HERMES_RUNTIME_PRIVACY_GUARD_ENABLED=true
HERMES_ONLINE_MODEL_ALLOWED_TOOLSETS=web,vision,clarify,todo,image_gen
HERMES_PRIVATE_TOOL_NAMES=terminal,process,read_terminal,execute_code,read_file,write_file,patch,search_files,memory,session_search,skill_manage,cronjob,delegate_task,send_message,browser_navigate,browser_snapshot,browser_click,browser_type,browser_scroll,browser_back,browser_press,browser_get_images,browser_vision,browser_console,browser_cdp,browser_dialog,computer_use
HERMES_PUBLIC_MCP_TOOL_PREFIXES=
HERMES_ALLOW_TERMINAL_NETWORK=false
HERMES_ALLOW_CODE_NETWORK=false
```

注意：应用层 guard 不能替代基础设施权限。数据库必须使用只读账号，Docker 网络必须限制
用户容器直连生产数据库和公网出口。否则用户仍可能通过第三方工具或未来新增工具形成绕路。

## ClickHouse 配置

ClickHouse 属于 private 数据源，不建议让模型直接拿到任意连接信息。推荐通过管理员策略
定义只读连接，再通过内部 MCP 服务暴露只读查询能力：

```text
Hermes Runtime
  ↓ internal network only
ClickHouse MCP Server
  ↓ readonly account
ClickHouse
```

策略示例：

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

安全要求：

- 使用只读账号。
- `access_mode` 必须是 `read-only`，否则 JupyterHub 拒绝启动用户容器。
- 限制可访问数据库和表。
- 限制单次查询行数、执行时长和导出大小。
- 查询结果进入模型上下文前标记为 private。
- private 上下文禁止发送到在线模型。
- 不把管理员级数据库写账号放进用户容器。
- 不允许用户容器通过命令行直接访问数据库写端口；推荐只暴露只读 MCP/只读查询服务。
- 对上传文件默认按 private 处理，除非用户或业务系统明确标记为 public。
- Runtime 会拦截终端、代码执行、MCP 数据工具里的数据库写意图，但这只是应用层防线。

## Dify 配置

Dify 是否 private 取决于知识库内容，不取决于技术形态。

如果 Dify 里只有公开资料：

```env
DIFY_PRIVACY_LEVEL=public
```

这类检索结果可以允许进入在线模型。

如果 Dify 里有内部文档、客户数据、未公开报告：

```env
DIFY_PRIVACY_LEVEL=private
```

这类检索结果必须走本地模型。

策略示例：

```json
{
  "data_connectors": {
    "connectors": [
      {
        "id": "dify-public",
        "type": "dify",
        "enabled": true,
        "base_url": "http://dify.internal",
        "api_key": "change-me",
        "app_id": "change-me",
        "privacy_level": "public",
        "access_mode": "read-only"
      }
    ]
  }
}
```

## 数据工具审计

所有命中数据连接面的工具调用都会写入：

```text
/home/hermes/data/audit/data-tools.jsonl
```

审计记录包含：

```text
用户 ID、会话 ID、工具名、模型档位、连接 ID、数据类型、读写意图、执行状态、耗时
```

审计记录不包含：

```text
SQL 全文、代码全文、文件正文、API Key、数据库密码
```

这份日志用于回答三类问题：

```text
谁在什么时候访问了哪个数据连接
当时使用的是本地安全模型还是在线档位
调用是完成、失败，还是被只读/隐私策略拦截
```

## 用户模型设置

生产环境建议：

```env
HERMES_ALLOW_USER_MODEL_SETTINGS=false
```

含义：

- 用户不直接配置模型供应商。
- 用户不看到在线模型 API Key。
- 用户最多选择“高质量 / 快速 / 本地安全”等管理员定义好的档位。
- 真实模型 ID 和供应商由模型网关映射。

当前 WebUI 已接入管理员锁定策略：

```text
HERMES_ALLOW_USER_MODEL_SETTINGS=false
```

开启后：

- `/api/models` 只返回“本地安全 / 高质量 / 快速”三个档位。
- 用户创建新会话时，`policy:safe` 会解析为 `HERMES_MODEL_TIER_SAFE_MODEL`。
- `policy:quality` 会解析为 `HERMES_MODEL_TIER_QUALITY_MODEL`。
- `policy:fast` 会解析为 `HERMES_MODEL_TIER_FAST_MODEL`。
- 如果用户绕过前端随意传模型 ID，后端会回退到“本地安全”档位。
- 保存默认模型时不会改写用户 profile 里的真实模型配置。

如果需要把档位固定到某个模型网关 provider：

```env
HERMES_MODEL_GATEWAY_PROVIDER=custom
```

如果留空，则只按模型 ID 交给现有模型解析逻辑处理。

## 用户自己的在线模型 Key

有些在线模型可以允许用户使用自己的 API Key，消耗用户自己的 token。但这个能力只应该
开放给非隐私档位：

```text
高质量 -> 可以使用用户自己的在线 Key
快速   -> 可以使用用户自己的在线 Key
本地安全 -> 不允许使用用户自己的在线 Key
```

管理员需要显式开启：

```env
HERMES_ALLOW_USER_ONLINE_MODEL_API_KEY=true
```

WebUI Runtime 已提供后端接口：

```text
GET  /api/user-online-model-keys/status
POST /api/user-online-model-keys/save
POST /api/user-online-model-keys/delete
```

保存示例：

```json
{
  "tier": "quality",
  "api_key": "sk-..."
}
```

删除示例：

```json
{
  "tier": "fast"
}
```

接口只返回是否已配置和 Key 末四位，不返回明文。Key 保存在当前用户自己的 Hermes 数据
目录：

```text
{HERMES_HOME}/user-online-model-keys.json
```

文件会尽量设置为 `0600`。如果用户没有配置对应档位 Key，运行时会回退到管理员配置的
Key。即使用户传入 `safe`，后端也会拒绝保存；本地安全档位运行时也不会读取用户 Key。

## 最小落地顺序

第一阶段：

```text
只接本地模型
Hermes 只配置 MODEL_BASE_URL 到本地模型网关
禁用用户自定义模型配置
ClickHouse 只读 MCP 接入
Dify 标记 privacy level
```

第二阶段：

```text
模型网关增加 online-public-model
普通非隐私任务允许在线模型
private 工具调用强制本地模型
记录每次路由原因
```

第三阶段：

```text
前端显示模型档位，不显示供应商密钥
管理员后台维护模型策略
增加审计日志和告警
```

## 关键原则

真正的安全边界不应只靠前端 UI。

需要同时做三层控制：

```text
前端：不展示危险配置入口
后端：模型网关做路由和拒绝
网络：用户容器不能直接访问外网模型 API
```

这样即使用户进入容器或通过工具发起请求，也只能访问管理员允许的模型出口。
