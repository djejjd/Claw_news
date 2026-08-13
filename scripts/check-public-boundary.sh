#!/usr/bin/env bash
set -euo pipefail

tracked_files=$(git ls-files)

failures=()

while IFS= read -r path; do
  case "$path" in
    .env.example)
      ;;
    .env|.env.*|config.yaml|feeds.yaml|data/*|deploy.sh|.superpowers/*|.github/private/*|docs/temp/*)
      failures+=("禁止跟踪的私有或运行时文件: $path")
      ;;
  esac
done <<< "$tracked_files"

if rg -n --glob '*.md' --glob '*.yml' --glob '*.yaml' --glob '*.sh' \
  --glob '!scripts/check-public-boundary.sh' \
  '(/home/ubuntu|/Users/lanser/)' docs README.md .github scripts 2>/dev/null; then
  failures+=("文档或脚本包含机器绝对路径")
fi

if rg -n --glob '*.md' --glob '*.yml' --glob '*.yaml' --glob '*.sh' \
  --glob '!scripts/check-public-boundary.sh' \
  'https?://[^[:space:]"'"'"']+\?key=[A-Za-z0-9_-]{16,}' docs README.md .github scripts 2>/dev/null; then
  failures+=("文档或脚本包含疑似真实 webhook")
fi

if ((${#failures[@]} > 0)); then
  printf '%s\n' "公开边界检查失败："
  printf ' - %s\n' "${failures[@]}"
  exit 1
fi

echo "公开边界检查通过"
