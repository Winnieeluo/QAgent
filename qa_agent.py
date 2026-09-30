"""Deterministic IBM i change checks for the synthetic local Git demo.

This is intentionally a small companion to PR-Agent, not an RPG compiler.
Only committed additions in the branch diff are eligible for findings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    title: str
    evidence: str
    impact: str
    action: str


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return result.stdout


def changed_lines(repo: Path, base: str) -> dict[str, set[int]]:
    diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--unified=0", f"{base}...HEAD", "--")
    changed: dict[str, set[int]] = {}
    path: str | None = None
    line_no = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            changed.setdefault(path, set())
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                line_no = int(match.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            if path is not None:
                changed[path].add(line_no)
            line_no += 1
        elif line.startswith(" "):
            line_no += 1
    return changed


def source_at_base(repo: Path, base: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{base}:{path}"],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    return result.stdout if result.returncode == 0 else ""


def dds_fields(source: str) -> dict[str, tuple[int, int]]:
    fields: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^\s*A\s+(?!R\b|K\b)([A-Z][A-Z0-9_]*)\s+(\d+)P\s+(\d+)\b", re.I)
    for line in source.splitlines():
        match = pattern.search(line)
        if match:
            fields[match.group(1).upper()] = (int(match.group(2)), int(match.group(3)))
    return fields


def review(repo: Path, base: str) -> list[Finding]:
    repo = repo.resolve()
    git(repo, "rev-parse", "--verify", base)
    changed = changed_lines(repo, base)
    findings: list[Finding] = []

    for path, additions in sorted(changed.items()):
        file_path = repo / path
        if file_path.is_symlink() or not file_path.is_file():
            continue
        lines = file_path.read_text(encoding="utf-8").splitlines()
        lower = path.lower()

        if lower.endswith((".rpgle", ".sqlrpgle")):
            for index, line in enumerate(lines):
                if index + 1 not in additions or not re.search(r"\bupdate\b|\bset\s+BALANCE\b", line, re.I):
                    continue
                # A narrow, transparent rule: inspect the statements immediately
                # following a changed UPDATE. A compiler/runtime check is still needed.
                following = "\n".join(lines[index + 1 : index + 6])
                if not re.search(r"\bsqlcode\b|\bsqlstate\b", following, re.I):
                    findings.append(Finding(
                        "IBMI-001", "high", path, index + 1,
                        "UPDATE 后缺少立即的 SQL 结果检查",
                        line.strip(),
                        "更新失败后流程可能继续提交此前的余额变更。",
                        "在后续业务操作或 COMMIT 前检查 SQLCODE/SQLSTATE，失败时 ROLLBACK；在 IBM i 测试环境验证。",
                    ))

        if lower.endswith((".pf", ".lf")):
            before = dds_fields(source_at_base(repo, base, path))
            after = dds_fields("\n".join(lines))
            for field, (old_precision, old_scale) in before.items():
                if field not in after:
                    continue
                new_precision, new_scale = after[field]
                if new_precision >= old_precision and new_scale >= old_scale:
                    continue
                for index, line in enumerate(lines):
                    if index + 1 in additions and re.search(rf"\b{re.escape(field)}\b", line, re.I):
                        findings.append(Finding(
                            "IBMI-002", "high", path, index + 1,
                            f"字段 {field} 精度缩小",
                            f"{old_precision}P {old_scale} → {new_precision}P {new_scale}",
                            "现有金额可能无法表示；依赖该记录格式的程序需要重新评估与编译。",
                            "恢复原精度，或提供数据分布检查、迁移及依赖对象重编译证据。",
                        ))
                        break

        if lower.endswith((".cl", ".clle", ".clp", ".cll")):
            for index, line in enumerate(lines):
                if index + 1 in additions and re.search(r"\bSNDPGMMSG\b.*\b(FROMACCT|TOACCT|ACCOUNT|ACCT_ID)\b", line, re.I):
                    findings.append(Finding(
                        "IBMI-003", "medium", path, index + 1,
                        "程序消息可能暴露账户标识",
                        line.strip(),
                        "作业日志或消息队列可能记录完整账户标识。",
                        "改用脱敏标识和内部关联 ID，并按团队日志规范复核。",
                    ))

    return findings


def render_markdown(repo: Path, base: str, findings: list[Finding]) -> str:
    head = git(repo, "rev-parse", "--short", "HEAD").strip()
    lines = [
        "# IBM i 本地变更 QA 报告", "",
        f"- 仓库：`{repo.name}`", f"- 比较：`{base}...HEAD`（HEAD `{head}`）",
        f"- 确定性规则发现：**{len(findings)}** 项", "",
        "| 编号 | 严重度 | 位置 | 问题 |",
        "|---|---|---|---|",
    ]
    for item in findings:
        lines.append(f"| {item.rule} | {item.severity} | `{item.file}:{item.line}` | {item.title} |")
    lines.extend(["", "## 证据与建议", ""])
    for item in findings:
        lines.extend([
            f"### {item.rule} · {item.title}", "",
            f"- 位置：`{item.file}:{item.line}`", f"- 变更证据：`{item.evidence}`",
            f"- 影响：{item.impact}", f"- 建议：{item.action}", "",
        ])
    lines.extend([
        "## 验证边界", "",
        "本报告由透明的差异规则生成；未编译 RPG/CL/DDS，未连接 IBM i，未执行 RPGUnit，未证明业务正确性。",
        "结果是人工审查的输入，不是合并批准。", "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Review committed IBM i branch changes")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    findings = review(repo, args.base)
    (output / "ibmi-review.json").write_text(
        json.dumps([asdict(x) for x in findings], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "ibmi-review.md").write_text(render_markdown(repo, args.base, findings), encoding="utf-8")
    print(f"{len(findings)} findings -> {output / 'ibmi-review.md'}")


if __name__ == "__main__":
    main()
