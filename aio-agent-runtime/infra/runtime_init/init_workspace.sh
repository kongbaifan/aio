#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

# Workspace root is a VEFAAS/TOS mount. Check health before touching it to avoid
# transport endpoint errors on standby warm containers.
runtime_init_log "start init workspace, workspace=${RUNTIME_INIT_WORKSPACE}, workspace_root=${RUNTIME_INIT_WORKSPACE_ROOT}, target=${RUNTIME_INIT_WORKSPACE_TARGET}"
stage_start_ms="$(runtime_init_now_ms)"
runtime_init_ensure_cookie_root
runtime_init_log_duration_ms "workspace_prepare_browser_profile" "${stage_start_ms}"

stage_start_ms="$(runtime_init_now_ms)"
mkdir -p "$(dirname "${RUNTIME_INIT_WORKSPACE}")"
runtime_init_log_duration_ms "workspace_prepare_runtime_parent" "${stage_start_ms}"

stage_start_ms="$(runtime_init_now_ms)"
if ! runtime_init_workspace_root_is_healthy || [ ! -d "${RUNTIME_INIT_WORKSPACE_ROOT}" ]; then
  runtime_init_log_duration_ms "workspace_check_root_health" "${stage_start_ms}"
  if [ -L "${RUNTIME_INIT_WORKSPACE}" ]; then
    runtime_init_log "workspace root is not healthy or not ready, keep existing workspace symlink untouched: ${RUNTIME_INIT_WORKSPACE}"
    runtime_init_skipped "workspace root is not ready"
  fi
  stage_start_ms="$(runtime_init_now_ms)"
  runtime_init_run_privileged mkdir -p "${RUNTIME_INIT_WORKSPACE}"
  runtime_init_run_privileged chmod 777 "${RUNTIME_INIT_WORKSPACE}"
  runtime_init_log_duration_ms "workspace_prepare_placeholder" "${stage_start_ms}"
  runtime_init_log "workspace root is not healthy or not ready, keep placeholder workspace: ${RUNTIME_INIT_WORKSPACE}"
  runtime_init_skipped "workspace root is not ready"
fi
runtime_init_log_duration_ms "workspace_check_root_health" "${stage_start_ms}"

runtime_init_log "workspace root is healthy, prepare target: ${RUNTIME_INIT_WORKSPACE_TARGET}"
stage_start_ms="$(runtime_init_now_ms)"
runtime_init_run_privileged mkdir -p "${RUNTIME_INIT_WORKSPACE_TARGET}" || runtime_init_failed "create workspace target failed"
runtime_init_run_privileged chown user:user "${RUNTIME_INIT_WORKSPACE_TARGET}" || runtime_init_failed "chown workspace target failed"
runtime_init_run_privileged chmod 777 "${RUNTIME_INIT_WORKSPACE_TARGET}" || runtime_init_failed "chmod workspace target failed"
runtime_init_log_duration_ms "workspace_prepare_target" "${stage_start_ms}"

if [ -e "${RUNTIME_INIT_WORKSPACE}" ] && [ ! -L "${RUNTIME_INIT_WORKSPACE}" ]; then
  # Standby 冷启动时 workspace mount 可能尚未 ready，前一次 init_workspace 会创建
  # 普通目录占位；后续只要挂载已就绪，就直接清理占位目录并切换为指向 session workspace 的软链。
  # 如需问题排查，可显式设置 RUNTIME_INIT_BACKUP_WORKSPACE_PLACEHOLDER=1 保留备份。
  if [ "${RUNTIME_INIT_BACKUP_WORKSPACE_PLACEHOLDER:-}" = "1" ]; then
    workspace_backup="${RUNTIME_INIT_WORKSPACE}.placeholder.$(runtime_init_now_ms)"
    runtime_init_log "backup existing non-symlink workspace placeholder before binding, path=${RUNTIME_INIT_WORKSPACE}, backup=${workspace_backup}"
    runtime_init_run_privileged mv "${RUNTIME_INIT_WORKSPACE}" "${workspace_backup}" || runtime_init_failed "backup workspace placeholder failed"
  else
    runtime_init_log "remove existing non-symlink workspace placeholder before binding, path=${RUNTIME_INIT_WORKSPACE}"
    runtime_init_run_privileged rm -rf "${RUNTIME_INIT_WORKSPACE}" || runtime_init_failed "remove workspace placeholder failed"
  fi
fi

runtime_init_log "bind runtime workspace symlink to session workspace"
stage_start_ms="$(runtime_init_now_ms)"
runtime_init_replace_symlink "${RUNTIME_INIT_WORKSPACE_TARGET}" "${RUNTIME_INIT_WORKSPACE}" || runtime_init_failed "replace workspace symlink failed"
runtime_init_log_duration_ms "workspace_bind_symlink" "${stage_start_ms}"

stage_start_ms="$(runtime_init_now_ms)"
runtime_init_run_privileged chown -h user:user "${RUNTIME_INIT_WORKSPACE}" || runtime_init_failed "chown workspace symlink failed"
runtime_init_log_duration_ms "workspace_chown_symlink" "${stage_start_ms}"

runtime_init_success "workspace linked to session workspace"
