#!/usr/bin/env python3
"""CI smoke gate：fresh llmw init + wiki → wiki 探测器 → 断言结构合规。

兑现 [[check-fixtures-as-executable-truth]]：CLI 改坏骨架 / fixtures 同步漂移
都让本 gate 红。双向覆盖。

断言策略：探测器所有 error 级 check passed=True（允许 skipped/null）。
另守护默认 workspace 路径抄写 slip（DEFAULT_WORKSPACE == ~/yzr-llm-wiki-workspace）。

standalone，Python 3.7+（与项目最低支持版本对齐）。用法：``python3 scripts/test/smoke_fixtures.py``
"""

# pylint: disable=missing-docstring

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _check_default_workspace():
    """默认 workspace 路径守卫。

    防常量抄写 slip（2026-08-20 config.py 重写时 DEFAULT_WORKSPACE 曾丢 "-wiki"，
    所有测试都显式传 --workspace 故无兜底）：默认路径与仓内文档引用一致。
    """
    sys.path.insert(0, str(REPO))
    from llmw.config import DEFAULT_WORKSPACE

    expected_default = Path.home() / "yzr-llm-wiki-workspace"
    if DEFAULT_WORKSPACE != expected_default:
        raise SystemExit(
            f"FAIL: DEFAULT_WORKSPACE={DEFAULT_WORKSPACE} != {expected_default}（抄写 slip？）"
        )
    print("[OK] 默认 workspace：DEFAULT_WORKSPACE == ~/yzr-llm-wiki-workspace")


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
    _check_default_workspace()
    with tempfile.TemporaryDirectory(prefix="llmw-smoke-") as tmp:
        ws = Path(tmp) / "ws"

        _llmw(["init", "--path=" + str(ws)])
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
            ]
        )

        # wiki 探测器（走 llmw.content 命令面，--path 直传 wiki 根）
        wiki_root = ws / "w"
        if not (wiki_root / "discussions" / ".gitkeep").is_file():
            raise SystemExit("FAIL: 新 wiki 缺 discussions/.gitkeep（出生布局漂移）")
        if (wiki_root / "raw" / "discussions").exists():
            raise SystemExit("FAIL: 新 wiki 不应创建 raw/discussions/（旧布局）")
        print("[OK] wiki 出生布局：discussions/ 位于 wiki 根")
        wiki_data = _assert_all_error_pass(
            ["wiki", "--path=" + str(wiki_root), "check-fixtures", "--json"], "wiki"
        )

        # 显式确认读取契约 check（E2）落地且 pass——SKILL 读取契约自洽对接
        ids = {c["id"]: c.get("passed") for c in wiki_data["checks"]}
        if ids.get("wiki-metadata-reads-satisfied") is not True:
            raise SystemExit(
                f"FAIL: wiki-metadata-reads-satisfied check 未 pass/缺失: {ids}"
            )
        print("[OK] 读取契约 check（E2）passed=True")

    print("\nsmoke gate PASS")


if __name__ == "__main__":
    main()
