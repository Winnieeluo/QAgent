# 可选集成：IBM i skill 与大模型

默认审查只运行本地确定性规则。网页的两个扩展勾选项默认关闭；未配置时不可勾选。系统不会因为打开页面、扫描仓库或读取 PR 自动连接 IBM i 或发送代码到模型。

## 1. IBM i skill 接口

现有 skill 的内容和连接方式不需要放入本仓库。独立网页无法直接“调用一个 Codex skill”；需要在获批运行环境中提供一个可导入的 Python 适配器，把现有 skill/MCP/CLI 工具包装为：

```python
def run_checks(context: dict) -> dict:
    ...
```

`context` 示例（字段见 `web/app.py`）：

```json
{
  "sourceMode": "local",
  "repository": "demo-repo",
  "baseSha": "...",
  "headSha": "...",
  "files": [{"path": "src/ACCTBAL.PF", "diff": "...", "diffTruncated": false}],
  "ruleFindings": []
}
```

适配器返回：

```python
return {
    "status": "passed",  # passed / failed / not_run
    "detail": "只读检查完成；共核对 2 个对象",
    "evidence": [
        {"name": "对象 ACCTBAL 当前字段精度", "value": "15P 2"}
    ],
}
```

在适配器中调用你已有的 skill 工具；不要把数据库用户名、密码、连接串或客户数据加入 `context`、`detail`、`evidence` 或日志。建议只开放经过批准的只读查询与对象元数据检查，并由适配器限制库、表、超时和返回行数。网页只负责显式触发和展示状态，不会替 skill 决定 SQL。配置环境变量 `QAAGENT_IBMI_ADAPTER=your_package.ibmi_bridge` 后重启服务，页面才允许勾选“IBM i 数据校验”。对应调用与输出校验在 `web/extensions.py` 的 `run_ibmi_adapter()`。

这个接口目前已用测试适配器验证契约，**没有连接真实 IBM i**。IBM i 数据校验不等于编译或 RPGUnit 测试。

## 2. 大模型调用

代码在 `web/extensions.py` 的 `run_llm_review()`：使用 OpenAI 官方 Python SDK 的 Responses API，发送本次 Git diff、固定的 base/head SHA 和规则发现，要求 JSON Schema 输出。模型建议保存在单独的 `aiReview` 字段，不混入确定性规则结果；返回的文件和行号必须能在 diff 新版本侧找到。请求设置 `store=False`，并限制输入为 100 KB。输出仍需人工复核。

先在获批环境安装可选依赖：

```powershell
python -m pip install openai
```

由服务端部署配置提供以下变量，不要把真实密钥写进脚本、`.env`、Git 仓库或网页表单：

| 变量 | 用途 |
|---|---|
| `QAAGENT_LLM_ENABLED=1` | 明确允许调用模型；默认关闭 |
| `QAAGENT_LLM_MODEL` | 团队批准的模型 ID |
| `QAAGENT_LLM_API_KEY` 或 `OPENAI_API_KEY` | 从获批密钥管理器注入到服务端进程 |
| `QAAGENT_LLM_BASE_URL` | 可选；获批的 HTTPS Responses 兼容网关地址。留空时 SDK 使用 OpenAI 默认服务 |

重启 `start_web.ps1` 后，页面的“大模型辅助审查”才能勾选。点击审查按钮时才会调用模型。服务器不会把 GitHub PR 令牌或 IBM i 数据库凭据放入模型请求。若配置内部网关，它需要兼容 Responses API、JSON Schema 输出与 `store=False` 参数。

`store=False` 关闭通过 Responses API 检索该响应的应用状态存储，**不代表零数据保留或替代数据分类审批**。任何真实银行源码发送至模型服务前，仍需按团队的数据处理、模型使用和网络出站流程批准。参考 [OpenAI Responses 文档](https://developers.openai.com/api/docs/guides/text)、[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs)与[数据控制](https://developers.openai.com/api/docs/guides/your-data)。

## 3. 状态与责任边界

| 步骤 | 当前默认状态 | 接入后证据 |
|---|---|---|
| IBM i 差异规则 | 已运行 | 文件、行号、规则证据 |
| 大模型辅助审查 | 未运行 | 模型 ID、摘要、待人工复核建议 |
| IBM i 数据校验 | 未运行 | 适配器状态与有限的只读证据 |
| IBM i 编译 | 未运行 | 需另接构建工具与测试机 |
| RPGUnit 测试 | 未运行 | 需另接测试机与测试套件 |

扩展失败时，原本的规则结果仍会保留，验证卡显示 `failed`；不能把“未运行”或模型建议解释成测试通过。
