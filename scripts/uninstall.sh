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
