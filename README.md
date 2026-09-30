# QAAgent · IBM i 变更审查工作台

这是可交互的本机网页 Demo，支持本地 Git 仓库与在线 GitHub PR。网页服务仅监听 `127.0.0.1:8765`。打开 PowerShell，在本目录运行：

```powershell
.\start_web.ps1
```

然后在浏览器打开 <http://127.0.0.1:8765/>。首次启动会在本机生成虚构的双分支 Git 仓库，页面随后自动审查它。

- **本地仓库**：从自动发现列表选择，或点“浏览文件夹”调用系统选择器；无需输入 Windows 路径。只允许当前用户 `Documents` 下的 Git 仓库，选择目标分支后运行审查。
- **在线仓库**：粘贴 GitHub 仓库或 PR 链接。公开仓库直接读取；私有仓库可临时输入仅授予目标仓库 `Contents: read` 和 `Pull requests: read` 的 fine-grained personal access token。页面列出最近更新的开放 PR，也支持直接粘贴指定 PR 链接。

GitHub 已停止使用账户密码进行 Git 认证，因此页面不收集用户名与密码。访问令牌仅在本次请求的内存及 Git 子进程环境中使用，不写入 Git URL、命令行、报告或磁盘；成功审查后输入框清空。在线源码临时检出供规则读取，审查结束即删除；在线报告只留在服务内存中，重启服务后消失。不要将未经批准的银行源码交给本 Demo；正式试点仍需团队的身份、数据分类及审计方案。

**页面交互**：查看审查摘要和验证状态；按风险级别筛选；选择发现查看证据、影响、建议和 Git diff；导出 Markdown 或 JSON。本地运行保存到 `runs/<运行编号>/`；在线运行仅在内存中提供导出。未提交的本地工作区变更不会纳入比较。

网页后端默认只需 Python 标准库，无需安装网页依赖。它不会执行仓库中的程序。模型辅助审查与 IBM i 数据校验设为可选扩展，默认关闭；RPGUnit 未接入时页面明确显示未运行。接入接口与模型调用代码见 [集成文档](INTEGRATIONS.md)，正式落地方案见 [交付方案](DELIVERY_PLAN.md)。

企业 GitHub Enterprise Server 需由管理员显式设置允许主机，例如 `$env:QAAGENT_GITHUB_HOSTS="github.company.example"` 后启动服务。默认只接受 `github.com` 的 HTTPS 链接；企业主机路径、API 兼容性与令牌流程需在实际环境验证。服务拒绝未知 Host、跨来源写请求、重定向到其他 GitHub API 主机，且限制请求与 API 响应大小。

---

这个包会生成一个**完全虚构**的 IBM i Git 仓库，并提供可重复运行的本地 QA 流程。它模拟“当前分支相对 `main` 的 PR”，先运行透明的 IBM i 差异规则；配置获批模型后可手动触发网页中的大模型辅助审查。另保留 [PR-Agent Local Git Provider](https://docs.pr-agent.ai/usage-guide/local_git_provider/) 的命令行演示配置。无需 GitHub 账号或 IBM i 连接即可演示第一层。

## 目录

| 路径 | 用途 |
|---|---|
| `create_demo_repo.py` → `demo-repo/` | 首次运行时生成两次提交、`main` 与 `feature/risky-transfer` 两个本地分支；RPGLE、DDS、CLLE 均为虚构样例 |
| `qa_agent.py` | IBM i 差异规则与 Markdown/JSON 证据输出；只读取仓库 |
| `run_demo.ps1` | 一键运行规则；加 `-WithPrAgent` 可调用 PR-Agent |
| `artifacts/` | 已跑出的样例报告和测试证据 |
| `DELIVERY_PLAN.md` | 演示脚本、架构、验收门槛与上线前缺口 |
| `INTEGRATIONS.md` | IBM i skill 适配器契约与获批模型配置 |

## Windows 快速运行

在本目录打开 PowerShell：

```powershell
.\run_demo.ps1
python -m unittest discover -s tests -v
git -C .\demo-repo status --short
```

预期：确定性检查报告 3 项（2 high、1 medium）；自动测试通过；生成的样例 Git 工作区干净。报告位于本机生成的 `artifacts/ibmi-review.md` 和 `artifacts/ibmi-review.json`；运行报告与临时仓库不提交到 GitHub。

## 调用现成的 PR-Agent

PR-Agent 是已有的开源 PR 审查器，支持本地 Git 分支比较；此包通过 `demo-repo/.pr_agent.toml` 增加 IBM i 审查指令。先按[官方安装文档](https://github.com/The-PR-Agent/pr-agent/blob/main/docs/docs/installation/locally.md)安装并配置已获批的模型，再运行：

```powershell
.\run_demo.ps1 -WithPrAgent
```

其报告写到 `artifacts/pr-agent-review.md`。本交付包**没有配置模型密钥，也没有实际运行 PR-Agent**，因此不能把 AI 审查当成已验证结果。仓库源码或差异是否允许发送至模型服务，应按贵司数据分类和模型使用流程批准；如需保持本地处理，可接获批的本地模型。

## 演示中的三个有意引入的问题

1. RPGLE：第二次余额 `UPDATE` 之后移除了 `SQLCODE` 失败检查，流程仍可执行 `COMMIT`。
2. DDS：`BALANCE` 从 `15P 2` 缩为 `9P 2`。
3. CLLE：把完整来源账户标识拼入程序消息。

这些源码用于展示审查流程，**未在 IBM i 上编译或运行**。确定性规则是审查提示，不是通用 RPG 语法检查器或正式安全扫描器。

## 复现 Git 历史

启动脚本会自动生成本地 Git 历史。需要另建样例时，在空目录运行：

```powershell
python .\create_demo_repo.py --out .\another-demo-repo
```

## 来源与许可证

PR-Agent：<https://github.com/The-PR-Agent/pr-agent>，MIT。此交付包未复制 PR-Agent 源码，只使用其公开的本地模式和配置接口。IBM i Testing CLI、TOBi、ibmi-ci 和 IBM i MCP Server 是后续集成候选；相关网址与边界见交付方案。本包的样例和脚本由本次 demo 新建，未使用真实银行代码或数据。
