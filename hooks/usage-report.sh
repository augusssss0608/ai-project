#!/bin/bash
# Usage report: 从 SQLite (events.db) 聚合输出使用排行 + 装饰品候选
# v2: sqlite 为唯一真理源, jsonl 仅备份
# 用法:
#   usage-report.sh                # 默认 30 天 all
#   usage-report.sh 7              # 最近 7 天
#   usage-report.sh 30 skill       # 最近 30 天，只看 skill
#   类别: skill | clinerule | subagent | explicit | claude | agents | memory | all

DB_FILE="$HOME/.claude/usage-stats/events.db"
DAYS="${1:-30}"
KIND="${2:-all}"

# A7: DAYS 参数兜底校验，非法值回退 30
if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [ "$DAYS" -lt 1 ] || [ "$DAYS" -gt 3650 ]; then
  echo "warning: invalid DAYS '$DAYS', fallback to 30" >&2
  DAYS=30
fi

if [ ! -f "$DB_FILE" ]; then
  echo "暂无数据库: $DB_FILE" >&2
  exit 1
fi

# A4: PROJECT_ROOT / MEMORY_DIR 改读环境变量
PROJECT_ROOT="${LIVE_APP_PATH:-/Users/augus/Desktop/开发项目/live_app}"
MEMORY_DIR="${LIVE_APP_MEMORY_PATH:-$HOME/.claude/projects/-Users-augus-Desktop------live-app/memory}"

CUTOFF=$(date -u -v-"${DAYS}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
  || date -u -d "${DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)

# A2: 从 SQLite 聚合，不再读 jsonl
# B4: 显示 sessions_30d 和 paired_30d (read 类事件)
PAIRABLE_TYPES="skill_read clinerule_read claude_md_read agents_md_read memory_read"

is_pairable() {
  local t="$1"
  for x in $PAIRABLE_TYPES; do
    [ "$x" = "$t" ] && return 0
  done
  return 1
}

section() {
  local title="$1" type="$2"
  echo "=== $title (最近 ${DAYS} 天) ==="
  if is_pairable "$type"; then
    # 读类: 显示 count / sessions / paired
    # SB1 修复: 按 (name, scope) 分组，避免同名跨 scope 被合并
    # SB3 修复: paired 分母只计 session != '' 的，避免 over-count
    sqlite3 "$DB_FILE" <<SQL
SELECT printf('%4d  %-30s [%s]  %d 会话  %d/%d 配对',
  c.cnt, c.name, c.scope,
  COALESCE(s.sess, 0),
  COALESCE(p.paired, 0),
  COALESCE(c.pairable_total, 0))
FROM (
  SELECT name, COALESCE(scope,'') AS scope,
         COUNT(*) AS cnt,
         SUM(CASE WHEN session != '' THEN 1 ELSE 0 END) AS pairable_total
  FROM events
  WHERE type='$type' AND ts >= '$CUTOFF'
  GROUP BY name, COALESCE(scope,'')
) c
LEFT JOIN (
  SELECT name, COALESCE(scope,'') AS scope, COUNT(DISTINCT session) AS sess
  FROM events
  WHERE type='$type' AND ts >= '$CUTOFF' AND session != ''
  GROUP BY name, COALESCE(scope,'')
) s ON s.name = c.name AND s.scope = c.scope
LEFT JOIN (
  SELECT e1.name, COALESCE(e1.scope,'') AS scope, COUNT(*) AS paired
  FROM events e1
  WHERE e1.type='$type' AND e1.ts >= '$CUTOFF' AND e1.session != ''
    AND EXISTS (
      SELECT 1 FROM events e2
      WHERE e2.session = e1.session
        AND e2.type IN ('skill_explicit','subagent')
        AND datetime(e2.ts) BETWEEN datetime(e1.ts) AND datetime(e1.ts, '+5 minutes')
    )
  GROUP BY e1.name, COALESCE(e1.scope,'')
) p ON p.name = c.name AND p.scope = c.scope
ORDER BY c.cnt DESC;
SQL
  else
    # SB1: 非读类也按 (name, scope) 分组
    sqlite3 "$DB_FILE" "SELECT printf('%4d  %-30s [%s]', COUNT(*), name, COALESCE(scope,'')) FROM events WHERE type='$type' AND ts >= '$CUTOFF' GROUP BY name, COALESCE(scope,'') ORDER BY COUNT(*) DESC;"
  fi
  echo
}

case "$KIND" in
  skill)     section "Skill 读取"        skill_read ;;
  clinerule) section ".clinerules 读取"   clinerule_read ;;
  subagent)  section "Subagent 派发"      subagent ;;
  explicit)  section "显式 Skill 调用"    skill_explicit ;;
  claude)    section "CLAUDE.md 读取"     claude_md_read ;;
  agents)    section "AGENTS.md 读取"     agents_md_read ;;
  memory)    section "memory 读取"        memory_read ;;
  all)
    section "Skill 读取"        skill_read
    section "显式 Skill 调用"    skill_explicit
    section "Subagent 派发"      subagent
    section ".clinerules 读取"   clinerule_read
    section "CLAUDE.md 读取"     claude_md_read
    section "AGENTS.md 读取"     agents_md_read
    section "memory 读取"        memory_read

    echo "=== 未触发 Skill (最近 ${DAYS} 天内 0 次) ==="
    # Bug #1 修复：按 name|scope 联合去重，避免 user/project 同名 skill 互相掩盖
    used_skills=$(sqlite3 "$DB_FILE" "SELECT name || '|' || COALESCE(scope,'') FROM events WHERE type='skill_read' AND ts >= '$CUTOFF';" | sort -u)
    for d in "$HOME/.claude/skills" "$PROJECT_ROOT/.claude/skills"; do
      [ -d "$d" ] || continue
      # SB6 修复: 与 tracker.sh 一致，按 PROJECT_ROOT 精确前缀判定 scope
      scope="user"; [[ "$d" == "$PROJECT_ROOT/"* ]] && scope="project"
      for sk in "$d"/*/SKILL.md; do
        [ -f "$sk" ] || continue
        name=$(basename "$(dirname "$sk")")
        if ! grep -qx "$name|$scope" <<<"$used_skills"; then
          printf '   0 %s  [%s]\n' "$name" "$scope"
        fi
      done
    done
    echo

    echo "=== 未触发 Subagent (最近 ${DAYS} 天内 0 次) ==="
    # A1: 同名 subagent 时 project 优先，user 隐藏（Claude Code 解析时 project 覆盖 user）
    used_agents=$(sqlite3 "$DB_FILE" "SELECT name FROM events WHERE type='subagent' AND ts >= '$CUTOFF';" | sort -u)
    project_agent_names=""
    if [ -d "$PROJECT_ROOT/.claude/agents" ]; then
      for f in "$PROJECT_ROOT/.claude/agents"/*.md; do
        [ -f "$f" ] || continue
        project_agent_names+="$(basename "$f" .md)"$'\n'
      done
    fi
    overridden_users=""
    for d in "$HOME/.claude/agents" "$PROJECT_ROOT/.claude/agents"; do
      [ -d "$d" ] || continue
      # SB6 修复: 与 tracker.sh 一致，按 PROJECT_ROOT 精确前缀判定 scope
      scope="user"; [[ "$d" == "$PROJECT_ROOT/"* ]] && scope="project"
      for f in "$d"/*.md; do
        [ -f "$f" ] || continue
        name=$(basename "$f" .md)
        # user 同名时被 project 覆盖，跳过 + 记录到 overridden 列表
        if [ "$scope" = "user" ] && grep -qx "$name" <<<"$project_agent_names"; then
          overridden_users+="$name "
          continue
        fi
        if ! grep -qx "$name" <<<"$used_agents"; then
          printf '   0 %s  [%s]\n' "$name" "$scope"
        fi
      done
    done
    # B5: 显示被覆盖的 user 版本提示
    if [ -n "$overridden_users" ]; then
      echo "  ⓘ 同名 user 版本被 project 覆盖（已隐藏未计入）: $overridden_users"
    fi
    echo

    echo "=== 未触发 .clinerules (最近 ${DAYS} 天内 0 次) ==="
    used_rules=$(sqlite3 "$DB_FILE" "SELECT name FROM events WHERE type='clinerule_read' AND ts >= '$CUTOFF';" | sort -u)
    if [ -d "$PROJECT_ROOT/.clinerules" ]; then
      while IFS= read -r f; do
        rel=${f#"$PROJECT_ROOT/.clinerules/"}
        if ! grep -qx "$rel" <<<"$used_rules"; then
          printf '   0 %s\n' "$rel"
        fi
      done < <(find "$PROJECT_ROOT/.clinerules" -type f -name '*.md')
    fi
    echo

    echo "=== 未触发 CLAUDE.md (最近 ${DAYS} 天内 0 次) ==="
    used_claude=$(sqlite3 "$DB_FILE" "SELECT name FROM events WHERE type='claude_md_read' AND ts >= '$CUTOFF';" | sort -u)
    check_claude() {
      local path="$1" name="$2" scope="$3"
      [ -f "$path" ] || return
      if ! grep -qx "$name" <<<"$used_claude"; then
        printf '   0 %s  [%s]\n' "$name" "$scope"
      fi
    }
    check_claude "$HOME/.claude/CLAUDE.md" "global" "global"
    check_claude "$PROJECT_ROOT/CLAUDE.md" "root" "project"
    while IFS= read -r f; do
      rel=${f#"$PROJECT_ROOT/"}
      sub=${rel%/CLAUDE.md}
      check_claude "$f" "$sub" "subproject"
    done < <(find "$PROJECT_ROOT" -mindepth 2 -maxdepth 4 -name CLAUDE.md \
              -not -path "*/node_modules/*" -not -path "*/build/*" \
              -not -path "*/.dart_tool/*" -not -path "*/.git/*" 2>/dev/null)
    echo

    echo "=== 未触发 memory (最近 ${DAYS} 天内 0 次) ==="
    used_mem=$(sqlite3 "$DB_FILE" "SELECT name FROM events WHERE type='memory_read' AND ts >= '$CUTOFF';" | sort -u)
    if [ -d "$MEMORY_DIR" ]; then
      for f in "$MEMORY_DIR"/*.md; do
        [ -f "$f" ] || continue
        name=$(basename "$f" .md)
        if ! grep -qx "$name" <<<"$used_mem"; then
          printf '   0 %s\n' "$name"
        fi
      done
    fi
    ;;
  *)
    echo "未知类别: $KIND (可选: skill | clinerule | subagent | explicit | claude | agents | memory | all)" >&2
    exit 2
    ;;
esac
