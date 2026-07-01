#!/bin/bash
# 每日自动推送脚本 — 将最新抓取结果发布到 GitHub Pages
# 由 Cowork 定时任务调用，无需手动操作

REPO="/Users/caijiakun/Desktop/hot pics/westie-daily"
cd "$REPO" || exit 1

# 检查是否有变更
if git diff --quiet && git diff --staged --quiet; then
  echo "ℹ️  今日无新内容，跳过推送"
  exit 0
fi

git add .
git commit -m "Daily update $(date '+%Y-%m-%d')"
git push

echo "✅ 已推送到 GitHub Pages"
