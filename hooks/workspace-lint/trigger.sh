#!/bin/bash
# workspace-lint trigger.sh
# Phase 1 骨架：路径过滤 + marker + 单 worker 锁 + nohup 脱离 hook + stub lint
# 调用方式：bash trigger.sh post-tool-use|session-start|--worker

set -u

# ============================================================
# 常量
# ============================================================
WORKSPACE_ROOT="${LIVE_APP_PATH:-/Users/augus/Desktop/dev-projects/live_app}"
LINT_DIR="${HOME}/Desktop/ai-project/hooks/workspace-lint"
STATE_DIR="${LINT_DIR}/state"
LOCK_DIR="${STATE_DIR}/worker.lockdir"
PENDING_FILE="${STATE_DIR}/pending.json"
FINGERPRINT_FILE="${STATE_DIR}/last-fingerprint"
LOG_FILE="${STATE_DIR}/lint.log"
STATUS_FILE="${HOME}/Desktop/ai-project/data/lint-status.json"
RUNNER="${LINT_DIR}/lint_runner.py"
BYPASS_FILE="${HOME}/.claude/.lint-bypass"

DEBOUNCE_SECONDS=90
STALE_LOCK_SECONDS=180  # debounce + max lint runtime + buffer
WORKER_POLL_SECONDS=5

mkdir -p "$STATE_DIR" 2>/dev/null
mkdir -p "$(dirname "$STATUS_FILE")" 2>/dev/null

# ============================================================
# 通用工具
# ============================================================
log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG_FILE" 2>/dev/null || true
}

now_unix() { date +%s; }

is_bypassed() { [ -f "$BYPASS_FILE" ]; }

# ============================================================
# 路径过滤：只看 workspace 内的 .claude/** 和 **/CLAUDE.md
# 输入参数：$1 = file_path（已转绝对路径）
# 退出码：0 = 命中 lint 范围；1 = 不命中
# ============================================================
# 路径相对化处理：相对路径补 WORKSPACE_ROOT 前缀
absolutize_path() {
  local p="${1:-}"
  case "$p" in
    /*) printf '%s' "$p" ;;
    "") printf '' ;;
    *)  printf '%s/%s' "$WORKSPACE_ROOT" "$p" ;;
  esac
}

is_target_path() {
  local fp="${1:-}"
  [ -z "$fp" ] && return 1
  # 命中范围：workspace 内的 .claude/** 或任意层级 CLAUDE.md（跟 fingerprint maxdepth 4 配套）
  case "$fp" in
    "$WORKSPACE_ROOT"/.claude/*) return 0 ;;
    "$WORKSPACE_ROOT"/CLAUDE.md) return 0 ;;
    "$WORKSPACE_ROOT"/*/CLAUDE.md) return 0 ;;
    "$WORKSPACE_ROOT"/*/*/CLAUDE.md) return 0 ;;
    "$WORKSPACE_ROOT"/*/*/*/CLAUDE.md) return 0 ;;
  esac
  return 1
}

# ============================================================
# 锁
# acquire_lock：mkdir 原子创建 lockdir。成功返回 0，失败返回 1。
# 失败时检查 stale lock（heartbeat 老于 STALE_LOCK_SECONDS 秒视为僵尸）。
# ============================================================
acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s' "$$" > "$LOCK_DIR/pid"
    printf '%s' "$(now_unix)" > "$LOCK_DIR/created_at"
    printf '%s' "$(now_unix)" > "$LOCK_DIR/heartbeat_at"
    return 0
  fi
  # lockdir 已存在 → 检查 stale
  local hb_at
  hb_at=$(cat "$LOCK_DIR/heartbeat_at" 2>/dev/null || echo 0)
  local age=$(( $(now_unix) - hb_at ))
  if [ "$age" -gt "$STALE_LOCK_SECONDS" ]; then
    log "stale_lock_detected age=${age}s removing"
    rm -rf "$LOCK_DIR" 2>/dev/null
    if mkdir "$LOCK_DIR" 2>/dev/null; then
      printf '%s' "$$" > "$LOCK_DIR/pid"
      printf '%s' "$(now_unix)" > "$LOCK_DIR/created_at"
      printf '%s' "$(now_unix)" > "$LOCK_DIR/heartbeat_at"
      return 0
    fi
  fi
  return 1
}

heartbeat() {
  printf '%s' "$(now_unix)" > "$LOCK_DIR/heartbeat_at" 2>/dev/null || true
}

release_lock() {
  rm -rf "$LOCK_DIR" 2>/dev/null || true
}

# ============================================================
# Pending marker
# ============================================================
write_pending() {
  local file_path="${1:-}"
  local trigger="${2:-post-tool-use}"
  local now_iso
  now_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local now_ts
  now_ts=$(now_unix)
  # change_token：进程间唯一标识，避免同秒多次更新被误判为同一次
  local token="${now_ts}-$$-${RANDOM}-${RANDOM}"
  # 原子写：先写 tmp 再 mv，避免极端并发半写
  local tmp="${PENDING_FILE}.tmp.$$"
  if jq -nc \
       --arg now_iso "$now_iso" \
       --arg now_ts "$now_ts" \
       --arg token "$token" \
       --arg fp "$file_path" \
       --arg trig "$trigger" \
       '{last_change_at_iso:$now_iso, last_change_at:($now_ts|tonumber), change_token:$token, trigger:$trig, last_path:$fp}' \
       > "$tmp" 2>/dev/null; then
    mv "$tmp" "$PENDING_FILE" 2>/dev/null || rm -f "$tmp" 2>/dev/null
  else
    rm -f "$tmp" 2>/dev/null || true
  fi
}

read_pending_unix() {
  jq -r '.last_change_at // 0' "$PENDING_FILE" 2>/dev/null || echo 0
}

read_pending_token() {
  jq -r '.change_token // ""' "$PENDING_FILE" 2>/dev/null || echo ""
}

clear_pending() {
  rm -f "$PENDING_FILE" 2>/dev/null || true
}

# ============================================================
# Fingerprint：对 .claude/ + CLAUDE.md 文件做结构 hash
# ============================================================
compute_fingerprint() {
  # 收集目标文件列表 → 每条输出 path|size|sha256 → 整体再 sha256
  {
    find "$WORKSPACE_ROOT/.claude" -type f \( -name '*.md' -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' \) 2>/dev/null
    find "$WORKSPACE_ROOT" -maxdepth 4 -type f -name 'CLAUDE.md' 2>/dev/null
  } | sort | while IFS= read -r f; do
    local sz
    sz=$(stat -f%z "$f" 2>/dev/null || echo 0)
    local hash
    hash=$(shasum -a 256 "$f" 2>/dev/null | awk '{print $1}')
    printf '%s|%s|%s\n' "$f" "$sz" "$hash"
  done | shasum -a 256 | awk '{print $1}'
}

# ============================================================
# 跑 lint runner，写状态文件
# ============================================================
run_lint_and_write_status() {
  local trigger="${1:-unknown}"
  local start_ts
  start_ts=$(now_unix)
  local fp
  fp=$(compute_fingerprint)
  local now_iso
  now_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # 启动 heartbeat watchdog：lint 跑期间周期更新 lockdir/heartbeat_at
  # 避免长 lint 被其它 hook 误判为 stale lock
  (
    while [ -d "$LOCK_DIR" ]; do
      printf '%s' "$(date +%s)" > "$LOCK_DIR/heartbeat_at" 2>/dev/null || break
      sleep 30
    done
  ) &
  local watchdog_pid=$!

  local runner_out
  local runner_exit=0
  if [ -x "$RUNNER" ] || [ -f "$RUNNER" ]; then
    runner_out=$(python3 "$RUNNER" 2>>"$LOG_FILE")
    runner_exit=$?
  else
    runner_out=""
    runner_exit=127
    log "runner_not_found path=$RUNNER"
  fi

  # 杀 watchdog（lockdir 还在但 lint 已经跑完，不需要继续 heartbeat）
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true

  local end_ts
  end_ts=$(now_unix)
  local duration=$(( (end_ts - start_ts) * 1000 ))

  if [ $runner_exit -eq 0 ] && [ -n "$runner_out" ]; then
    # runner OK：在 runner 输出基础上加元数据
    printf '%s\n' "$runner_out" | jq \
      --arg ts "$now_iso" \
      --arg trig "$trigger" \
      --arg fp "$fp" \
      --argjson dur "$duration" \
      --arg ws "$WORKSPACE_ROOT" \
      '. + {last_run:$ts, trigger:$trig, fingerprint:$fp, duration_ms:$dur, workspace:$ws, stale:false}' \
      > "$STATUS_FILE" 2>>"$LOG_FILE" || log "status_write_failed"
  else
    # runner 失败：写错误状态
    jq -n \
      --arg ts "$now_iso" \
      --arg trig "$trigger" \
      --arg fp "$fp" \
      --argjson dur "$duration" \
      --arg ws "$WORKSPACE_ROOT" \
      --arg msg "runner exit_code=$runner_exit" \
      --argjson ec "$runner_exit" \
      '{version:1, workspace:$ws, last_run:$ts, trigger:$trig, fingerprint:$fp, duration_ms:$dur, stale:false, summary:{total:0,passed:0,failed:0}, checks:[], error:{stage:"lint_runner",message:$msg,exit_code:$ec}}' \
      > "$STATUS_FILE" 2>>"$LOG_FILE" || log "status_write_failed_error_path"
  fi

  printf '%s' "$fp" > "$FINGERPRINT_FILE" 2>/dev/null || true
  log "lint_run trigger=$trigger duration_ms=$duration runner_exit=$runner_exit"
}

# ============================================================
# Worker 模式：脱离 hook 进程后跑 quiet-window 等待循环
# ============================================================
run_worker() {
  log "worker_start pid=$$"
  # worker 启动后用自己的 PID 覆盖 lockdir/pid（之前是父 hook 进程的 PID）
  printf '%s' "$$" > "$LOCK_DIR/pid" 2>/dev/null || true
  trap 'release_lock; exit 0' EXIT TERM INT HUP

  while true; do
    heartbeat

    if [ ! -f "$PENDING_FILE" ]; then
      log "worker_exit reason=no_pending"
      release_lock
      exit 0
    fi

    local last_change
    last_change=$(read_pending_unix)
    local now_ts
    now_ts=$(now_unix)
    local age=$(( now_ts - last_change ))

    if [ "$age" -lt "$DEBOUNCE_SECONDS" ]; then
      local remaining=$(( DEBOUNCE_SECONDS - age ))
      local sleep_for=$WORKER_POLL_SECONDS
      [ "$remaining" -lt "$sleep_for" ] && sleep_for="$remaining"
      sleep "$sleep_for"
      continue
    fi

    # quiet-window 达到，用 change_token（不是秒级 timestamp）做防并发标识
    local lint_for_token
    lint_for_token=$(read_pending_token)
    log "worker_run_lint pending_age=${age}s lint_for_token=$lint_for_token"
    run_lint_and_write_status "post-tool-use"
    heartbeat

    # 关键：lint 期间可能有新 PostToolUse 写入新 pending，比对 token（避免秒级冲突）
    if [ ! -f "$PENDING_FILE" ]; then
      release_lock
      exit 0
    fi
    local current_token
    current_token=$(read_pending_token)
    if [ "$current_token" = "$lint_for_token" ]; then
      # pending token 没变 → 是这次跑的，可清掉
      clear_pending
      release_lock
      exit 0
    fi
    # pending 被更新了 → 期间有新改动，回到 loop 继续等下一个 quiet-window
    log "worker_continue reason=pending_updated old_token=$lint_for_token new_token=$current_token"
  done
}

# ============================================================
# 主入口
# ============================================================
main() {
  if is_bypassed; then
    log "bypass_active skipping"
    exit 0
  fi

  local mode="${1:-}"

  case "$mode" in
    post-tool-use)
      local input
      input=$(cat 2>/dev/null || echo '{}')
      local raw_file_path
      raw_file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_response.filePath // empty' 2>/dev/null)
      local file_path
      file_path=$(absolutize_path "$raw_file_path")
      if ! is_target_path "$file_path"; then
        exit 0
      fi
      write_pending "$file_path" "post-tool-use"
      log "pending_written path=$file_path"
      if acquire_lock; then
        # 脱离 hook 进程 + redirect 防 stdout 进 session
        nohup bash "$0" --worker >/dev/null 2>&1 &
        disown 2>/dev/null || true
      fi
      exit 0
      ;;
    session-start)
      local current_fp
      current_fp=$(compute_fingerprint)
      local last_fp
      last_fp=$(cat "$FINGERPRINT_FILE" 2>/dev/null || echo "")
      if [ "$current_fp" = "$last_fp" ] && [ -n "$last_fp" ]; then
        log "session_start_no_change fp=${current_fp:0:12}"
        exit 0
      fi
      log "session_start_stale_detected"
      if acquire_lock; then
        # SessionStart 直接跑 lint（不防抖），跑完无条件释放锁
        # 期间若 PostToolUse 写了新 pending，留给下一次 PostToolUse 触发新 worker
        # （SessionStart 后立刻又改配置的概率低，下次 PostToolUse 几乎一定会来）
        clear_pending
        run_lint_and_write_status "session-start"
        release_lock
      fi
      exit 0
      ;;
    --worker)
      run_worker
      exit 0
      ;;
    *)
      log "unknown_mode mode=$mode"
      exit 0
      ;;
  esac
}

main "$@"
exit 0
