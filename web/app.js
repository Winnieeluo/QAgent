const state = { demoPath: "", repository: null, result: null, filter: "all", selectedRule: null, busy: false, mode: "local", pulls: [], loadedUrl: "" };
const $ = (id) => document.getElementById(id);

async function request(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { throw new Error("服务返回了无法读取的结果。"); }
  if (!response.ok) throw new Error(payload.error || `请求失败 (${response.status})`);
  return payload;
}

function post(url, body) {
  return request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function notice(message) {
  const box = $("notice");
  box.textContent = message || "";
  box.classList.toggle("hidden", !message);
}

function busy(value) {
  state.busy = value;
  $("run-button").disabled = value;
  $("run-button-text").textContent = value ? "正在分析变更…" : "运行变更审查";
  if (value) $("run-status").className = "status-pill running";
  if (value) $("run-status").innerHTML = "<span></span> 分析中";
}

function setMode(mode) {
  state.mode = mode;
  const local = mode === "local";
  $("local-fields").hidden = !local;
  $("online-fields").hidden = local;
  for (const [id, selected] of [["mode-local", local], ["mode-github", !local]]) {
    const button = $(id);
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  }
  $("run-button-text").textContent = local ? "运行本地审查" : "审查所选 PR";
  notice("");
}

function localOptions(repositories, selectedPath) {
  const select = $("repo-select");
  select.replaceChildren();
  if (!repositories.length) {
    const option = document.createElement("option");
    option.value = ""; option.textContent = "未发现仓库，请浏览文件夹";
    select.appendChild(option);
    return;
  }
  repositories.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.path;
    option.textContent = `${item.name}  ·  ${item.path}`;
    select.appendChild(option);
  });
  select.value = selectedPath && repositories.some((item) => item.path === selectedPath) ? selectedPath : repositories[0].path;
}

function setRepository(info) {
  state.repository = info;
  $("commit-label").textContent = "当前提交";
  const select = $("base-branch");
  const previous = select.value;
  select.replaceChildren();
  info.branches.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });
  select.value = info.branches.includes(previous) ? previous : (info.branches.includes("main") ? "main" : info.branches[0] || "");
  $("current-branch").textContent = info.currentBranch || "detached HEAD";
  $("commit-message").textContent = info.lastCommit || "—";
  $("commit-sha").textContent = info.headSha ? info.headSha.slice(0, 12) : "—";
  if (info.dirty) notice("工作区存在未提交变更；本次审查仅比较已提交的 HEAD。");
  else notice("");
}

async function loadRepository() {
  const repoPath = $("repo-select").value;
  if (!repoPath) throw new Error("请选择本地 Git 仓库。");
  const payload = await post("/api/repository", { repoPath });
  setRepository(payload.repository);
  return payload.repository;
}

async function scanRepositories() {
  const selected = $("repo-select").value;
  const payload = await request("/api/local/repositories");
  localOptions(payload.repositories, selected || state.demoPath);
  await loadRepository();
}

async function loadPulls() {
  const url = $("github-url").value.trim();
  if (!url) throw new Error("请粘贴 GitHub 仓库或 PR 链接。");
  $("load-pulls").disabled = true;
  $("load-pulls").textContent = "读取中…";
  try {
    const response = await post("/api/github/pulls", { url, token: $("github-token").value.trim() });
    state.pulls = response.pulls;
    state.loadedUrl = url;
    const select = $("pr-select"); select.replaceChildren();
    if (!state.pulls.length) throw new Error("这个仓库目前没有开放的 PR。可直接粘贴指定 PR 链接。");
    state.pulls.forEach((pr) => {
      const option = document.createElement("option");
      option.value = String(pr.number);
      option.textContent = `#${pr.number}  ${pr.title}  ·  ${pr.author}`;
      select.appendChild(option);
    });
    select.disabled = false;
    notice("");
    return state.pulls;
  } finally {
    $("load-pulls").disabled = false;
    $("load-pulls").textContent = "读取 PR";
  }
}

function count(number) { return String(number).padStart(2, "0"); }

function renderChecks(checks) {
  const container = $("checks");
  container.replaceChildren();
  checks.forEach((check) => {
    const card = document.createElement("div");
    card.className = `check-card ${check.status}`;
    const icon = document.createElement("span");
    icon.className = "check-icon";
    icon.textContent = check.status === "passed" ? "✓" : check.status === "failed" ? "!" : "–";
    const text = document.createElement("div");
    const strong = document.createElement("strong"); strong.textContent = check.name;
    const small = document.createElement("small"); small.textContent = check.detail;
    text.append(strong, small); card.append(icon, text); container.appendChild(card);
  });
}

function renderExtensions(result) {
  const section = $("extensions-output");
  section.replaceChildren();
  section.hidden = !result.aiReview && !result.ibmiEvidence;
  if (result.aiReview) {
    const panel = document.createElement("div"); panel.className = "panel extension-panel";
    const title = document.createElement("h3"); title.textContent = "大模型辅助建议 · 待人工复核";
    const summary = document.createElement("p"); summary.textContent = result.aiReview.summary;
    panel.append(title, summary);
    if (result.aiReview.findings.length) {
      const list = document.createElement("ul");
      result.aiReview.findings.forEach((finding) => {
        const item = document.createElement("li");
        item.textContent = `${finding.title} · ${finding.file}:${finding.line} · ${finding.evidence} · 建议：${finding.action}`;
        list.appendChild(item);
      });
      panel.appendChild(list);
    }
    section.appendChild(panel);
  }
  if (result.ibmiEvidence) {
    const panel = document.createElement("div"); panel.className = "panel extension-panel";
    const title = document.createElement("h3"); title.textContent = "IBM i 数据校验证据";
    const detail = document.createElement("p"); detail.textContent = result.ibmiEvidence.detail;
    panel.append(title, detail);
    if (result.ibmiEvidence.evidence.length) {
      const list = document.createElement("ul");
      result.ibmiEvidence.evidence.forEach((evidence) => {
        const item = document.createElement("li"); item.textContent = `${evidence.name}：${evidence.value}`;
        list.appendChild(item);
      });
      panel.appendChild(list);
    }
    section.appendChild(panel);
  }
}

function filteredFindings() {
  const findings = state.result?.findings || [];
  return state.filter === "all" ? findings : findings.filter((finding) => finding.severity === state.filter);
}

function renderFindings() {
  const container = $("finding-list");
  container.replaceChildren();
  const findings = filteredFindings();
  if (!findings.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = state.result?.findings.length
      ? '<div class="empty-symbol">◎</div><strong>当前筛选没有发现</strong><p>可切换到其他风险级别，查看完整审查结果。</p>'
      : '<div class="empty-symbol">◎</div><strong>未触发 IBM i 规则</strong><p>仍需人工复核变更并执行适用测试。</p>';
    container.appendChild(empty);
    $("detail-panel").innerHTML = '<div class="empty-state detail-empty"><div class="empty-symbol">◫</div><strong>没有可显示的发现</strong></div>';
    return;
  }
  if (!findings.some((finding) => finding.rule === state.selectedRule)) state.selectedRule = findings[0].rule;
  findings.forEach((finding) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `finding-card ${finding.rule === state.selectedRule ? "selected" : ""}`;
    button.setAttribute("aria-pressed", String(finding.rule === state.selectedRule));
    const top = document.createElement("div"); top.className = "finding-top";
    const rule = document.createElement("span"); rule.className = "rule-code"; rule.textContent = finding.rule;
    const severity = document.createElement("span"); severity.className = `severity ${finding.severity}`; severity.textContent = finding.severity === "high" ? "高风险" : "中风险";
    top.append(rule, severity);
    const title = document.createElement("strong"); title.textContent = finding.title;
    const location = document.createElement("small"); location.textContent = `${finding.file}:${finding.line}`;
    button.append(top, title, location);
    button.addEventListener("click", () => { state.selectedRule = finding.rule; renderFindings(); });
    container.appendChild(button);
  });
  renderDetail(findings.find((finding) => finding.rule === state.selectedRule));
}

function addBlock(parent, heading, body, code = false) {
  const section = document.createElement("div"); section.className = "detail-block";
  const title = document.createElement("h4"); title.textContent = heading;
  const content = document.createElement(code ? "div" : "p");
  if (code) content.className = "evidence-line";
  content.textContent = body;
  section.append(title, content); parent.appendChild(section);
}

function renderDetail(finding) {
  if (!finding) return;
  const panel = $("detail-panel"); panel.replaceChildren();
  const head = document.createElement("div"); head.className = "detail-head";
  const left = document.createElement("div");
  const overline = document.createElement("div"); overline.className = "detail-overline"; overline.textContent = `${finding.rule} / REVIEW FINDING`;
  const title = document.createElement("h3"); title.className = "detail-title"; title.textContent = finding.title;
  const location = document.createElement("div"); location.className = "detail-location"; location.textContent = `${finding.file}:${finding.line}`;
  left.append(overline, title, location);
  const severity = document.createElement("span"); severity.className = `severity ${finding.severity}`; severity.textContent = finding.severity === "high" ? "高风险" : "中风险";
  head.append(left, severity); panel.appendChild(head);
  addBlock(panel, "变更证据", finding.evidence, true);
  addBlock(panel, "潜在影响", finding.impact);
  addBlock(panel, "建议验证与处理", finding.action);

  const file = state.result.files.find((item) => item.path === finding.file);
  if (file) {
    const header = document.createElement("div"); header.className = "diff-header";
    const label = document.createElement("h4"); label.textContent = "关联差异";
    const tally = document.createElement("span"); tally.className = "diff-count"; tally.textContent = `+${file.additions} / -${file.deletions}${file.diffTruncated ? " · 差异过长，展示已截断" : ""}`;
    header.append(label, tally); panel.appendChild(header);
    const diff = document.createElement("div"); diff.className = "diff-view"; diff.setAttribute("aria-label", `${file.path} 的 Git diff`);
    file.diff.split("\n").forEach((line) => {
      if (!line) return;
      const row = document.createElement("span");
      row.className = "diff-line" + (line.startsWith("@@") ? " hunk" : line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") ? " file" : line.startsWith("+") ? " add" : line.startsWith("-") ? " del" : "");
      row.textContent = line;
      diff.appendChild(row);
    });
    panel.appendChild(diff);
  }
}

function renderResult(result) {
  state.result = result; state.filter = "all"; state.selectedRule = result.findings[0]?.rule || null;
  if (result.sourceMode === "local") setRepository(result.repository);
  else {
    notice("");
    $("commit-label").textContent = `GitHub PR #${result.pullRequest.number}`;
    $("commit-message").textContent = result.pullRequest.title;
    $("commit-sha").textContent = result.repository.headSha.slice(0, 12);
  }
  $("count-total").textContent = count(result.findings.length);
  $("count-high").textContent = count(result.findings.filter((item) => item.severity === "high").length);
  $("count-medium").textContent = count(result.findings.filter((item) => item.severity === "medium").length);
  $("count-files").textContent = count(result.files.length);
  $("run-status").className = "status-pill done"; $("run-status").innerHTML = "<span></span> 审查完成";
  $("filter-all-count").textContent = result.findings.length;
  document.querySelectorAll(".filter").forEach((button) => { button.classList.toggle("active", button.dataset.filter === "all"); button.setAttribute("aria-pressed", String(button.dataset.filter === "all")); });
  renderChecks(result.checks); renderExtensions(result); renderFindings();
  const markdown = $("export-md"), json = $("export-json");
  markdown.href = `/api/report?run=${result.runId}&format=md`;
  json.href = `/api/report?run=${result.runId}&format=json`;
  [markdown, json].forEach((link) => { link.classList.remove("disabled"); link.removeAttribute("aria-disabled"); });
  const date = new Date(result.createdAt).toLocaleString("zh-CN", { hour12: false });
  $("run-meta").textContent = result.sourceMode === "github"
    ? `GitHub PR #${result.pullRequest.number} · 运行 ${result.runId} · ${date} · HEAD ${result.repository.headSha.slice(0, 12)} · 报告仅保留在当前服务内存中`
    : `本地仓库 · 运行 ${result.runId} · ${date} · HEAD ${result.repository.headSha.slice(0, 12)} · 对比 ${result.baseBranch} · ${result.repository.dirty ? "存在未提交变更" : "工作区干净"}`;
}

async function runReview() {
  if (state.busy) return;
  busy(true);
  try {
    let result;
    const extensions = { runAi: $("run-ai").checked, runIbmi: $("run-ibmi").checked };
    if (state.mode === "local") {
      const repo = await loadRepository();
      result = await post("/api/review", { repoPath: repo.path, baseBranch: $("base-branch").value, ...extensions });
    } else {
      if (state.loadedUrl !== $("github-url").value.trim() || !state.pulls.length) await loadPulls();
      const number = Number($("pr-select").value);
      if (!number) throw new Error("请选择一个 PR。");
      result = await post("/api/github/review", { url: $("github-url").value.trim(),
        number, token: $("github-token").value.trim(), ...extensions });
      $("github-token").value = "";
    }
    renderResult(result);
  } catch (error) {
    notice(error.message || "审查失败，请检查仓库路径和分支。");
    $("run-status").className = "status-pill waiting";
    $("run-status").innerHTML = "<span></span> 审查失败";
  } finally { busy(false); if (!state.busy) $("run-button-text").textContent = state.mode === "local" ? "运行本地审查" : "审查所选 PR"; }
}

document.addEventListener("DOMContentLoaded", async () => {
  $("review-form").addEventListener("submit", (event) => { event.preventDefault(); runReview(); });
  $("mode-local").addEventListener("click", () => setMode("local"));
  $("mode-github").addEventListener("click", () => setMode("github"));
  $("repo-select").addEventListener("change", async () => { try { await loadRepository(); } catch (error) { notice(error.message); } });
  $("scan-button").addEventListener("click", async () => { try { await scanRepositories(); } catch (error) { notice(error.message); } });
  $("browse-button").addEventListener("click", async () => {
    try {
      const response = await post("/api/local/pick", {});
      if (!response.repository) return;
      const select = $("repo-select");
      if (![...select.options].some((option) => option.value === response.repository.path)) {
        const option = document.createElement("option"); option.value = response.repository.path;
        option.textContent = `${response.repository.name}  ·  ${response.repository.path}`;
        select.appendChild(option);
      }
      select.value = response.repository.path;
      setRepository(response.repository);
    } catch (error) { notice(error.message); }
  });
  $("load-pulls").addEventListener("click", async () => { try { await loadPulls(); } catch (error) { notice(error.message); } });
  $("github-url").addEventListener("input", () => { state.pulls = []; state.loadedUrl = ""; $("pr-select").disabled = true; });
  document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach((item) => { const active = item === button; item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active)); });
    renderFindings();
  }));
  try {
    const bootstrap = await request("/api/bootstrap");
    state.demoPath = bootstrap.demoPath;
    $("run-ai").disabled = !bootstrap.integrations.llmAvailable;
    $("run-ibmi").disabled = !bootstrap.integrations.ibmiAvailable;
    $("integration-hint").textContent = bootstrap.integrations.llmAvailable || bootstrap.integrations.ibmiAvailable
      ? "扩展步骤只会在主动勾选后执行；结果与规则发现分别展示。"
      : "可选步骤尚未配置；规则审查可直接运行。";
    localOptions(bootstrap.localRepositories, bootstrap.demoPath);
    setRepository(bootstrap.repository);
    await runReview();
  } catch (error) { notice(error.message || "无法连接本地 QA 服务。"); }
});
