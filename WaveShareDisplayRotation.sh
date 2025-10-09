sudo apt update
sudo apt install wlr-randr


mkdir -p /home/daniel/.config/autostart
cat > /home/daniel/.config/autostart/rotate-wayland.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Rotate Screen (Wayland)
Exec=/usr/bin/wlr-randr --output HDMI-A-1 --transform 180
X-GNOME-Autostart-enabled=true
EOF

sudo reboot
