#!/bin/bash

set -euo pipefail

RUNTIME_INIT_STATUS_MARKER="__RUNTIME_INIT_STATUS__="
RUNTIME_INIT_MESSAGE_MARKER="__RUNTIME_INIT_MESSAGE__="
RUNTIME_INIT_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_INIT_ROOT_DIR="$(cd "${RUNTIME_INIT_SCRIPT_DIR}/.." && pwd)"
RUNTIME_INIT_USER_HOME="/home/user"
RUNTIME_INIT_RUNTIME_PATH="${RUNTIME_INIT_ROOT_DIR}"
RUNTIME_INIT_WORKSPACE="/home/user/.super_doubao/super-doubao-runtime/workspace"
RUNTIME_INIT_WORKSPACE_ROOT="/sandboxdata/workspace"
RUNTIME_INIT_WORKSPACE_TARGET="${RUNTIME_INIT_WORKSPACE_ROOT}/file"
RUNTIME_INIT_DOWNLOADS_PATH="${RUNTIME_INIT_WORKSPACE}/Downloads"
RUNTIME_INIT_BROWSER_CONFIG_DIR="${RUNTIME_INIT_USER_HOME}/.config/browser"
RUNTIME_INIT_BROWSER_DEFAULT_DIR="${RUNTIME_INIT_BROWSER_CONFIG_DIR}/Default"
RUNTIME_INIT_COOKIE_ROOT="${RUNTIME_INIT_BROWSER_DEFAULT_DIR}/customCookie"

runtime_init_log() {
  echo "[runtime_init][$(basename "$0")] $*"
}

runtime_init_now_ms() {
  date +%s%3N
}

runtime_init_log_duration_ms() {
  local stage_name="$1"
  local start_ms="$2"
  local end_ms
  end_ms="$(runtime_init_now_ms)"
  runtime_init_log "timing, stage=${stage_name}, duration_ms=$((end_ms - start_ms))"
}

runtime_init_emit_status() {
  local status="$1"
  local message="${2:-}"
  echo "${RUNTIME_INIT_STATUS_MARKER}${status}"
  if [ -n "${message}" ]; then
    echo "${RUNTIME_INIT_MESSAGE_MARKER}${message}"
  fi
}

runtime_init_success() {
  runtime_init_emit_status "success" "${1:-}"
  exit 0
}

runtime_init_skipped() {
  runtime_init_emit_status "skipped" "${1:-}"
  exit 0
}

runtime_init_failed() {
  runtime_init_emit_status "failed" "${1:-}" >&2
  exit 1
}

runtime_init_replace_symlink() {
  local target_path="$1"
  local link_path="$2"
  local parent_dir
  local stage_start_ms
  parent_dir="$(dirname "${link_path}")"

  runtime_init_log "ensure symlink, link=${link_path}, target=${target_path}"
  stage_start_ms="$(runtime_init_now_ms)"
  mkdir -p "${parent_dir}"
  runtime_init_log_duration_ms "replace_symlink_prepare_parent" "${stage_start_ms}"

  if [ -L "${link_path}" ]; then
    stage_start_ms="$(runtime_init_now_ms)"
    if [ "$(readlink "${link_path}")" = "${target_path}" ]; then
      runtime_init_log_duration_ms "replace_symlink_readlink" "${stage_start_ms}"
      runtime_init_log "symlink already points to target: ${link_path}"
      return 0
    fi
    runtime_init_log_duration_ms "replace_symlink_readlink" "${stage_start_ms}"
    runtime_init_log "replace existing symlink: ${link_path}"
    stage_start_ms="$(runtime_init_now_ms)"
    ln -sfnT "${target_path}" "${link_path}"
    runtime_init_log_duration_ms "replace_symlink_replace_existing" "${stage_start_ms}"
    return 0
  fi

  if [ -e "${link_path}" ]; then
    stage_start_ms="$(runtime_init_now_ms)"
    if [ -d "${link_path}" ] && [ -z "$(find "${link_path}" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
      runtime_init_log_duration_ms "replace_symlink_check_existing_path" "${stage_start_ms}"
      stage_start_ms="$(runtime_init_now_ms)"
      rmdir "${link_path}"
      runtime_init_log_duration_ms "replace_symlink_remove_empty_dir" "${stage_start_ms}"
    else
      runtime_init_log_duration_ms "replace_symlink_check_existing_path" "${stage_start_ms}"
      runtime_init_log "refuse to replace non-empty path: ${link_path}"
      return 1
    fi
  fi

  stage_start_ms="$(runtime_init_now_ms)"
  ln -sfnT "${target_path}" "${link_path}"
  runtime_init_log_duration_ms "replace_symlink_create_new" "${stage_start_ms}"
}

runtime_init_replace_managed_block() {
  local file_path="$1"
  local start_marker="$2"
  local end_marker="$3"
  local block_content="$4"
  local tmp_file filtered_file

  runtime_init_log "replace managed block in file: ${file_path}"
  mkdir -p "$(dirname "${file_path}")"
  touch "${file_path}"

  tmp_file="$(mktemp)"
  filtered_file="$(mktemp)"

  awk -v start="${start_marker}" -v end="${end_marker}" '
    $0 == start { skip = 1; next }
    $0 == end { skip = 0; next }
    skip != 1 { print }
  ' "${file_path}" > "${filtered_file}"

  cat "${filtered_file}" > "${tmp_file}"
  {
    echo "${start_marker}"
    printf "%s\n" "${block_content}"
    echo "${end_marker}"
  } >> "${tmp_file}"

  mv "${tmp_file}" "${file_path}"
  rm -f "${filtered_file}"
}

runtime_init_path_owner() {
  local path="$1"
  stat -c '%U:%G' "${path}" 2>/dev/null
}

runtime_init_path_is_healthy() {
  local path="$1"
  stat "${path}" >/dev/null 2>&1
}

runtime_init_workspace_root_is_healthy() {
  runtime_init_path_is_healthy "${RUNTIME_INIT_WORKSPACE_ROOT}"
}

runtime_init_chown_user_if_needed() {
  local path="$1"
  local recursive="${2:-false}"
  local owner

  owner="$(runtime_init_path_owner "${path}")" || {
    runtime_init_log "skip chown because path is not healthy: ${path}"
    return 0
  }

  if [ "${owner}" = "user:user" ]; then
    runtime_init_log "owner already user:user, skip chown: ${path}"
    return 0
  fi

  if [ "${recursive}" = "true" ]; then
    runtime_init_log "change owner recursively to user:user, path=${path}, current_owner=${owner}"
    runtime_init_run_privileged chown -R user:user "${path}"
  else
    runtime_init_log "change owner to user:user, path=${path}, current_owner=${owner}"
    runtime_init_run_privileged chown user:user "${path}"
  fi
}

runtime_init_ensure_cookie_root() {
  # Browser profile parent directories must be user-owned even when the cookie
  # mount itself is absent or unhealthy; otherwise Chromium cannot create locks.
  runtime_init_log "ensure browser profile parent directories, browser_default_dir=${RUNTIME_INIT_BROWSER_DEFAULT_DIR}"
  runtime_init_run_privileged mkdir -p "${RUNTIME_INIT_BROWSER_DEFAULT_DIR}"

  runtime_init_chown_user_if_needed "${RUNTIME_INIT_USER_HOME}/.config"
  runtime_init_chown_user_if_needed "${RUNTIME_INIT_BROWSER_CONFIG_DIR}"
  runtime_init_chown_user_if_needed "${RUNTIME_INIT_BROWSER_DEFAULT_DIR}"

  # Cookie root may be a VEFAAS/TOS mount. Touch it only after stat succeeds to
  # avoid errors such as "Transport endpoint is not connected".
  if runtime_init_path_is_healthy "${RUNTIME_INIT_COOKIE_ROOT}"; then
    runtime_init_log "cookie root is healthy, ensure owner: ${RUNTIME_INIT_COOKIE_ROOT}"
    runtime_init_chown_user_if_needed "${RUNTIME_INIT_COOKIE_ROOT}" true
    return 0
  fi

  runtime_init_log "skip cookie root owner ensure because cookie root is not healthy: ${RUNTIME_INIT_COOKIE_ROOT}"
}

runtime_init_workspace_is_ready() {
  runtime_init_workspace_root_is_healthy &&
    [ -L "${RUNTIME_INIT_WORKSPACE}" ] &&
    [ "$(readlink "${RUNTIME_INIT_WORKSPACE}")" = "${RUNTIME_INIT_WORKSPACE_TARGET}" ]
}

runtime_init_run_privileged() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return $?
  fi
  sudo "$@"
}
