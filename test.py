import os, signal, subprocess

def quit_sdrpp():
    try:
        pid = int(subprocess.check_output(["pidof", "sdrpp"]).strip())
        os.kill(pid, signal.SIGTERM)  # graceful quit (like clicking ×)
        print(f"Sent graceful quit to SDR++ (pid {pid})")
    except subprocess.CalledProcessError:
        print("SDR++ not running")

if __name__ == "__main__":
    quit_sdrpp()
