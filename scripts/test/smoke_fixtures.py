#!/usr/bin/env python3
"""CI smoke gate：fresh llmw init + wiki → 两探测器 → 断言结构合规。

兑现 [[check-fixtures-as-executable-truth]]：CLI 改坏骨架 / fixtures 同步漂移
都让本 gate 红。双向覆盖。

断言策略：两探测器所有 error 级 check passed=True（允许 skipped/null）。
版本常量（llmw.WIKI_SPEC_VERSION / WORKSPACE_SPEC_VERSION）与两 SKILL.md
frontmatter 的 *_spec_version 由本 gate 比对，漂移即挂。

standalone，Python 3.7+（与项目最低支持版本对齐）。用法：``python3 scripts/test/smoke_fixtures.py``
"""

# pylint: disable=missing-docstring

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _check_spec_version_alignment():
    """版本门：SKILL.md frontmatter *_spec_version 必须 == llmw 包内常量。

    读 SKILL.md frontmatter 与 llmw.WIKI_SPEC_VERSION / WORKSPACE_SPEC_VERSION 比对；
    任一不一致即 exit 1。这是 [[spec-version-bump-single-repo]] 的机械 gate（纪律升级为 gate）。
    """
    sys.path.insert(0, str(REPO))
    import llmw
    from llmw.config import DEFAULT_WORKSPACE

    # 防常量抄写 slip（2026-08-20 config.py 重写时 DEFAULT_WORKSPACE 曾丢 "-wiki"，
    # 所有测试都显式传 --workspace 故无兜底）：默认路径与仓内 18 处文档引用一致
    expected_default = Path.home() / "yzr-llm-wiki-workspace"
    if DEFAULT_WORKSPACE != expected_default:
        raise SystemExit(
            f"FAIL: DEFAULT_WORKSPACE={DEFAULT_WORKSPACE} != {expected_default}（抄写 slip？）"
        )

    cases = [
        ("yzr-llm-wiki-management", "wiki_spec_version", llmw.WIKI_SPEC_VERSION),
        (
            "yzr-llm-workspace-management",
            "workspace_spec_version",
            llmw.WORKSPACE_SPEC_VERSION,
        ),
    ]
    drifts = []
    for skill_dir, key, expected in cases:
        skill_md = REPO / skill_dir / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        m = re.search(rf"^[ \t]*{key}:[ \t]*(\S+)[ \t]*$", text, re.MULTILINE)
        if m is None:
            drifts.append(f"{skill_md}: 未找到 {key} 字段")
            continue
        frontmatter_value = m.group(1).strip()
        if frontmatter_value != expected:
            drifts.append(
                f"{skill_dir}: SKILL.md {key}={frontmatter_value} != llmw.{key.rstrip('_version').upper()}_SPEC_VERSION={expected}"
            )
    if drifts:
        sys.stderr.write("FAIL: spec 版本对齐检查失败:\n")
        for d in drifts:
            sys.stderr.write(f"  {d}\n")
        sys.stderr.write(
            "修复：按 MEMORY/spec-version-bump-single-repo.md 同 commit 改 SKILL.md frontmatter + llmw/__init__.py 常量\n"
        )
        raise SystemExit(1)
    print("[OK] spec 版本对齐：SKILL.md frontmatter == llmw 包内常量")


def _llmw(args):
    """跑 ``python -m llmw <args>``，失败即抛（gate 红）。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, "-m", "llmw", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"FAIL: llmw {' '.join(args)} exit={proc.returncode}")
    return proc


def _detector_json(args):
    """跑 llmw 探测器子命令 --json，容忍 exit 1（有 error check），返回解析 dict。"""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    proc = subprocess.run(
        [sys.executable, "-m", "llmw", *args],
        env=env,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(proc.stdout)
    except ValueError:
        sys.stderr.write(f"探测器 JSON 解析失败 (exit={proc.returncode}):\n")
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(1)


def _assert_all_error_pass(args, label):
    """断言探测器所有 error 级 check passed=True（允许 skipped/null）。

    fail → 列出 fail 的 check id（诊断）+ exit 1；返回解析后的 JSON dict。
    """
    data = _detector_json(args)
    failed = [
        f"{c['id']} ({c.get('file', '?')})"
        for c in data["checks"]
        if c.get("severity") == "error" and c.get("passed") is False
    ]
    if failed:
        sys.stderr.write(f"FAIL: {label} 探测器 error check fail: {failed}\n")
        sys.stderr.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        raise SystemExit(1)
    print(f"[OK] {label} 探测器：所有 error check pass")
    return data


def main():
    _check_spec_version_alignment()
    with tempfile.TemporaryDirectory(prefix="llmw-smoke-") as tmp:
        ws = Path(tmp) / "ws"

        _llmw(["init", "--path=" + str(ws)])
        _llmw(
            [
                "--workspace=" + str(ws),
                "model",
                "add",
                "--model-id=m1",
                "--name=T",
                "--base-url=https://x.com",
                "--api-key=k",
                "--context-window=200000",
                "--default",
            ]
        )
        _llmw(
            [
                "--workspace=" + str(ws),
                "wiki",
                "--name=w",
                "add",
                "--topic=T",
                "--display-name=T",
                "--description=d",
                "--tag=x",
                "--model=m1",
            ]
        )

        # 两探测器：workspace 级 + wiki 级（走 llmw.content 命令面，--path 直传 wiki 根）
        ws_data = _assert_all_error_pass(
            ["--workspace=" + str(ws), "check-fixtures", "--json"], "workspace"
        )
        wiki_data = _assert_all_error_pass(
            ["wiki", "--path=" + str(ws / "w"), "check-fixtures", "--json"], "wiki"
        )

        # 显式确认两条读取契约 check（E1/E2）落地且 pass——SKILL 读取契约自洽对接
        for check_id, data in [
            ("workspace-toml-reads-satisfied", ws_data),
            ("wiki-metadata-reads-satisfied", wiki_data),
        ]:
            ids = {c["id"]: c.get("passed") for c in data["checks"]}
            if ids.get(check_id) is not True:
                raise SystemExit(f"FAIL: {check_id} check 未 pass/缺失: {ids}")
        print("[OK] 读取契约 check（E1/E2）passed=True")

    print("\nsmoke gate PASS")


if __name__ == "__main__":
    main()
