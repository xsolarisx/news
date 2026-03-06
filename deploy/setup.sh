#!/usr/bin/env bash
# setup.sh — LXC container setup script for news-digest
# Run this once as root inside the Proxmox LXC container (Debian 12 / Ubuntu 22.04).
# Usage: bash setup.sh [path/to/source/dir]
#   The optional argument points to the directory containing news_digest.py,
#   config.toml, and requirements.txt. Defaults to the script's own directory.
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTALL_DIR="/opt/news-digest"
VENV_DIR="${INSTALL_DIR}/venv"
OUTPUT_DIR="${INSTALL_DIR}/output"
LOG_DIR="/var/log/news-digest"
ENV_DIR="/etc/news-digest"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_USER="newsdigest"

# Directory containing the source files to deploy
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${1:-${SCRIPT_DIR}}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[INFO]  $*"; }
die()   { echo "[ERROR] $*" >&2; exit 1; }

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "This script must be run as root."
}

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
install_packages() {
    info "Updating apt and installing system packages..."
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        git \
        curl \
        ca-certificates
    info "System packages installed."
}

# ---------------------------------------------------------------------------
# 2. System user
# ---------------------------------------------------------------------------
create_user() {
    if id "${SERVICE_USER}" &>/dev/null; then
        info "User '${SERVICE_USER}' already exists — skipping creation."
    else
        info "Creating system user '${SERVICE_USER}'..."
        useradd \
            --system \
            --no-create-home \
            --shell /usr/sbin/nologin \
            --comment "news-digest service account" \
            "${SERVICE_USER}"
        info "User '${SERVICE_USER}' created."
    fi
}

# ---------------------------------------------------------------------------
# 3. Directory structure
# ---------------------------------------------------------------------------
create_directories() {
    info "Creating directory structure..."

    install -d -m 755 "${INSTALL_DIR}"
    install -d -m 755 "${OUTPUT_DIR}"
    install -d -m 750 "${ENV_DIR}"
    install -d -m 755 "${LOG_DIR}"

    # newsdigest must be able to write output and logs
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"
    # env dir is root-owned but readable by newsdigest (for EnvironmentFile)
    chown root:"${SERVICE_USER}" "${ENV_DIR}"
    chmod 750 "${ENV_DIR}"

    info "Directories created."
}

# ---------------------------------------------------------------------------
# 4. Copy application files
# ---------------------------------------------------------------------------
copy_app_files() {
    info "Copying application files from '${SOURCE_DIR}'..."

    for f in news_digest.py requirements.txt; do
        [[ -f "${SOURCE_DIR}/${f}" ]] || die "Required file not found: ${SOURCE_DIR}/${f}"
        cp "${SOURCE_DIR}/${f}" "${INSTALL_DIR}/${f}"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/${f}"
    done

    # config.toml is optional — warn but don't abort if missing
    if [[ -f "${SOURCE_DIR}/config.toml" ]]; then
        cp "${SOURCE_DIR}/config.toml" "${INSTALL_DIR}/config.toml"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/config.toml"
    else
        info "config.toml not found in source — skipping (create it manually if needed)."
    fi

    info "Application files copied."
}

# ---------------------------------------------------------------------------
# 5. Python virtual environment
# ---------------------------------------------------------------------------
setup_venv() {
    info "Setting up Python virtual environment in '${VENV_DIR}'..."

    if [[ ! -d "${VENV_DIR}" ]]; then
        python3.11 -m venv "${VENV_DIR}"
        chown -R "${SERVICE_USER}:${SERVICE_USER}" "${VENV_DIR}"
    fi

    info "Installing Python dependencies..."
    # Run pip as the service user to keep ownership clean
    sudo -u "${SERVICE_USER}" \
        "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    sudo -u "${SERVICE_USER}" \
        "${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

    info "Python dependencies installed."
}

# ---------------------------------------------------------------------------
# 6. Systemd unit files
# ---------------------------------------------------------------------------
install_systemd_units() {
    info "Installing systemd unit files..."

    for unit in news-digest.service news-digest.timer; do
        [[ -f "${SOURCE_DIR}/${unit}" ]] || die "Systemd unit not found: ${SOURCE_DIR}/${unit}"
        cp "${SOURCE_DIR}/${unit}" "${SYSTEMD_DIR}/${unit}"
        chmod 644 "${SYSTEMD_DIR}/${unit}"
    done

    systemctl daemon-reload
    info "Systemd units installed and daemon reloaded."
}

# ---------------------------------------------------------------------------
# 7. Environment file
# ---------------------------------------------------------------------------
setup_env_file() {
    local env_file="${ENV_DIR}/env"

    if [[ -f "${env_file}" ]]; then
        info "Environment file '${env_file}' already exists — not overwriting."
        info "Edit it manually to set API keys."
    else
        info "Creating stub environment file at '${env_file}'..."
        if [[ -f "${SOURCE_DIR}/env.example" ]]; then
            cp "${SOURCE_DIR}/env.example" "${env_file}"
        else
            # Minimal fallback stub
            cat > "${env_file}" <<'EOF'
# news-digest environment variables
# Fill in the values below and remove any keys you do not use.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
        fi
        chown root:"${SERVICE_USER}" "${env_file}"
        chmod 640 "${env_file}"
        info "Environment file created. Edit '${env_file}' and add your API keys before starting."
    fi
}

# ---------------------------------------------------------------------------
# 8. Enable and start the timer
# ---------------------------------------------------------------------------
enable_timer() {
    info "Enabling and starting news-digest.timer..."
    systemctl enable --now news-digest.timer
    systemctl status news-digest.timer --no-pager || true
    info "Timer enabled."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    require_root
    info "Starting news-digest deployment to LXC container..."

    install_packages
    create_user
    create_directories
    copy_app_files
    setup_venv
    install_systemd_units
    setup_env_file
    enable_timer

    info "-----------------------------------------------------"
    info "Setup complete."
    info "  App:     ${INSTALL_DIR}/news_digest.py"
    info "  Output:  ${OUTPUT_DIR}/digest.html"
    info "  Logs:    journalctl -u news-digest.service"
    info "           ${LOG_DIR}/"
    info ""
    info "ACTION REQUIRED: add your API keys to ${ENV_DIR}/env"
    info "  then run: systemctl restart news-digest.timer"
    info "-----------------------------------------------------"
}

main "$@"
