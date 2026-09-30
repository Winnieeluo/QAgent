# IBM i PR QA Agent · 演示与交付方案

## 1. 目标与范围

**用户故事**：开发者选择本地 Git 仓库或在线 GitHub PR，QA Agent 比较目标分支与 HEAD，汇总差异、IBM i 专项风险、证据位置和建议验证步骤。网页将两种来源的结果呈现在同一处；AgentHub 后续可调用相同审查契约。

**本次已交付**：可生成的虚构双分支仓库、三条可解释的确定性检查、Markdown/JSON 报告、本地与 GitHub PR 双模式网页、默认关闭的模型调用、IBM i skill 适配器接口、自动测试、PR-Agent 本地模式配置、演示脚本和验证记录。

**尚未执行**：真实模型调用、现有 IBM i skill 连接、IBM i 编译、RPGUnit、端到端交易测试、AgentHub 平台集成、汇丰内部控制审批。这些结果不可在演示中宣称为通过。

## 2. 组件与复用策略

```text
网页输入：自动发现的本地仓库 + base 分支，或 GitHub PR URL + 可选只读令牌
  └─ 在线 PR：固定 base/head SHA → 临时检出 → 审查后清理
  ├─ 本包 qa_agent.py：Git 差异 → IBM i 专项规则 → JSON/Markdown
  ├─ 显式选择后：Responses 兼容模型 → 结构化建议 → 人工复核
  └─ 显式选择后：现有 IBM i skill 的 Python 适配器 → 只读数据证据
       └─ 后续测试环境：TOBi 构建 + IBM i Testing CLI 测试
```

| 组件 | 已核实的现成能力 | 本 demo 用法 |
|---|---|
| [PR-Agent](https://github.com/The-PR-Agent/pr-agent) | 本地 Git Provider 比较当前 HEAD 与目标分支并写入 `review.md`；可配置审查指令 | 独立命令行候选；当前仅提供配置，模型运行未验证 |
| [IBM TOBi](https://github.com/IBM/ibmi-tobi) | IBM i 原生对象的依赖构建 | 连接测试机后做编译证据；本次不运行 |
| [IBM i Testing](https://github.com/IBM/vscode-ibmi-testing) | CLI 可在 CI 中运行 RPG/COBOL 测试 | 连接测试机并有真实测试套件后运行 |
| [ibmi-ci](https://github.com/IBM/ibmi-ci) | 从流水线连接 IBM i 并执行命令 | 后续测试机桥接候选 |
| [IBM i MCP Server](https://github.com/IBM/ibmi-mcp-server) | 用 MCP 暴露 IBM i SQL 工具；需 Mapepire | AgentHub 需要实时系统数据时再引入 |

网页中的模型调用走独立的 Responses 适配层；PR-Agent 仍可作为独立命令行审查候选，保留上游更新路径。IBM i skill 的实现留在获批环境，通过 `run_checks(context)` 接入，避免把数据库连接逻辑或凭据发布到比赛仓库。接口细节见 [集成文档](INTEGRATIONS.md)。

**AgentHub 工具契约**：`review_local_ibmi_repo(repo_path, base_ref)` 与 `review_github_pr(repo_url, pr_number, temporary_token)` 返回固定的 `base_sha`/`head_sha`、规则发现 JSON、报告编号与各验证步骤状态（`passed` / `failed` / `not_run`）。本地路径限制在批准的工作区。网页分别通过 `POST /api/review` 与 `POST /api/github/review` 实现；尚未接入具体 AgentHub 平台。

## 3. 五分钟网页演示脚本

| 时间 | 操作 | 屏幕应显示的证据 |
|---|---|---|
| 0:00–0:45 | 打开 `http://127.0.0.1:8765/`，展示仓库、目标分支与当前分支 | 本地样例自动载入，当前 HEAD 可追溯 |
| 0:45–1:15 | 点击“运行变更审查” | 3 条发现、2 项高风险、3 个变更文件 |
| 1:15–2:45 | 依次选择 SQL 错误处理、DDS 精度、CL 日志三项发现 | 行号、Git diff、业务影响、验证建议 |
| 2:45–3:30 | 切换高/中风险筛选并导出 Markdown、JSON | 可交互筛选与可归档证据 |
| 3:30–4:15 | 展示验证状态和运行编号，运行自动测试 | 规则已运行；AI、编译与 RPGUnit 明确未运行 |
| 4:15–5:00 | 切换“在线仓库”，粘贴公开 PR 链接，读取并审查 | 同一套摘要、证据与导出；注明 AI、编译与测试未运行 |

## 4. 银行项目交付门槛

这是基于通用银行技术交付实践制定的**建议验收矩阵，不代表已获汇丰内部标准认证**。汇丰公开的 Conduct Approach 强调对风险、市场和操作采取可举证的方式；具体内部 SDLC、数据分类、模型使用和变更审批要求仍以团队文件为准。[HSBC Our Conduct](https://www.hsbc.com/who-we-are/our-strategy-and-values/our-conduct)

| 门槛 | 本次证据 | 正式落地前需补齐 |
|---|---|---|
| 可追溯性 | 固定 base/head、文件与行号、JSON 报告 | 记录 PR SHA、运行 ID、规则版本、模型版本 |
| 正确性 | 三项预期发现和回归测试 | 在 IBM i 上编译；正反例、边界值、回归与交易原子性测试 |
| 数据保护 | 全虚构样例；在线源码临时检出后删除，在线报告只保留在服务内存 | 数据分类、脱敏、模型出境/外发审批、日志保留期限与内存数据处置 |
| 访问控制 | 服务仅监听回环地址；本地路径限制；GitHub HTTPS 主机白名单；可选细粒度只读令牌 | 企业身份集成、集中密钥保管、RBAC、审计及代理策略 |
| 变更控制 | 报告只建议，不自动合并 | 人工审查、缺陷分流、例外审批、发布回退计划 |
| 依赖管理 | PR-Agent 上游项目与许可证已列明 | 固定版本、SBOM/漏洞扫描、第三方软件审批 |
| 运行韧性 | 脚本失败返回错误；输出单独保存 | 超时、重试、审查覆盖率、监控、故障处理手册 |

GitHub 官方建议工作流凭据遵循最小权限，并避免在具有高权限/密钥的 `pull_request_target` 作业中执行不可信 PR 代码。[GitHub Secure Use](https://docs.github.com/en/actions/reference/security/secure-use) 本 Demo 不执行 PR 代码，不创建 GitHub Action，也不自动评论。网页接受临时令牌来读取私有 PR；公开 PR 不需要令牌。账户密码不用于 Git 认证。[GitHub authentication](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)

## 5. 验收标准

1. 在 Windows PowerShell 执行 `.\start_web.ps1` 并打开网页；样例仓库自动显示三项规则发现。
2. 风险筛选、发现详情、Git diff 和 Markdown/JSON 导出可用。
3. `python -m unittest discover -s tests -v` 全部通过。
4. `git -C demo-repo status --short` 无输出。
5. 报告可指出准确文件与行号、变更证据、影响和下一步验证，且默认声明未编译、未调用模型；扩展步骤只有实际执行才改变状态。
6. 加上真实 IBM i 环境后，编译与测试结果必须作为独立证据显示；模型意见不得冒充测试结果。

## 6. 上线演进

**阶段 A：手动评估**。由 QA 主动选择本地仓库或公开 PR，处理获批测试代码；本地报告保存到本机，在线报告只留在服务内存。

**阶段 B：受控团队试点**。AgentHub 接入已批准模型；设置访问控制与日志；对若干真实但可使用的 PR 做人工盲评，记录准确率、误报、漏报、时延。

**阶段 C：CI 与 IBM i 测试机**。加入 TOBi 构建、RPGUnit/IBM i Testing CLI、失败日志；用隔离库与虚构测试数据，禁止生产交易写入。

**阶段 D：GitHub 自动触发**。在目前手动读取 PR 的基础上，加入获批 webhook/PR 事件、服务身份、审计日志和人工确认后的评论发布。GitHub 流水线采用最小权限并隔离不可信代码执行。

## 7. 风险与决策

| 风险 | 处理方式 |
|---|---|
| 静态规则误报或漏报 | 每条意见有具体证据；人工复核；收集评估集 |
| 模型猜测 IBM i 行为 | 规则提示要求标明未验证；编译与测试独立呈现 |
| 源码发送到未批准模型 | 默认不调用模型；先完成数据分类与模型审批 |
| 将 demo 当作生产就绪 | 报告和材料明确验证边界与待补门槛 |
| 内部标准缺失 | 获取团队 SDLC、AI 使用、信息安全与变更清单后逐项映射 |
