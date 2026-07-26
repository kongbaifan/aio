#!/bin/bash

set -euo pipefail

# 重定输出到日志文件
if [ -n "${MCP_VM_SERVER_LOG_PATH:-}" ]; then
    touch "${MCP_VM_SERVER_LOG_PATH}"
    chown user:user "${MCP_VM_SERVER_LOG_PATH}"
    exec &> >(tee -a "${MCP_VM_SERVER_LOG_PATH}")
fi

PROFILE="${MCP_VM_PROFILE:-all}"
# 统一镜像入口：默认走 all，命中 ci profile 时尽早转发到专用入口。
echo "entrypoint(all): MCP_VM_PROFILE=${PROFILE} ENABLE_CI_SERVER=${ENABLE_CI_SERVER:-true} WAIT_PORTS=${WAIT_PORTS:-<empty>}"
case "${PROFILE}" in
  all)
    ;;
  ci)
    echo "entrypoint(all): routing to ci entrypoint ${RUNTIME_PATH}/entrypoint_ci.sh"
    exec "${RUNTIME_PATH}/entrypoint_ci.sh" "$@"
    ;;
  *)
    echo "Unknown MCP_VM_PROFILE=${PROFILE}" >&2
    exit 1
    ;;
esac

normalize_wait_ports() {
  local wait_ports="${WAIT_PORTS:-8091}"
  local original_wait_ports="${WAIT_PORTS:-<empty>}"

  # all 模式下 nginx 默认等待 8091；如果启用了 CI server，再补上 9999。
  if [ "${ENABLE_CI_SERVER:-true}" = "true" ]; then
    case ",${wait_ports}," in
      *,9999,*)
        ;;
      *)
        wait_ports="${wait_ports},9999"
        ;;
    esac
  fi

  export WAIT_PORTS="${wait_ports}"
  echo "entrypoint(all): normalized WAIT_PORTS from ${original_wait_ports} to ${WAIT_PORTS}"
}

normalize_wait_ports

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_INIT_DIR="${SCRIPT_DIR}/runtime_init"

create_symlink() {
  local target_path="$1"
  local link_path="$2"
  echo "create_symlink: target_path=$target_path ; link_path=$link_path"

  if [ -d "$link_path" ]; then
      echo "错误: $link_path 是目录" >&2
  elif [ -f "$link_path" ]; then
      echo "错误: $link_path 是文件" >&2
  elif [ -L "$link_path" ]; then
      echo "错误: $link_path 已存在符号链接" >&2
  else
      echo "创建符号链接: $target_path -> $link_path"
      ln -sfT "$target_path" "$link_path"
  fi
}

USER_HOME=/home/user

sync_browser_proxy_server_env() {
  if [ -z "${PROXY:-}" ]; then
    echo "sync_browser_proxy_server_env: PROXY is empty, skip"
    return 0
  fi

  export PROXY_SERVER="${PROXY}"
  echo "sync_browser_proxy_server_env: PROXY_SERVER synced from PROXY"
}

run_runtime_init_script() {
  local script_name="$1"
  local script_path="${RUNTIME_INIT_DIR}/${script_name}"
  echo "run_runtime_init_script: ${script_name}"
  if [ ! -f "${script_path}" ]; then
    echo "runtime init script not found: ${script_path}" >&2
    exit 1
  fi
  bash "${script_path}"
}

run_runtime_init_script_best_effort() {
  local script_name="$1"
  if run_runtime_init_script "${script_name}"; then
    return 0
  fi
  echo "run_runtime_init_script_best_effort: ${script_name} failed, continue startup"
  return 0
}

init_browser_config() {
  echo "init_browser_config"
  local start_marker="# >>> mcp_vm_server browser config start >>>"
  local end_marker="# <<< mcp_vm_server browser config end <<<"
  local tmp_file filtered_file
  tmp_file="$(mktemp)"
  filtered_file="$(mktemp)"
  touch /root/.bashrc
  awk -v start="${start_marker}" -v end="${end_marker}" '
    $0 == start { skip = 1; next }
    $0 == end { skip = 0; next }
    skip != 1 { print }
  ' /root/.bashrc > "${filtered_file}"
  cat "${filtered_file}" > "${tmp_file}"
  {
    echo "${start_marker}"
    echo "export BROWSER_EXTRA_ARGS=\"${BROWSER_EXTRA_ARGS:-} --disable-sync\""
    echo "${end_marker}"
  } >> "${tmp_file}"
  mv "${tmp_file}" /root/.bashrc
  rm -f "${filtered_file}"
}

start_vm_runtime_hook() {
  if [ -z "${VM_RUNTIME_HOOK_INTERNAL_TOKEN:-}" ]; then
    VM_RUNTIME_HOOK_INTERNAL_TOKEN="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
    export VM_RUNTIME_HOOK_INTERNAL_TOKEN
  fi

  "${SCRIPT_DIR}/vm_runtime_hook" --host 127.0.0.1 --port 10080 &
  VM_RUNTIME_HOOK_PID=$!
  echo "vm_runtime_hook started asynchronously, pid=${VM_RUNTIME_HOOK_PID}"
}

run_runtime_init_script ensure_cookie_dir_owner.sh
run_runtime_init_script init_workspace.sh
run_runtime_init_script init_shell_http_proxy.sh
run_runtime_init_script prepare_downloads_dir.sh
# 个人 skills 数据源 /sandboxdata/data 必须仅 root 可读：兜底收紧挂载目录本身为 700
# （仅目录本身、不递归——700 已阻断 user 进入，子项权限无意义；挂载缺失则跳过，best-effort）。
if [ -d /sandboxdata/data ]; then
  chmod 700 /sandboxdata/data || echo "[entrypoint] chmod 700 /sandboxdata/data failed (best-effort)"
fi
# 官方 + 个人 skills 冷加载：复用 Go 内核（root 身份、一次性进程）。
# load_session_skills.sh 现在只负责把官方包解到 skills.tmp/official，真实落地由 Go commit；
# 因此 entrypoint 不能直接调用该脚本，否则会先消费 workspace skills.zip，导致 sync-skills 无法 commit。
"${SCRIPT_DIR}/vm_runtime_hook" sync-skills || echo "[entrypoint] personal skills cold sync failed (best-effort)"
("${SCRIPT_DIR}/vm_runtime_hook" audit-skill-permissions || echo "[entrypoint] skill permission audit failed (best-effort)") &
SKILL_PERMISSION_AUDIT_PID=$!
echo "skill permission audit submitted asynchronously, pid=${SKILL_PERMISSION_AUDIT_PID}"
run_runtime_init_script_best_effort init_lark_cli.sh
init_browser_config
start_vm_runtime_hook

bash "${RUNTIME_INIT_DIR}/start_hijack_proxy.sh" &
HIJACK_PROXY_INIT_PID=$!
echo "hijack proxy start script submitted asynchronously, pid=${HIJACK_PROXY_INIT_PID}"

# nginx
envsubst '${VM_SERVER_PORT} ${CI_PYTHON_SERVER_PORT}' < /tmp/nginx.mcp_vm_server.conf.template > /opt/gem/nginx/nginx.mcp_vm_server.conf

# 启动 aio & gem browser
sync_browser_proxy_server_env
/opt/gem/run.sh &
RUN_GEM_PID=$!
child_pid="${RUN_GEM_PID}"
echo "start gem. pid=$RUN_GEM_PID"


# 转发信号给子进程
forward_signal() {
  sig="$1"
  echo "Entrypoint received SIG$sig, forwarding..."
  if [ -n "${VM_RUNTIME_HOOK_PID:-}" ]; then
    kill "-$sig" "${VM_RUNTIME_HOOK_PID}" 2>/dev/null || true
  fi
  kill "-$sig" -"$child_pid" 2>/dev/null
}

trap 'forward_signal TERM' SIGTERM
trap 'forward_signal INT'  SIGINT
trap 'forward_signal QUIT' SIGQUIT

wait "$RUN_GEM_PID"
