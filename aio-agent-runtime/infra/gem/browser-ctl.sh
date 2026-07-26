#!/bin/bash

#
# A script to install and configure browser under supervisor.
#

# --- Configuration ---
# The location of your Supervisor program config.
SUPERVISOR_CONF="/opt/gem/supervisord/browser.conf"

# The target directory for installations from .zip files.
INSTALL_DIR="/opt/browser"

# The generic, system-wide link managed by update-alternatives.
# Supervisor should always point to this link.
ALT_LINK="/usr/local/bin/browser"
ALT_NAME="browser"

# --- Installation URLs ---
ASSET_PREFIX_DEFAULT="https://lf3-static.bytednsdoc.com/obj/eden-cn/100upeupq/"
ASSET_PREFIX="${ASSET_PREFIX:-$ASSET_PREFIX_DEFAULT}"
# Ensure ASSET_PREFIX ends with exactly one slash to avoid malformed URLs.
ASSET_PREFIX="${ASSET_PREFIX%/}/"

# URL for official chromium version.
CR_DOWNLOAD_URL_AMD64="https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1155/chromium-linux.zip"
CR_DOWNLOAD_URL_ARM64="${ASSET_PREFIX}aio/playwright-chromium_133.0.6943.16_arm64.zip"

# URL for rs version.
RS_DOWNLOAD_URL_AMD64="${CUSTOM_BROWSER_KERNEL:-http://tosv.byted.org/obj/ttwebview-static-res/gembrowser/20251217_152612_chromium-browser-stable_141.0.7390.70-1_amd64.deb}"
RS_DOWNLOAD_URL_ARM64="${ASSET_PREFIX}aio/playwright-chromium_133.0.6943.16_arm64.zip"

# URL for Google Chrome (official build).
# Google Chrome is only available for amd64 on Linux.
GC_DOWNLOAD_URL_AMD64="https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_139.0.7258.127-1_amd64.deb"
GC_DOWNLOAD_URL_ARM64="${ASSET_PREFIX}aio/playwright-chromium_133.0.6943.16_arm64.zip"

# --- Script Setup ---
# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error.
set -u

# --- Helper Functions ---

# Function to print usage information.
usage() {
  echo "Usage: $0 <command> [options]"
  echo
  echo "Commands:"
  echo "  install <source>      Install a browser. If Supervisor is running, it will restart the service."
  echo "                        <source> can be 'cr' (Chromium), 'gc' (Google Chrome), 'rs',"
  echo "                        or a direct URL to a .deb, .zip, or .tar.gz file."
  echo
  echo "  set-args '<args>'     Set command-line arguments in Supervisor and restart the service."
  echo "                        Example: $0 set-args '--no-sandbox --start-maximized'"
  echo
  echo "  append-args '<args>'  Append command-line arguments in Supervisor and restart the service."
  echo "                        Example: $0 append-args '--user-data-dir=/tmp/chrome-profile'"
  echo
  exit 1
}

# Function to restart the browser ONLY if the supervisord daemon is running.
# Ideal for build environments like Dockerfiles.
restart_browser_if_running() {
  # Check if supervisorctl can successfully connect to the supervisord process.
  if supervisorctl status >/dev/null 2>&1; then
    echo "Supervisor is running. Restarting the browser service..."
    supervisorctl restart browser
    echo "browser service restarted."
  else
    echo "Supervisor does not appear to be running. Skipping restart."
    echo "The new browser version will be used when the service starts."
  fi
}

# Function to reload supervisor config and restart the browser unconditionally.
# Used by arg-setting commands which run when the container is live.
reload_and_restart_supervisor() {
  echo "Reloading Supervisor configuration and restarting browser..."
  supervisorctl reread
  supervisorctl update
  supervisorctl restart browser
  echo "Supervisor reloaded and browser restarted successfully."
}

# Function to set up update-alternatives.
# $1: The path to the new executable.
# $2: The priority for the alternative.
setup_alternatives() {
  local executable_path="$1"
  local priority="$2"
  echo "Setting up update-alternatives for $executable_path..."
  # Install the new alternative
  update-alternatives --install "$ALT_LINK" "$ALT_NAME" "$executable_path" "$priority"
  # Set the new alternative as the default for this group
  update-alternatives --set "$ALT_NAME" "$executable_path"
  echo "Alternative '$ALT_LINK' now points to the new installation."
}

reset_install_dir() {
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
}

move_dir_contents_to_install_dir() {
  local source_dir="$1"

  reset_install_dir
  find "$source_dir" -mindepth 1 -maxdepth 1 -exec mv {} "$INSTALL_DIR"/ \;

  if [ -z "$(find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "Error: '$source_dir' did not produce any browser files."
    exit 1
  fi
}

browser_runtime_looks_complete() {
  local runtime_dir="$1"

  [ -n "$runtime_dir" ] || return 1

  if [ ! -f "$runtime_dir/icudtl.dat" ]; then
    return 1
  fi

  if [ ! -d "$runtime_dir/locales" ]; then
    return 1
  fi

  if [ ! -x "$runtime_dir/chrome" ] && [ ! -x "$runtime_dir/chromium" ] && [ ! -x "$runtime_dir/chromium-browser" ] && [ ! -x "$runtime_dir/google-chrome-stable" ]; then
    return 1
  fi
}

normalize_archive_source_dir() {
  local extract_root="$1"
  local first_entry=""

  first_entry=$(find "$extract_root" -mindepth 1 -maxdepth 1 | head -n 1)
  if [ -n "$first_entry" ] && \
    [ "$(find "$extract_root" -mindepth 1 -maxdepth 1 | wc -l | tr -d ' ')" = "1" ] && \
    [ -d "$first_entry" ]; then
    echo "$first_entry"
    return 0
  fi

  echo "$extract_root"
}

find_browser_runtime_root() {
  local search_root="$1"
  local executable_path=""
  local runtime_dir=""
  local candidate=""
  local -a preferred_candidates=(
    "$search_root/opt/chromium.org/chromium"
    "$search_root/opt/google/chrome"
    "$search_root/usr/lib/google-chrome"
    "$search_root/usr/lib/chromium"
    "$search_root/usr/lib/chromium-browser"
  )

  for candidate in "${preferred_candidates[@]}"; do
    if browser_runtime_looks_complete "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  while IFS= read -r executable_path; do
    runtime_dir="$(dirname "$executable_path")"
    if browser_runtime_looks_complete "$runtime_dir"; then
      echo "$runtime_dir"
      return 0
    fi
  done < <(find "$search_root" -type f \( -name "chrome" -o -name "chromium" -o -name "chromium-browser" -o -name "google-chrome-stable" \) -executable | sort)
}

validate_browser_install_dir() {
  local executable_path=""

  executable_path=$(find_browser_executable)
  if [ -z "$executable_path" ]; then
    echo "Error: Could not find browser executable in '$INSTALL_DIR'."
    return 1
  fi

  if ! browser_runtime_looks_complete "$INSTALL_DIR"; then
    if [ ! -f "$INSTALL_DIR/icudtl.dat" ]; then
      echo "Error: Browser runtime in '$INSTALL_DIR' is missing icudtl.dat."
    elif [ ! -d "$INSTALL_DIR/locales" ]; then
      echo "Error: Browser runtime in '$INSTALL_DIR' is missing locales/."
    else
      echo "Error: Browser runtime in '$INSTALL_DIR' is incomplete."
    fi
    return 1
  fi
}

find_nested_browser_package() {
  local search_root="$1"

  find "$search_root" -type f \( -name "*.deb" -o -name "*.zip" -o -name "*.tar.gz" -o -name "*.tgz" \) | sort | head -n 1
}

link_runtime_root_to_install_dir() {
  local runtime_root="$1"

  if [ -z "$runtime_root" ] || [ ! -d "$runtime_root" ]; then
    echo "Error: Invalid browser runtime root '$runtime_root'."
    exit 1
  fi

  rm -rf "$INSTALL_DIR"
  ln -s "$runtime_root" "$INSTALL_DIR"
}

find_browser_runtime_root_for_installed_package() {
  local package_name="$1"
  local installed_path=""
  local candidate_dir=""

  [ -n "$package_name" ] || return 1

  while IFS= read -r installed_path; do
    [ -n "$installed_path" ] || continue

    if [ -d "$installed_path" ]; then
      candidate_dir="$installed_path"
    else
      candidate_dir="$(dirname "$installed_path")"
    fi

    if browser_runtime_looks_complete "$candidate_dir"; then
      echo "$candidate_dir"
      return 0
    fi
  done < <(dpkg -L "$package_name" 2>/dev/null | sort -u)
}

set_default_flag() {
  local defaults_file="$1"
  local key="$2"
  local value="$3"

  mkdir -p "$(dirname "$defaults_file")"
  touch "$defaults_file"

  if grep -q "^${key}=" "$defaults_file"; then
    sed -i "s#^${key}=.*#${key}=\"${value}\"#" "$defaults_file"
  else
    printf '%s="%s"\n' "$key" "$value" >> "$defaults_file"
  fi
}

disable_browser_repo_updates() {
  local package_name="$1"
  local defaults_file=""

  case "$package_name" in
  chromium-browser*)
    defaults_file="/etc/default/chromium-browser"
    ;;
  google-chrome*)
    defaults_file="/etc/default/google-chrome"
    ;;
  *)
    return 0
    ;;
  esac

  set_default_flag "$defaults_file" "repo_add_once" "false"
  set_default_flag "$defaults_file" "repo_reenable_on_distupgrade" "false"
}

stop_browser_repo_jobs() {
  if ! command -v pkill >/dev/null 2>&1; then
    return 0
  fi

  pkill -f '/etc/cron.daily/chromium-browser' >/dev/null 2>&1 || true
  pkill -f '/etc/cron.daily/google-chrome' >/dev/null 2>&1 || true
}

cleanup_browser_repo_artifacts() {
  local apt_sources_dir="/etc/apt/sources.list.d"
  local apt_trusted_dir="/etc/apt/trusted.gpg.d"

  if command -v apt-config >/dev/null 2>&1; then
    eval "$(
      apt-config shell \
        APT_SOURCESDIR 'Dir::Etc::sourceparts/d' \
        APT_TRUSTEDDIR 'Dir::Etc::trustedparts/d'
    )"
    apt_sources_dir="${APT_SOURCESDIR:-$apt_sources_dir}"
    apt_trusted_dir="${APT_TRUSTEDDIR:-$apt_trusted_dir}"
  fi

  rm -f \
    "${apt_sources_dir%/}/chromium-browser.list" \
    "${apt_sources_dir%/}/google-chrome.list" \
    "${apt_trusted_dir%/}/chromium-browser.gpg" \
    "${apt_trusted_dir%/}/google-chrome.gpg"
}

install_package_file_to_install_dir() {
  local package_path="$1"

  case "$package_path" in
  *.deb)
    install_deb_to_install_dir "$package_path"
    ;;
  *.zip)
    extract_archive_to_install_dir "$package_path" "zip"
    ;;
  *.tar.gz | *.tgz)
    extract_archive_to_install_dir "$package_path" "tar.gz"
    ;;
  *)
    echo "Error: Unsupported nested browser package '$package_path'."
    exit 1
    ;;
  esac
}

extract_archive_to_install_dir() {
  local archive_path="$1"
  local archive_format="$2"
  local temp_extract_dir
  local source_dir
  local runtime_root
  local nested_package

  temp_extract_dir=$(mktemp -d)

  if [ "$archive_format" = "zip" ]; then
    unzip -oq "$archive_path" -d "$temp_extract_dir"
  else
    tar -xzf "$archive_path" -C "$temp_extract_dir"
  fi

  source_dir="$(normalize_archive_source_dir "$temp_extract_dir")"
  runtime_root="$(find_browser_runtime_root "$source_dir")"

  if [ -n "$runtime_root" ]; then
    move_dir_contents_to_install_dir "$runtime_root"
    rm -rf "$temp_extract_dir"
    return 0
  fi

  nested_package="$(find_nested_browser_package "$source_dir")"
  if [ -n "$nested_package" ]; then
    echo "Found nested browser package in archive: $nested_package"
    install_package_file_to_install_dir "$nested_package"
    rm -rf "$temp_extract_dir"
    return 0
  fi

  move_dir_contents_to_install_dir "$source_dir"

  rm -rf "$temp_extract_dir"
}

install_deb_to_install_dir() {
  local deb_path="$1"
  local package_name=""
  local runtime_root

  package_name=$(dpkg-deb -f "$deb_path" Package 2>/dev/null || true)

  echo "Installing .deb package via apt: $deb_path"
  apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 update
  DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 install --fix-missing -y --no-install-recommends "$deb_path"

  disable_browser_repo_updates "$package_name"
  stop_browser_repo_jobs
  cleanup_browser_repo_artifacts
  sleep 1
  stop_browser_repo_jobs
  cleanup_browser_repo_artifacts
  rm -rf /var/lib/apt/lists/*

  runtime_root=$(find_browser_runtime_root_for_installed_package "$package_name" || true)
  if [ -z "$runtime_root" ]; then
    runtime_root=$(find_browser_runtime_root "/" || true)
  fi

  if [ -z "$runtime_root" ]; then
    echo "Error: Could not find browser runtime root after deb installation."
    if [ -n "$package_name" ]; then
      echo "Installed package files:"
      dpkg -L "$package_name" 2>/dev/null || true
    fi
    exit 1
  fi

  link_runtime_root_to_install_dir "$runtime_root"
}

find_browser_executable() {
  local candidate=""
  local -a preferred_candidates=(
    "$INSTALL_DIR/chrome"
    "$INSTALL_DIR/chromium"
    "$INSTALL_DIR/chromium-browser"
    "$INSTALL_DIR/google-chrome-stable"
    "$INSTALL_DIR/opt/google/chrome/google-chrome-stable"
    "$INSTALL_DIR/usr/lib/chromium/chromium"
    "$INSTALL_DIR/usr/lib/chromium-browser/chromium-browser"
  )

  for candidate in "${preferred_candidates[@]}"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done

  find "$INSTALL_DIR" -type f \( -name "chrome" -o -name "chromium" -o -name "chromium-browser" -o -name "google-chrome-stable" \) -executable | sort | head -n 1
}

# --- Main Logic Functions ---

# Function to handle the installation of the browser.
install_browser() {
  local source="$1"
  local url=""

  # Detect CPU architecture and set a suffix for variable names
  # Prefer TARGETARCH (set by Docker buildx) over uname -m
  local arch_suffix
  if [ -n "${TARGETARCH:-}" ]; then
    if [ "$TARGETARCH" = "arm64" ]; then
      echo "Detected ARM64 architecture (via TARGETARCH)."
      arch_suffix="_ARM64"
    else
      echo "Detected AMD64 architecture (via TARGETARCH)."
      arch_suffix="_AMD64"
    fi
  else
    local arch
    arch=$(uname -m)
    if [ "$arch" = "aarch64" ]; then
      echo "Detected ARM64 architecture."
      arch_suffix="_ARM64"
    else
      echo "Detected AMD64 (x86_64) architecture."
      arch_suffix="_AMD64"
    fi
  fi

  # Determine the URL using a single, clean case statement
  case "$source" in
  cr)
    local url_var="CR_DOWNLOAD_URL${arch_suffix}"
    url="${!url_var}"
    ln -s /etc/browser /etc/chromium
    ;;
  rs)
    local url_var="RS_DOWNLOAD_URL${arch_suffix}"
    url="${!url_var}"
    ln -s /etc/browser /etc/chromium
    ;;
  gc)
    local url_var="GC_DOWNLOAD_URL${arch_suffix}"
    url="${!url_var}"
    mkdir -p /etc/opt/ && ln -s /etc/browser /etc/opt/chrome
    ;;
  http://* | https://*)
    url="$source"
    ;;
  *)
    echo "Error: Invalid source '$source'. Must be 'cr', 'rs', 'gc', or a valid URL." >&2
    usage
    ;;
  esac

  echo "Source set to: $source"

  local filename
  filename=$(basename "$url")
  local temp_file
  temp_file="/tmp/$filename"

  if [[ "$filename" == *.deb ]]; then
    :
  elif [[ "$filename" == *.zip ]] || [[ "$filename" == *.tar.gz ]] || [[ "$filename" == *.tgz ]]; then
    if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR")" ]; then
      echo "Error: An existing installation was found in the target directory '$INSTALL_DIR'."
      echo "Please remove this directory manually before proceeding: rm -rf $INSTALL_DIR"
      exit 1
    fi
  else
    echo "Error: Unsupported file type '$filename'."
    exit 1
  fi

  echo "Downloading from: $url"
  curl -# -L --retry 5 --retry-delay 5 --retry-all-errors -C - --http1.1 -o "$temp_file" "$url"
  echo "Download complete."

  local executable_path=""
  if [[ "$filename" == *.deb ]]; then
    echo "Installing .deb package to $INSTALL_DIR..."
    install_deb_to_install_dir "$temp_file"
    if ! validate_browser_install_dir; then
      echo "Contents of $INSTALL_DIR:"
      find "$INSTALL_DIR" -maxdepth 2 -mindepth 1 2>/dev/null || true
      exit 1
    fi
    executable_path=$(find_browser_executable)
  elif [[ "$filename" == *.zip ]]; then
    echo "Installing from .zip package..."
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 update

    # Steps to find Chromium dependencies on Ubuntu 22.04-x64 system
    # The following steps are used to obtain the dependency library information required by a specific version of Chromium on Ubuntu 22.04-x64 system
    #
    # 1. Clone the Playwright repository
    #    Clone the source code of Microsoft's Playwright project using the git command to get the complete codebase
    #       `git clone https://github.com/microsoft/playwright.git`
    #
    # 2. Enter the repository directory
    #    Switch to the cloned cloned playwright directory that was cloned to perform subsequent operations
    #       `cd playwright`
    #
    # 3. View the commit history of the browsers.json file
    #    This file records browser version information. By checking its commit history, you can find the commit record corresponding to the target Chromium version
    #       `git log packages/playwright-core/browsers.json`
    #
    # 4. Search for the commit corresponding to the target version
    #    In the log output from the above command, find the commit record that contains the target Chromium version (e.g., r1155) and get the corresponding commit id
    #
    # 5. View the content of the nativeDeps.ts file in that commit
    #    The nativeDeps.ts file stores dependency information for various browsers on different platforms. View the content of this file at the corresponding version by specifying the commit id
    #       `git show <corresponding-commitid>:packages/playwright-core/src/server/registry/nativeDeps.ts`
    #
    # 6. Extract Chromium dependencies corresponding to Ubuntu 22.04-x64
    #    In the content output from the above command, find the "chromium" dependency array under the "ubuntu22.04-x64" configuration, which contains the dependency libraries required to run Chromium in this environment
    #
    # 7. Copy the dependency information
    #    Copy the found Chromium dependency information to the required location for environment configuration or dependency installation
    DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=120 install --fix-missing -y --no-install-recommends libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 libpango-1.0-0 libwayland-client0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2

    extract_archive_to_install_dir "$temp_file" "zip"
    if ! validate_browser_install_dir; then
      echo "Contents of $INSTALL_DIR:"
      find "$INSTALL_DIR" -maxdepth 2 -mindepth 1 2>/dev/null || true
      exit 1
    fi
    executable_path=$(find_browser_executable)
    if [ -z "$executable_path" ]; then
      echo "Error: Could not find 'chrome' or 'chromium' executable in the zip file."
      exit 1
    fi
  elif [[ "$filename" == *.tar.gz ]] || [[ "$filename" == *.tgz ]]; then
    echo "Installing from .tar.gz package..."
    extract_archive_to_install_dir "$temp_file" "tar.gz"
    if ! validate_browser_install_dir; then
      echo "Contents of $INSTALL_DIR:"
      find "$INSTALL_DIR" -maxdepth 2 -mindepth 1 2>/dev/null || true
      exit 1
    fi
    executable_path=$(find_browser_executable)
    if [ -z "$executable_path" ]; then
      echo "Error: Could not find browser executable in the tar.gz package."
      exit 1
    fi
  fi

  setup_alternatives "$executable_path" 150
  restart_browser_if_running

  echo "Cleaning up downloaded file..."
  rm "$temp_file"
  echo "Installation script finished successfully."
}

# Function to set/replace browser arguments.
set_browser_args() {
  if [ ! -f "$SUPERVISOR_CONF" ]; then
    echo "Error: Supervisor config file not found at $SUPERVISOR_CONF"
    exit 1
  fi
  local new_args="$1"
  echo "Setting new arguments: $new_args"
  sed -i.bak -E "s#(command=${ALT_LINK}).*#\1 $new_args#" "$SUPERVISOR_CONF"
  echo "Arguments have been set."
  reload_and_restart_supervisor
}

# Function to append arguments to the existing ones.
append_browser_args() {
  if [ ! -f "$SUPERVISOR_CONF" ]; then
    echo "Error: Supervisor config file not found at $SUPERVISOR_CONF"
    exit 1
  fi
  local extra_args="$1"
  echo "Appending arguments: $extra_args"
  sed -i.bak "/^command=/ s/$/ $extra_args/" "$SUPERVISOR_CONF"
  echo "Arguments have been appended."
  reload_and_restart_supervisor
}

# --- Main Logic ---

# Check for root privileges
if [ "$(id -u)" != 0 ]; then
  echo "This script must be run as root"
  exit 1
fi

# Check if a command is provided
if [ -z "${1:-}" ]; then
  echo "Error: No command specified."
  usage
fi

COMMAND=$1
shift # Remove the command from the arguments list

# Process the command
case "$COMMAND" in
install)
  if [ $# -ne 1 ]; then
    echo "Error: 'install' requires exactly one argument (source)."
    usage
  fi
  install_browser "$1"
  ;;
set-args)
  if [ $# -ne 1 ]; then
    echo "Error: 'set-args' requires exactly one argument (a string of arguments)."
    usage
  fi
  set_browser_args "$1"
  ;;
append-args)
  if [ $# -ne 1 ]; then
    echo "Error: 'append-args' requires exactly one argument (a string of arguments)."
    usage
  fi
  append_browser_args "$1"
  ;;
*)
  echo "Error: Unknown command '$COMMAND'"
  usage
  ;;
esac

exit 0
