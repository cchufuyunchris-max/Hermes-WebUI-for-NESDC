# 推荐 Skill 管理方案

## 目标

第一版只做“管理员推荐 skill”，不做“我的技能”同步。

原因是 Hermes WebUI / Hermes Agent 已经有自己的 skill 面板和用户 skill 目录。
平台侧重复做“我的技能”会增加状态同步和权限边界，收益不高。

## 分工

```text
管理员推荐源
  /srv/hermes/recommended-skills
  或本地开发的 ./skills

用户实际 skill
  /srv/hermes/users/{id}/skills
  容器内路径：/home/hermes/data/skills

Hermes WebUI skill 面板
  读取和管理用户实际 skill
```

管理员只更新推荐源。用户实际安装 skill 的动作，交给后续 Skill Hub 或 Hermes
WebUI 原生能力完成；默认不把推荐 skill 自动塞进用户目录。

## 本地开发

本地 `docker-compose.local.yml` 已经把仓库的 `skills/` 作为推荐源：

```env
HERMES_HOST_PROVISIONED_SKILLS_ROOT=/Users/chufuyun/Documents/Hermes WebUI/skills
```

JupyterHub 会把它只读挂载进每个用户容器：

```text
/home/hermes/provisioned-skills
```

更新本地推荐 skill 后，它可以作为未来 Skill Hub 的数据源。默认情况下不会自动
安装到用户目录。

## 生产部署

生产推荐使用宿主机目录：

```text
/srv/hermes/recommended-skills
```

JupyterHub 环境变量：

```env
HERMES_HOST_PROVISIONED_SKILLS_ROOT=/srv/hermes/recommended-skills
HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS=false
PROJECT_SKILLS_UPDATE_POLICY=manual
```

每个推荐 skill 建议包含：

```text
skill-name/
  SKILL.md
  skill-version.json
  references/
  scripts/
  templates/
  assets/
```

`skill-version.json` 示例：

```json
{
  "version": "2026.06.24",
  "title": "生态站气候报告",
  "description": "生成生态站气候分析报告的推荐工作流"
}
```

## 更新策略

第一版使用：

```env
HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS=false
PROJECT_SKILLS_UPDATE_POLICY=manual
```

行为：

- 新用户第一次启动时不会自动获得推荐 skill。
- 管理员维护推荐源，作为 Skill Hub 的展示和安装来源。
- 用户是否安装，交给后续 Skill Hub 按钮或 Hermes WebUI 原生 skill 面板处理。
- 如果临时需要恢复“启动时自动安装”，再把 `HERMES_AUTO_INSTALL_RECOMMENDED_SKILLS=true` 打开。

可选策略：

```text
manual  只检测，不自动覆盖
safe    用户未修改时自动升级
force   强制覆盖，只建议测试环境使用
```

## 后续管理端

如果以后要做管理员后台，MVP 只需要三个能力：

```text
上传/编辑推荐 skill
发布 skill-version.json 新版本
查看当前推荐列表
```

不需要做：

```text
我的技能同步
收藏
连接收藏
用户技能资产管理
```

这样平台管理端保持轻，Hermes WebUI 继续负责用户侧 skill 体验。

## 已落地的 WebUI MVP

当前最小版已经接入 Hermes WebUI 的 Skill Hub 页面：

```text
GET  /api/skillhub/recommended
POST /api/skillhub/install
```

行为：

- `/api/skillhub/recommended` 读取 `HERMES_PROVISIONED_SKILLS_DIR` 下的推荐 skill。
- 推荐 skill 必须至少包含 `SKILL.md`。
- `skill-version.json` 可选，用于提供 `version`、`title`、`description`、`tags`。
- `/api/skillhub/install` 将推荐 skill 完整复制到当前用户 Hermes profile 的 `skills` 目录。
- 安装目标使用 WebUI 原生 skill 面板实际读取的路径，即 `HERMES_HOME/skills`。

第一版页面只保留：

```text
推荐列表
搜索
安装按钮
已安装状态
```

暂时不做：

```text
我的技能同步
收藏
连接收藏
团队库
强制升级
```

## 从 GitHub 导入推荐 Skill

管理后台支持从 GitHub 仓库导入推荐 Skill：

1. 打开 `http://127.0.0.1:8001/admin.html`
2. 进入「推荐 Skill」
3. 在「从 GitHub 导入」中填写仓库地址，例如：

```text
https://github.com/Yuan1z0825/nature-skills
```

可选字段：

- `Ref / 分支`：默认 `main`，也可以填写 tag、branch 或 commit。
- `子目录`：只扫描仓库中的某个目录。
- `目录前缀`：给导入到推荐目录的 Skill ID 加前缀，避免同名冲突。
- `覆盖同名推荐 Skill`：开启后会替换已有同名推荐 Skill。

后台会下载 GitHub zip 包，扫描所有 `SKILL.md`，然后把对应目录复制到推荐 Skill 目录。导入过程不会执行仓库里的代码。

生产环境建议只允许管理员使用该功能，并配合 GitHub 来源白名单或人工审核流程。
