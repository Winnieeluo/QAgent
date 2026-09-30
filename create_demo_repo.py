"""Create a fully synthetic two-commit IBM i Git repository for the QA demo."""

from pathlib import Path
import argparse
import subprocess


BASE = {
    "src/TRANSFER.sqlrpgle": """**free
ctl-opt dftactgrp(*no) actgrp(*caller);

dcl-pi *n;
  fromAcct packed(10:0) const;
  toAcct   packed(10:0) const;
  amount   packed(15:2) const;
end-pi;

exec sql set option commit = *chg;

exec sql update DEMO.ACCOUNT_BALANCE
           set BALANCE = BALANCE - :amount
         where ACCT_ID = :fromAcct;
if sqlcode <> 0;
  exec sql rollback;
  return;
endif;

exec sql update DEMO.ACCOUNT_BALANCE
           set BALANCE = BALANCE + :amount
         where ACCT_ID = :toAcct;
if sqlcode <> 0;
  exec sql rollback;
  return;
endif;

exec sql commit;
return;
""",
    "src/ACCTBAL.PF": """     A          R ACCTBALR
     A            ACCT_ID       10P 0
     A            BALANCE       15P 2
     A          K ACCT_ID
""",
    "src/TRANSFER.CLLE": """PGM PARM(&FROMACCT &TOACCT)
  DCL VAR(&FROMACCT) TYPE(*CHAR) LEN(10)
  DCL VAR(&TOACCT) TYPE(*CHAR) LEN(10)
  SNDPGMMSG MSG('Transfer request received')
ENDPGM
""",
    ".pr_agent.toml": """[config]
git_provider = "local"

[local]
review_path = "../artifacts/pr-agent-review.md"
description_path = "../artifacts/pr-agent-description.md"
improve_path = "../artifacts/pr-agent-improve.md"

[pr_reviewer]
extra_instructions = """ + "'''" + """
Review only risks introduced by the diff in this synthetic IBM i repository.
Prioritize RPG SQLCODE/SQLSTATE handling, transaction atomicity, DDS numeric
precision changes, downstream record-format dependencies, and disclosure of
account identifiers in CL job messages. Give file and line evidence, a concrete
failure scenario, and focused verification steps. Mark compiler/runtime claims
as unverified unless execution evidence is present. Never claim merge approval.
""" + "'''" + """
""",
    ".gitignore": "artifacts/\nreview.md\ndescription.md\nimprove.md\n",
    "README.md": "# Synthetic IBM i transfer example\n\nAll names and data in this repository are fictional. The `main` branch is a small baseline; `feature/risky-transfer` contains three deliberate QA risks for a local branch review. This code is illustrative and has not been compiled on IBM i.\n",
}


def run(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def create_repository(root: Path) -> None:
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to overwrite nonempty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    run(root, "init", "-b", "main")
    run(root, "config", "user.name", "Synthetic Demo")
    run(root, "config", "user.email", "demo@example.invalid")
    write(root, BASE)
    run(root, "add", ".")
    run(root, "commit", "-m", "Baseline fictional IBM i transfer")
    run(root, "checkout", "-b", "feature/risky-transfer")

    risky = dict(BASE)
    risky["src/TRANSFER.sqlrpgle"] = BASE["src/TRANSFER.sqlrpgle"].replace(
        "exec sql update DEMO.ACCOUNT_BALANCE\n"
        "           set BALANCE = BALANCE + :amount\n"
        "         where ACCT_ID = :toAcct;\n"
        "if sqlcode <> 0;\n"
        "  exec sql rollback;\n"
        "  return;\n"
        "endif;\n",
        "exec sql update DEMO.ACCOUNT_BALANCE\n"
        "           set BALANCE = COALESCE(BALANCE, 0) + :amount\n"
        "         where ACCT_ID = :toAcct;\n",
    )
    risky["src/ACCTBAL.PF"] = BASE["src/ACCTBAL.PF"].replace("BALANCE       15P 2", "BALANCE        9P 2")
    risky["src/TRANSFER.CLLE"] = BASE["src/TRANSFER.CLLE"].replace(
        "SNDPGMMSG MSG('Transfer request received')",
        "SNDPGMMSG MSG('Transfer from account ' *CAT &FROMACCT)",
    )
    write(root, risky)
    run(root, "add", ".")
    run(root, "commit", "-m", "Demonstrate risky transfer change for QA")
    print(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    create_repository(args.out)


if __name__ == "__main__":
    main()
