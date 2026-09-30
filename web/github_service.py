"""Read-only GitHub PR access for QAAgent.

Hosts are allowlisted, requests never follow redirects, and credentials are
passed only through request headers or a child process environment.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_API_BYTES = 2_000_000
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


@dataclass(frozen=True)
class GithubTarget:
    host: str
    owner: str
    repo: str
    number: int | None = None

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.owner}/{self.repo}"

    @property
    def api_root(self) -> str:
        return "https://api.github.com" if self.host == "github.com" else f"https://{self.host}/api/v3"


def allowed_hosts() -> set[str]:
    extra = os.environ.get("QAAGENT_GITHUB_HOSTS", "")
    hosts = {"github.com"}
    for entry in extra.split(","):
        host = entry.strip().lower()
        if host and re.fullmatch(r"[a-z0-9.-]+", host) and "." in host and host != "localhost":
            hosts.add(host)
    return hosts


def parse_github_target(raw: str) -> GithubTarget:
    raw = raw.strip()
    if not raw:
        raise ValueError("请输入 GitHub 仓库或 PR 链接。")
    if "://" not in raw:
        raw = "https://github.com/" + raw.lstrip("/")
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in allowed_hosts() or parsed.port is not None or parsed.username or parsed.password:
        raise ValueError("仅允许已批准的 HTTPS GitHub 主机。")
    if parsed.query or parsed.fragment:
        raise ValueError("请使用不含查询参数的仓库或 PR 链接。")
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) == 2:
        owner, repo = parts
        number = None
    elif len(parts) == 4 and parts[2] == "pull" and parts[3].isdigit():
        owner, repo = parts[:2]
        number = int(parts[3])
    else:
        raise ValueError("链接格式应为 owner/repo 或 https://github.com/owner/repo/pull/123。")
    repo = repo.removesuffix(".git")
    if not NAME.fullmatch(owner) or not NAME.fullmatch(repo) or (number is not None and number <= 0):
        raise ValueError("仓库或 PR 编号格式无效。")
    return GithubTarget(host, owner, repo, number)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("GitHub API 返回了重定向，已停止请求。")


def github_json(target: GithubTarget, endpoint: str, token: str = "") -> dict | list:
    url = target.api_root + endpoint
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "QAAgent-Local/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(url, headers=headers), timeout=20) as response:
            body = response.read(MAX_API_BYTES + 1)
            if len(body) > MAX_API_BYTES:
                raise ValueError("GitHub API 响应过大，请缩小审查范围。")
            return json.loads(body)
    except HTTPError as error:
        if error.code == 401:
            raise ValueError("GitHub 认证失败，请检查访问令牌。") from None
        if error.code == 403:
            raise ValueError("访问被拒绝。请检查仓库权限、令牌范围或 API 速率限制。") from None
        if error.code == 404:
            raise ValueError("找不到仓库或 PR；私有仓库也可能缺少读取权限。") from None
        raise ValueError(f"GitHub API 返回 HTTP {error.code}。") from None
    except URLError:
        raise ValueError("无法连接 GitHub，请检查网络或企业代理。") from None


def pull_summary(pr: dict) -> dict:
    return {"number": pr["number"], "title": pr["title"], "url": pr["html_url"],
            "state": pr["state"], "updatedAt": pr["updated_at"],
            "baseBranch": pr["base"]["ref"], "baseSha": pr["base"]["sha"],
            "headSha": pr["head"]["sha"], "author": pr["user"]["login"]}


def list_pulls(target: GithubTarget, token: str = "") -> list[dict]:
    prefix = f"/repos/{quote(target.owner)}/{quote(target.repo)}/pulls"
    if target.number:
        return [pull_summary(github_json(target, f"{prefix}/{target.number}", token))]
    data = github_json(target, prefix + "?state=open&sort=updated&direction=desc&per_page=10", token)
    return [pull_summary(pr) for pr in data]


def get_pull(target: GithubTarget, number: int, token: str = "") -> dict:
    pr = github_json(target, f"/repos/{quote(target.owner)}/{quote(target.repo)}/pulls/{number}", token)
    if pr["base"]["repo"]["full_name"].lower() != f"{target.owner}/{target.repo}".lower():
        raise ValueError("PR 的目标仓库与输入不一致。")
    return pull_summary(pr)


def git_remote(repo: Path, args: list[str], host: str, token: str = "", timeout: int = 120) -> str:
    env = os.environ.copy()
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "NUL" if os.name == "nt" else "/dev/null",
                "GIT_TRACE": "0", "GIT_CURL_VERBOSE": "0", "GIT_TRACE_PACKET": "0",
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": ""})
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_1": f"http.https://{host}/.extraheader",
                    "GIT_CONFIG_VALUE_1": f"Authorization: Basic {basic}"})
    command = ["git", "-c", "http.followRedirects=false",
               "-c", "core.hooksPath=NUL" if os.name == "nt" else "core.hooksPath=/dev/null",
               "-c", "filter.lfs.smudge=", "-c", "filter.lfs.required=false", "-C", str(repo), *args]
    process = subprocess.run(command, env=env, text=True, capture_output=True, timeout=timeout)
    if process.returncode:
        # Git stderr is deliberately omitted: it may contain authentication details.
        raise ValueError("GitHub 仓库读取失败。请检查仓库权限、网络和 PR 状态。")
    return process.stdout


@contextmanager
def checked_out_pull(target: GithubTarget, pr: dict, token: str, work_root: Path):
    work_root.mkdir(parents=True, exist_ok=True)
    checkout = Path(tempfile.mkdtemp(prefix="github-pr-", dir=work_root)).resolve()
    if not checkout.is_relative_to(work_root.resolve()):
        raise ValueError("临时仓库路径无效。")
    try:
        git_remote(checkout, ["init", "-q"], target.host)
        git_remote(checkout, ["remote", "add", "origin", target.url + ".git"], target.host)
        branch = pr["baseBranch"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", branch):
            raise ValueError("PR 目标分支名称无效。")
        git_remote(checkout, ["fetch", "-q", "--depth=100", "origin",
                              f"refs/heads/{branch}", f"refs/pull/{pr['number']}/head"], target.host, token)
        for sha in (pr["baseSha"], pr["headSha"]):
            exists = subprocess.run(["git", "-C", str(checkout), "cat-file", "-e", sha + "^{commit}"],
                                    capture_output=True, timeout=10).returncode == 0
            if not exists:
                git_remote(checkout, ["fetch", "-q", "--depth=100", "origin", sha], target.host, token)
        git_remote(checkout, ["update-ref", "refs/heads/qa-base", pr["baseSha"]], target.host)
        git_remote(checkout, ["update-ref", "refs/heads/qa-head", pr["headSha"]], target.host)
        git_remote(checkout, ["checkout", "-q", "qa-head"], target.host, token)
        merge_base = subprocess.run(["git", "-C", str(checkout), "merge-base", "qa-base", "qa-head"],
                                    capture_output=True, text=True, timeout=10)
        if merge_base.returncode:
            raise ValueError("PR 历史超过当前抓取深度，无法可靠计算差异。")
        yield checkout
    finally:
        if checkout.is_relative_to(work_root.resolve()):
            def clear_readonly(function, path, _error):
                os.chmod(path, stat.S_IWRITE)
                function(path)
            shutil.rmtree(checkout, onexc=clear_readonly)
