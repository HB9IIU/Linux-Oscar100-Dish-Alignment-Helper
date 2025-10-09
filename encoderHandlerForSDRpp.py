#!/usr/bin/env python3
import socket
import time
import os, signal, subprocess
from gpiozero import RotaryEncoder, Button

# ------------------------------
# SDR++ RigCtl connection config
# ------------------------------
HOST = "127.0.0.1"
PORT = 4532
STEP = 50  # Hz per detent

# ------------------------------
# Helper functions
# ------------------------------
def connect():
    """Try once to connect to SDR++ rigctl, return None if not available"""
    try:
        s = socket.create_connection((HOST, PORT), timeout=2)
        s.settimeout(2)
        print("✅ Connected to SDR++ rigctl")
        return s
    except OSError:
        return None

def cmd(s, line):
    """Send a command to rigctl and return the reply"""
    s.sendall((line+"\n").encode())
    return s.recv(1024).decode().strip()

def get_f(s):
    """Get frequency from SDR++"""
    try:
        return int(cmd(s, "f"))
    except Exception:
        print("⚠️ Rigctl connection lost, will retry...")
        return None

def set_f(s, hz):
    """Set frequency in SDR++"""
    try:
        cmd(s, f"F {hz}")
        print(f"📡 Set frequency: {hz} Hz")
    except Exception:
        print("⚠️ Rigctl connection lost, command skipped")

def kill_or_start_sdrpp():
    """Kill SDR++ if running, or start it if not"""
    try:
        pid = int(subprocess.check_output(["pidof", "-s", "sdrpp"]).strip())
        os.kill(pid, signal.SIGTERM)  # graceful quit
        print(f"🛑 Sent graceful quit to SDR++ (pid {pid})")
    except subprocess.CalledProcessError:
        print("▶️ SDR++ not running, starting it...")
        subprocess.Popen(["/usr/bin/sdrpp", "--autostart"])
    time.sleep(0.3)  # debounce

# ------------------------------
# GPIO setup
# ------------------------------
encoder_freq = RotaryEncoder(a=17, b=18, max_steps=0)  # Encoder 1 = Frequency
encoder_vol  = RotaryEncoder(a=22, b=23, max_steps=0)  # Encoder 2 = Volume
button_reset = Button(27)                              # Reset to QO-100 center
button_kill  = Button(24)                              # Kill/Start SDR++

# ------------------------------
# Main loop
# ------------------------------
s = connect()   # try to connect once (may be None if SDR++ not running)

while True:
    # --------------------------
    # If not connected, try again
    # --------------------------
    if s is None:
        s = connect()

    # --------------------------
    # Frequency encoder
    # --------------------------
    if s:
        step = encoder_freq.steps
        if step != 0:
            freq = get_f(s)
            if freq:
                freq -= step * STEP
                set_f(s, freq)
            encoder_freq.steps = 0

    # --------------------------
    # Volume encoder
    # --------------------------
    step_vol = encoder_vol.steps
    if step_vol != 0:
        if step_vol > 0:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+4%"])
            print("🔊 Volume up")
        else:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-4%"])
            print("🔉 Volume down")
        encoder_vol.steps = 0

    # --------------------------
    # Reset button
    # --------------------------
    if s and button_reset.is_pressed:
        print("🔘 Reset to QO-100 NB center (10.489750 GHz)")
        set_f(s, 10489750000)
        time.sleep(0.3)  # debounce

    # --------------------------
    # Kill/Start button
    # --------------------------
    if button_kill.is_pressed:
        print("🔘 Kill/Start button pressed")
        kill_or_start_sdrpp()
        s = None   # force reconnect after SDR++ is restarted

    time.sleep(0.01)  # main loop tick
