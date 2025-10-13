#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
import subprocess, os, time
from pathlib import Path

# --- Adjust to your setup ---
PROJECT_DIR = Path("/home/daniel/hb9iiu_dishaligner")
VENV_BIN    = PROJECT_DIR / "bin"   # ignored if it doesn't exist

COMMANDS = [
    {
        "label": "Narrow Band Monitor",
        "cmd": [str(VENV_BIN / "python3"), str(PROJECT_DIR / "NBfinal.py")],
        "cwd": PROJECT_DIR,
    },
    {
        "label": "Wide Band Beacon",
        "cmd": [str(VENV_BIN / "python3"), str(PROJECT_DIR / "WBfinal.py")],
        "cwd": PROJECT_DIR,
    },
    {
        "label": "SDR++",
        "cmd": ["sdrpp", "--autostart"],   # or "/usr/bin/sdrpp"
        "cwd": Path.home(),
    },
]
# ----------------------------

# --- Styling ---
BG_ROOT   = "#0f172a"   # slate-900
BG_BTN    = "#1e293b"   # slate-800
BG_HOVER  = "#334155"   # slate-700
BG_ACTIVE = "#475569"   # slate-600
FG_TEXT   = "#ffffff"
FONT_BIG  = ("DejaVu Sans", 30, "bold")
PAD       = {"padx": 24, "pady": 18}
BORDER    = 6  # button border width
# ---------------

LOG_DIR = Path.home() / ".hb9iiu_launcher_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def launch(entry):
    cmd, cwd = entry["cmd"], entry["cwd"]
    if not cwd.exists():
        messagebox.showerror("Path error", f"Working directory not found:\n{cwd}")
        return

    env = os.environ.copy()
    if VENV_BIN.exists():
        env["PATH"] = str(VENV_BIN) + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(PROJECT_DIR)

    ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{entry['label'].replace(' ', '_')}-{ts}.log"

    try:
        with open(log_path, "ab", buffering=0) as log:
            subprocess.Popen(
                cmd, cwd=str(cwd), env=env, stdout=log, stderr=log, start_new_session=True
            )
        # launcher stays open
    except Exception as e:
        messagebox.showerror("Launch error", f"Failed to start:\n{cmd}\n\n{e}")

def make_touch_button(parent, text, command):
    """Create a big, high-contrast button with hover/press effects."""
    btn = tk.Button(
        parent,
        text=text,
        font=FONT_BIG,
        fg=FG_TEXT,
        bg=BG_BTN,
        activeforeground=FG_TEXT,
        activebackground=BG_ACTIVE,
        relief="raised",
        bd=BORDER,
        highlightthickness=0,
        padx=20,
        pady=14,
        command=command,
    )

    # Hover effect
    def on_enter(_):
        btn.configure(bg=BG_HOVER)
    def on_leave(_):
        btn.configure(bg=BG_BTN)
    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

    # Touch “press” visual feedback (helps on capacitive screens)
    def on_press(_):
        btn.configure(bg=BG_ACTIVE, relief="sunken")
    def on_release(_):
        btn.configure(bg=BG_HOVER, relief="raised")
    btn.bind("<ButtonPress-1>", on_press)
    btn.bind("<ButtonRelease-1>", on_release)

    # Make the button ignore keyboard focus rectangle (cleaner look)
    btn.configure(takefocus=0)

    return btn

def main():
    root = tk.Tk()

    # --- Fullscreen / kiosk ---
    root.attributes("-fullscreen", True)             # fullscreen
    root.bind("<Escape>", lambda e: root.destroy())  # ESC to quit
    # root.config(cursor="none")                     # uncomment to hide mouse cursor
    # ------------------------------------------

    # Dark background
    root.configure(bg=BG_ROOT)

    frame = tk.Frame(root, bg=BG_ROOT)
    frame.pack(expand=True, fill="both")

    # Three big app buttons
    for i, entry in enumerate(COMMANDS):
        btn = make_touch_button(frame, entry["label"], command=lambda e=entry: launch(e))
        btn.grid(row=i, column=0, sticky="nsew", **PAD)

    # Quit button
    quit_btn = make_touch_button(frame, "Quit", command=root.destroy)
    quit_btn.grid(row=len(COMMANDS), column=0, sticky="nsew", **PAD)

    # Even sizing
    frame.columnconfigure(0, weight=1)
    for r in range(len(COMMANDS) + 1):
        frame.rowconfigure(r, weight=1)

    root.mainloop()

if __name__ == "__main__":
    main()
