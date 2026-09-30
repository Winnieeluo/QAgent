# 验证记录 · 2026-09-30

| 项目 | 结果 | 证据 |
|---|---|---|
| 本地 Git 样例 | 通过 | `main` 与 `feature/risky-transfer` 两分支；HEAD `ebb152dc345ed97b14eee9db92d47e561f56745d`；工作区干净 |
| 确定性审查 | 通过 | `artifacts/ibmi-review.md` 与 `.json`，发现 3 项（high 2、medium 1） |
| 规则与网页自动测试 | 通过 | 14 个 unittest，包括规则、路径限制、GitHub URL 白名单、扩展接口契约、模型请求参数、仓库元数据和报告生成 |
| 本地网页 | 通过 | `GET /`、`GET /api/bootstrap`、`POST /api/review` 返回成功；自动选择样例仓库，浏览器展示 3 项发现及 Git diff |
| 在线 GitHub PR | 通过（公开仓库） | 浏览器读取 `octocat/Hello-World` PR #11306 并完成审查；API 返回固定 PR 编号、SHA 和 1 个变更文件；在线 JSON 报告可导出；临时工作目录清空 |
| 安全拦截 | 通过 | 未授权 Host 和跨来源 POST 返回 403；非 HTTPS/未批准 URL 返回 400；错误体不回显测试令牌 |
| 网页筛选 | 通过 | 中风险筛选仅显示 `IBMI-003`，详情同步更新 |
| 报告下载 | 通过 | `GET /api/report` 的 Markdown 与 JSON 均返回 200 和附件文件名 |
| `.pr_agent.toml` 解析 | 通过 | Python `tomllib` 可解析 `config`、`local`、`pr_reviewer`；模型和 PR-Agent 未在本环境运行 |
| IBM i 编译与 RPGUnit | 未运行 | 无 IBM i 测试机或真实测试套件 |
| AgentHub 集成 | 未运行 | 工具契约已定义，平台接口待确认 |
| 大模型实际调用 | 未运行 | 已实现显式开关、服务端 Responses 调用和结构化结果验证；无获批模型密钥，测试使用模拟客户端 |
| IBM i skill 实际连接 | 未运行 | 已实现 `run_checks(context)` 适配器接口并以模拟模块验证；尚未提供现有 skill 的桥接实现 |
| 私有 PR 与 GitHub Enterprise | 未运行 | 无获批私有令牌与企业实例；需在目标环境做集成验证 |

**验证命令**：`.\start_web.ps1`；`.\run_demo.ps1`；`python -m unittest discover -s tests -v`；`git -C .\demo-repo status --short`。

此记录证明本地模拟仓库、公开 GitHub PR 读取以及确定性检查按预期运行。GitHub 网络曾短暂失败一次，页面提示后重试成功；正式试点应加入网络重试与代理配置。任何汇丰内部 SDLC、信息安全或变更审批结论均需团队确认。
