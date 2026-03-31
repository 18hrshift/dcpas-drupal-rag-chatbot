#!/usr/bin/env bash
# deploy.sh — Sync dcpas_chatbot to the local Drupal install and clear cache
#
# Usage:
#   ./deploy.sh                     # deploy with defaults
#   ./deploy.sh /custom/module/dir  # override target module dir
#
# Requires sudo for writes into /var/www/html

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
MODULE_DIR="${1:-/var/www/html/dcpas-dev/web/modules/contrib}"
DRUPAL_ROOT="/var/www/html/dcpas-dev"
LOCAL_MODULE="$(cd "$(dirname "$0")/drupal/dcpas_chatbot" && pwd)"
TARGET="$MODULE_DIR/dcpas_chatbot"

# ── Sanity check ─────────────────────────────────────────────────────────────
if [[ ! -d "$LOCAL_MODULE" ]]; then
  echo "ERROR: module not found at $LOCAL_MODULE" >&2
  exit 1
fi

if [[ ! -d "$MODULE_DIR" ]]; then
  echo "ERROR: target directory not found: $MODULE_DIR" >&2
  exit 1
fi

# ── Backup ───────────────────────────────────────────────────────────────────
if [[ -d "$TARGET" ]]; then
  echo "==> Backing up existing module → ${TARGET}.bak"
  sudo rm -rf "${TARGET}.bak"
  sudo cp -a "$TARGET" "${TARGET}.bak"
fi

# ── Sync ─────────────────────────────────────────────────────────────────────
echo "==> Syncing $LOCAL_MODULE → $TARGET"
sudo rsync -a --delete "$LOCAL_MODULE/" "$TARGET/"

# ── Cache clear ──────────────────────────────────────────────────────────────
echo "==> Running drush cr"
cd "$DRUPAL_ROOT"
sudo ./vendor/bin/drush cr

echo "==> Done."
