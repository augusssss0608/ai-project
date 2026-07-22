#!/bin/bash
# Usage tracker: 记录 skill SKILL.md / .clinerules 文件 Read、subagent 派发、显式 Skill 调用
# 挂在 PostToolUse 上，写入 events.db (SQLite 单一真理源)

LOG_DIR="$HOME/Desktop/ai-project/data"
DB_FILE="$LOG_DIR/events.db"
ERR_FILE="$LOG_DIR/tracker-errors.log"
# SB2: scope 路径检测改用精确前缀，避免任何含 'live_app' 子串的路径被误判为 project
PROJECT_ROOT="${LIVE_APP_PATH:-/Users/augus/Desktop/dev-projects/live_app}"
mkdir -p "$LOG_DIR"

# Bug #3 修复：每次都跑 CREATE TABLE IF NOT EXISTS，文件存在但表丢了也能补建
# A5 修复：schema 初始化失败也写错误日志，不再静默吞掉
INIT_ERR=$(sqlite3 "$DB_FILE" <<'SQL' 2>&1
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT,
  scope TEXT,
  path TEXT,
  description TEXT,
  session TEXT
);
CREATE INDEX IF NOT EXISTS idx_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_type_name ON events(type, name);
CREATE INDEX IF NOT EXISTS idx_session ON events(session);
SQL
)
if [ -n "$INIT_ERR" ]; then
  printf '[%s] schema_init_failed err=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$INIT_ERR" >> "$ERR_FILE"
fi

INPUT=$(cat)
if [ -z "$INPUT" ]; then
  exit 0
fi

TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')
HOOK_EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty')
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')

# SQL 字符串转义：单引号变双单引号
sql_escape() {
  printf "%s" "$1" | sed "s/'/''/g"
}

emit() {
  # $1 = JSON line, 直接写入 SQLite
  local etype ename escope epath edesc sql_err
  etype=$(printf '%s' "$1" | jq -r '.type // ""')
  ename=$(printf '%s' "$1" | jq -r '.name // ""')
  escope=$(printf '%s' "$1" | jq -r '.scope // ""')
  epath=$(printf '%s' "$1" | jq -r '.path // ""')
  edesc=$(printf '%s' "$1" | jq -r '.description // ""')
  # Bug #2 修复：sqlite 写失败不再静默吞掉，错误写入 tracker-errors.log
  sql_err=$(sqlite3 "$DB_FILE" "INSERT INTO events(ts,type,name,scope,path,description,session) VALUES('$TS','$(sql_escape "$etype")','$(sql_escape "$ename")','$(sql_escape "$escope")','$(sql_escape "$epath")','$(sql_escape "$edesc")','$(sql_escape "$SESSION")');" 2>&1)
  if [ -n "$sql_err" ]; then
    printf '[%s] sqlite_insert_failed type=%s name=%s err=%s\n' "$TS" "$etype" "$ename" "$sql_err" >> "$ERR_FILE"
  fi
}

case "$TOOL_NAME" in
  Read)
    FP=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
    case "$FP" in
      */skills/*/SKILL.md)
        NAME=$(printf '%s' "$FP" | sed -E 's|.*/skills/([^/]+)/SKILL\.md|\1|')
        SCOPE="user"
        # SB2: 精确前缀匹配 PROJECT_ROOT，不再用模糊 */live_app/*
        if [[ "$FP" == "$PROJECT_ROOT/"* ]]; then
          SCOPE="project"
        elif [[ "$FP" == */plugins/* ]]; then
          SCOPE="plugin"
        fi
        emit "$(jq -nc \
          --arg ts "$TS" --arg name "$NAME" --arg scope "$SCOPE" \
          --arg path "$FP" --arg sid "$SESSION" \
          '{ts:$ts,type:"skill_read",name:$name,scope:$scope,path:$path,session:$sid}')"
        ;;
      */\.claude/docs/*)
        REL=$(printf '%s' "$FP" | sed -E 's|.*\.claude/docs/||')
        emit "$(jq -nc \
          --arg ts "$TS" --arg rel "$REL" --arg path "$FP" --arg sid "$SESSION" \
          '{ts:$ts,type:"clinerule_read",name:$rel,scope:"project",path:$path,session:$sid}')"
        ;;
      */CLAUDE.md)
        # SB2: 精确前缀匹配 PROJECT_ROOT
        SCOPE="other"
        NAME="$FP"
        if [ "$FP" = "$HOME/.claude/CLAUDE.md" ]; then
          SCOPE="global"; NAME="global"
        elif [ "$FP" = "$PROJECT_ROOT/CLAUDE.md" ]; then
          SCOPE="project"; NAME="root"
        elif [[ "$FP" == "$PROJECT_ROOT/"*"/CLAUDE.md" ]]; then
          SCOPE="subproject"
          NAME="${FP#$PROJECT_ROOT/}"
          NAME="${NAME%/CLAUDE.md}"
        fi
        emit "$(jq -nc \
          --arg ts "$TS" --arg name "$NAME" --arg scope "$SCOPE" \
          --arg path "$FP" --arg sid "$SESSION" \
          '{ts:$ts,type:"claude_md_read",name:$name,scope:$scope,path:$path,session:$sid}')"
        ;;
      */AGENTS.md)
        # SB2: 精确前缀匹配 PROJECT_ROOT
        AG_SCOPE="other"
        AG_NAME="$FP"
        if [ "$FP" = "$HOME/.claude/AGENTS.md" ]; then
          AG_SCOPE="global"; AG_NAME="global"
        elif [ "$FP" = "$PROJECT_ROOT/AGENTS.md" ]; then
          AG_SCOPE="project"; AG_NAME="root"
        elif [[ "$FP" == "$PROJECT_ROOT/"*"/AGENTS.md" ]]; then
          AG_SCOPE="subproject"
          AG_NAME="${FP#$PROJECT_ROOT/}"
          AG_NAME="${AG_NAME%/AGENTS.md}"
        fi
        emit "$(jq -nc \
          --arg ts "$TS" --arg name "$AG_NAME" --arg scope "$AG_SCOPE" \
          --arg path "$FP" --arg sid "$SESSION" \
          '{ts:$ts,type:"agents_md_read",name:$name,scope:$scope,path:$path,session:$sid}')"
        ;;
      */memory/*.md|*/auto-memory/*.md)
        NAME=$(basename "$FP" .md)
        emit "$(jq -nc \
          --arg ts "$TS" --arg name "$NAME" --arg path "$FP" --arg sid "$SESSION" \
          '{ts:$ts,type:"memory_read",name:$name,scope:"auto",path:$path,session:$sid}')"
        ;;
    esac
    ;;
  Agent|Task)
    AGENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.subagent_type // "general-purpose"')
    DESC=$(printf '%s' "$INPUT" | jq -r '.tool_input.description // empty')
    emit "$(jq -nc \
      --arg ts "$TS" --arg name "$AGENT" --arg desc "$DESC" --arg sid "$SESSION" \
      '{ts:$ts,type:"subagent",name:$name,description:$desc,session:$sid}')"
    ;;
  Skill)
    SK=$(printf '%s' "$INPUT" | jq -r '.tool_input.skill // empty')
    emit "$(jq -nc \
      --arg ts "$TS" --arg name "$SK" --arg sid "$SESSION" \
      '{ts:$ts,type:"skill_explicit",name:$name,session:$sid}')"
    ;;
esac

# UserPromptSubmit hook：记录每个 prompt 前 200 字（路由 tab 显示用）
# Hook 输入 JSON 字段：hook_event_name=UserPromptSubmit / prompt
if [ "$HOOK_EVENT" = "UserPromptSubmit" ]; then
  PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // .user_prompt // empty')
  if [ -n "$PROMPT" ]; then
    # 截前 200 字（按 unicode 字符不是字节）
    PROMPT_TRUNC=$(printf '%s' "$PROMPT" | awk '{
      n=length($0)
      if (n <= 200) print $0
      else print substr($0, 1, 200) "…"
    }')
    emit "$(jq -nc \
      --arg ts "$TS" --arg name "$PROMPT_TRUNC" --arg sid "$SESSION" \
      '{ts:$ts,type:"user_prompt",name:$name,session:$sid}')"
  fi
fi

exit 0
