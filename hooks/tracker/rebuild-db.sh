#!/bin/bash
# Usage rebuild: 灾备工具 — 从 events.jsonl 重建 events.db
#
# ⚠️ 警告 ⚠️
# sqlite 才是统计真理源，jsonl 只是备份。
# 本工具会用 jsonl 覆盖重建 sqlite，**会丢失只存在于 sqlite 中的事件**
# （比如某次 jsonl 写失败但 sqlite 写成功的情况）。
# 仅在 sqlite 损坏 / 误删 / 表结构破坏等灾难场景下使用。
# 平时不要跑。
#
# 用法:
#   usage-rebuild-db.sh           # 干跑：只对比 jsonl/sqlite 差异，不动数据
#   usage-rebuild-db.sh --apply   # 实际重建（备份旧 db）

set -e

LOG_DIR="$HOME/Desktop/ai-project/data"
JSONL="$LOG_DIR/events.jsonl"
DB="$LOG_DIR/events.db"
APPLY=0

if [ "$1" = "--apply" ]; then
  APPLY=1
fi

if [ ! -f "$JSONL" ]; then
  echo "暂无 jsonl: $JSONL" >&2
  exit 1
fi

JCOUNT=$(wc -l < "$JSONL" | tr -d ' ')
SCOUNT=0
if [ -f "$DB" ]; then
  SCOUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo 0)
fi

echo "当前状态:"
echo "  jsonl 事件数: $JCOUNT"
echo "  sqlite 事件数: $SCOUNT"
DIFF=$((JCOUNT - SCOUNT))
echo "  差异 (jsonl - sqlite): $DIFF"
echo
if [ "$DIFF" -lt 0 ]; then
  echo "⚠️  警告: sqlite 比 jsonl 多 $((-DIFF)) 条事件。"
  echo "   这通常意味着存在 sqlite-only 事件（jsonl 写失败但 sqlite 写成功的情况）。"
  echo "   重建后这些事件会丢失。"
  echo
fi

if [ "$APPLY" -eq 0 ]; then
  echo "干跑模式（未实际执行）。要重建请运行: $0 --apply"
  exit 0
fi

# --apply 前的二次确认
echo "⚠️  即将用 jsonl 覆盖重建 sqlite。这是灾备操作。"
if [ "$DIFF" -lt 0 ]; then
  echo "   你将丢失 $((-DIFF)) 条 sqlite-only 事件（无法从 jsonl 恢复）。"
fi
echo -n "确认继续？(输入 yes 继续，其他任意键取消): "
read -r CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "已取消。"
  exit 0
fi

# 备份旧 db
if [ -f "$DB" ]; then
  BAK="$DB.bak.$(date +%s)"
  cp "$DB" "$BAK"
  echo "已备份旧 db: $BAK"
fi

# 重建 schema
rm -f "$DB"
sqlite3 "$DB" <<'SQL'
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT,
  scope TEXT,
  path TEXT,
  description TEXT,
  session TEXT
);
CREATE INDEX idx_ts ON events(ts);
CREATE INDEX idx_type_name ON events(type, name);
CREATE INDEX idx_session ON events(session);
SQL

# 从 jsonl 灌入 db
INSERTED=0
FAILED=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  ts=$(printf '%s' "$line" | jq -r '.ts // ""')
  etype=$(printf '%s' "$line" | jq -r '.type // ""')
  ename=$(printf '%s' "$line" | jq -r '.name // ""')
  escope=$(printf '%s' "$line" | jq -r '.scope // ""')
  epath=$(printf '%s' "$line" | jq -r '.path // ""')
  edesc=$(printf '%s' "$line" | jq -r '.description // ""')
  esession=$(printf '%s' "$line" | jq -r '.session // ""')
  # SQL 字符串转义
  esc() { printf "%s" "$1" | sed "s/'/''/g"; }
  if sqlite3 "$DB" "INSERT INTO events(ts,type,name,scope,path,description,session) VALUES('$(esc "$ts")','$(esc "$etype")','$(esc "$ename")','$(esc "$escope")','$(esc "$epath")','$(esc "$edesc")','$(esc "$esession")');" 2>/dev/null; then
    INSERTED=$((INSERTED + 1))
  else
    FAILED=$((FAILED + 1))
  fi
done < "$JSONL"

NEW_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM events;")
echo
echo "重建完成:"
echo "  插入: $INSERTED"
echo "  失败: $FAILED"
echo "  最终 sqlite 事件数: $NEW_COUNT"
