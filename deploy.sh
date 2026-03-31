#!/usr/bin/env bash
# deploy.sh — Pull dcpas_chatbot from GitHub and deploy to the local Drupal install
#
# Usage (run on the Drupal server):
#   sudo ./deploy.sh               # deploy from default branch (develop)
#   sudo ./deploy.sh main          # deploy a different branch

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
BRANCH="${1:-develop}"
REPO="18hrshift/dcpas-drupal-rag-chatbot"
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

MODULE_DIR="/var/www/html/dcpas-dev/web/modules/contrib"
DRUPAL_ROOT="/var/www/html/dcpas-dev"
TARGET="$MODULE_DIR/dcpas_chatbot"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# ── Download ──────────────────────────────────────────────────────────────────
echo "==> Downloading $ZIP_URL"
wget -q --show-progress -O "$WORK_DIR/repo.zip" "$ZIP_URL"

# ── Extract ───────────────────────────────────────────────────────────────────
echo "==> Extracting"
unzip -q "$WORK_DIR/repo.zip" -d "$WORK_DIR"

# GitHub zip extracts to <repo>-<branch>/
EXTRACTED="$WORK_DIR/$(ls "$WORK_DIR" | grep -v repo.zip | head -1)"
MODULE_SRC="$EXTRACTED/drupal/dcpas_chatbot"

if [[ ! -d "$MODULE_SRC" ]]; then
  echo "ERROR: dcpas_chatbot not found in extracted archive at $MODULE_SRC" >&2
  exit 1
fi

# ── Backup ────────────────────────────────────────────────────────────────────
if [[ -d "$TARGET" ]]; then
  echo "==> Backing up existing module → ${TARGET}.bak"
  rm -rf "${TARGET}.bak"
  cp -a "$TARGET" "${TARGET}.bak"
fi

# ── Deploy ────────────────────────────────────────────────────────────────────
echo "==> Deploying module to $TARGET"
rsync -a --delete "$MODULE_SRC/" "$TARGET/"

# ── Cache clear ───────────────────────────────────────────────────────────────
echo "==> Running drush cr"
cd "$DRUPAL_ROOT"
./vendor/bin/drush cr

echo "==> Done. Deployed branch: $BRANCH"
