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

# 构造一个只有常用工具、没有 python3 的 PATH 目录
make_fakebin_no_python3() {
  local fb="$TMPHOME/fakebin"; mkdir -p "$fb"
  local t p
  for t in mkdir chmod rm cat grep awk uname mktemp mv dirname printf bash; do
    p="$(command -v "$t" 2>/dev/null)" && ln -s "$p" "$fb/$t"
  done
  printf '%s' "$fb"
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
test_marker_written_when_bin_not_in_path() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  [ "$INST_CODE" = 0 ] || { cat "$TMPHOME/inst.out"; exit 1; }
  assert_exists "$TMPHOME/.zshrc"
  assert_contains "$TMPHOME/.zshrc" "# >>> llmw (managed by install.sh) >>>"
  assert_contains "$TMPHOME/.zshrc" "# <<< llmw <<<"
  assert_contains "$TMPHOME/.zshrc" '$HOME/.local/bin'
}
test_path_marker_written_to_all_shells() {
  # 新设计：给所有候选 shell 的 rc 注册 PATH（与 completion 三套对称），各自语法。
  # 以 rc marker 为准（旧 already 看 install 进程 PATH 的逻辑已移除——进程 PATH 不代表 rc 已配置，不可靠）。
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  [ "$INST_CODE" = 0 ] || { cat "$TMPHOME/inst.out"; exit 1; }
  assert_contains "$TMPHOME/.bashrc"                  "# >>> llmw (managed by install.sh) >>>"
  assert_contains "$TMPHOME/.zshrc"                   "# >>> llmw (managed by install.sh) >>>"
  assert_contains "$TMPHOME/.config/fish/config.fish" "# >>> llmw (managed by install.sh) >>>"
  # fish 用 fish 语法（set -gx），不是 bash 的 case/esac
  assert_contains     "$TMPHOME/.config/fish/config.fish" "set -gx PATH"
  assert_not_contains "$TMPHOME/.config/fish/config.fish" "esac"
}
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
test_install_fails_without_python3() {
  local fb; fb="$(make_fakebin_no_python3)"
  HOME="$TMPHOME" SHELL=/bin/zsh PATH="$fb" bash "$INSTALL" >"$TMPHOME/inst.out" 2>&1
  local code=$?
  [ "$code" != 0 ] || { echo "      期望非零退出，实际 0"; cat "$TMPHOME/inst.out"; exit 1; }
  assert_contains "$TMPHOME/inst.out" "python3"
}
test_wrapper_reports_when_repo_missing() {
  run_install /bin/zsh "$PYDIR:/usr/bin:/bin"
  awk -v new='REPO="/nonexistent/llmw-repo"' '/^REPO=/{print new; next} 1' \
    "$TMPHOME/.local/bin/llmw" > "$TMPHOME/badllmw"
  chmod +x "$TMPHOME/badllmw"
  HOME="$TMPHOME" PATH="$PYDIR:/usr/bin:/bin" "$TMPHOME/badllmw" --help >"$TMPHOME/bad.out" 2>&1
  local code=$?
  [ "$code" != 0 ] || { echo "      期望非零退出"; cat "$TMPHOME/bad.out"; exit 1; }
  assert_contains "$TMPHOME/bad.out" "仓库目录不存在"
}
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
  # 把 marker 块手动种到 .bashrc，验证 uninstall 扫所有候选 rc 都能清（不止 install 写的那些）
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

# ---- runner ----
TESTS=(
  test_install_creates_wrapper
  test_wrapper_runs_help
  test_wrapper_embeds_repo
  test_marker_written_when_bin_not_in_path
  test_path_marker_written_to_all_shells
  test_install_idempotent_no_dup_marker
  test_reinstall_overwrites_wrapper
  test_install_fails_without_python3
  test_wrapper_reports_when_repo_missing
  test_uninstall_removes_wrapper
  test_uninstall_strips_marker_keeps_other_lines
  test_uninstall_scans_all_candidate_rc
  test_uninstall_idempotent
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
