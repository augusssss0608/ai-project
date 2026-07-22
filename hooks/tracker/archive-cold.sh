#!/bin/bash
# 冷藏禁用工具: 把 N 天 0 触发的 skill / subagent 移动到 .disabled/ 目录
# 目的: 降低每次 Claude Code session 的 baseline token 消耗
#
# 用法:
#   usage-archive-cold.sh                # 干跑, 列出候选 (默认 30 天)
#   usage-archive-cold.sh --days 60      # 改变阈值
#   usage-archive-cold.sh --apply        # 实际移动到 .disabled/
#   usage-archive-cold.sh --restore NAME # 从 .disabled/ 恢复指定对象
#   usage-archive-cold.sh --list         # 列出已禁用的对象
#
# 可逆: 所有移动都记录到 archive-log.jsonl, 可以 --restore 恢复

set -e

LOG_DIR="$HOME/Desktop/ai-project/data"
DB="$LOG_DIR/events.db"
ARCHIVE_LOG="$LOG_DIR/archive-log.jsonl"
USER_SKILLS_DIR="$HOME/.claude/skills"
USER_AGENTS_DIR="$HOME/.claude/agents"
PROJECT_ROOT="${LIVE_APP_PATH:-/Users/augus/Desktop/dev-projects/live_app}"
PROJECT_SKILLS_DIR="$PROJECT_ROOT/.claude/skills"
PROJECT_AGENTS_DIR="$PROJECT_ROOT/.claude/agents"

# 白名单: 这些对象无论多久没触发都不禁用 (核心工作流依赖)
WHITELIST=(
  "using-superpowers"
  "brainstorming"
  "writing-plans"
  "executing-plans"
  "verification-before-completion"
  "requesting-code-review"
  "receiving-code-review"
  "systematic-debugging"
  "test-driven-development"
)

# 参数解析
DAYS=30
MODE="dryrun"
RESTORE_NAME=""

while [ $# -gt 0 ]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --apply) MODE="apply"; shift ;;
    --restore) MODE="restore"; RESTORE_NAME="$2"; shift 2 ;;
    --list) MODE="list"; shift ;;
    --help|-h)
      head -20 "$0" | tail -15
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$DB" ]; then
  echo "暂无 events.db: $DB" >&2
  exit 1
fi

is_whitelisted() {
  local name="$1"
  for w in "${WHITELIST[@]}"; do
    [ "$w" = "$name" ] && return 0
  done
  return 1
}

log_action() {
  # 记录到 archive-log.jsonl
  local ts action type name src dst
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  action="$1"; type="$2"; name="$3"; src="$4"; dst="$5"
  printf '{"ts":"%s","action":"%s","type":"%s","name":"%s","src":"%s","dst":"%s"}\n' \
    "$ts" "$action" "$type" "$name" "$src" "$dst" >> "$ARCHIVE_LOG"
}

# ========== list 模式 ==========
if [ "$MODE" = "list" ]; then
  echo "=== 已禁用对象 ==="
  for d in "$USER_SKILLS_DIR/.disabled" "$PROJECT_SKILLS_DIR/.disabled" \
           "$USER_AGENTS_DIR/.disabled" "$PROJECT_AGENTS_DIR/.disabled"; do
    if [ -d "$d" ]; then
      count=$(ls -A "$d" 2>/dev/null | wc -l | tr -d ' ')
      if [ "$count" -gt 0 ]; then
        echo
        echo "$d ($count 项):"
        ls -A "$d" | sed 's|^|  |'
      fi
    fi
  done
  exit 0
fi

# ========== restore 模式 ==========
if [ "$MODE" = "restore" ]; then
  if [ -z "$RESTORE_NAME" ]; then
    echo "用法: $0 --restore <name>" >&2
    exit 2
  fi
  found=0
  for d in "$USER_SKILLS_DIR" "$PROJECT_SKILLS_DIR"; do
    disabled="$d/.disabled/$RESTORE_NAME"
    if [ -d "$disabled" ]; then
      mv "$disabled" "$d/$RESTORE_NAME"
      echo "✓ skill 已恢复: $d/$RESTORE_NAME"
      log_action "restore" "skill" "$RESTORE_NAME" "$disabled" "$d/$RESTORE_NAME"
      found=1
    fi
  done
  for d in "$USER_AGENTS_DIR" "$PROJECT_AGENTS_DIR"; do
    disabled="$d/.disabled/$RESTORE_NAME.md"
    if [ -f "$disabled" ]; then
      mv "$disabled" "$d/$RESTORE_NAME.md"
      echo "✓ subagent 已恢复: $d/$RESTORE_NAME.md"
      log_action "restore" "subagent" "$RESTORE_NAME" "$disabled" "$d/$RESTORE_NAME.md"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo "未找到已禁用的 '$RESTORE_NAME'" >&2
    exit 1
  fi
  exit 0
fi

# ========== dryrun / apply 模式 ==========
CUTOFF=$(date -u -v-"${DAYS}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d "${DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)

echo "=== 冷藏候选 (阈值: ${DAYS} 天) ==="
echo "模式: $MODE"
echo

# 获取触发过的 skill 名字 (按 name|scope 联合)
used_skills=$(sqlite3 "$DB" \
  "SELECT DISTINCT name || '|' || COALESCE(scope,'') FROM events WHERE type='skill_read' AND ts >= '$CUTOFF';")
used_skills_explicit=$(sqlite3 "$DB" \
  "SELECT DISTINCT name FROM events WHERE type='skill_explicit' AND ts >= '$CUTOFF';")
used_subagents=$(sqlite3 "$DB" \
  "SELECT DISTINCT name FROM events WHERE type='subagent' AND ts >= '$CUTOFF';")

archive_skill_count=0
archive_agent_count=0

# --- 处理 skills ---
echo "--- Skills ---"
for scope_dir_pair in "user:$USER_SKILLS_DIR" "project:$PROJECT_SKILLS_DIR"; do
  scope="${scope_dir_pair%%:*}"
  dir="${scope_dir_pair#*:}"
  [ -d "$dir" ] || continue
  for sk in "$dir"/*/SKILL.md; do
    [ -f "$sk" ] || continue
    name=$(basename "$(dirname "$sk")")
    # 白名单跳过
    if is_whitelisted "$name"; then continue; fi
    # 触发检测: read 或 explicit 都没触发才算冷
    key="$name|$scope"
    if grep -qFx "$key" <<<"$used_skills"; then continue; fi
    if grep -qFx "$name" <<<"$used_skills_explicit"; then continue; fi
    # 这是冷藏候选
    parent=$(dirname "$sk")
    disabled_dir="$dir/.disabled"
    target="$disabled_dir/$name"
    printf '  [%s] %s\n' "$scope" "$name"
    archive_skill_count=$((archive_skill_count + 1))
    if [ "$MODE" = "apply" ]; then
      mkdir -p "$disabled_dir"
      mv "$parent" "$target"
      log_action "archive" "skill" "$name" "$parent" "$target"
    fi
  done
done

echo
echo "--- Subagents ---"
for scope_dir_pair in "user:$USER_AGENTS_DIR" "project:$PROJECT_AGENTS_DIR"; do
  scope="${scope_dir_pair%%:*}"
  dir="${scope_dir_pair#*:}"
  [ -d "$dir" ] || continue
  for f in "$dir"/*.md; do
    [ -f "$f" ] || continue
    name=$(basename "$f" .md)
    if is_whitelisted "$name"; then continue; fi
    if grep -qFx "$name" <<<"$used_subagents"; then continue; fi
    disabled_dir="$dir/.disabled"
    target="$disabled_dir/$name.md"
    printf '  [%s] %s\n' "$scope" "$name"
    archive_agent_count=$((archive_agent_count + 1))
    if [ "$MODE" = "apply" ]; then
      mkdir -p "$disabled_dir"
      mv "$f" "$target"
      log_action "archive" "subagent" "$name" "$f" "$target"
    fi
  done
done

echo
echo "=== 统计 ==="
echo "skill 候选数: $archive_skill_count"
echo "subagent 候选数: $archive_agent_count"
if [ "$MODE" = "dryrun" ]; then
  echo
  echo "这是干跑。要实际禁用请加 --apply"
  echo "禁用后可用 --restore NAME 恢复单个, --list 查看已禁用"
else
  echo
  echo "✓ 已全部移动到 .disabled/ 目录"
  echo "  恢复: $0 --restore <name>"
  echo "  查看: $0 --list"
fi
