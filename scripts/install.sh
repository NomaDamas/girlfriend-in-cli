#!/usr/bin/env bash
set -euo pipefail

# Girlfriend Generator - Global Install Script
# Usage: bash scripts/install.sh
# After install: just type `mygf` anywhere in your terminal

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo ""
echo "  Installing Girlfriend Generator..."
echo ""

if ! command -v uv >/dev/null 2>&1; then
    echo "  [ERROR] uv is required for this install path."
    echo "  Install uv first: brew install uv"
    echo "  Or see: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Create/update project environment with uv
uv sync --extra dev >/dev/null

# Get the path to the installed binary
MYGF_PATH="$ROOT_DIR/.venv/bin/mygf"
if [ ! -x "$MYGF_PATH" ]; then
    echo "  [ERROR] Installation failed."
    exit 1
fi

# Create a global wrapper script
INSTALL_DIR="$HOME/.local/bin"
mkdir -p "$INSTALL_DIR"

cat > "$INSTALL_DIR/mygf" << WRAPPER
#!/usr/bin/env bash
export GIRLFRIEND_GENERATOR_ROOT="$ROOT_DIR"
exec "$ROOT_DIR/.venv/bin/python" -m girlfriend_generator "\$@"
WRAPPER
chmod +x "$INSTALL_DIR/mygf"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    SHELL_RC=""
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$SHELL_RC" 2>/dev/null; then
            echo '' >> "$SHELL_RC"
            echo '# Girlfriend Generator' >> "$SHELL_RC"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
            echo "  Added ~/.local/bin to PATH in $SHELL_RC"
        fi
    fi
fi

echo ""
echo "  Installed successfully!"
echo ""
echo "  Usage:"
echo "    mygf              Open main menu"
echo "    mygf --help       Show all options"
echo ""
echo "  If 'mygf' is not found, run:"
echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
echo "  or restart your terminal."
echo ""
