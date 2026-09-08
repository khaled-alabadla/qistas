#!/usr/bin/env bash
# Fetch the Tailwind CSS standalone CLI into ./bin/tailwindcss (gitignored).
# docs/adr/0024 — no Node build pipeline in the Django repo.
set -euo pipefail

TAILWIND_VERSION="${TAILWIND_VERSION:-v3.4.17}"
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/bin"
mkdir -p "$BIN_DIR"
TARGET="$BIN_DIR/tailwindcss"

if [ -x "$TARGET" ]; then
    echo "Tailwind CLI already present: $($TARGET --help 2>/dev/null | head -1 || true)"
    exit 0
fi

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)        ASSET="tailwindcss-linux-x64" ;;
    Linux-aarch64)       ASSET="tailwindcss-linux-arm64" ;;
    Darwin-x86_64)       ASSET="tailwindcss-macos-x64" ;;
    Darwin-arm64)        ASSET="tailwindcss-macos-arm64" ;;
    MINGW*|MSYS*|CYGWIN*) ASSET="tailwindcss-windows-x64.exe"; TARGET="$TARGET.exe" ;;
    *)                   ASSET="tailwindcss-linux-x64" ;;
esac

URL="https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/${ASSET}"
echo "Downloading ${URL}"
curl -sSL --fail -o "$TARGET" "$URL"
chmod +x "$TARGET"
echo "Installed $($TARGET --help 2>/dev/null | head -1 || echo "$TARGET")"
