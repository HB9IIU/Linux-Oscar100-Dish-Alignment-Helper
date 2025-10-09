#!/usr/bin/env python3
import socket
import time
import subprocess
from gpiozero import RotaryEncoder, Button

# ------------------------------
# SDR++ RigCtl connection
# ------------------------------
HOST = "127.0.0.1"
PORT = 4532
STEP = 50  # Hz per detent

def connect():
    """Keep trying until SDR++ is available"""
    while True:
        try:
            s = socket.create_connection((HOST, PORT), timeout=2)
            s.settimeout(2)
            print("✅ Connected to SDR++ rigctl")
            return s
        except OSError:
            print("⏳ Waiting for SDR++...")
            time.sleep(1)

def cmd(s, line):
    s.sendall((line+"\n").encode())
    return s.recv(1024).decode().strip()

def get_f(s):
    try:
        return int(cmd(s, "f"))
    except Exception:
        s.close()
        s = connect()
        return int(cmd(s, "f"))

def set_f(s, hz):
    try:
        cmd(s, f"F {hz}")
        print("📡 Set frequency:", hz)
    except Exception:
        s.close()
        s = connect()
        cmd(s, f"F {hz}")
        print("📡 Set frequency:", hz)

# ------------------------------
# GPIO setup
# ------------------------------
# Encoder 1 = Frequency
encoder_freq = RotaryEncoder(a=17, b=18, max_steps=0)

# Encoder 2 = Volume
encoder_vol = RotaryEncoder(a=22, b=23, max_steps=0)

# Button = Reset frequency
button_reset = Button(27)

# Button = Kill SDR++
button_kill = Button(24)

# ------------------------------
# Main loop
# ------------------------------
s = connect()
print("Starting at:", get_f(s))

try:
    while True:
        # Frequency encoder
        step = encoder_freq.steps
        if step != 0:
            freq = get_f(s)
            freq -= step * STEP
            set_f(s, freq)
            encoder_freq.steps = 0

        # Volume encoder
        step_vol = encoder_vol.steps
        if step_vol != 0:
            if step_vol > 0:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+4%"])
                print("🔊 Volume up")
            else:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-4%"])
                print("🔉 Volume down")
            encoder_vol.steps = 0

        # Reset button
        if button_reset.is_pressed:
            print("🔘 Reset to QO-100 NB center (10.489750 GHz)")
            set_f(s, 10489750000)
            time.sleep(0.3)

        # Kill button (momentary)
        if button_kill.is_pressed:
            print("🛑 Kill button pressed! Terminating SDR++")
            subprocess.run(["pkill", "-f", "sdrpp"])
            time.sleep(0.3)

        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n🛑 Exiting")
