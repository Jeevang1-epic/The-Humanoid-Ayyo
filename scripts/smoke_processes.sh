#!/usr/bin/env bash

# Exact process ownership and bounded teardown for Ayyo smoke scripts.
# This file is sourced; it does not start or kill anything on its own.

readonly ayyo_smoke_script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ayyo_smoke_session_launcher="$ayyo_smoke_script_root/smoke_session.py"

launch_pid="${launch_pid:-}"
launch_session_id="${launch_session_id:-}"
launch_run_id="${launch_run_id:-}"
ayyo_smoke_shutdown_escalated=0

ayyo_smoke_owned_pids() {
  local environment pid state
  [[ -n "$launch_run_id" ]] || return 0
  for environment in /proc/[0-9]*/environ; do
    [[ -r "$environment" ]] || continue
    if ! grep -z -Fqx "AYYO_SMOKE_RUN_ID=$launch_run_id" "$environment" \
      2>/dev/null; then
      continue
    fi
    pid="${environment#/proc/}"
    pid="${pid%/environ}"
    state="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
    [[ -n "$state" && "$state" != Z* ]] && printf '%s\n' "$pid"
  done
}

ayyo_smoke_owned_processes() {
  local pid
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    ps -o pid=,ppid=,sid=,pgid=,stat=,comm=,args= -p "$pid" \
      2>/dev/null || true
  done < <(ayyo_smoke_owned_pids)
}

ayyo_smoke_wait_owned_exit() {
  local attempts="${1:-${AYYO_SMOKE_SHUTDOWN_ATTEMPTS:-100}}"
  local delay="${2:-${AYYO_SMOKE_SHUTDOWN_DELAY_SECONDS:-0.1}}"
  local attempt
  for ((attempt = 0; attempt < attempts; attempt++)); do
    if [[ -z "$(ayyo_smoke_owned_pids)" ]]; then
      if [[ -n "$launch_pid" ]]; then
        wait "$launch_pid" 2>/dev/null || true
      fi
      launch_pid=""
      launch_session_id=""
      launch_run_id=""
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

ayyo_smoke_signal_owned() {
  local signal="$1"
  local -a pids=()
  mapfile -t pids < <(ayyo_smoke_owned_pids)
  if [[ "${#pids[@]}" -gt 0 ]]; then
    kill "-$signal" "${pids[@]}" 2>/dev/null || true
  fi
}

ayyo_smoke_start_owned_launch() {
  local log_path="$1"
  shift
  if [[ -n "$launch_pid" || -n "$launch_run_id" ]]; then
    printf 'FAIL: an owned smoke launch is already registered\n' >&2
    return 1
  fi
  launch_run_id="ayyo-smoke.$$.${RANDOM}.${RANDOM}"
  env AYYO_SMOKE_RUN_ID="$launch_run_id" \
    python3 "$ayyo_smoke_session_launcher" "$@" >"$log_path" 2>&1 &
  launch_pid=$!
  for _ in {1..20}; do
    launch_session_id="$(ps -o sid= -p "$launch_pid" 2>/dev/null | tr -d ' ')"
    [[ "$launch_session_id" == "$launch_pid" ]] && break
    sleep 0.05
  done
  if [[ "$launch_session_id" != "$launch_pid" ]]; then
    printf 'FAIL: smoke launch did not establish a dedicated process session\n' >&2
    ayyo_smoke_signal_owned TERM
    ayyo_smoke_wait_owned_exit 20 0.05 || true
    return 1
  fi
}

ayyo_smoke_shutdown_owned_launch() {
  local -a remaining=()
  local failed_run_id=""
  ayyo_smoke_shutdown_escalated=0
  [[ -n "$launch_run_id" ]] || return 0

  if [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill -INT "$launch_pid" 2>/dev/null || true
  else
    ayyo_smoke_signal_owned INT
  fi
  if ayyo_smoke_wait_owned_exit; then
    return 0
  fi

  ayyo_smoke_shutdown_escalated=1
  printf 'WARN: graceful launch shutdown left these owned processes:\n' >&2
  ayyo_smoke_owned_processes >&2
  ayyo_smoke_signal_owned TERM
  if ayyo_smoke_wait_owned_exit; then
    return 0
  fi

  printf 'FAIL: owned smoke processes survived bounded SIGINT and SIGTERM:\n' >&2
  ayyo_smoke_owned_processes >&2
  failed_run_id="$launch_run_id"
  mapfile -t remaining < <(ayyo_smoke_owned_pids)
  ayyo_smoke_signal_owned KILL
  ayyo_smoke_wait_owned_exit 20 0.05 || true
  if [[ "${#remaining[@]}" -gt 0 ]]; then
    printf 'FAIL: forced cleanup was scoped to run %s; smoke must fail\n' \
      "$failed_run_id" >&2
  fi
  return 1
}
