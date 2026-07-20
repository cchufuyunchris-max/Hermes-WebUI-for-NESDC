# Hermes 管理后端设计

## 目标

Hermes 工程化以后，需要一个独立的管理后端，统一管理：

```text
1. 推荐 skill 的上传、更新、删除
2. 模型档位和模型路由策略
3. 知识库、数据库连接
4. 用户管理、容器资源和磁盘空间分配
```

这个管理后端建议命名为：

```text
Hermes Admin Service
```

它不是给普通用户使用的 WebUI，也不是每个用户容器的一部分。它是平台侧的控制面。

## 总体架构

```text
Java + Vue 主平台
  ├─ 用户登录、组织、权限、菜单
  └─ iframe 打开 Hermes WebUI

Hermes Admin Service
  ├─ Skill 管理
  ├─ 模型策略管理
  ├─ 数据源管理
  ├─ 用户配额管理
  └─ 写入 JupyterHub / Hermes Runtime 所需配置

JupyterHub + DockerSpawner
  ├─ 用户认证接入 OAuth
  ├─ 按用户创建容器
  ├─ 按用户挂载目录
  └─ 按用户应用 CPU / 内存 / 磁盘 / 环境变量

Hermes Runtime
  ├─ Hermes WebUI
  ├─ Hermes Agent
  ├─ 推荐 Skill Hub
  └─ 用户会话、文件、记忆、skill
```

## 服务边界

### 主平台负责

```text
用户注册
用户登录
角色权限
套餐/资源购买
业务入口导航
```

### Hermes Admin Service 负责

```text
管理员配置 Hermes 能力
维护推荐 skill
维护模型档位
维护数据库/知识库连接
维护用户容器资源配额
生成 JupyterHub / Runtime 策略
```

### JupyterHub 负责

```text
用户鉴权后的容器生命周期
按用户启动 Hermes Runtime
按用户挂载持久目录
按用户设置资源限制
```

### Hermes Runtime 负责

```text
用户实际使用 WebUI
保存会话、记忆、文件、用户安装 skill
调用模型网关
调用被允许的数据源工具
```

## 数据存储

建议 Admin Service 使用一套自己的数据库，例如 PostgreSQL。

不要把管理配置散落在 `.env`、JupyterHub SQLite、用户目录里。`.env` 适合本地开发，
生产环境应该由 Admin Service 生成或下发。

推荐表：

```text
admin_users
admin_audit_logs
skills
skill_versions
model_tiers
model_gateways
data_sources
knowledge_bases
user_resource_plans
user_runtime_overrides
runtime_policy_snapshots
```

## 模块 1：Skill 管理

### 功能

```text
上传 skill 包
校验 SKILL.md
编辑 skill-version.json
发布新版本
下架 skill
删除 skill
查看安装次数
```

### 存储路径

生产环境推荐：

```text
/srv/hermes/recommended-skills/{skill_name}/
```

每个 skill：

```text
skill-name/
  SKILL.md
  skill-version.json
  references/
  scripts/
  templates/
  assets/
```

### API 草案

```text
GET    /admin/api/skills
POST   /admin/api/skills
GET    /admin/api/skills/{name}
PUT    /admin/api/skills/{name}
DELETE /admin/api/skills/{name}
POST   /admin/api/skills/{name}/versions
POST   /admin/api/skills/{name}/publish
POST   /admin/api/skills/{name}/unpublish
```

### 和 WebUI 的关系

WebUI 已经有：

```text
GET  /api/skillhub/recommended
POST /api/skillhub/install
```

Admin Service 只需要维护推荐目录。用户安装仍然在 Hermes WebUI 里完成。

## 模块 2：模型控制

### 用户看到的档位

普通用户不看供应商和 Key，只看到：

```text
本地安全
高质量
快速
```

管理员配置真实映射：

```text
本地安全 -> local-private-default
高质量   -> online-quality
快速     -> online-fast
```

### 配置项

```env
HERMES_ALLOW_USER_MODEL_SETTINGS=false
HERMES_MODEL_POLICY_MODE=local-only 或 privacy-router
HERMES_MODEL_TIER_SAFE_MODEL=local-private-default
HERMES_MODEL_TIER_QUALITY_MODEL=online-quality
HERMES_MODEL_TIER_FAST_MODEL=online-fast
HERMES_MODEL_GATEWAY_PROVIDER=custom
```

### 管理端能力

```text
配置模型网关地址
配置本地模型
配置在线模型
配置三个用户档位
设置默认档位
设置隐私路由策略
查看调用审计
禁用用户自定义模型
```

### API 草案

```text
GET  /admin/api/model-gateways
POST /admin/api/model-gateways
PUT  /admin/api/model-gateways/{id}

GET  /admin/api/model-tiers
PUT  /admin/api/model-tiers/safe
PUT  /admin/api/model-tiers/quality
PUT  /admin/api/model-tiers/fast

GET  /admin/api/model-policy
PUT  /admin/api/model-policy
```

### 安全边界

在线模型 Key 不进入用户容器。

推荐做法：

```text
Hermes Runtime 只连接 Admin Model Gateway
Admin Model Gateway 决定转发到本地模型还是在线模型
```

## 模块 3：知识库和数据库连接

### 数据分级

每个数据源必须标记：

```text
public   可以进入在线模型
private 只能进入本地模型
```

当前建议：

```text
ClickHouse / 数据库：private
Dify：取决于知识库内容，可 public，也可 private
```

### 数据源类型

第一版支持：

```text
Dify knowledge base
ClickHouse
```

后续可以扩展：

```text
PostgreSQL
MySQL
文件知识库
向量库
内部 API
```

### API 草案

```text
GET    /admin/api/data-sources
POST   /admin/api/data-sources
GET    /admin/api/data-sources/{id}
PUT    /admin/api/data-sources/{id}
DELETE /admin/api/data-sources/{id}
POST   /admin/api/data-sources/{id}/test

GET    /admin/api/knowledge-bases
POST   /admin/api/knowledge-bases
PUT    /admin/api/knowledge-bases/{id}
DELETE /admin/api/knowledge-bases/{id}
POST   /admin/api/knowledge-bases/{id}/test
```

### ClickHouse 建议

不要把 ClickHouse 账号直接交给模型。建议通过内部 MCP 服务：

```text
Hermes Runtime
  ↓
ClickHouse MCP Server
  ↓ readonly
ClickHouse
```

管理端保存：

```text
host
port
database
readonly user
password / secret ref
allowed databases
allowed tables
max rows
max execution seconds
privacy level
```

### Dify 建议

管理端保存：

```text
base_url
app_id
api_key / secret ref
privacy level
description
enabled
```

## 模块 4：用户管理和资源分配

### 用户来源

用户身份仍以主平台为准：

```text
platform_user_id = OAuth userinfo.id
```

Hermes Admin Service 不做注册系统，只缓存 Hermes 需要的运行策略。

### 管理能力

```text
查看用户
禁用用户 Hermes 访问
设置 CPU 限制
设置内存限制
设置磁盘配额
设置默认模型档位
设置可用 skill 范围
查看容器状态
停止用户容器
重启用户容器
清理或归档用户数据
```

### API 草案

```text
GET  /admin/api/users
GET  /admin/api/users/{id}
PUT  /admin/api/users/{id}/runtime-policy
POST /admin/api/users/{id}/stop-server
POST /admin/api/users/{id}/restart-server
GET  /admin/api/users/{id}/usage
```

### 资源策略

建议分成 plan：

```text
free
standard
pro
enterprise
```

每个 plan：

```text
cpu_limit
memory_limit
disk_quota
max_concurrent_sessions
allowed_model_tiers
allowed_data_sources
```

JupyterHub 当前已经支持：

```python
c.Spawner.mem_limit
c.Spawner.cpu_limit
```

后续要改成 per-user：

```text
pre_spawn_hook 查询 Admin Service
根据用户 id 设置 spawner.mem_limit
根据用户 id 设置 spawner.cpu_limit
根据用户 id 设置挂载目录
根据用户 id 注入环境变量
```

### 磁盘配额

DockerSpawner 本身不直接优雅管理每个 bind mount 的磁盘上限。

生产可选方案：

```text
1. 宿主机文件系统 quota
2. 每用户独立 Docker volume + 外部 quota 管理
3. 定期扫描用户目录，超过配额后禁止新任务/上传
4. 对象存储托管大文件，用户目录只保留索引
```

MVP 推荐：

```text
定期扫描 /srv/hermes/users/{id}
记录 used_bytes
超过配额后：
  禁止上传
  禁止新建大文件任务
  提醒管理员或用户清理
```

## Admin Service 与 JupyterHub 集成

### 方案 A：JupyterHub 启动时查询 Admin Service

`pre_spawn_hook`：

```text
1. 拿到 username / platform_user_id
2. 调用 Admin Service /internal/runtime-policy/{user_id}
3. 设置 CPU / 内存 / 环境变量 / 挂载目录
4. 启动用户容器
```

优点：

```text
策略实时
适合套餐和权限经常变化
```

缺点：

```text
Admin Service 不可用时会影响 spawn
需要缓存和 fallback
```

### 方案 B：Admin Service 生成本地策略文件

Admin Service 写：

```text
/srv/hermes/policies/users/{id}.json
/srv/hermes/policies/global.json
```

JupyterHub 读取本地 JSON。

优点：

```text
稳定
不依赖每次 spawn 的网络请求
```

缺点：

```text
策略变更有同步延迟
```

MVP 推荐：方案 B。

当前已先实现方案 B 的本地闭环：

```text
configs/policies/global.json
configs/policies/users/{username}.json
```

JupyterHub 会在 `pre_spawn_hook` 中读取并应用这些策略。详细说明见：

```text
docs/runtime-policy-closed-loop.md
```

## 配置下发方式

生产不要让管理员直接编辑 `.env`。

推荐：

```text
Admin Service DB
  ↓
策略文件 / policy snapshots
  ↓
JupyterHub pre_spawn_hook
  ↓
用户 Hermes Runtime 环境变量
```

示例用户策略：

```json
{
  "user_id": "12345",
  "enabled": true,
  "plan": "standard",
  "cpu_limit": 2,
  "memory_limit": "4g",
  "disk_quota_bytes": 21474836480,
  "model_policy": {
    "allow_user_model_settings": false,
    "default_tier": "safe",
    "allowed_tiers": ["safe", "quality", "fast"]
  },
  "data_sources": ["dify-public", "clickhouse-readonly"],
  "recommended_skills_root": "/srv/hermes/recommended-skills"
}
```

## 权限模型

管理端至少需要：

```text
super_admin
ops_admin
skill_admin
model_admin
data_admin
support_admin
```

权限建议：

```text
skill_admin 只能管理 skill
model_admin 只能管理模型档位和模型网关
data_admin 只能管理数据源
support_admin 只能查看用户状态、重启容器，不能看密钥
super_admin 全部权限
```

## 审计日志

所有高风险操作必须记日志：

```text
上传/删除 skill
修改模型档位
修改模型网关 Key
修改数据库连接
修改用户资源配额
停止/重启用户容器
禁用用户
```

日志字段：

```text
operator_id
action
target_type
target_id
before
after
ip
created_at
```

## 开发顺序

### 第 1 阶段：Admin Service MVP

```text
1. 建库和基础 API
2. Skill 上传、列表、删除
3. 模型三个档位配置
4. 数据源配置只做保存和测试连接
5. 用户资源 plan 保存
6. 生成本地 policy JSON
```

### 第 2 阶段：接入 JupyterHub

```text
1. pre_spawn_hook 读取 policy JSON
2. 按用户设置 CPU / 内存
3. 按用户注入模型档位变量
4. 按用户注入 Dify / ClickHouse 变量
5. 按用户禁用 Hermes 访问
```

### 第 3 阶段：资源和审计

```text
1. 用户目录大小扫描
2. 上传/文件写入配额限制
3. 容器状态查看
4. 停止/重启用户容器
5. 审计日志页面
```

### 第 4 阶段：模型隐私路由

```text
1. 模型网关接入本地模型和在线模型
2. private 工具强制本地模型
3. public 任务允许高质量/快速在线模型
4. 路由原因记录
```

## 技术选型建议

因为主平台是 Java + Vue，有两种路线：

### 路线 A：Admin Service 用 Java

适合：

```text
团队熟悉 Java
希望和主平台共用认证、权限、审计
```

建议：

```text
Spring Boot + PostgreSQL + MinIO/本地文件存储
```

### 路线 B：Admin Service 用 Python

适合：

```text
更贴近 JupyterHub / Docker / Hermes 脚本生态
快速开发内部控制面
```

建议：

```text
FastAPI + PostgreSQL + Alembic
```

当前项目阶段推荐路线 A 或 A+B：

```text
Java 主平台提供管理页面和权限
Hermes Admin Service 可以先用 Python/FastAPI 做内部控制 API
稳定后再决定是否合并到 Java 管理端
```

## MVP 边界

第一版不要做太大。

必须做：

```text
推荐 skill 上传/删除
模型三个档位配置
Dify / ClickHouse 连接配置
用户 CPU / 内存 / 磁盘配额配置
生成 policy JSON
JupyterHub 读取 policy JSON
```

暂时不做：

```text
复杂计费
实时用量扣费
在线模型自动成本优化
复杂组织多租户
跨服务器迁移用户目录
精细到表字段级的数据权限
```

这些可以等 Hermes 服务稳定后再扩展。
