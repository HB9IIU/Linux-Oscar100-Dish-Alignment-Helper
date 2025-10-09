#!/bin/bash
set -e


SERVICE_NAME="encoderServiceForSDRpp"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="${USER_SYSTEMD_DIR}/${SERVICE_NAME}.service"


echo "📥 Downloading Encoder Handler for SDRpp"
cd "$HOME/hb9iiu_dishaligner/"
curl -L -o encoderHandlerForSDRpp.py \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/encoderHandlerForSDRpp.py

echo "📝 Creating user service in ${SERVICE_FILE}..."
mkdir -p ${USER_SYSTEMD_DIR}
cat > ${SERVICE_FILE} <<EOF
[Unit]
Description=Encoder Service for SDR++

[Service]
ExecStart=${HOME}/hb9iiu_dishaligner/bin/python3 ${HOME}/hb9iiu_dishaligner/encoderHandlerForSDRpp.py
Restart=always
RestartSec=5
WorkingDirectory=${HOME}/hb9iiu_dishaligner

[Install]
WantedBy=default.target
EOF

echo "🔄 Reloading user systemd..."
systemctl --user daemon-reload

echo "✅ Enabling user service..."
systemctl --user enable ${SERVICE_NAME}.service

echo "🚀 Starting user service..."
systemctl --user start ${SERVICE_NAME}.service

echo "🔓 Enabling linger so user services run at boot..."
sudo loginctl enable-linger "$(whoami)"

echo "📡 Done!"
echo "Check status with: systemctl --user status ${SERVICE_NAME}.service"



AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/sdrpp.desktop"

echo "📝 Creating SDR++ autostart entry at ${AUTOSTART_FILE}..."
mkdir -p "${AUTOSTART_DIR}"
cat > "${AUTOSTART_FILE}" <<EOF
[Desktop Entry]
Type=Application
Name=SDR++
Exec=/usr/bin/sdrpp --autostart
Comment=Start SDR++ automatically
X-GNOME-Autostart-enabled=true
Categories=AudioVideo;HamRadio;
EOF

echo "📡 Done!"
echo "SDR++ will now launch automatically with your desktop session."