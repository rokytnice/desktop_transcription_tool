#!/bin/bash
set -e

echo "================================"
echo "🎙️  Desktop Transcription Tool"
echo "Installation Script"
echo "================================"
echo ""

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 1. System packages
echo "[1/5] Installing system packages..."
sudo apt update
sudo apt install -y ffmpeg xdotool python3-pip python3-venv
echo "✓ System packages installed"
echo ""

# 2. Python virtual environment
echo "[2/5] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# 3. Keyboard access fix (udev rule)
echo "[3/5] Setting up keyboard access..."
bash fix_keyboard_access.sh
echo "✓ Keyboard access configured"
echo ""

# 4. Systemd service
echo "[4/5] Installing systemd service..."
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/transcribe.service << 'EOF'
[Unit]
Description=Transcription Daemon - Alt Double-Tap Recording
After=network.target

[Service]
Type=simple
ExecStart=/home/aroc/projects/desktop_transcription_tool_/.venv/bin/python3 /home/aroc/projects/desktop_transcription_tool_/transcribe_daemon_v3.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable transcribe
echo "✓ Systemd service installed"
echo ""

# 5. ydotool system service (for text injection)
echo "[5/5] Checking ydotool..."
if command -v ydotool &> /dev/null; then
    echo "✓ ydotool already installed"
else
    echo "⚠️  ydotool not found - you may need to build it:"
    echo "   git clone https://github.com/ReimuNotMoe/ydotool.git"
    echo "   cd ydotool && mkdir build && cd build && cmake .. && make && sudo make install"
fi
echo ""

# 6. Bashrc setup
echo "[OPTIONAL] Adding input group auto-activation to ~/.bashrc..."
if ! grep -q "newgrp input" ~/.bashrc; then
    cat >> ~/.bashrc << 'EOF'

# Activate input group for keyboard access (transcription tool)
if ! id -G | grep -q 995; then
    exec newgrp input
fi
EOF
    echo "✓ Added to ~/.bashrc"
else
    echo "✓ Already in ~/.bashrc"
fi
echo ""

echo "================================"
echo "✅ INSTALLATION COMPLETE!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Close and reopen terminal (to activate input group)"
echo "2. Run: ./start.sh"
echo "3. Press Alt TWICE to record"
echo "4. Speak German"
echo "5. Press Alt TWICE to transcribe and inject text"
echo ""
echo "Usage:"
echo "  ./start.sh     Start the system (shows live logs)"
echo "  systemctl --user status transcribe    Check daemon status"
echo "  systemctl --user stop transcribe      Stop daemon"
echo ""
