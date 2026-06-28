# Install / Uninstall 脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `scripts/install.sh` 与 `scripts/uninstall.sh` 两个 bash 脚本，把生成的 `llmw` wrapper 装进 `~/.local/bin` 并按需注册 PATH，卸载为精确逆操作。

**Architecture:** install.sh 在仓库根被 `./scripts/install.sh` 调用，以脚本自身上一级定位仓库根，生成一个内嵌仓库绝对路径、用 `PYTHONPATH` 解析 `llmw` 包的 wrapper 到 `~/.local/bin/llmw`；当 `~/.local/bin` 不在 PATH 时，往 `$SHELL` 对应的 rc 追加一个带 marker 的 PATH 块。uninstall.sh 删 wrapper，并扫描所有候选 rc 文件按 marker 整段删除。全程不碰 pip / 包本身 / 用户数据。

**Tech Stack:** 纯 bash（兼容 macOS bash 3.2 + Ubuntu/其他 Linux），`awk` 做 marker 块增删（不用 `sed -i`），一个 bash 测试套件。

**共享契约（三处必须逐字一致）：**
- marker 起始行：`# >>> llmw (managed by install.sh) >>>`
- marker 结束行：`# <<< llmw <<<`

**Spec 来源：** `doc/design/08-install-uninstall.md`

---

## File Structure

| 文件 | 职责 |
| --- | --- |
| `scripts/install.sh` | 安装：定位仓库根 → 检测 python3 → 建 `~/.local/bin` → 生成 wrapper → 按 PATH 现状决定是否写 marker 块 |
| `scripts/uninstall.sh` | 卸载：删 `~/.local/bin/llmw` → 扫描所有候选 rc 按 marker 整段删除 |
| `scripts/test/test_install_uninstall.sh` | 测试套件：临时 HOME + 受控 PATH/SHELL 跑 install/uninstall，断言产物 |
| `README.md` | 更新「安装」章节，把 install 脚本作为推荐方式 |

---

## Task 1: 测试套件脚手架 + install.sh 生成 wrapper

**Files:**
- Create: `scripts/test/test_install_uninstall.sh`
- Create: `scripts/install.sh`

- [ ] **Step 1: 写测试套件（含 3 个 wrapper 测试）**

Create `scripts/test/test_install_uninstall.sh`:

```bash
#!/usr/bin/env bash
# install/uninstall 脚本测试套件。用临时 HOME 跑，绝不碰真实环境。
set -u

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL="$REPO/scripts/install.sh"
UNINSTALL="$REPO/scripts/uninstall.sh"

PASS=0
FAIL=0
TMPHOME=""
PYDIR=""

setup() {
  TMPHOME="$(mktemp -d)"
  PYDIR="$(dirname "$(command -v python3 2>/dev/null || command -v python 2>/dev/null)")"
  [ -n "$PYDIR" ] || PYDIR="/usr/bin"
}

teardown() {
  [ -n "$TMPHOME" ] && rm -rf "$TMPHOME"
}
trap teardown EXIT

# 断言（在子 shell 里跑测试，失败 exit 1 只结束该子 shell）
assert_exists()       { [ -e "$1" ]      || { echo "    assert_exists FAIL: $1"; exit 1; }; }
assert_not_exists()   { [ ! -e "$1" ]    || { echo "    assert_not_exists FAIL: $1 存在"; exit 1; }; }
assert_executable()   { [ -x "$1" ]      || { echo "    assert_executable FAIL: $1"; exit 1; }; }
assert_contains()     { grep -qF "$2" "$1" 2>/dev/null || { echo "    assert_contains FAIL: '$2' 不在 $1"; exit 1; }; }
assert_not_contains() { ! grep -qF "$2" "$1" 2>/dev/null || { echo "    assert_not_contains FAIL: '$2' 在 $1"; exit 1; }; }
assert_count()        { local n; n="$(grep -cF "$2" "$1" 2>/dev/null || true)"; [ "$n" = "$3" ] || { echo "    assert_count FAIL: $1 有 $n 个 '$2'，期望 $3"; exit 1; }; }

# 受控环境跑 install/uninstall/wrapper，退出码存入全局
run_install() {
  HOME="$TMPHOME" SHELL="${1:-/bin/zsh}" PATH="${2:-$PYDIR:/usr/bin:/bin}" \
    bash "$INSTALL" >"$TMPHOME/inst.out" 2>&1
  INST_CODE=$?
}
run_uninstall() {
  HOME="$TMPHOME" PATH="${1:-$PYDIR:/usr/bin:/bin}" \
    bash "$UNINSTALL" >"$TMPHOME/uninst.out" 2>&1
  UNINST_CODE=$?
}
run_llmw() {
  HOME="$TMPHOME" PATH="$PYDIR:/usr/bin:/bin" "$TMPHOME/.local/bin/llmw" "$@" >"$TMPHOME/llmw.out" 2>&1
  LLMW_CODE=$?
}

# ---- 测试用例 ----
test_install_creates_wrapper() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_exists "$TMPHOME/.local/bin/llmw"
  assert_executable "$TMPHOME/.local/bin/llmw"
}
test_wrapper_runs_help() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  run_llmw --help
  [ "$LLMW_CODE" = 0 ] || { echo "      llmw --help 退出码 $LLMW_CODE"; cat "$TMPHOME/llmw.out"; exit 1; }
}
test_wrapper_embeds_repo() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_contains "$TMPHOME/.local/bin/llmw" "PYTHONPATH="
  assert_contains "$TMPHOME/.local/bin/llmw" "python3 -m llmw"
}

# ---- runner ----
TESTS=(
  test_install_creates_wrapper
  test_wrapper_runs_help
  test_wrapper_embeds_repo
)

run_test() {
  local name="$1"
  ( "$name" ) >"$TMPHOME/test.out" 2>&1
  local code=$?
  if [ "$code" = 0 ]; then echo "PASS  $name"; PASS=$((PASS+1));
  else echo "FAIL  $name"; sed 's/^/      /' "$TMPHOME/test.out"; FAIL=$((FAIL+1)); fi
}

main() {
  local tests=("$@")
  [ "${#tests[@]}" -gt 0 ] || tests=("${TESTS[@]}")
  local t
  for t in "${tests[@]}"; do setup; run_test "$t"; teardown; done
  echo "----"
  echo "PASS=$PASS FAIL=$FAIL"
  [ "$FAIL" = 0 ]
}
main "$@"
```

- [ ] **Step 2: 跑测试，确认因 install.sh 不存在而失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `FAIL test_install_creates_wrapper`（及另外两个），最终 `FAIL=3`，脚本非 0 退出。原因是 `bash "$INSTALL"` 找不到文件。

- [ ] **Step 3: 写 install.sh（最小版：生成 wrapper）**

Create `scripts/install.sh`:

```bash
#!/usr/bin/env bash
# scripts/install.sh — 把生成的 llmw wrapper 装进 ~/.local/bin（Phase 2）
set -euo pipefail

usage() {
  cat <<'USG'
usage: ./scripts/install.sh
  生成 ~/.local/bin/llmw（PYTHONPATH 指向本仓库），并按需注册 PATH。
  卸载用 ./scripts/uninstall.sh。
USG
}

# 脚本在 scripts/，仓库根是其上一级；不依赖 readlink -f（兼容 macOS bash 3.2）
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bin_dir="$HOME/.local/bin"

mkdir -p "$bin_dir"

cat > "$bin_dir/llmw" <<EOF
#!/usr/bin/env bash
# llmw launcher — generated by install.sh. Repo: $repo_root
# 仓库被挪走会失效；重跑 ./scripts/install.sh 即可修复。
export PYTHONPATH="$repo_root:\$PYTHONPATH"
exec python3 -m llmw "\$@"
EOF
chmod +x "$bin_dir/llmw"

echo "已安装 llmw -> $bin_dir/llmw"
```

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 三个 `PASS`，`PASS=3 FAIL=0`，退出码 0。

- [ ] **Step 5: 提交**

```bash
git add scripts/install.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(install): generate ~/.local/bin/llmw wrapper + test harness"
```

---

## Task 2: install.sh 按需注册 PATH marker 块（带条件）

**Files:**
- Modify: `scripts/install.sh`（加 `select_rc` + marker 追加逻辑）
- Modify: `scripts/test/test_install_uninstall.sh`（加 2 个测试到 TESTS）

- [ ] **Step 1: 加 2 个测试**

Append to the test functions in `scripts/test/test_install_uninstall.sh` (before the `# ---- runner ----` line):

```bash
test_marker_written_when_bin_not_in_path() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  [ "$INST_CODE" = 0 ] || { cat "$TMPHOME/inst.out"; exit 1; }
  assert_exists "$TMPHOME/.zshrc"
  assert_contains "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>"
  assert_contains "$TMPHOME/.zshrc" "# <<< llmw <<<"
  assert_contains "$TMPHOME/.zshrc" '$HOME/.local/bin'
}
test_no_marker_when_bin_in_path() {
  run_install /bin/zsh "$TMPHOME/.local/bin:$PYDIR:/usr/bin:/bin"
  [ "$INST_CODE" = 0 ] || { cat "$TMPHOME/inst.out"; exit 1; }
  if [ -e "$TMPHOME/.zshrc" ]; then
    assert_not_contains "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>"
  fi
}
```

And add both names to the `TESTS=(...)` array.

- [ ] **Step 2: 跑测试，确认新增 2 个失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `test_marker_written_when_bin_not_in_path` FAIL（`.zshrc` 没被创建）。前 3 个仍 PASS。

- [ ] **Step 3: 给 install.sh 加 select_rc 与 marker 追加**

In `scripts/install.sh`, add the `select_rc` function after `usage()`:

```bash
# 按 $SHELL 选目标 rc（启发式；macOS bash 为 login → .bash_profile）
select_rc() {
  local sh="${SHELL:-/bin/sh}"
  sh="${sh##*/}"
  case "$sh" in
    zsh)  printf '%s/.zshrc' "$HOME" ;;
    bash)
      if [ "$(uname)" = "Darwin" ]; then printf '%s/.bash_profile' "$HOME"
      else printf '%s/.bashrc' "$HOME"; fi ;;
    fish) printf '%s/.config/fish/config.fish' "$HOME" ;;
    *)    printf '%s/.profile' "$HOME" ;;
  esac
}
```

Then after the `chmod +x "$bin_dir/llmw"` line and before the final `echo`, add:

```bash
# --- 按 PATH 现状决定是否注册 marker 块 ---
case ":$PATH:" in
  *":$HOME/.local/bin:"*) already=1 ;;
  *) already=0 ;;
esac

if [ "$already" = 0 ]; then
  rc_file="$(select_rc)"
  mkdir -p "$(dirname "$rc_file")"
  cat >> "$rc_file" <<'BLOCK'
# >>> llmw (managed by install.sh) >>>
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
esac
# <<< llmw <<<
BLOCK
  wrote_rc=1
fi
```

And change the final echo to:

```bash
echo "已安装 llmw -> $bin_dir/llmw"
[ "${wrote_rc:-0}" = 1 ] && echo "已写入 PATH 到 $rc_file；请运行 source $rc_file 或重开终端使其生效。"
```

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 5 个 `PASS`，`FAIL=0`。

- [ ] **Step 5: 提交**

```bash
git add scripts/install.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(install): register PATH via marker block when ~/.local/bin not in PATH"
```

---

## Task 3: install.sh 幂等重装

**Files:**
- Modify: `scripts/install.sh`（marker 追加前加去重判断）
- Modify: `scripts/test/test_install_uninstall.sh`（加 2 个测试）

- [ ] **Step 1: 加 2 个测试**

Append:

```bash
test_install_idempotent_no_dup_marker() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_count "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>" 1
}
test_reinstall_overwrites_wrapper() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  echo "SENTINEL_BEFORE" >> "$TMPHOME/.local/bin/llmw"
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_not_contains "$TMPHOME/.local/bin/llmw" "SENTINEL_BEFORE"
  assert_contains "$TMPHOME/.local/bin/llmw" "python3 -m llmw"
}
```

Add both names to `TESTS`.

- [ ] **Step 2: 跑测试，确认 idempotent 测试失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `test_install_idempotent_no_dup_marker` FAIL（marker 出现 2 次）。

- [ ] **Step 3: 给 marker 追加加去重判断**

In `scripts/install.sh`, wrap the `cat >> "$rc_file"` block so it skips when the marker start line already exists. Replace the `if [ "$already" = 0 ]; then ... fi` block (from Task 2) with:

```bash
if [ "$already" = 0 ]; then
  rc_file="$(select_rc)"
  mkdir -p "$(dirname "$rc_file")"
  if ! grep -qx '# >>> llmw (managed by install.sh) >>>' "$rc_file" 2>/dev/null; then
    cat >> "$rc_file" <<'BLOCK'
# >>> llmw (managed by install.sh) >>>
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
esac
# <<< llmw <<<
BLOCK
    wrote_rc=1
  fi
fi
```

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 7 个 `PASS`，`FAIL=0`。

- [ ] **Step 5: 提交**

```bash
git add scripts/install.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(install): idempotent reinstall (no duplicate marker, overwrite wrapper)"
```

---

## Task 4: install.sh 错误处理（python3 缺失 + 老 Python tomli 提示）

**Files:**
- Modify: `scripts/install.sh`（顶部加 python3 检查 + 版本提示）
- Modify: `scripts/test/test_install_uninstall.sh`（加 fakebin 工具 + 1 个测试）

- [ ] **Step 1: 加 fakebin 工具函数与测试**

Append to the helper section of `scripts/test/test_install_uninstall.sh` (near the other `run_*` helpers):

```bash
# 构造一个只有常用工具、没有 python3 的 PATH 目录
make_fakebin_no_python3() {
  local fb="$TMPHOME/fakebin"; mkdir -p "$fb"
  local t p
  for t in mkdir chmod rm cat grep awk uname mktemp mv dirname printf; do
    p="$(command -v "$t" 2>/dev/null)" && ln -s "$p" "$fb/$t"
  done
  printf '%s' "$fb"
}
```

Append a test:

```bash
test_install_fails_without_python3() {
  local fb; fb="$(make_fakebin_no_python3)"
  HOME="$TMPHOME" SHELL=/bin/zsh PATH="$fb" bash "$INSTALL" >"$TMPHOME/inst.out" 2>&1
  local code=$?
  [ "$code" != 0 ] || { echo "      期望非零退出，实际 0"; cat "$TMPHOME/inst.out"; exit 1; }
  assert_contains "$TMPHOME/inst.out" "python3"
}
```

Add `test_install_fails_without_python3` to `TESTS`.

- [ ] **Step 2: 跑测试，确认失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `test_install_fails_without_python3` FAIL（install.sh 没检查 python3，用 fakebin 跑会因别处先报错或退出码不符）。

- [ ] **Step 3: 给 install.sh 顶部加检查**

In `scripts/install.sh`, immediately after `repo_root="$(cd ...)"` and before `bin_dir=`, add:

```bash
if ! command -v python3 >/dev/null 2>&1; then
  echo "install.sh: 未找到 python3（需要 Python 3.7+）。请先安装 python3 再重试。" >&2
  exit 1
fi

# Python < 3.11 运行时需要 tomli；只提示，不自动安装
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
  echo "install.sh: 注意 Python < 3.11，运行时可能需要 tomli（pip install 'tomli>=1.1'）。继续安装。" >&2
fi
```

> 注：tomli 提示依赖真实 python3 版本，无法在 3.14 测试环境自动覆盖该分支；归入 Task 8 手动验证。

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 8 个 `PASS`，`FAIL=0`。

- [ ] **Step 5: 提交**

```bash
git add scripts/install.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(install): fail fast when python3 missing; warn on Python <3.11"
```

---

## Task 5: wrapper 仓库被挪走的友好报错

**Files:**
- Modify: `scripts/install.sh`（wrapper 模板加 REPO 变量 + 目录检查）
- Modify: `scripts/test/test_install_uninstall.sh`（加 1 个测试）

- [ ] **Step 1: 加测试**

Append:

```bash
test_wrapper_reports_when_repo_missing() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  # 把 wrapper 里的 REPO 行改成不存在的路径
  awk -v new='REPO="/nonexistent/llmw-repo"' '/^REPO=/{print new; next} 1' \
    "$TMPHOME/.local/bin/llmw" > "$TMPHOME/badllmw"
  chmod +x "$TMPHOME/badllmw"
  HOME="$TMPHOME" PATH="$PYDIR:/usr/bin:/bin" "$TMPHOME/badllmw" --help >"$TMPHOME/bad.out" 2>&1
  local code=$?
  [ "$code" != 0 ] || { echo "      期望非零退出"; cat "$TMPHOME/bad.out"; exit 1; }
  assert_contains "$TMPHOME/bad.out" "仓库目录不存在"
}
```

Add to `TESTS`.

- [ ] **Step 2: 跑测试，确认失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `test_wrapper_reports_when_repo_missing` FAIL（Task 1 的 wrapper 没有 `REPO=` 行，awk 不替换，wrapper 仍指向真实仓库 → 退出 0）。

- [ ] **Step 3: 更新 wrapper 模板，加 REPO 变量与目录检查**

In `scripts/install.sh`, replace the `cat > "$bin_dir/llmw" <<EOF ... EOF` block with:

```bash
cat > "$bin_dir/llmw" <<EOF
#!/usr/bin/env bash
# llmw launcher — generated by install.sh. Repo: $repo_root
# 仓库被挪走会失效；重跑 ./scripts/install.sh 即可修复。
REPO="$repo_root"
if [ ! -d "\$REPO" ]; then
  echo "llmw: 仓库目录不存在: \$REPO（可能被移动或删除，请重跑 ./scripts/install.sh）" >&2
  exit 1
fi
export PYTHONPATH="\$REPO:\$PYTHONPATH"
exec python3 -m llmw "\$@"
EOF
chmod +x "$bin_dir/llmw"
```

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 9 个 `PASS`，`FAIL=0`（含 `test_wrapper_embeds_repo`，新模板仍含 `PYTHONPATH=` 与 `python3 -m llmw`）。

- [ ] **Step 5: 提交**

```bash
git add scripts/install.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(install): wrapper errors clearly when repo moved/deleted"
```

---

## Task 6: uninstall.sh（删 wrapper + 清所有候选 rc 的 marker）

**Files:**
- Create: `scripts/uninstall.sh`
- Modify: `scripts/test/test_install_uninstall.sh`（加 4 个测试）

- [ ] **Step 1: 加 4 个测试**

Append:

```bash
test_uninstall_removes_wrapper() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_exists "$TMPHOME/.local/bin/llmw"
  run_uninstall "$PYDIR:/usr/bin:/bin"
  [ "$UNINST_CODE" = 0 ] || { cat "$TMPHOME/uninst.out"; exit 1; }
  assert_not_exists "$TMPHOME/.local/bin/llmw"
}
test_uninstall_strips_marker_keeps_other_lines() {
  printf 'alias x=1\n# my line\n' > "$TMPHOME/.zshrc"
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  assert_contains "$TMPHOME/.zshrc" "# my line"
  assert_contains "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>"
  run_uninstall "$PYDIR:/usr/bin:/bin"
  assert_not_contains "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>"
  assert_not_contains "$TMPHOME/.zshrc" "# <<< llmw <<<"
  assert_contains "$TMPHOME/.zshrc" "alias x=1"
  assert_contains "$TMPHOME/.zshrc" "# my line"
}
test_uninstall_scans_all_candidate_rc() {
  # 把 marker 块手动种到 install 不会选的 .bashrc，验证 uninstall 仍能清掉
  cat > "$TMPHOME/.bashrc" <<'B'
# >>> llmw (managed by install.sh) >>>
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) PATH="$HOME/.local/bin:$PATH"; export PATH ;;
esac
# <<< llmw <<<
B
  run_uninstall "$PYDIR:/usr/bin:/bin"
  assert_not_contains "$TMPHOME/.bashrc" "# >>> llmw (managed by install.sh) >>>"
}
test_uninstall_idempotent() {
  run_uninstall "$PYDIR:/usr/bin:/bin"   # 啥都没装
  [ "$UNINST_CODE" = 0 ] || { cat "$TMPHOME/uninst.out"; exit 1; }
  run_uninstall "$PYDIR:/usr/bin:/bin"   # 再跑一次
  [ "$UNINST_CODE" = 0 ] || { cat "$TMPHOME/uninst.out"; exit 1; }
}
```

Add all four names to `TESTS`.

- [ ] **Step 2: 跑测试，确认 4 个新测试失败**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 4 个 `test_uninstall_*` FAIL（`$UNINSTALL` 文件不存在）。

- [ ] **Step 3: 写 uninstall.sh**

Create `scripts/uninstall.sh`:

```bash
#!/usr/bin/env bash
# scripts/uninstall.sh — install.sh 的逆操作：删 wrapper + 清 PATH marker 块
set -euo pipefail

usage() {
  cat <<'USG'
usage: ./scripts/uninstall.sh
  删除 ~/.local/bin/llmw，并从所有候选 shell rc 移除 llmw marker 块。
  不删仓库、不删 workspace 数据。
USG
}

MARKER_START='# >>> llmw (managed by install.sh) >>>'
MARKER_END='# <<< llmw <<<'

# 从单个文件按 marker 整段删除（含边界行），块外内容不动；用 awk，不用 sed -i
strip_marker() {
  local f="$1"
  [ -f "$f" ] || return 0
  local tmp; tmp="$(mktemp)"
  awk -v s="$MARKER_START" -v e="$MARKER_END" '
    $0==s {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$f" > "$tmp"
  mv "$tmp" "$f"
}

rm -f "$HOME/.local/bin/llmw"

for f in \
  "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" \
  "$HOME/.profile" "$HOME/.config/fish/config.fish"; do
  strip_marker "$f"
done

echo "已卸载 llmw（~/.local/bin/llmw 已删除，PATH marker 块已清理）。"
```

- [ ] **Step 4: 跑测试，确认全过**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: 13 个 `PASS`，`FAIL=0`。

- [ ] **Step 5: 提交**

```bash
git add scripts/uninstall.sh scripts/test/test_install_uninstall.sh
git commit -m "feat(uninstall): remove wrapper and strip marker block from all rc files"
```

---

## Task 7: 更新 README 安装说明

**Files:**
- Modify: `README.md`（安装章节 + Phase 边界表）

- [ ] **Step 1: 把 install 脚本列为推荐安装方式**

In `README.md`, replace the section starting at `### 2. 让 `llmw` 可用（二选一）` through the end of `### 3. Python 依赖` (lines ~17–41) with:

````markdown
### 2. 安装命令（推荐）

```bash
./scripts/install.sh
```

生成 `~/.local/bin/llmw`（wrapper 内嵌本仓库路径，用 `PYTHONPATH` 解析 `llmw` 包，**无需 pip/venv**），并在 `~/.local/bin` 不在 `PATH` 时自动往 shell rc 注册一个 marker 块。装完按提示 `source ~/.zshrc`（或重开终端）即可。

> 全程不动 `llmw/` 包本身、不碰 pip。Python 3.11+ 零第三方依赖；<3.11 运行时需 `pip install 'tomli>=1.1'`。

卸载（只删 wrapper + PATH marker，**不删仓库、不删 workspace 数据**）：

```bash
./scripts/uninstall.sh
```

### 3. 备选：pip 安装

入口是仓库根的 `bin/llmw`（thin shell，`exec python3 -m llmw`）。若更喜欢走 pip：

```bash
pip install -e .
```

> 系统 Python（Homebrew 等 PEP 668 externally-managed）会拒绝全局 install，改用 `pip install -e . --user`、`pipx install -e .` 或先建 venv。
````

- [ ] **Step 2: 更新 Phase 边界表**

In `README.md`, in the `## Phase 边界` table, change the install/uninstall row from:

```markdown
| install / uninstall 脚本 | ❌（手动加 PATH） | ✅ |
```

to:

```markdown
| install / uninstall 脚本 | ✅（`./scripts/install.sh` / `./scripts/uninstall.sh`） | |
```

- [ ] **Step 3: 校验 README 渲染**

Run: `grep -n "scripts/install.sh\|scripts/uninstall.sh" README.md`
Expected: 至少 3 行命中（安装命令块、卸载命令块、Phase 边界行）。

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: document ./scripts/install.sh & uninstall.sh in README"
```

---

## Task 8: 手动跨平台验证

**Files:** 无（验证 + 记录结果）

> 自动测试用临时 HOME、固定 `SHELL=/bin/zsh`，覆盖 wrapper/marker/幂等/卸载/扫描。本任务验证真实登录 shell 与多平台行为，尤其是 zsh/bash/fish/profile 分支与 `source` 后 PATH 真的生效。

- [ ] **Step 1: macOS（zsh）跑自动化套件**

Run: `bash scripts/test/test_install_uninstall.sh`
Expected: `PASS=13 FAIL=0`，退出码 0。

- [ ] **Step 2: macOS 真实安装并新开终端验证**

Run（在仓库根）:
```bash
./scripts/install.sh
```
Expected: 输出 `已安装 llmw -> ~/.local/bin/llmw`，并提示 `source ~/.zshrc`。

Then open a **new** terminal and run:
```bash
llmw --help
```
Expected: 打印 `llmw` 帮助，退出码 0。

- [ ] **Step 3: macOS 卸载并验证干净**

Run:
```bash
./scripts/uninstall.sh
grep -n "llmw" ~/.zshrc
```
Expected: 第一行输出「已卸载」；`grep` 无命中（marker 块已整段移除，rc 其余行保留）。

- [ ] **Step 4: Linux/Ubuntu（bash）验证（如有环境）**

In a Linux/bash environment at the repo root, repeat Steps 1–3, but verify the marker went into `~/.bashrc` (not `.zshrc`): after install, `grep -n "managed by install.sh" ~/.bashrc` should hit, and after uninstall should be clean. If no Linux env available, note this as deferred.

- [ ] **Step 5: 记录结果**

把 Step 1–4 的实际输出贴回本计划对应 step 下方（或提交到 PR 描述）。全部通过即视为 install/uninstall 交付完成。

---

## Self-Review（写计划后自检）

**1. Spec 覆盖（对照 `doc/design/08-install-uninstall.md`）：**
- I-5（只动 wrapper + marker，不删数据/仓库，无深度清理 flag）→ Task 1/2/6，uninstall 仅删 wrapper + marker。✅
- I-6（仓库根直接跑、自身上一级定位仓库根、不依赖 readlink -f）→ Task 1 `repo_root` 行。✅
- I-7（wrapper 自包含、PYTHONPATH 不 cd、不 symlink）→ Task 1 wrapper 模板。✅
- 依赖（python3 检查、<3.11 tomli 提示）→ Task 4。✅（tomli 分支手动验证）
- wrapper 仓库被挪走友好报错 → Task 5。✅
- marker 幂等 / reinstall 覆盖 → Task 3。✅
- 卸载 marker 整段删、块外不动、扫所有候选 rc、幂等 → Task 6。✅
- 跨平台（`#!/usr/bin/env bash`、无 `sed -i`、用 awk、POSIX case）→ Task 1/2/6 + Task 8 手动。✅
- README 安装说明 → Task 7。✅

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码或确切命令与期望输出。tomli 分支已显式标注「手动验证」，非占位符。✅

**3. 类型/字符串一致性：** marker 起止字符串（`# >>> llmw (managed by install.sh) >>>` / `# <<< llmw <<<`）在 install.sh（Task 2/3 写入）、uninstall.sh（Task 6 删除）、测试（Task 2/3/6 断言）四处逐字一致。awk 用 `$0==s` 精确整行匹配，与写入行一致。✅
