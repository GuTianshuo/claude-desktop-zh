#!/usr/bin/env bash
# Install the patched archives (needs sudo once per Claude Desktop upgrade).
#
#   ./scripts/apply.sh [--app /usr/lib/claude-desktop] [--work ~/.cache/claude-desktop-zh]
#
# Build first with:
#   python scripts/extract.py --work "$WORK"
#   python scripts/run_translate.py --work "$WORK"
#   python scripts/build.py --work "$WORK"
set -euo pipefail

APP="${CLAUDE_DESKTOP_DIR:-/usr/lib/claude-desktop}"
WORK="${WORK:-$HOME/.cache/claude-desktop-zh}"

while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    --work) WORK="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

RES="$APP/resources"
# suffix backups with the app version (from the archive, not the Electron build id)
VERSION="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" \
  "$WORK/extract/app/package.json" 2>/dev/null || echo unknown)"
STAMP="orig-$VERSION"

for name in app.asar ion-dist.asar; do
  if [ ! -f "$RES/$name.$STAMP" ]; then
    echo "backup -> $RES/$name.$STAMP"
    sudo cp "$RES/$name" "$RES/$name.$STAMP"
  fi
done

echo "applying patched archives"
sudo cp "$WORK/out/app.asar" "$RES/app.asar"
sudo cp "$WORK/out/ion-dist.asar" "$RES/ion-dist.asar"
if [ -d "$WORK/out/app.asar.unpacked" ]; then
  sudo cp -r "$WORK/out/app.asar.unpacked/." "$RES/app.asar.unpacked/"
fi
echo "done - restart Claude Desktop"
