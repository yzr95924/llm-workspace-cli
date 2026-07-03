#!/usr/bin/env bash
# scripts/uninstall.sh — install.sh 的逆操作：删 wrapper + 清 PATH marker 块 + 删 completion
set -euo pipefail

usage() {
  cat <<'USG'
usage: ./scripts/uninstall.sh
  删除 ~/.local/bin/llmw、已装的 shell completion（bash/fish/zsh），
  并从所有候选 shell rc 移除 llmw marker 块（PATH + completion fpath）。
  不删仓库、不删 workspace 数据。
USG
}

# marker 对：(start, end)；awk 按字符串整行匹配
declare -a MARKERS=(
  '# >>> llmw (managed by install.sh) >>>|# <<< llmw <<<'
  '# >>> llmw completion (managed by install.sh) >>>|# <<< llmw completion <<<'
  '# >>> llmw (bash-completion loader, managed by install.sh) >>>|# <<< llmw bash-completion loader <<<'
)

# 从单个文件按某组 marker 整段删除（含边界行），块外内容不动；用 awk，不用 sed -i
strip_marker() {
  local f="$1" start="$2" end="$3"
  [ -f "$f" ] || return 0
  local tmp; tmp="$(mktemp)"
  awk -v s="$start" -v e="$end" '
    $0==s {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$f" > "$tmp"
  mv "$tmp" "$f"
}

# 删 wrapper
rm -f "$HOME/.local/bin/llmw"

# 删 completion 文件（XDG-aware bash 路径）
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions/llmw"
rm -f "$HOME/.config/fish/completions/llmw.fish"
rm -f "$HOME/.local/share/zsh/site-functions/_llmw"

# 从所有候选 shell rc 移除两类 marker 块
for f in \
  "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile" \
  "$HOME/.profile" "$HOME/.config/fish/config.fish"; do
  for pair in "${MARKERS[@]}"; do
    start="${pair%%|*}"
    end="${pair#*|}"
    strip_marker "$f" "$start" "$end"
  done
done

echo "已卸载 llmw（wrapper + completion 已删除，rc marker 块已清理）。"