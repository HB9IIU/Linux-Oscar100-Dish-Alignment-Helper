# QO-100 (OSCAR-100) Satellite Dish Alignment Helper

Tools to help amateur radio operators align their satellite dish for **OSCAR-100 (QO-100)** reception.

- **Target platform:** Raspberry Pi (tested on **Raspberry Pi 4**)
- **Supported SDRs:** RTL-SDR, Airspy R2, HackRF
- **Use case:** Receive-beacon–aided alignment (wideband & narrowband beacons), live SNR readout, LNB skew aid

---

## Background

Getting on **OSCAR-100 (QO-100)** starts with one of the trickiest steps: **dish alignment**.  
Traditionally this meant dragging a laptop out to the dish and running SDR-Console nearby (or using a remote desktop). It works, but it’s clunky. And when you finally get close to the right az/el, you still need a fine alignment step—usually by watching the **narrowband (NB) beacon** spectrum and peaking the signal. That’s often where things go sideways: wrong SDR settings, flaky USB, or just too many moving parts.

This project is a **plug-and-play appliance** that needs almost no configuration: a Raspberry Pi + a simple RTL-SDR dongle. Power it up, see the spectrum, and peak the dish.

---

## How it works in practice

### 1) Hookup

Connect the LNB to the SDR dongle **through a Bias-T** (or LNB power inserter).

- **12 V → Vertical polarization** → use for **Narrowband transponder (NB beacon)**
- **18 V → Horizontal polarization** → use for **Wideband (DATV) transponder (WB beacon)**

> Typical QO-100 downlink setup: **NB = V/12 V**, **WB = H/18 V**.

### 2) Coarse alignment (NB)

Start the app with **12 V** on the LNB (NB). Slowly move the dish **left/right**, then **up/down** until you see activity (peaks) around the expected IF.  
Zoom toward the **NB beacon** and adjust for the **highest SNR / tallest peak**.

### 3) Fine alignment (WB/DATV)

The NB beacon can wander a bit and the peak is not always perfectly “fixed,” which makes finding the absolute maximum fiddly.  
For the **final peaking**, switch the LNB to **18 V** and view the **DATV (WB) beacon**. Its broader, stable plateau makes the **true maximum** easier to hit. Nudge azimuth and elevation for the best reading, then lock the mount.

---

## BONUS: SDR++ Monitor + Dual Encoders

Since the Raspberry Pi has a proper display and enough CPU, the project includes a **fully pre-configured SDR++** setup.  
You can use the device as a compact **QO-100 desktop monitor** with full RX capabilities.

### Hardware controls (dual encoders)

Two rotary encoders are included for easier operation:

- **Fine tuning:** smooth frequency nudging
- **Volume control:** quick audio level adjustment
- **Beacon centering (click):** press to snap the tuned frequency to the beacon center
- **Quit application (click):** press upper encoder to Quit 

### Audio: Bluetooth speaker

High-quality audio is easy: pair a **Bluetooth speaker** with the Raspberry Pi and set it as the default output.

---

## What’s inside the box (programmatically)

- **Narrowband monitor (Python app)**  
  Processes IQ from the connected SDR to visualize and peak the **NB beacon**.

- **Wideband/DATV monitor (Python app)**  
  Uses the same SDR to display and peak the **WB (DATV) beacon**.

- **SDR++ (open source)**  
  A **preconfigured** SDR++ setup with QO-100 profiles for full RX monitoring.

- **Rig control bridge (Python service)**  
  A lightweight background service that talks to **SDR++ via rigctl** for tuning/commands.

- **Launcher UI (fullscreen Python app)**  
  A big-button, kiosk-style launcher to start any of the above (easier than tiny desktop shortcuts on small displays).

---

## How to install

1. **Prepare your Pi**
   - Flash a fresh Raspberry Pi OS to a microSD card **or** use an existing installation.
   - Ensure keyboard/mouse/monitor (or SSH) and internet access.

2. **Run the installer**
   ```bash
   cd ~
   curl -fsSL -o installer.sh \
     https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/installer.sh
   chmod 755 installer.sh
   bash installer.sh

- The system will set up required packages, SDR drivers, and the QO-100 tools.
- Installation time varies by Raspberry Pi model and network speed, but will take approx. 30 minutes!!!!

## Source code

- The source code for all Python apps is included in this repository for tweaking and customization.

## First-time use

Most SDRs need a small frequency correction before the beacon appears at the exact spot. Apply a correction in **both** SDR++ and the Python apps:

- **In SDR++:** In the left pane under **Source**, adjust **PPM Correction** until the beacon aligns.  
  *(Tip: press the lower encoder to snap/center on the beacon.)*

- **In the Python NB monitor:** Use the **± offset** buttons to nudge the frequency until the beacon is centered.  
  *(The set values are saved and automatically restored next time you start.)*

## Demo

<p align="center">
  <a href="https://www.youtube.com/watch?v=0tdZihSDElc" title="Demo — click to play">
    <img src="https://img.youtube.com/vi/0tdZihSDElc/hqdefault.jpg" alt="Demo — click to play">
  </a>
</p>
> If the thumbnail doesn’t load, use the direct link: https://www.youtube.com/watch?v=0tdZihSDElc

## Hardware

- **Displays tested**
  - Raspberry Pi **Official 7" Touchscreen**
  - Waveshare **4.3" HDMI LCD** (used in the demo video)  
    *I designed a 3D-printed enclosure for this panel; the build shown in the video uses that case.*  
    The repository also includes my **STL files** for 3D printing  
    *(Autodesk Fusion 360 project: https://a360.co/3IGViGW)*

- **Rotary encoders**
  - Two low-cost 360° rotary encoders (e.g., **KY-040** type) with push-switch  
    *Used for fine tuning, volume, **beacon-centering on press**, and **QUIT**.*

- **Typical RF chain**
  - Dish + **LNB** → **Bias-T / power inserter** (12 V for NB, 18 V for WB) → **SDR** (RTL-SDR / Airspy R2 / HackRF) → **Raspberry Pi**

- **Nice-to-haves**
  - Small **Bluetooth speaker** for audio
  - Short, good-quality **coax** and **USB** cables
  - Stable **12 V / 18 V** supply for the LNB *(I’ll soon publish my portable solution using two 3.6 V cells)*

## Pictures

<!-- Large -->
<p align="center">
  <img src="https://github.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/blob/main/Documentation/Setup.png?raw=1" alt="" width="100%">
</p>

<!-- Three in a row (table) -->
| | | |
|:-:|:-:|:-:|
| <img src="https://github.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/blob/main/Documentation/3dRender1.png?raw=1" width="100%"/> | <img src="https://github.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/blob/main/Documentation/3dRender2.png?raw=1" width="100%"/> | <img src="https://github.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/blob/main/Documentation/3dRender3.png?raw=1" width="100%"/> |
