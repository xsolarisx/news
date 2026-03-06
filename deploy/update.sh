#!/usr/bin/env bash
# update.sh — pull the latest code and restart the news-digest timer.
# Run as root inside the LXC container from the directory that contains the
# updated source files.
# Usage: bash update.sh [path/to/source/dir]
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (must match setup.sh)
# ---------------------------------------------------------------------------
INSTALL_DIR="/opt/news-digest"
VENV_DIR="${INSTALL_DIR}/venv"
SERVICE_USER="newsdigest"
TIMER_UNIT="news-digest.timer"
SERVICE_UNIT="news-digest.service"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${1:-${SCRIPT_DIR}}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info() { echo "[INFO]  $*"; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "This script must be run as root."
}

# ---------------------------------------------------------------------------
# 1. Validate source
# ---------------------------------------------------------------------------
validate_source() {
    info "Source directory: ${SOURCE_DIR}"
    [[ -f "${SOURCE_DIR}/news_digest.py" ]] \
        || die "news_digest.py not found in ${SOURCE_DIR}"
}

# ---------------------------------------------------------------------------
# 2. Copy updated script
# ---------------------------------------------------------------------------
copy_script() {
    info "Copying news_digest.py to ${INSTALL_DIR}..."
    cp "${SOURCE_DIR}/news_digest.py" "${INSTALL_DIR}/news_digest.py"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/news_digest.py"
    info "Script updated."
}

# ---------------------------------------------------------------------------
# 3. Optionally update config and requirements
# ---------------------------------------------------------------------------
copy_optional_files() {
    if [[ -f "${SOURCE_DIR}/config.toml" ]]; then
        info "Copying config.toml..."
        cp "${SOURCE_DIR}/config.toml" "${INSTALL_DIR}/config.toml"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/config.toml"
    fi

    if [[ -f "${SOURCE_DIR}/requirements.txt" ]]; then
        info "Copying requirements.txt..."
        cp "${SOURCE_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
        chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/requirements.txt"
    fi
}

# ---------------------------------------------------------------------------
# 4. Upgrade Python dependencies
# ---------------------------------------------------------------------------
upgrade_deps() {
    if [[ -f "${INSTALL_DIR}/requirements.txt" ]]; then
        info "Upgrading Python dependencies in venv..."
        sudo -u "${SERVICE_USER}" \
            "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
        sudo -u "${SERVICE_USER}" \
            "${VENV_DIR}/bin/pip" install --quiet --upgrade \
            -r "${INSTALL_DIR}/requirements.txt"
        info "Dependencies upgraded."
    else
        info "requirements.txt not found in ${INSTALL_DIR} — skipping pip upgrade."
    fi
}

# ---------------------------------------------------------------------------
# 5. Reload systemd units if they changed
# ---------------------------------------------------------------------------
reload_systemd_units() {
    local changed=0

    for unit in news-digest.service news-digest.timer; do
        if [[ -f "${SOURCE_DIR}/${unit}" ]]; then
            local dest="/etc/systemd/system/${unit}"
            # Only copy+reload if the file actually differs
            if ! diff -q "${SOURCE_DIR}/${unit}" "${dest}" &>/dev/null; then
                info "Updating systemd unit: ${unit}"
                cp "${SOURCE_DIR}/${unit}" "${dest}"
                chmod 644 "${dest}"
                changed=1
            fi
        fi
    done

    if [[ "${changed}" -eq 1 ]]; then
        info "Reloading systemd daemon..."
        systemctl daemon-reload
    fi
}

# ---------------------------------------------------------------------------
# 6. Restart the timer (and stop any running service instance)
# ---------------------------------------------------------------------------
restart_timer() {
    info "Restarting ${TIMER_UNIT}..."

    # If the one-shot service is currently running, stop it gracefully first.
    if systemctl is-active --quiet "${SERVICE_UNIT}"; then
        info "Stopping running instance of ${SERVICE_UNIT}..."
        systemctl stop "${SERVICE_UNIT}"
    fi

    systemctl restart "${TIMER_UNIT}"
    systemctl status "${TIMER_UNIT}" --no-pager || true
    info "Timer restarted. Next scheduled run:"
    systemctl list-timers "${TIMER_UNIT}" --no-pager || true
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    require_root
    info "Starting news-digest update from '${SOURCE_DIR}'..."

    validate_source
    copy_script
    copy_optional_files
    upgrade_deps
    reload_systemd_units
    restart_timer

    info "-----------------------------------------------------"
    info "Update complete."
    info "  To run immediately: systemctl start news-digest.service"
    info "  To watch logs:      journalctl -fu news-digest.service"
    info "-----------------------------------------------------"
}

main "$@"
