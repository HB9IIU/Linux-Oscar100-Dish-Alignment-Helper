#!/bin/bash
set -e
# ============================================
# SDR++ + SDRplay + Soapy drivers + DishAligner Helper Installer
# Author: HB9IIU (enhanced install script)
# Target: Raspberry Pi (64-bit)
# ============================================

echo "🚀 Starting SDR++ and DishAligner Helper installation..."

# ------------------------------------------------------------
# Step 0: Clean up previous installation directory if exists
# ------------------------------------------------------------
cd "$HOME"
if [ -d "hb9iiu_dishaligner" ]; then
    echo "🧹 Removing old hb9iiu_dishaligner directory..."
    rm -rf hb9iiu_dishaligner/
else
    echo "ℹ️  No existing hb9iiu_dishaligner directory found."
fi

# ------------------------------------------------------------
# Step 1: Update system
# ------------------------------------------------------------
echo "🔄 Updating system packages..."
sudo DEBIAN_FRONTEND=noninteractive apt update && sudo apt upgrade -y

# ------------------------------------------------------------
# Step 2: Install build tools and core dependencies
# ------------------------------------------------------------
echo "📥 Installing build tools (cmake, make, pkg-config, git)..."
sudo apt install -y cmake build-essential pkg-config git
cmake --version && git --version

echo "📥 Installing VOLK (Vector Optimized Library of Kernels)..."
sudo apt install -y libvolk-dev
dpkg -s libvolk-dev >/dev/null && echo "✅ volk installed"

echo "📥 Installing Zstandard compression library..."
sudo apt install -y libzstd-dev
dpkg -s libzstd-dev >/dev/null && echo "✅ libzstd installed"

echo "📥 Installing RtAudio (audio I/O)..."
sudo apt install -y librtaudio-dev
dpkg -s librtaudio-dev >/dev/null && echo "✅ librtaudio installed"

echo "📥 Installing RTL-SDR development package..."
sudo apt install -y librtlsdr-dev
dpkg -s librtlsdr-dev >/dev/null && echo "✅ librtlsdr-dev installed"

echo "📥 Installing GLFW3 + OpenGL support..."
sudo apt install -y libglfw3-dev libglew-dev libgl1-mesa-dev
dpkg -s libglfw3-dev >/dev/null && echo "✅ GLFW3 installed"

echo "📥 Installing FFTW3 (fast Fourier transforms)..."
sudo apt install -y libfftw3-dev
dpkg -s libfftw3-dev >/dev/null && echo "✅ fftw3 installed"

echo "📥 Installing curl..."
sudo apt install -y curl
curl --version | head -n 1

echo "📥 Installing PyQt5 (Qt GUI support for Python)..."
sudo apt install -y python3-pyqt5 python3-pyqt5.qtquick python3-pyqt5.sip
python3 -c "import PyQt5" && echo "✅ PyQt5 installed"

# ------------------------------------------------------------
# Step 3: Install SoapySDR and SDR hardware modules
# ------------------------------------------------------------
echo "📥 Installing SoapySDR base libraries + tools + Python bindings..."
sudo apt install -y libsoapysdr-dev soapysdr-tools python3-soapysdr
soapy_config_info --info | head -n 3

echo "📥 Installing all SoapySDR hardware drivers..."
sudo apt install -y soapysdr-module-all

echo "📥 Installing RTL-SDR runtime support..."
sudo apt install -y rtl-sdr soapysdr-module-rtlsdr

echo "📥 Installing HackRF runtime support..."
sudo apt install -y hackrf soapysdr-module-hackrf

echo "📥 Installing Airspy runtime support..."
sudo apt install -y soapysdr-module-airspy

echo "📥 Installing PlutoSDR support (libiio + libad9361)..."
sudo apt install -y libiio-dev libad9361-dev

# ------------------------------------------------------------
# Step 4: Build SoapyPlutoSDR from source
# ------------------------------------------------------------
cd "$HOME"
if [ -d "$HOME/SoapyPlutoSDR" ]; then
  echo "🧹 Removing old SoapyPlutoSDR source..."
  sudo chattr -R -i "$HOME/SoapyPlutoSDR" 2>/dev/null || true
  sudo rm -rf --no-preserve-root "$HOME/SoapyPlutoSDR"
fi

echo "📥 Cloning SoapyPlutoSDR..."
git clone https://github.com/pothosware/SoapyPlutoSDR.git "$HOME/SoapyPlutoSDR"

echo "🛠️ Building SoapyPlutoSDR..."
cd "$HOME/SoapyPlutoSDR"
mkdir -p build && cd build
cmake .. && make -j$(nproc)
sudo make install
sudo ldconfig

echo "🧹 Cleaning SoapyPlutoSDR build sources..."
cd "$HOME"
sudo rm -rf --no-preserve-root "$HOME/SoapyPlutoSDR"

# ------------------------------------------------------------
# Step 5: Install SDRplay API
# ------------------------------------------------------------
echo "📥 Downloading SDRplay API (modified installer)..."
curl -L -o SDRplay_RSP_API-Linux-3.15.2-modified.run \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/SDRplay_RSP_API-Linux-3.15.2-modified.run

echo "⚙️ Installing SDRplay API..."
chmod +x SDRplay_RSP_API-Linux-3.15.2-modified.run
sudo ./SDRplay_RSP_API-Linux-3.15.2-modified.run
rm SDRplay_RSP_API-Linux-3.15.2-modified.run
echo "✅ SDRplay API installed"

# ------------------------------------------------------------
# Step 6: Build SDR++ from source
# ------------------------------------------------------------
echo "=== SDR++ Build Script for Raspberry Pi ==="

if [ -d "$HOME/SDRPlusPlus/build" ]; then
  echo "🧹 Removing old SDR++ build directory..."
  rm -rf "$HOME/SDRPlusPlus/build"
fi

echo "📥 Installing SDR++ extra dependencies..."
sudo apt install -y libhackrf-dev libairspy-dev libiio-dev libad9361-dev

if [ -d "$HOME/SDRPlusPlus" ]; then
  echo "🧹 Removing old SDR++ source..."
  rm -rf "$HOME/SDRPlusPlus"
fi

echo "📥 Cloning SDR++ source..."
git clone https://github.com/AlexandreRouma/SDRPlusPlus.git "$HOME/SDRPlusPlus"

echo "🛠️ Configuring SDR++ with CMake..."
cd "$HOME/SDRPlusPlus"
mkdir build && cd build
cmake .. \
  -DOPT_BUILD_AIRSPY_SOURCE=ON \
  -DOPT_BUILD_AIRSPYHF_SOURCE=OFF \
  -DOPT_BUILD_HACKRF_SOURCE=ON \
  -DOPT_BUILD_PLUTOSDR_SOURCE=ON \
  -DOPT_BUILD_SDRPLAY_SOURCE=ON

echo "⚙️ Building SDR++..."
make -j$(nproc)

echo "📦 Installing SDR++..."
sudo make install
sudo ldconfig
echo "✅ SDR++ installed"

echo "🔎 Verifying SDR++ installation..."
if command -v sdrpp >/dev/null 2>&1; then
  echo "✅ SDR++ binary found at: $(command -v sdrpp)"
  sdrpp --help | head -n 1
else
  echo "❌ ERROR: SDR++ not found in PATH!"
fi

# ------------------------------------------------------------
# Step 7: Install SDR++ desktop shortcut
# ------------------------------------------------------------
echo "🖥️ Creating Desktop launcher for SDR++..."
mkdir -p "$HOME/Desktop"
DESKTOP_FILE="$HOME/Desktop/SDR++.desktop"
ICON_FILE="$HOME/SDRPlusPlus/root/res/icons/sdrpp.png"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=SDR++
Comment=Launch SDR++
Exec=sdrpp --autostart
Icon=$ICON_FILE
Terminal=false
Type=Application
Categories=AudioVideo;HamRadio;
EOF

chmod +x "$DESKTOP_FILE"
gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
echo "✅ Desktop launcher created at $DESKTOP_FILE"

# ------------------------------------------------------------
# Step 8: Setup Python virtual environment for DishAligner
# ------------------------------------------------------------
echo "🐍 Creating Python virtual environment for DishAligner..."
python3 -m venv --system-site-packages "$HOME/hb9iiu_dishaligner"

echo "✅ Activating virtual environment..."
source "$HOME/hb9iiu_dishaligner/bin/activate"

echo "⬆️ Upgrading pip..."
pip install --upgrade pip

echo "📦 Installing Python packages (numpy, pyqtgraph)..."
pip install numpy pyqtgraph

# ------------------------------------------------------------
# Step 9: Fetch DishAligner Python scripts
# ------------------------------------------------------------
APP_DIR="$HOME/hb9iiu_dishaligner"
mkdir -p "$APP_DIR"

echo "📥 Downloading NBfinal.py..."
curl -L -o "$APP_DIR/NBfinal.py" \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/NBfinal.py

echo "📥 Downloading WBfinal.py..."
curl -L -o "$APP_DIR/WBfinal.py" \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/WBfinal.py



echo "✅ DishAligner scripts ready in $APP_DIR"

# ------------------------------------------------------------
# Step 10: Add custom icons + desktop launchers for Aligner tools
# ------------------------------------------------------------
APP_DIR="$HOME/hb9iiu_dishaligner"
DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$APP_DIR" "$DESKTOP_DIR"

ICON_PNG="$APP_DIR/HB9IIU_Aligner.png"

echo "📥 Downloading application icon..."
curl -fsSL -o "$ICON_PNG" \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/HB9IIU_Aligner.png

DESKTOP_FILE_NB="$DESKTOP_DIR/HB9IIU NB Monitor.desktop"
DESKTOP_FILE_WB="$DESKTOP_DIR/HB9IIU WB Monitor.desktop"

# ------------------------------------------------------------
# Narrow Band launcher
# ------------------------------------------------------------
echo "🖥️ Creating Narrow Band launcher..."
cat > "$DESKTOP_FILE_NB" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=HB9IIU NB Monitor
Comment=HB9IIU Dish Aligner - Narrow Band
Exec=$APP_DIR/bin/python3 $APP_DIR/NBfinal.py
Icon=$ICON_PNG
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE_NB"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_FILE_NB" metadata::trusted true || true
fi

# ------------------------------------------------------------
# Wide Band launcher
# ------------------------------------------------------------
echo "🖥️ Creating Wide Band launcher..."
cat > "$DESKTOP_FILE_WB" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=HB9IIU WB Monitor
Comment=HB9IIU Dish Aligner - Wide Band
Exec=$APP_DIR/bin/python3 $APP_DIR/WBfinal.py
Icon=$ICON_PNG
Terminal=false
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE_WB"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_FILE_WB" metadata::trusted true || true
fi

# Refresh desktop if PCManFM is running
if pgrep -x pcmanfm >/dev/null 2>&1; then
  echo "🔄 Refreshing PCManFM..."
  pcmanfm --reconfigure >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------
# Step 11: Enable VNC service
# ------------------------------------------------------------
echo "🔌 Enabling VNC server..."
sudo raspi-config nonint do_vnc 0

# ------------------------------------------------------------
# Step 12: Inject default SDR++ config
# ------------------------------------------------------------
echo "📥 Downloading SDR++ default config..."
curl -fsSL -o /tmp/sdrppConfig.zip \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/sdrppConfig.zip

echo "🧹 Resetting SDR++ config directory..."
rm -rf ~/.config/sdrpp
mkdir -p ~/.config/sdrpp

echo "📦 Unpacking config into ~/.config/sdrpp..."
unzip -oq /tmp/sdrppConfig.zip -d ~/.config/sdrpp
# ------------------------------------------------------------
# Step 13: Build and install GQRX with RTL-SDR, HackRF, Airspy, PlutoSDR support
# ------------------------------------------------------------
echo "=== Building GQRX SDR receiver ==="

echo "📥 Installing GQRX dependencies..."
sudo apt install -y \
  gnuradio \
  libboost-all-dev \
  qtbase5-dev qtchooser qt5-qmake qtbase5-dev-tools \
  libqt5svg5-dev libqwt-qt5-dev \
  libpulse-dev portaudio19-dev \
  libusb-1.0-0-dev \
  libhackrf-dev \
  libairspy-dev \
  libairspyhf-dev \
  libiio-dev libad9361-dev \
  librtlsdr-dev
echo "✅ GQRX dependencies installed"

# ------------------------------------------------------------
# Step 13a: Build gr-osmosdr with multiple backends
# ------------------------------------------------------------
cd "$HOME"
if [ -d "gr-osmosdr" ]; then
    echo "🧹 Removing old gr-osmosdr source..."
    rm -rf gr-osmosdr
fi

echo "📥 Cloning gr-osmosdr..."
git clone https://git.osmocom.org/gr-osmosdr
cd gr-osmosdr
mkdir build && cd build

echo "🛠️ Configuring gr-osmosdr..."
cmake .. -DENABLE_DEFAULT=OFF \
  -DENABLE_RTL=ON \
  -DENABLE_HACKRF=ON \
  -DENABLE_AIRSPY=ON \
  -DENABLE_AIRSPYHF=ON \
  -DENABLE_PLUTOSDR=ON

echo "⚙️ Building gr-osmosdr..."
make -j$(nproc)
sudo make install
sudo ldconfig
echo "✅ gr-osmosdr built and installed"

# ------------------------------------------------------------
# Step 13b: Build GQRX
# ------------------------------------------------------------
cd "$HOME"
if [ -d "gqrx" ]; then
    echo "🧹 Removing old GQRX source..."
    rm -rf gqrx
fi

echo "📥 Cloning GQRX source..."
git clone https://github.com/csete/gqrx.git
cd gqrx
mkdir build && cd build

echo "🛠️ Configuring GQRX..."
cmake ..

echo "⚙️ Building GQRX..."
make -j$(nproc)
sudo make install
sudo ldconfig
echo "✅ GQRX built and installed"

# ------------------------------------------------------------
# Step 13c: Desktop launcher for GQRX
# ------------------------------------------------------------
echo "🖥️ Creating Desktop launcher for GQRX..."
mkdir -p "$HOME/Desktop"
DESKTOP_FILE="$HOME/Desktop/GQRX.desktop"

# Use system GQRX icon if available, otherwise fallback to generic
ICON_PATH="/usr/share/icons/hicolor/48x48/apps/gqrx.png"
if [ ! -f "$ICON_PATH" ]; then
  ICON_PATH="multimedia-volume-control"
fi

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Name=GQRX SDR
Comment=Launch GQRX SDR Receiver
Exec=gqrx
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=AudioVideo;HamRadio;
EOF

chmod +x "$DESKTOP_FILE"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_FILE" metadata::trusted true || true
fi

echo "✅ Desktop launcher created at $DESKTOP_FILE"

# ------------------------------------------------------------
# Final cleanup
# ------------------------------------------------------------
echo "✅ All steps completed successfully."
echo "🧹 Cleaning up installer script..."
(sleep 5; rm -- "\$0") &

exit 0
