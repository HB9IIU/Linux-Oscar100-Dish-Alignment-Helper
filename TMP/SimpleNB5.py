#!/usr/bin/env python3
# qo100_nb_rtlsdr_spectrum_touch_SNR.py
# QO-100 Narrowband spectrum viewer (RTL-SDR)
# - Noise floor fixed at 0 dB, spectrum shows SNR directly
# - Green = BPSK beacon center (10,489.750 MHz)
# - Cyan = CW beacons (10,489.500 / 10,490.000 MHz)
# - Yellow dashed = 0 dB noise reference
# - Touchscreen buttons for zoom, offset, centering

import sys, os
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

# -------------------------------------------------
# USER SETTINGS
NB_LOWER_CW_DL  = 10489.500
NB_BPSK_DL      = 10489.750
NB_UPPER_CW_DL  = 10490.000

LNB_LO_NOMINAL_MHZ = 9750.000

SAMPLE_RATE = 2.4e6
FFT_SIZE    = 8192*4
GAIN_TUNER  = 30
GAIN_MIXER  = None
GAIN_LNA    = None
RTL_PPM     = 0.0
AVG_FRAMES  = 8

OFFSET_STEP_KHZ   = 0.1
ZOOM_BEACON_FACTOR = 0.05
REPEAT_INTERVAL_MS = 100   # continuous repeat speed for long press

# Noise estimation window
NOISE_WINDOW_KHZ = 10.0   # ±10 kHz
EXCLUDE_KHZ      = 3.0    # exclude ±3 kHz around beacon

OFFSET_FILE = "lnb_offset.txt"
# -------------------------------------------------

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc, fs=SAMPLE_RATE, N=FFT_SIZE, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        # Detect device
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        driver = None
        args = {}

        if devs:
            d = devs[0]  # first detected
            driver = str(d.get("driver", "")).lower()
            args = {"driver": driver}
            if "serial" in d:
                args["serial"] = d["serial"]
            print(f"[SDR] Detected driver: {driver}")
        else:
            args = {"driver": "rtlsdr"}
            driver = "rtlsdr"
            print("[SDR] No device found, fallback to RTL-SDR")

        sdr = SoapySDR.Device(args)

        # Select sample rate + gains depending on device
        if driver == "rtlsdr":
            self.fs = 2.4e6
            print("[SDR] Using RTL-SDR mode (fs=2.4 MHz)")
            sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", GAIN_TUNER)

        elif driver == "airspy":
            self.fs = 3.0e6
            print("[SDR] Using Airspy mode (fs=3.0 MHz)")
            if GAIN_LNA is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "LNA", GAIN_LNA)
            if GAIN_MIXER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "MIXER", GAIN_MIXER)

        elif driver == "hackrf":
            self.fs = 8.0e6
            print("[SDR] Using HackRF mode (fs=8.0 MHz)")
            if GAIN_LNA is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "LNA", GAIN_LNA)
            # HackRF also has VGA gain
            try:
                sdr.setGain(SOAPY_SDR_RX, 0, "VGA", 20)
            except Exception:
                pass

        else:
            print(f"[SDR] Unknown driver '{driver}', using default fs=2.4 MHz")
            self.fs = 2.4e6

        # Apply frequency correction if supported
        try:
            sdr.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(RTL_PPM))
        except Exception:
            pass

        # Configure stream
        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        rx = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rx)

        buff = np.empty(self.N, np.complex64)
        win = np.hanning(self.N).astype(np.complex64)

        rbw = self.fs / self.N

        while self.running:
            sr = sdr.readStream(rx, [buff], len(buff), timeoutUs=100000)
            if sr.ret > 0:
                x = buff[:sr.ret] * win[:sr.ret]
                X = np.fft.fftshift(np.fft.fft(x, n=self.N)) / self.N
                P_db = 10 * np.log10(np.abs(X)**2 + 1e-20)
                P_db = P_db - 10*np.log10(rbw)
                self.new_data.emit(P_db)

        sdr.deactivateStream(rx)
        sdr.closeStream(rx)

    def stop(self):
        self.running = False
        self.wait()

class SpectrumViewer(QtWidgets.QWidget):
    def __init__(self, fs=SAMPLE_RATE, N=FFT_SIZE):
        super().__init__()
        self.fs, self.N = fs, N

        # Load last offset or init to 50.0 kHz
        if os.path.exists(OFFSET_FILE):
            try:
                with open(OFFSET_FILE, "r") as f:
                    self.lnb_lo_adj_khz = float(f.read().strip())
                print(f"[INFO] Loaded offset {self.lnb_lo_adj_khz:.2f} kHz")
            except:
                self.lnb_lo_adj_khz = 50.0
                print("[WARN] Failed reading offset file, using 50.0 kHz")
        else:
            self.lnb_lo_adj_khz = 50.0
            with open(OFFSET_FILE, "w") as f:
                f.write(str(self.lnb_lo_adj_khz))
            print("[INFO] Offset file created with 50.0 kHz")

        # Fullscreen
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Plot
        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "SNR (dB)")
        layout.addWidget(self.plot)

        self.update_axis()

        self.curve = self.plot.plot(
            self.freq_axis,
            np.full(self.N, -50.0),
            pen=pg.mkPen(color=(220, 220, 220), width=1)
        )

        # Full NB span
        self.full_span = (self.nb_lower_if, self.nb_upper_if)
        self.plot.setXRange(*self.full_span, padding=0)
        self.plot.setYRange(0, 40)  # 0 dB at bottom

        # Markers
        self.line_cw_lo = pg.InfiniteLine(pos=self.nb_lower_if, angle=90, pen=pg.mkPen('c', width=2))
        self.line_bpsk  = pg.InfiniteLine(pos=self.nb_bpsk_if,  angle=90, pen=pg.mkPen('g', width=2))
        self.line_cw_hi = pg.InfiniteLine(pos=self.nb_upper_if, angle=90, pen=pg.mkPen('c', width=2))
        self.plot.addItem(self.line_cw_lo)
        self.plot.addItem(self.line_bpsk)
        self.plot.addItem(self.line_cw_hi)

        # Noise reference line at 0 dB
        self.noise_line = pg.InfiniteLine(angle=0, pos=0.0,
                                          pen=pg.mkPen('y', style=QtCore.Qt.DashLine))
        self.plot.addItem(self.noise_line)

        # Averaging
        self.fft_buffer = np.zeros((AVG_FRAMES, self.N))
        self.idx = 0

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(btn_layout)

        # Map buttons to functions
        self.btn_actions = {
            "Zoom +": self.zoom_in,
            "Zoom -": self.zoom_out,
            "Offset -": self.offset_minus,
            "Offset +": self.offset_plus,
            "Center X": self.center_full,
            "Zoom Beacon": self.zoom_beacon,
            "Quit": self.quit_app
        }

        # Timers for long-press repeat
        self.timers = {}

        for text, slot in self.btn_actions.items():
            btn = QtWidgets.QPushButton(text)
            btn.setFixedHeight(40)
            btn_layout.addWidget(btn)

            if text in ["Zoom +", "Zoom -", "Offset -", "Offset +"]:
                timer = QtCore.QTimer(self)
                timer.setInterval(REPEAT_INTERVAL_MS)
                timer.timeout.connect(slot)
                self.timers[text] = timer

                btn.pressed.connect(lambda checked=False, t=text, s=slot: self.start_repeat(t, s))
                btn.released.connect(lambda t=text: self.stop_repeat(t))
            else:
                btn.clicked.connect(slot)

        # SDR thread
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    def start_repeat(self, name, slot):
        slot()  # do one step immediately
        self.timers[name].start()

    def stop_repeat(self, name):
        self.timers[name].stop()

    def save_offset(self):
        with open(OFFSET_FILE, "w") as f:
            f.write(str(self.lnb_lo_adj_khz))
        print(f"[INFO] Saved offset {self.lnb_lo_adj_khz:.2f} kHz")

    def update_axis(self):
        LNB_LO_CORR_MHZ = LNB_LO_NOMINAL_MHZ + (self.lnb_lo_adj_khz / 1000.0)
        self.nb_lower_if = NB_LOWER_CW_DL - LNB_LO_CORR_MHZ
        self.nb_bpsk_if  = NB_BPSK_DL     - LNB_LO_CORR_MHZ
        self.nb_upper_if = NB_UPPER_CW_DL - LNB_LO_CORR_MHZ

        self.fc = self.nb_bpsk_if * 1e6
        self.freq_axis = np.linspace(
            self.fc - self.fs/2, self.fc + self.fs/2, self.N, endpoint=False
        ) / 1e6

        if hasattr(self, "curve"):
            self.curve.setData(self.freq_axis, self.curve.yData)

    def update_curve(self, P_db):
        self.fft_buffer[self.idx % AVG_FRAMES, :] = P_db
        self.idx += 1
        avg_P = self.fft_buffer.mean(axis=0)

        # Local noise estimate
        left_edge = self.nb_bpsk_if - NOISE_WINDOW_KHZ/1000.0
        right_edge = self.nb_bpsk_if + NOISE_WINDOW_KHZ/1000.0
        mask = (self.freq_axis > left_edge) & (self.freq_axis < right_edge)
        exclude = (self.freq_axis > (self.nb_bpsk_if - EXCLUDE_KHZ/1000.0)) & \
                  (self.freq_axis < (self.nb_bpsk_if + EXCLUDE_KHZ/1000.0))
        final_mask = mask & ~exclude

        if np.any(final_mask):
            noise_floor = np.median(avg_P[final_mask])
            avg_P_rel = avg_P - noise_floor  # normalize to noise=0 dB
            self.curve.setData(self.freq_axis, avg_P_rel)

    # Button actions
    def zoom_in(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        c = (xmin + xmax) / 2
        span = (xmax - xmin) * 0.9
        self.plot.setXRange(c - span/2, c + span/2)

    def zoom_out(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        c = (xmin + xmax) / 2
        span = (xmax - xmin) * 1.1
        self.plot.setXRange(c - span/2, c + span/2)

    def offset_minus(self):
        self.lnb_lo_adj_khz -= OFFSET_STEP_KHZ
        self.save_offset()
        self.update_axis()

    def offset_plus(self):
        self.lnb_lo_adj_khz += OFFSET_STEP_KHZ
        self.save_offset()
        self.update_axis()

    def center_full(self):
        self.plot.setXRange(*self.full_span, padding=0)

    def zoom_beacon(self):
        span = (self.nb_upper_if - self.nb_lower_if) * ZOOM_BEACON_FACTOR
        self.plot.setXRange(self.nb_bpsk_if - span/2, self.nb_bpsk_if + span/2)

    def quit_app(self):
        print("[INFO] Quit requested by user")
        self.close()

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = SpectrumViewer()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
