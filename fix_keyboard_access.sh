#!/bin/bash
set -e

echo "================================"
echo "🔧 Fixing Keyboard Access"
echo "================================"
echo ""

# Create udev rule to allow all users to access input devices
echo "Creating udev rule..."
echo 'KERNEL=="event*", SUBSYSTEM=="input", MODE="0666"' | sudo tee /etc/udev/rules.d/99-input-access.rules > /dev/null

# Reload udev rules
echo "Reloading udev rules..."
sudo udevadm control --reload-rules
sudo udevadm trigger

echo ""
echo "================================"
echo "✓ DONE!"
echo "================================"
echo ""
echo "Keyboard input is now accessible to all users."
echo "You can now use Alt double-tap without group membership!"
echo ""
