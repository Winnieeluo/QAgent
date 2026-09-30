"""Loopback-only web UI for local Git and read-only GitHub PR review."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .github_service import checked_out_pull, get_pull, list_pulls, parse_github_target
from .extensions import ibmi_available, llm_available, run_ibmi_adapter, run_llm_review

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent
DOCUMENTS = (Path.home() / "Documents").resolve()
RUNS = ROOT / "runs"
DEMO = ROOT / "demo-repo"
WORK = ROOT / "work"
MEMORY_REPORTS: dict[str, tuple[bytes, bytes]] = {}
sys.path.insert(0, str(ROOT))
from qa_agent import git, render_markdown, review  # noqa: E402


def check_repo(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_relative_to(DOCUMENTS):
        raise ValueError("仓库必须位于当前用户的 Documents 目录内。")
    if not path.is_dir() or not (path / ".git").exists():
        raise ValueError("请选择一个包含 .git 的本地仓库目录。")
    return path


def discover_repositories() -> list[dict]:
    """Find nearby Git repos without asking users to type Windows paths."""
    found: list[Path] = [DEMO] if (DEMO / ".git").exists() else []
    visited = 0
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", "runs", "work", "AppData"}
    for current, dirs, _ in os.walk(DOCUMENTS, followlinks=False):
        visited += 1
        folder = Path(current)
        depth = len(folder.relative_to(DOCUMENTS).parts)
        if (folder / ".git").exists():
            if folder != DEMO:
                found.append(folder)
            if folder != DOCUMENTS:
                dirs.clear()
        elif depth >= 5:
            dirs.clear()
        else:
            dirs[:] = [name for name in dirs if name not in skip and not (folder / name).is_symlink()]
        if visited >= 1500 or len(found) >= 30:
            break
    found.sort(key=lambda item: (item.resolve() != DEMO.resolve(), -item.stat().st_mtime))
    return [{"path": str(path), "name": path.name} for path in found]


def pick_repository() -> dict | None:
    """Use the OS folder dialog; no browser filesystem permission is required."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(parent=root, initialdir=str(DOCUMENTS),
                                           title="选择本地 Git 仓库")
        root.destroy()
    except Exception:
        raise ValueError("无法打开系统文件夹选择器；请使用页面上的仓库列表。") from None
    if not selected:
        return None
    repo = check_repo(selected)
    return repository_info(repo)


def git_text(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=20,
    )
    if process.returncode:
        raise ValueError(process.stderr.strip() or "Git 命令失败。")
    return process.stdout


def repository_info(repo: Path) -> dict:
    branches = [b.strip() for b in git_text(repo, "branch", "--format=%(refname:short)").splitlines() if b.strip()]
    current = git_text(repo, "branch", "--show-current").strip()
    head = git_text(repo, "rev-parse", "HEAD").strip()
    last_commit = git_text(repo, "log", "-1", "--format=%s").strip()
    dirty = bool(git_text(repo, "status", "--porcelain").strip())
    return {"path": str(repo), "name": repo.name, "branches": branches,
            "currentBranch": current, "headSha": head,
            "lastCommit": last_commit, "dirty": dirty}


def check_base(repo: Path, base: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", base) or base.startswith("-"):
        raise ValueError("目标分支名称无效。")
    branches = repository_info(repo)["branches"]
    if base not in branches:
        raise ValueError("目标分支不存在于该本地仓库。")


def changed_files(repo: Path, base: str) -> list[dict]:
    paths = git_text(repo, "diff", "--name-only", f"{base}...HEAD", "--").splitlines()
    if len(paths) > 100:
        raise ValueError("变更文件超过 100 个，请拆分 PR 后审查，避免遗漏证据。")
    files = []
    for path in paths:
        patch = git_text(repo, "diff", "--no-ext-diff", "--no-textconv", "--unified=4", f"{base}...HEAD", "--", path)
        files.append({"path": path, "diff": patch[:50000], "diffTruncated": len(patch) > 50000,
                      "additions": sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")),
                      "deletions": sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))})
    return files


def build_review(repo: Path, base: str, *, persist: bool = True,
                 online: dict | None = None, run_ai: bool = False,
                 run_ibmi: bool = False) -> dict:
    if run_ai and not llm_available():
        raise ValueError("未配置获批模型；请先完成服务端配置。")
    if run_ibmi and not ibmi_available():
        raise ValueError("IBM i 适配器尚未接入。")
    check_base(repo, base)
    info = repository_info(repo)
    findings = review(repo, base)
    files = changed_files(repo, base)
    context = {"sourceMode": "github" if online else "local",
               "repository": online["repoName"] if online else repo.name,
               "baseSha": online["baseSha"] if online else git_text(repo, "merge-base", base, "HEAD").strip(),
               "headSha": info["headSha"], "files": files,
               "ruleFindings": [item.__dict__ for item in findings]}
    ai_review = None
    ai_check = {"name": "大模型辅助审查", "status": "not_run", "detail": "未选择或未配置获批模型"}
    if run_ai:
        try:
            ai_review = run_llm_review(context)
            ai_check = {"name": "大模型辅助审查", "status": "passed",
                        "detail": f"完成，提出 {len(ai_review['findings'])} 项待人工复核建议"}
        except ValueError as error:
            ai_check = {"name": "大模型辅助审查", "status": "failed", "detail": str(error)}
        except Exception:
            ai_check = {"name": "大模型辅助审查", "status": "failed", "detail": "模型调用失败，请检查服务端配置或网络。"}
    ibmi_evidence = None
    ibmi_check = {"name": "IBM i 数据校验", "status": "not_run", "detail": "未选择或未接入适配器"}
    if run_ibmi:
        try:
            ibmi_evidence = run_ibmi_adapter(context)
            ibmi_check = {"name": "IBM i 数据校验", "status": ibmi_evidence["status"],
                          "detail": ibmi_evidence["detail"]}
        except Exception:
            ibmi_check = {"name": "IBM i 数据校验", "status": "failed",
                          "detail": "适配器执行失败，请检查服务端配置。"}
    run_id = uuid.uuid4().hex[:12]
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    markdown = render_markdown(repo, base, findings)
    if ibmi_evidence:
        markdown = markdown.replace("未连接 IBM i，", "IBM i 数据校验结果见下方独立章节，")
    if online:
        info = {"path": "", "name": online["repoName"], "branches": [online["baseBranch"]],
                "currentBranch": f"PR #{online['number']}", "headSha": online["headSha"],
                "lastCommit": online["title"], "dirty": False}
        markdown = markdown.replace(f"- 仓库：`{repo.name}`", f"- 仓库：`{online['repoName']}`")
        markdown = markdown.replace(f"- 比较：`{base}...HEAD`", f"- 比较：`{online['baseBranch']}...HEAD`")
        markdown = (f"# GitHub PR #{online['number']} · {online['title']}\n\n"
                    f"- 来源：{online['url']}\n- 目标：{online['baseBranch']}\n"
                    f"- Base SHA：`{online['baseSha']}`\n- Head SHA：`{online['headSha']}`\n\n"
                    + markdown)
    if ai_review:
        markdown += (f"\n## 大模型辅助建议（待人工复核）\n\n模型：`{ai_review['model']}`\n\n"
                     f"{ai_review['summary']}\n\n")
        for item in ai_review["findings"]:
            markdown += (f"- **{item['title']}**（{item['severity']}，`{item['file']}:{item['line']}`）："
                         f"{item['evidence']}；影响：{item['impact']}；建议：{item['action']}\n")
    if ibmi_evidence:
        markdown += f"\n## IBM i 数据校验\n\n状态：`{ibmi_evidence['status']}`。{ibmi_evidence['detail']}\n\n"
        for item in ibmi_evidence["evidence"]:
            markdown += f"- {item['name']}：{item['value']}\n"
    output = {
        "runId": run_id, "createdAt": created, "repository": info,
        "sourceMode": "github" if online else "local",
        "pullRequest": online,
        "baseBranch": online["baseBranch"] if online else base,
        "findings": [item.__dict__ for item in findings],
        "files": files,
        "aiReview": ai_review,
        "ibmiEvidence": ibmi_evidence,
        "checks": [
            {"name": "IBM i 差异规则", "status": "passed", "detail": f"完成，发现 {len(findings)} 项待复核风险"},
            ai_check,
            ibmi_check,
            {"name": "IBM i 编译", "status": "not_run", "detail": "未连接测试机"},
            {"name": "RPGUnit 测试", "status": "not_run", "detail": "未连接测试机或测试套件"},
        ],
    }
    json_bytes = (json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if persist:
        report_dir = RUNS / run_id
        report_dir.mkdir(parents=True, exist_ok=False)
        (report_dir / "review.md").write_text(markdown, encoding="utf-8")
        (report_dir / "review.json").write_bytes(json_bytes)
    else:
        MEMORY_REPORTS[run_id] = (markdown.encode("utf-8"), json_bytes)
        while len(MEMORY_REPORTS) > 20:
            MEMORY_REPORTS.pop(next(iter(MEMORY_REPORTS)))
    return output


class Handler(BaseHTTPRequestHandler):
    server_version = "QAAgentLocal/1.0"

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def _trusted_host(self) -> bool:
        return self.headers.get("Host", "").lower() in ("127.0.0.1:8765", "localhost:8765")

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if not self._trusted_host():
            return self._json(403, {"error": "无效的本地主机名。"})
        url = urlsplit(self.path)
        if url.path in ("/", "/index.html"):
            return self._file(WEB / "index.html", "text/html; charset=utf-8")
        if url.path == "/app.js":
            return self._file(WEB / "app.js", "text/javascript; charset=utf-8")
        if url.path == "/styles.css":
            return self._file(WEB / "styles.css", "text/css; charset=utf-8")
        if url.path == "/favicon.svg":
            return self._file(WEB / "favicon.svg", "image/svg+xml")
        if url.path == "/api/bootstrap":
            try:
                return self._json(200, {"demoPath": str(DEMO), "allowedRoot": str(DOCUMENTS),
                                        "repository": repository_info(check_repo(str(DEMO))),
                                        "localRepositories": discover_repositories(),
                                        "integrations": {"llmAvailable": llm_available(),
                                                         "ibmiAvailable": ibmi_available()}})
            except (ValueError, subprocess.TimeoutExpired) as error:
                return self._json(500, {"error": str(error)})
        if url.path == "/api/local/repositories":
            return self._json(200, {"repositories": discover_repositories()})
        if url.path == "/api/report":
            query = parse_qs(url.query)
            run_id = query.get("run", [""])[0]
            output_format = query.get("format", ["md"])[0]
            if not re.fullmatch(r"[0-9a-f]{12}", run_id) or output_format not in ("md", "json"):
                return self._json(400, {"error": "报告参数无效。"})
            name = "review.md" if output_format == "md" else "review.json"
            path = RUNS / run_id / name
            memory = MEMORY_REPORTS.get(run_id)
            if not path.is_file() and not memory:
                return self._json(404, {"error": "报告不存在。"})
            content_type = "text/markdown; charset=utf-8" if output_format == "md" else "application/json; charset=utf-8"
            data = path.read_bytes() if path.is_file() else memory[0 if output_format == "md" else 1]
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="ibmi-qa-{run_id}.{output_format}"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            return self.wfile.write(data)
        return self._json(404, {"error": "页面不存在。"})

    def do_POST(self) -> None:
        if not self._trusted_host():
            return self._json(403, {"error": "无效的本地主机名。"})
        if self.path not in ("/api/repository", "/api/review", "/api/local/pick",
                             "/api/github/pulls", "/api/github/review"):
            return self._json(404, {"error": "接口不存在。"})
        origin = self.headers.get("Origin", "")
        if origin and origin not in ("http://127.0.0.1:8765", "http://localhost:8765"):
            return self._json(403, {"error": "只接受本机页面的请求。"})
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            return self._json(415, {"error": "请求必须使用 JSON。"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8192:
                raise ValueError("请求大小无效。")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("请求体必须是 JSON 对象。")
            run_ai = body.get("runAi", False)
            run_ibmi = body.get("runIbmi", False)
            if type(run_ai) is not bool or type(run_ibmi) is not bool:
                raise ValueError("扩展选项格式无效。")
            if self.path == "/api/local/pick":
                return self._json(200, {"repository": pick_repository()})
            if self.path in ("/api/github/pulls", "/api/github/review"):
                target = parse_github_target(str(body.get("url", "")))
                token = str(body.get("token", ""))
                if len(token) > 1024 or "\n" in token or "\r" in token:
                    raise ValueError("访问令牌格式无效。")
                if self.path == "/api/github/pulls":
                    return self._json(200, {"repository": target.url,
                                            "pulls": list_pulls(target, token)})
                number = int(body.get("number", target.number or 0))
                if number <= 0:
                    raise ValueError("请选择一个 PR。")
                pr = get_pull(target, number, token)
                online = {**pr, "repoName": f"{target.owner}/{target.repo}"}
                with checked_out_pull(target, pr, token, WORK) as checkout:
                    result = build_review(checkout, "qa-base", persist=False, online=online,
                                          run_ai=run_ai, run_ibmi=run_ibmi)
                return self._json(200, result)
            repo = check_repo(str(body.get("repoPath", "")))
            if self.path == "/api/repository":
                return self._json(200, {"repository": repository_info(repo)})
            base = str(body.get("baseBranch", "main"))
            return self._json(200, build_review(repo, base, run_ai=run_ai, run_ibmi=run_ibmi))
        except (ValueError, json.JSONDecodeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            return self._json(400, {"error": str(error)})


def main() -> None:
    if not (DEMO / ".git").exists():
        from create_demo_repo import create_repository
        create_repository(DEMO)
    host, port = "127.0.0.1", 8765
    print(f"QAAgent ready at http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
