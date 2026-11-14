#!/usr/bin/env bash
# Put the untouched archives back (undo the patch).
#
#   ./scripts/restore.sh [--app /usr/lib/claude-desktop]
set -euo pipefail

APP="${CLAUDE_DESKTOP_DIR:-/usr/lib/claude-desktop}"
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

RES="$APP/resources"
mapfile -t BACKUPS < <(find "$RES" -maxdepth 1 -name 'app.asar.orig-*' -o -maxdepth 1 -name 'ion-dist.asar.orig-*' | sort)
if [ ${#BACKUPS[@]} -eq 0 ]; then
  echo "no *.orig-* backups found in $RES" >&2
  exit 1
fi

for backup in "${BACKUPS[@]}"; do
  target="${backup%%.orig-*}"
  echo "restore $backup -> $target"
  sudo cp "$backup" "$target"
done
echo "restored - restart Claude Desktop"
