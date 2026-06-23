#!/bin/bash

# Desktop Transcription Tool - Master Installation Script
# Installiert alle Tools und Abhängigkeiten

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║  🎤 Desktop Transcription Tool - Installation     ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. System dependencies
echo -e "${BLUE}[1/5]${NC} Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    wl-clipboard \
    ydotool \
    wtype \
    alsa-utils \
    pulseaudio-utils \
    portaudio19-dev \
    libsndfile1-dev > /dev/null 2>&1

echo -e "${GREEN}✓ System dependencies installed${NC}\n"

# 2. Create virtual environment (if not exists)
echo -e "${BLUE}[2/5]${NC} Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv > /dev/null 2>&1
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
else
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}\n"
fi

# 3. Install all requirements
echo -e "${BLUE}[3/5]${NC} Installing Python packages for all tools..."
source .venv/bin/activate

pip install --break-system-packages --upgrade pip setuptools wheel > /dev/null 2>&1

# Install offline requirements
echo "   → offline/ (Whisper)"
pip install --break-system-packages -q -r offline/requirements.txt

# Install big_audio_file requirements
if [ -f "big_audio_file_transcription/requirements.txt" ]; then
    echo "   → big_audio_file_transcription/ (Große Dateien)"
    pip install --break-system-packages -q -r big_audio_file_transcription/requirements.txt
fi

echo -e "${GREEN}✓ All packages installed${NC}\n"

# 4. Make scripts executable
echo -e "${BLUE}[4/6]${NC} Making scripts executable..."
chmod +x offline/transcription_offline.py
chmod +x offline/transcription_streaming.py
chmod +x offline/install.sh
chmod +x offline/run.sh
chmod +x install.sh
chmod +x enable-service.sh
chmod +x restart-transcription-service.sh
echo -e "${GREEN}✓ Scripts are executable${NC}\n"

# 5. Install service + global commands
echo -e "${BLUE}[5/6]${NC} Installing systemd service and global commands..."

mkdir -p ~/.config/systemd/user
cp "$SCRIPT_DIR/transcription-offline.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable transcription-offline.service

mkdir -p ~/.local/bin

cat > ~/.local/bin/transcription-restart << SCRIPT
#!/bin/bash
systemctl --user restart transcription-offline.service
systemctl --user status transcription-offline.service --no-pager
SCRIPT

cat > ~/.local/bin/transcription-stop << SCRIPT
#!/bin/bash
systemctl --user stop transcription-offline.service
echo "Service stopped."
SCRIPT

cat > ~/.local/bin/transcription-start << SCRIPT
#!/bin/bash
systemctl --user start transcription-offline.service
systemctl --user status transcription-offline.service --no-pager
SCRIPT

cat > ~/.local/bin/transcription-status << SCRIPT
#!/bin/bash
systemctl --user status transcription-offline.service --no-pager
SCRIPT

chmod +x ~/.local/bin/transcription-restart
chmod +x ~/.local/bin/transcription-stop
chmod +x ~/.local/bin/transcription-start
chmod +x ~/.local/bin/transcription-status

# Ensure ~/.local/bin is in PATH
if ! grep -q 'local/bin' ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

echo -e "${GREEN}✓ Service enabled, global commands installed${NC}"
echo -e "   ${YELLOW}transcription-restart${NC}  restart-service"
echo -e "   ${YELLOW}transcription-start${NC}    start service"
echo -e "   ${YELLOW}transcription-stop${NC}     stop service"
echo -e "   ${YELLOW}transcription-status${NC}   show status"
echo -e "   (Run ${YELLOW}source ~/.bashrc${NC} if commands not found yet)\n"

# 6. Make management scripts executable
echo -e "${BLUE}[6/6]${NC} Finalizing..."
chmod +x run_offline.sh run_streaming.sh enable-service.sh restart-transcription-service.sh
echo -e "${GREEN}✓ Done${NC}\n"

# Summary
echo "╔════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✓ Installation Complete!${NC}                      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo -e "${BLUE}🔧 Service Commands (überall ausführbar):${NC}"
echo -e "   ${YELLOW}transcription-restart${NC}  Service neu starten"
echo -e "   ${YELLOW}transcription-start${NC}    Service starten"
echo -e "   ${YELLOW}transcription-stop${NC}     Service stoppen"
echo -e "   ${YELLOW}transcription-status${NC}   Status anzeigen"
echo ""
echo -e "${BLUE}🚀 Starten (klassisch: aufnehmen → stoppen → einfügen):${NC}"
echo -e "   ${YELLOW}./run_offline.sh${NC}        Interaktive Geräteauswahl"
echo -e "   ${YELLOW}./run_offline.sh -a${NC}     Ein Gerät für Input + Output"
echo -e "   ${YELLOW}./run_offline.sh -d${NC}     Schnellstart mit Defaults"
echo -e "   ${YELLOW}./run_offline.sh --help${NC} Alle Optionen anzeigen"
echo ""
echo -e "${BLUE}⚡ Streaming (live tippen am Cursor während des Sprechens):${NC}"
echo -e "   ${YELLOW}./run_streaming.sh${NC}        Interaktive Geräteauswahl"
echo -e "   ${YELLOW}./run_streaming.sh -a${NC}     Ein Gerät für Input + Output"
echo -e "   ${YELLOW}./run_streaming.sh --help${NC} Alle Optionen anzeigen"
echo ""
echo -e "${BLUE}🎤 Bedienung:${NC}"
echo "   Alt Tap Tap  → Aufnahme starten"
echo "   Sprechen"
echo "   Alt Tap Tap  → Stoppen + transkribieren"
echo "   Ctrl+V       → Paste text"
echo ""
echo "═══════════════════════════════════════════════════════"
echo ""
