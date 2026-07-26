#!/bin/bash
#
# AIO Sandbox + GemBrowser Merged Entrypoint
# This script initializes the sandbox environment and starts supervisord.
#

set -e

# ----------------------
# Timing Functions
# ----------------------
TIMING_START=$(date +%s%3N)
TIMING_LAST=$TIMING_START

timing_checkpoint() {
  local checkpoint_name="$1"
  local now=$(date +%s%3N)
  local elapsed_from_start=$((now - TIMING_START))
  local elapsed_from_last=$((now - TIMING_LAST))
  echo "$(date '+%Y-%m-%d %H:%M:%S,%3N') TIMING [${checkpoint_name}] +${elapsed_from_last}ms (total: ${elapsed_from_start}ms)"
  TIMING_LAST=$now
}

# ----------------------
# Logging Function
# ----------------------
log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S,%3N') INFO $@"
}

# ----------------------
# Lifecycle Hook Runner
# ----------------------
# Usage: run_hook <hook_name> <env_commands>
run_hook() {
  local hook_name="$1"
  local hook_commands="$2"

  # Trim leading and trailing whitespace while preserving internal formatting
  local trimmed_commands
  trimmed_commands="$(printf '%s' "$hook_commands" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [ -z "$trimmed_commands" ] && return 0

  local strict_mode
  strict_mode="$(echo -n "${RUN_HOOKS_STRICT:-false}" | xargs | tr '[:upper:]' '[:lower:]')"

  log "Executing $hook_name hook..."
  if [ "$strict_mode" = "true" ]; then
    bash -c "$trimmed_commands"
  else
    bash -c "$trimmed_commands" || log "WARNING: $hook_name hook failed with exit code $? (RUN_HOOKS_STRICT=false, continuing...)"
  fi
  log "$hook_name hook completed."
}

log "Starting AIO Sandbox entrypoint..."
timing_checkpoint "entrypoint_start"

# ----------------------
# Convert DISABLE_* to supervisord autostart format
# ----------------------
export AUTOSTART_JUPYTER=$([ "$DISABLE_JUPYTER" != "true" ] && echo "true" || echo "false")
export AUTOSTART_CODE_SERVER=$([ "$DISABLE_CODE_SERVER" != "true" ] && echo "true" || echo "false")
export AUTOSTART_BROWSER=$([ "$DISABLE_BROWSER" != "true" ] && echo "true" || echo "false")
# MCP_BROWSER depends on browser, disable it if browser is disabled
export AUTOSTART_MCP_BROWSER=$([ "$DISABLE_MCP_BROWSER" != "true" ] && [ "$DISABLE_BROWSER" != "true" ] && echo "true" || echo "false")

# VNC/GUI services (tigervnc, websocat, openbox)
export AUTOSTART_VNC=$([ "$DISABLE_VNC" != "true" ] && echo "true" || echo "false")

# Node.js REPL server autostart based on NODE_CODE_EXEC_VERSION
# Only the default version starts automatically, others start on-demand
NODE_VERSION="${NODE_CODE_EXEC_VERSION:-node22}"
export AUTOSTART_NODEJS_REPL_20=$([ "$NODE_VERSION" = "node20" ] && echo "true" || echo "false")
export AUTOSTART_NODEJS_REPL_22=$([ "$NODE_VERSION" = "node22" ] && echo "true" || echo "false")
export AUTOSTART_NODEJS_REPL_24=$([ "$NODE_VERSION" = "node24" ] && echo "true" || echo "false")

# ----------------------
# Logging Configuration
# ----------------------
export LOG_TOOL_TRACE="${LOG_TOOL_TRACE:-false}"
export LOG_STDOUT_SERVER="${LOG_STDOUT_SERVER:-false}"

log "Python tool trace: ${LOG_TOOL_TRACE}"
log "Log stdout server: ${LOG_STDOUT_SERVER}"

# ----------------------
# Run Init Hook (very early, before user creation)
# ----------------------
run_hook "RUN_HOOK_INIT" "$RUN_HOOK_INIT"
timing_checkpoint "init_hook"

# ----------------------
# Create Non-root User
# ----------------------
log "Creating user ('$USER') with UID ($USER_UID) and GID ($USER_GID)..."
if ! getent group $USER >/dev/null; then
  groupadd --gid $USER_GID $USER
fi
if ! id -u $USER >/dev/null 2>&1; then
  useradd --uid $USER_UID --gid $USER_GID --shell /bin/bash --create-home $USER
fi

# Add user to sudoers with NOPASSWD (only if we have permission)
if [ -w /etc/sudoers.d ]; then
  mkdir -p /etc/sudoers.d
  echo "$USER ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/$USER
  chmod 440 /etc/sudoers.d/$USER
else
  log "Warning: Cannot modify sudoers (running in restricted environment)"
fi
timing_checkpoint "create_user"

# ----------------------
# X11 Setup (from gembrowser)
# ----------------------
log "Setting up X11 permissions..."
rm -rf /tmp/.X11-unix  # Clean stale sockets on restart
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix
chown $USER /tmp/.X11-unix/

# ----------------------
# Create Necessary Directories
# ----------------------
log "Creating necessary directories..."
mkdir -p "$LOG_DIR" "$XDG_RUNTIME_DIR"
chmod 1777 "$LOG_DIR"
chown $USER "$LOG_DIR" "$XDG_RUNTIME_DIR"

log "Setting up Nginx directories..."
mkdir -p /var/lib/nginx
chmod 1777 /var/lib/nginx
chown nobody /var/lib/nginx

chown -R $USER:$USER /opt/jupyter
timing_checkpoint "create_directories"

# Control whether bundled skills are copied into user home.
COPY_SKILLS_TO_USER_HOME_RAW="$(echo -n "${AIO_CLI_SKILL_ENABLED:-false}" | xargs | tr '[:upper:]' '[:lower:]')"
if [ "${COPY_SKILLS_TO_USER_HOME_RAW}" = "true" ]; then
  COPY_SKILLS_TO_USER_HOME="true"
else
  COPY_SKILLS_TO_USER_HOME="false"
fi
log "Copy bundled skills to user home: ${COPY_SKILLS_TO_USER_HOME}"

# ----------------------
# Parallel Setup: User config + DNS/Nginx config run concurrently
# ----------------------
log "Starting parallel setup (user_setup + config)..."

# Group A: User-specific Setup (runs as $USER)
(
  su - $USER -c "AIO_CLI_SKILL_ENABLED=${COPY_SKILLS_TO_USER_HOME} BROWSER_LANG=${BROWSER_LANG:-en-US} bash -s" << 'EOF'
mkdir -p /home/$USER/.npm-global/lib/node_modules

# 1. Copy default configurations
cp -f /opt/gem/bashrc /home/$USER/.bashrc

# code-server
mkdir -p /home/$USER/.config/code-server /home/$USER/.local/share/code-server \
     && chmod -R 755 /home/$USER/.local/share/code-server/
cp -rf /opt/gem/vscode /home/$USER/.config/code-server/vscode

# jupyter
cp -rf /opt/gem/jupyter /home/$USER/.jupyter

# matplotlib
mkdir -p /home/$USER/.config/matplotlib
cp -f /opt/gem/matplotlibrc /home/$USER/.config/matplotlib/matplotlibrc
rm -rf /home/$USER/.cache/matplotlib/fontlist-*.json 2>/dev/null || true

# 2. Merge staged configs
if [ -d "/opt/aio-staged-configs" ]; then
  rsync -a /opt/aio-staged-configs/ /home/$USER/
fi

# 3. Agent skills
if [ "${AIO_CLI_SKILL_ENABLED}" = "true" ] && [ -d "/opt/skills" ]; then
  mkdir -p /home/$USER/.agents
  cp -rf /opt/skills /home/$USER/.agents/skills
fi

# 4. Browser preferences
touch "$HOME/.Xauthority"
mkdir -p "$HOME/.config/browser/Default"
cp "/opt/gem/preferences.json" "$HOME/.config/browser/Default/Preferences"

# Chrome prefers profile language settings over --lang, so keep Preferences in sync.
BROWSER_LANGS="${BROWSER_LANG}"
BROWSER_BASE="${BROWSER_LANG%%-*}"
case "${BROWSER_LANG}" in
  *-*) BROWSER_LANGS="${BROWSER_LANGS},${BROWSER_BASE}" ;;
esac
[ "${BROWSER_LANG}" != "en-US" ] && [ "${BROWSER_BASE}" != "en" ] && BROWSER_LANGS="${BROWSER_LANGS},en-US,en"
[ "${BROWSER_LANG}" != "en-US" ] && [ "${BROWSER_BASE}" = "en" ] && BROWSER_LANGS="${BROWSER_LANGS},en-US"
jq --arg langs "${BROWSER_LANGS}" \
  '.intl.selected_languages = $langs | .intl.accept_languages = $langs' \
  "$HOME/.config/browser/Default/Preferences" > "$HOME/.config/browser/Default/Preferences.tmp" \
  && mv "$HOME/.config/browser/Default/Preferences.tmp" "$HOME/.config/browser/Default/Preferences"

# Configure download directory if env var is set
if [ -n "${BROWSER_DOWNLOAD_DIR}" ]; then
  mkdir -p "${BROWSER_DOWNLOAD_DIR}"
  jq --arg dir "${BROWSER_DOWNLOAD_DIR}" \
    '.download.default_directory = $dir | .download.directory_upgrade = true | .savefile.default_directory = $dir' \
    "$HOME/.config/browser/Default/Preferences" > "$HOME/.config/browser/Default/Preferences.tmp" \
    && mv "$HOME/.config/browser/Default/Preferences.tmp" "$HOME/.config/browser/Default/Preferences"
fi
EOF
) &
PID_USER_SETUP=$!

# Group B: DNS + Nginx Configuration (independent, runs as root)
(
  # DNS over HTTPS Configuration
  TRIMMED_DOH_TEMPLATES="$(echo -n "$DNS_OVER_HTTPS_TEMPLATES" | xargs)"
  if [ -n "$TRIMMED_DOH_TEMPLATES" ]; then
    mkdir -p /etc/browser/policies/managed
    cat >/etc/browser/policies/managed/dns_over_https.json <<DOHEOF
{
  "DnsOverHttpsMode": "secure",
  "DnsOverHttpsTemplates": "$TRIMMED_DOH_TEMPLATES"
}
DOHEOF
  fi

  # URL Blocklist/Allowlist Policy
  TRIMMED_BLOCKLIST="$(echo -n "${BROWSER_URL_BLOCKLIST:-}" | xargs)"
  TRIMMED_ALLOWLIST="$(echo -n "${BROWSER_URL_ALLOWLIST:-}" | xargs)"
  if [ -n "$TRIMMED_BLOCKLIST" ] || [ -n "$TRIMMED_ALLOWLIST" ]; then
    URL_POLICY="{}"
    if [ -n "$TRIMMED_BLOCKLIST" ]; then
      URL_POLICY=$(echo "$URL_POLICY" | jq --argjson list "$(echo "$TRIMMED_BLOCKLIST" | jq -R 'split(",") | map(gsub("^\\s+|\\s+$";""))')" '.URLBlocklist = $list')
    fi
    if [ -n "$TRIMMED_ALLOWLIST" ]; then
      URL_POLICY=$(echo "$URL_POLICY" | jq --argjson list "$(echo "$TRIMMED_ALLOWLIST" | jq -R 'split(",") | map(gsub("^\\s+|\\s+$";""))')" '.URLAllowlist = $list')
    fi
    echo "$URL_POLICY" > /etc/browser/policies/managed/url_filter.json
  fi

  # Nginx listen address configuration
  if [ "${FAAS_SANDBOX_RUNTIME_INJECTION_ENABLE_SANDBOXD}" = "true" ]; then
    export PUBLIC_LISTEN_IPV4="127.0.0.1"
    export PUBLIC_LISTEN_IPV6="[::1]"
  else
    export PUBLIC_LISTEN_IPV4="${PUBLIC_LISTEN_IPV4:-0.0.0.0}"
    export PUBLIC_LISTEN_IPV6="${PUBLIC_LISTEN_IPV6:-[::]}"
  fi

  # Runtime port: platform health check port (e.g. ByteFaaS _BYTEFAAS_RUNTIME_PORT)
  # In sandboxd mode, sandboxd occupies the runtime port and proxies to nginx on PUBLIC_PORT,
  # so nginx must also listen on the runtime port for direct platform health checks.
  if [ "${FAAS_SANDBOX_RUNTIME_INJECTION_ENABLE_SANDBOXD}" = "true" ] && [ -n "$_BYTEFAAS_RUNTIME_PORT" ] && [ "$_BYTEFAAS_RUNTIME_PORT" != "$PUBLIC_PORT" ]; then
    export RUNTIME_LISTEN="listen ${PUBLIC_LISTEN_IPV4}:${_BYTEFAAS_RUNTIME_PORT}; listen ${PUBLIC_LISTEN_IPV6}:${_BYTEFAAS_RUNTIME_PORT};"
  else
    export RUNTIME_LISTEN=""
  fi

  # Auth configuration selection
  AUTH_CONFIG="/opt/gem/nginx-server-with-auth.conf"
  NO_AUTH_CONFIG="/opt/gem/nginx-server-without-auth.conf"
  ACTIVE_CONFIG="/opt/gem/nginx-server-active.conf"
  TRIMMED_JWT_PUBLIC_KEY="$(echo -n "$JWT_PUBLIC_KEY" | xargs)"
  if [ -n "$TRIMMED_JWT_PUBLIC_KEY" ]; then
    envsubst '${PUBLIC_PORT} ${AUTH_BACKEND_PORT} ${SANDBOX_SRV_PORT} ${PUBLIC_LISTEN_IPV4} ${PUBLIC_LISTEN_IPV6} ${RUNTIME_LISTEN}' <"$AUTH_CONFIG" >"$ACTIVE_CONFIG"
  else
    envsubst '${PUBLIC_PORT} ${PUBLIC_LISTEN_IPV4} ${PUBLIC_LISTEN_IPV6} ${RUNTIME_LISTEN}' <"$NO_AUTH_CONFIG" >"$ACTIVE_CONFIG"
  fi

  # Generate nginx configs
  envsubst '${BROWSER_REMOTE_DEBUGGING_PORT}' <"/opt/gem/nginx.legacy.conf" >"/opt/gem/nginx/legacy.conf"
  envsubst '${WEBSOCKET_PROXY_PORT}' <"/opt/gem/nginx.vnc.conf" >"/opt/gem/nginx/vnc.conf"

  [ -f "/opt/gem/nginx/nginx.python_srv.conf" ] && \
    envsubst '${SANDBOX_SRV_PORT}' <"/opt/gem/nginx/nginx.python_srv.conf" >"/opt/gem/nginx/python_srv.conf" && rm -f "/opt/gem/nginx/nginx.python_srv.conf"

  [ -f "/opt/gem/nginx/nginx.gembrowser_compat.conf" ] && \
    envsubst '${SANDBOX_SRV_PORT}' <"/opt/gem/nginx/nginx.gembrowser_compat.conf" >"/opt/gem/nginx/gembrowser_compat.conf" && rm -f "/opt/gem/nginx/nginx.gembrowser_compat.conf"

  if [ -f "/opt/gem/nginx/nginx.mcp_hub.conf" ]; then
    envsubst '${SANDBOX_SRV_PORT}' <"/opt/gem/nginx/nginx.mcp_hub.conf" >"/opt/gem/nginx/mcp_hub.conf" && rm -f "/opt/gem/nginx/nginx.mcp_hub.conf"

    EXTRA_MCP_SERVERS="${EXTRA_MCP_SERVERS#"${EXTRA_MCP_SERVERS%%[![:space:]]*}"}"
    EXTRA_MCP_SERVERS="${EXTRA_MCP_SERVERS%"${EXTRA_MCP_SERVERS##*[![:space:]]}"}"
    if [ -n "${EXTRA_MCP_SERVERS}" ]; then
      if ! echo "${EXTRA_MCP_SERVERS}" | jq -e '.' > /dev/null 2>&1; then
        echo "ERROR: EXTRA_MCP_SERVERS JSON format invalid" >&2
        exit 1
      fi
      jq --argjson extra "${EXTRA_MCP_SERVERS}" \
         '.mcpServers = ((.mcpServers + $extra) | with_entries(select(.value != null)))' \
         /opt/gem/mcp-hub.json.template > /opt/gem/mcp-hub.json.template.tmp \
      && mv /opt/gem/mcp-hub.json.template.tmp /opt/gem/mcp-hub.json.template
    fi
    envsubst '${SANDBOX_SRV_PORT} ${MCP_SERVER_BROWSER_PORT} ${BROWSER_REMOTE_DEBUGGING_PORT}' < /opt/gem/mcp-hub.json.template > /opt/gem/mcp-hub.json && rm -f /opt/gem/mcp-hub.json.template
  fi

  [ -f "/opt/gem/nginx/nginx.jupyter_lab.conf" ] && \
    envsubst '${JUPYTER_LAB_PORT}' <"/opt/gem/nginx/nginx.jupyter_lab.conf" >"/opt/gem/nginx/jupyter_lab.conf" && rm -f "/opt/gem/nginx/nginx.jupyter_lab.conf"
  [ -f "/opt/gem/nginx/nginx.code_server.conf" ] && \
    envsubst '${CODE_SERVER_PORT}' <"/opt/gem/nginx/nginx.code_server.conf" >"/opt/gem/nginx/code_server.conf" && rm -f "/opt/gem/nginx/nginx.code_server.conf"
  [ -f "/opt/gem/nginx/nginx.ui_browser.conf" ] && \
    envsubst '${BROWSER_REMOTE_DEBUGGING_PORT}' <"/opt/gem/nginx/nginx.ui_browser.conf" >"/opt/gem/nginx/ui_browser.conf" && rm -f "/opt/gem/nginx/nginx.ui_browser.conf"

  envsubst '${PUBLIC_PORT} ${PUBLIC_LISTEN_IPV4} ${PUBLIC_LISTEN_IPV6}' <"/opt/gem/nginx-server-port-proxy.conf.template" >"/opt/gem/nginx-server-port-proxy.conf"
) &
PID_CONFIG=$!

# Wait for both parallel tasks
wait $PID_USER_SETUP || { log "ERROR: user_setup failed"; exit 1; }
wait $PID_CONFIG || { log "ERROR: config setup failed"; exit 1; }
timing_checkpoint "parallel_setup"

# ----------------------
# Environment Variables Setup
# ----------------------
export IMAGE_VERSION=$(cat /etc/aio_version 2>/dev/null || echo "unknown")

# AIO_USER: Trusted user identity for sandboxd integration
# If AIO_USER is set, use it to override USER; otherwise fallback to USER
export AIO_USER="${AIO_USER:-$USER}"
export USER="$AIO_USER"

# Node.js version setup (symlinks already exist, just export the version var)
export NODE_CODE_EXEC_VERSION="${NODE_CODE_EXEC_VERSION:-node22}"
export NGINX_LOG_LEVEL=${NGINX_LOG_LEVEL:-debug}
export NPM_CONFIG_PREFIX=/home/$USER/.npm-global
export PATH=$NPM_CONFIG_PREFIX/bin:/home/$USER/.local/bin:$PATH
export HOMEPAGE=${HOMEPAGE:-""}
BROWSER_LANG_RESOLVED="${BROWSER_LANG:-en-US}"
BROWSER_EXEC_PATH="$(readlink -f "${BROWSER_EXECUTABLE_PATH:-/usr/local/bin/browser}" 2>/dev/null || true)"
LOCALE_DIR_CANDIDATES=(
  "/opt/browser/locales"
  "/opt/browser/usr/lib/chromium/locales"
  "/opt/browser/usr/lib/chromium-browser/locales"
  "/opt/browser/opt/google/chrome/locales"
  "/usr/lib/chromium/locales"
  "/usr/lib/chromium-browser/locales"
  "/opt/google/chrome/locales"
)
if [ -n "${BROWSER_EXEC_PATH}" ]; then
  BROWSER_EXEC_DIR="$(dirname "${BROWSER_EXEC_PATH}")"
  LOCALE_DIR_CANDIDATES=("${BROWSER_EXEC_DIR}/locales" "$(dirname "${BROWSER_EXEC_DIR}")/locales" "${LOCALE_DIR_CANDIDATES[@]}")
fi
LOCALES_DIR=""
for candidate in "${LOCALE_DIR_CANDIDATES[@]}"; do
  if [ -d "${candidate}" ]; then
    LOCALES_DIR="${candidate}"
    break
  fi
done
if [ -n "${LOCALES_DIR}" ] && [ ! -f "${LOCALES_DIR}/${BROWSER_LANG_RESOLVED}.pak" ]; then
  BROWSER_LANG_BASE="${BROWSER_LANG_RESOLVED%%-*}"
  if [ -f "${LOCALES_DIR}/${BROWSER_LANG_BASE}.pak" ]; then
    BROWSER_LANG_RESOLVED="${BROWSER_LANG_BASE}"
  fi
fi
export BROWSER_EXTRA_ARGS="${BROWSER_NO_SANDBOX} --lang=${BROWSER_LANG_RESOLVED} --time-zone-for-testing=${TZ} --homepage ${HOMEPAGE} ${BROWSER_EXTRA_ARGS}"

# Add user-agent if BROWSER_USER_AGENT is set
if [ -n "${BROWSER_USER_AGENT}" ]; then
  export BROWSER_EXTRA_ARGS=" --user-agent=\"${BROWSER_USER_AGENT}\" ${BROWSER_EXTRA_ARGS}"
fi
timing_checkpoint "env_vars_setup"

# ----------------------
# TinyProxy Configuration
# ----------------------
PROXY_SERVER="$(echo -n "$PROXY_SERVER" | xargs)"
if [ -n "${PROXY_SERVER}" ]; then
  mkdir -p -m 755 /var/run/tinyproxy
  chown $USER:$USER /var/run/tinyproxy

  PROXY_SERVER=${PROXY_SERVER#\"}
  PROXY_SERVER=${PROXY_SERVER%\"}
  PROXY_SERVER=${PROXY_SERVER#http://}
  PROXY_SERVER=${PROXY_SERVER#https://}

  TINYPROXY_CONFIG_DIR="/opt/gem/tinyproxy"
  TINYPROXY_CONFIG="/etc/tinyproxy.conf"

  if [ -d "${TINYPROXY_CONFIG_DIR}" ]; then
    if [ ! -f "${TINYPROXY_CONFIG_DIR}/base.conf" ]; then
      echo "ERROR: ${TINYPROXY_CONFIG_DIR}/base.conf is required but not found!" >&2
      exit 1
    fi

    > "${TINYPROXY_CONFIG}"
    echo "# === base.conf ===" >> "${TINYPROXY_CONFIG}"
    envsubst '${TINYPROXY_PORT}' < "${TINYPROXY_CONFIG_DIR}/base.conf" >> "${TINYPROXY_CONFIG}"
    echo "" >> "${TINYPROXY_CONFIG}"

    if [ "${PROXY_SERVER}" != "true" ]; then
      echo "# === Auto-generated Upstream ===" >> "${TINYPROXY_CONFIG}"
      echo "Upstream http ${PROXY_SERVER}" >> "${TINYPROXY_CONFIG}"
      echo "" >> "${TINYPROXY_CONFIG}"
    fi

    for conf_file in $(find "${TINYPROXY_CONFIG_DIR}" -type f -name "*.conf" 2>/dev/null | grep -vE "base.conf" | sort); do
      if [ -f "${conf_file}" ]; then
        rel_path="${conf_file#${TINYPROXY_CONFIG_DIR}/}"
        echo "# === ${rel_path} ===" >> "${TINYPROXY_CONFIG}"
        envsubst '${PROXY_SERVER}' < "${conf_file}" >> "${TINYPROXY_CONFIG}"
        echo "" >> "${TINYPROXY_CONFIG}"
      fi
    done

    log "Tinyproxy configuration assembled from ${TINYPROXY_CONFIG_DIR}"
  else
    echo "ERROR: Tinyproxy config directory ${TINYPROXY_CONFIG_DIR} not found!" >&2
    exit 1
  fi

  TRIMMED_BYPASS="$(echo -n "${PROXY_BYPASS_LIST:-}" | xargs)"
  if [ -n "${TRIMMED_BYPASS}" ]; then
    # Generate PAC file for split-routing: bypass domains go DIRECT, rest through proxy
    PAC_FILE="/opt/gem/proxy.pac"
    {
      echo 'function FindProxyForURL(url, host) {'
      IFS=',' read -ra BYPASS_DOMAINS <<< "$TRIMMED_BYPASS"
      for domain in "${BYPASS_DOMAINS[@]}"; do
        domain=$(echo "$domain" | xargs)
        clean_domain="${domain#\*.}"
        echo "  if (dnsDomainIs(host, \"${clean_domain}\") || host === \"${clean_domain}\") return \"DIRECT\";"
      done
      echo "  return \"PROXY 127.0.0.1:${TINYPROXY_PORT}\";"
      echo '}'
    } > "$PAC_FILE"
    export BROWSER_EXTRA_ARGS="${BROWSER_EXTRA_ARGS} --proxy-pac-url=file://${PAC_FILE}"
    log "Generated PAC file at ${PAC_FILE} with bypass: ${TRIMMED_BYPASS}"
  else
    export BROWSER_EXTRA_ARGS="${BROWSER_EXTRA_ARGS} --proxy-server=http://127.0.0.1:${TINYPROXY_PORT}"
  fi
else
  rm -f /opt/gem/supervisord/supervisord.tinyproxy.conf
fi
timing_checkpoint "tinyproxy_config"

# ----------------------
# Generate Index Page
# ----------------------
if [ -f "/opt/aio/index.html.template" ]; then
  envsubst '${DISABLE_JUPYTER},${DISABLE_CODE_SERVER}' \
    < /opt/aio/index.html.template > /opt/aio/index.html
  rm -rf /opt/aio/index.html.template
fi
timing_checkpoint "index_page"

# ----------------------
# Display Startup Banner
# ----------------------
print_banner() {
  echo ""
  echo -e "\033[36m █████╗ ██╗ ██████╗     ███████╗ █████╗ ███╗   ██╗██████╗ ██████╗  ██████╗ ██╗  ██╗\033[0m"
  echo -e "\033[36m██╔══██╗██║██╔═══██╗    ██╔════╝██╔══██╗████╗  ██║██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝\033[0m"
  echo -e "\033[36m███████║██║██║   ██║    ███████╗███████║██╔██╗ ██║██║  ██║██████╔╝██║   ██║ ╚███╔╝\033[0m"
  echo -e "\033[36m██╔══██║██║██║   ██║    ╚════██║██╔══██║██║╚██╗██║██║  ██║██╔══██╗██║   ██║ ██╔██╗\033[0m"
  echo -e "\033[36m██║  ██║██║╚██████╔╝    ███████║██║  ██║██║ ╚████║██████╔╝██████╔╝╚██████╔╝██╔╝ ██╗\033[0m"
  echo -e "\033[36m╚═╝  ╚═╝╚═╝ ╚═════╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝\033[0m"
  echo ""
  echo -e "\033[32m AIO(All-in-One) Agent Sandbox Environment\033[0m"
  if [ -n "${IMAGE_VERSION}" ]; then
    echo -e "\033[34m Image Version: ${IMAGE_VERSION}\033[0m"
  fi
  echo -e "\033[33m Dashboard: http://localhost:${PUBLIC_PORT}\033[0m"
  echo -e "\033[33m Documentation: http://localhost:${PUBLIC_PORT}/v1/docs\033[0m"
  echo ""
  echo -e "\033[35m================================================================\033[0m"
}

print_banner
timing_checkpoint "banner"

# ----------------------
# Run Pre-services Hook
# ----------------------
run_hook "RUN_HOOK_PRE_SERVICES" "$RUN_HOOK_PRE_SERVICES"
timing_checkpoint "pre_services_hook"

# ----------------------
# Start Supervisord
# ----------------------
log "Starting supervisord as the main process..."
timing_checkpoint "supervisord_start"
exec /usr/bin/supervisord -n -c /opt/gem/supervisord.conf
