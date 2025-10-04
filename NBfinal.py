#!/usr/bin/env python3
import sys, os
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

# -------------------------- USER SETTINGS --------------------------
NB_LOWER_CW_DL  = 10489.500   # MHz
NB_BPSK_DL      = 10489.750   # MHz
NB_UPPER_CW_DL  = 10490.000   # MHz

LNB_LO_NOMINAL_MHZ = 9750.000 # MHz

SAMPLE_RATE = 2.4e6           # Hz
FFT_SIZE    = 8192*5
GAIN_TUNER  = 30
GAIN_MIXER  = None
GAIN_LNA    = None
RTL_PPM     = 0.0
AVG_FRAMES  = 8

OFFSET_STEP_KHZ     = 0.1
ZOOM_BEACON_FACTOR  = 0.025
REPEAT_INTERVAL_MS  = 100

NOISE_WINDOW_KHZ = 10.0
EXCLUDE_KHZ      = 3.0

OFFSET_FILE = "lnb_offset.txt"

DISPLAY_OFFSET_MHZ = 10000.0
# -------------------------------------------------------------------

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc, fs=SAMPLE_RATE, N=FFT_SIZE, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        # ---- Detect SDR devices ----
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        print("[SDR] Devices found:", devs)

        preferred = ["rtlsdr", "airspy", "hackrf"]
        driver = None
        args = None

        for pref in preferred:
            found = [d for d in devs if str(d.get("driver", "")).lower() == pref]
            if found:
                driver = pref
                args = {"driver": pref}
                if "serial" in found[0]:
                    args["serial"] = found[0]["serial"]
                break

        # ---- If nothing supported found → show error ----
        if not driver:
            print("[SDR] ERROR: No supported device found!")
            QtWidgets.QMessageBox.critical(
                None,
                "SDR Error",
                "No supported SDR device found!\n\nPlease connect RTL-SDR, Airspy, or HackRF."
            )
            return

        print(f"[SDR] Opening {driver} with args: {args}")
        sdr = SoapySDR.Device(args)

        # ---- Common setup ----
        try:
            sdr.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(RTL_PPM))
        except Exception:
            pass

        # ---- Device-specific setup ----
        if driver == "rtlsdr":
            sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
            sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
            if GAIN_TUNER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", GAIN_TUNER)

        elif driver == "airspy":
            sdr.setSampleRate(SOAPY_SDR_RX, 0, 2.5e6)
            sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
            sdr.setGain(SOAPY_SDR_RX, 0, "LNA", 12)
            sdr.setGain(SOAPY_SDR_RX, 0, "LINEARITY", 5)
            sdr.setGain(SOAPY_SDR_RX, 0, "SENSITIVITY", 5)

        elif driver == "hackrf":
            sdr.setSampleRate(SOAPY_SDR_RX, 0, 2.0e6)
            sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
            sdr.setGain(SOAPY_SDR_RX, 0, "LNA", 32)
            sdr.setGain(SOAPY_SDR_RX, 0, "VGA", 16)

        else:
            sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
            sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        # ---- Streaming ----
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

        # ---- Load absolute offset (kHz), create with 50.0 if missing
        self.offset_khz = self.load_offset()

        # ---- Nominal IF centers (fixed; markers use nominal DL minus 10 GHz for display)
        self.nb_lower_disp = NB_LOWER_CW_DL - DISPLAY_OFFSET_MHZ
        self.nb_bpsk_disp  = NB_BPSK_DL     - DISPLAY_OFFSET_MHZ
        self.nb_upper_disp = NB_UPPER_CW_DL - DISPLAY_OFFSET_MHZ

        # ---- SDR center at nominal IF (hardware tuned once; not shifted by offset)
        self.nb_bpsk_if_nom = NB_BPSK_DL - LNB_LO_NOMINAL_MHZ
        self.fc_nominal_hz  = self.nb_bpsk_if_nom * 1e6

        # ---- Fullscreen UI
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()

        # Force exact screen geometry (fixes right margin issue)
        screen = QtWidgets.QApplication.primaryScreen()
        rect = screen.geometry()
        self.setGeometry(rect)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # ---- Plot
        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "SNR (dB)")
        layout.addWidget(self.plot)
        # Force axis text and lines to solid white
        for axis in ("bottom", "left"):
            ax = self.plot.getAxis(axis)
            ax.setTextPen(pg.mkPen(color=(255, 255, 255)))  # tick labels
            ax.setPen(pg.mkPen(color=(255, 255, 255)))  # axis line + ticks

        # Custom ticks
        ax = self.plot.getAxis('bottom')
        ax.setTicks([
            [(v, f"{v:.2f}") for v in np.arange(489.5, 490.1, 0.05)],
            [(v, f"{v:.2f}") for v in np.arange(489.5, 490.1, 0.01)]
        ])

        # ---- Build axis
        self.recompute_display_axis()

        # ---- Spectrum curve
        self.colors = [
            (220, 220, 220),
            (0, 255, 0),
            (255, 0, 0),
            (0, 200, 255),
            (255, 165, 0),
        ]
        self.color_index = 0
        self.curve = self.plot.plot(
            self.freq_axis_disp,
            np.full(self.N, -50.0),
            pen=pg.mkPen(color=self.colors[self.color_index], width=1)
        )

        # ---- Markers
        self.line_cw_lo = pg.InfiniteLine(pos=self.nb_lower_disp, angle=90, pen=pg.mkPen('c', width=2))
        self.line_bpsk  = pg.InfiniteLine(pos=self.nb_bpsk_disp,  angle=90, pen=pg.mkPen('g', width=2))
        self.line_cw_hi = pg.InfiniteLine(pos=self.nb_upper_disp, angle=90, pen=pg.mkPen('c', width=2))
        self.plot.addItem(self.line_cw_lo)
        self.plot.addItem(self.line_bpsk)
        self.plot.addItem(self.line_cw_hi)

        # ---- View ranges
        self.full_span = (self.nb_lower_disp, self.nb_upper_disp)
        self.plot.setXRange(*self.full_span, padding=0)
        self.plot.setYRange(0, 32)
        self.plot.setMouseEnabled(x=True, y=False)

        # ---- Noise reference
        self.noise_line = pg.InfiniteLine(angle=0, pos=0.0,
                                          pen=pg.mkPen('y', style=QtCore.Qt.DashLine))
        self.plot.addItem(self.noise_line)

        # ---- Offset label
        self.offset_text = pg.TextItem(
            text=f"Offset: {self.offset_khz:.1f} kHz",
            color='w',
            anchor=(1, 0)
        )
        self.plot.addItem(self.offset_text)
        self.offset_text.setPos(self.full_span[1], 30)

        # ---- Averaging
        self.fft_buffer = np.zeros((AVG_FRAMES, self.N))
        self.idx = 0

        # ---- Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(btn_layout)

        self.btn_actions = {
            "Zoom +": self.zoom_in,
            "Zoom -": self.zoom_out,
            "Offset -": self.offset_minus,
            "Offset +": self.offset_plus,
            "NB Full": self.center_full,
            "Zoom Beacon": self.zoom_beacon,
            "Color": self.cycle_color,
            "Quit": self.quit_app,
        }

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
                btn.pressed.connect(lambda checked=False, t=text, s=slot: self._start_repeat(t, s))
                btn.released.connect(lambda t=text: self._stop_repeat(t))
            else:
                btn.clicked.connect(slot)

        # ---- SDR thread
        self.worker = SDRWorker(fc=self.fc_nominal_hz, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

        print(f"[INIT] Offset (kHz) loaded: {self.offset_khz:.3f}")

    # ---------------- Persistence ----------------
    def load_offset(self):
        if os.path.exists(OFFSET_FILE):
            try:
                with open(OFFSET_FILE, "r") as f:
                    raw = f.read().strip()
                val = float(raw)
                print(f"[LOAD] {OFFSET_FILE} = '{raw}' -> {val:.3f} kHz")
                return val
            except Exception as e:
                print(f"[LOAD] Failed ({e}); using 50.0 kHz")
                self.save_offset(50.0)
                return 50.0
        else:
            print(f"[LOAD] No {OFFSET_FILE}; creating with 50.0 kHz")
            self.save_offset(50.0)
            return 50.0

    def save_offset(self, val=None):
        if val is not None:
            self.offset_khz = float(val)
        try:
            with open(OFFSET_FILE, "w") as f:
                f.write(f"{self.offset_khz:.3f}")
                f.flush()
                os.fsync(f.fileno())
            print(f"[SAVE] Offset -> {self.offset_khz:.3f} kHz")
        except Exception as e:
            print(f"[ERROR] Could not save offset: {e}")

    # ---------------- Axis / display mapping ----------------
    def recompute_display_axis(self):
        freq_axis_raw_if = np.linspace(
            self.fc_nominal_hz - self.fs/2, self.fc_nominal_hz + self.fs/2, self.N, endpoint=False
        ) / 1e6
        freq_axis_if_with_offset = freq_axis_raw_if + (self.offset_khz / 1000.0)
        self.freq_axis_disp = freq_axis_if_with_offset + (LNB_LO_NOMINAL_MHZ - DISPLAY_OFFSET_MHZ)

        if hasattr(self, "curve"):
            y = self.curve.yData if self.curve.yData is not None else np.full(self.N, -50.0)
            self.curve.setData(self.freq_axis_disp, y)

        if hasattr(self, "offset_text"):
            self.offset_text.setPos(self.full_span[1], 30)
            self.offset_text.setText(f"Offset: {self.offset_khz:.1f} kHz")

    # ---------------- Spectrum update ----------------
    def update_curve(self, P_db):
        self.fft_buffer[self.idx % AVG_FRAMES, :] = P_db
        self.idx += 1
        avg_P = self.fft_buffer.mean(axis=0)

        beacon_disp = self.nb_bpsk_disp
        left_edge  = beacon_disp - NOISE_WINDOW_KHZ/1000.0
        right_edge = beacon_disp + NOISE_WINDOW_KHZ/1000.0
        mask = (self.freq_axis_disp > left_edge) & (self.freq_axis_disp < right_edge)
        exclude = (self.freq_axis_disp > (beacon_disp - EXCLUDE_KHZ/1000.0)) & \
                  (self.freq_axis_disp < (beacon_disp + EXCLUDE_KHZ/1000.0))
        final_mask = mask & ~exclude

        if np.any(final_mask):
            noise_floor = np.median(avg_P[final_mask])
            avg_P_rel = avg_P - noise_floor
            self.curve.setData(self.freq_axis_disp, avg_P_rel)

    # ---------------- Long-press helpers ----------------
    def _start_repeat(self, name, slot):
        slot()
        self.timers[name].start()

    def _stop_repeat(self, name):
        self.timers[name].stop()

    # ---------------- Buttons ----------------
    def zoom_in(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        c = (xmin + xmax) / 2.0
        span = (xmax - xmin) * 0.9
        self.plot.setXRange(c - span/2, c + span/2)

    def zoom_out(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        c = (xmin + xmax) / 2.0
        span = (xmax - xmin) * 1.1
        self.plot.setXRange(c - span/2, c + span/2)

    def offset_minus(self):
        self.offset_khz -= OFFSET_STEP_KHZ
        self.save_offset()
        self.recompute_display_axis()

    def offset_plus(self):
        self.offset_khz += OFFSET_STEP_KHZ
        self.save_offset()
        self.recompute_display_axis()

    def center_full(self):
        self.plot.setXRange(*self.full_span, padding=0)

    def zoom_beacon(self):
        span = (self.nb_upper_disp - self.nb_lower_disp) * ZOOM_BEACON_FACTOR
        self.plot.setXRange(self.nb_bpsk_disp - span/2, self.nb_bpsk_disp + span/2)

    def cycle_color(self):
        self.color_index = (self.color_index + 1) % len(self.colors)
        self.curve.setPen(pg.mkPen(color=self.colors[self.color_index], width=1))
        print(f"[COLOR] Spectrum color changed to {self.colors[self.color_index]}")

    def quit_app(self):
        print("[QUIT] Closing app...")
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
