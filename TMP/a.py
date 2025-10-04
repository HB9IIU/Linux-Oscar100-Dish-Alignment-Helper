#!/usr/bin/env python3
# spectrum_hackrf_relfloor_topline.py
# Original: SDRplay version adapted to use HackRF via SoapySDR.
#
# Minimal changes:
#  - autodetect HackRF device via SoapySDR.Device.enumerate()
#  - use that device's serial (if present) when opening
#  - fall back to driver="hackrf" if autodetect fails

import sys, time
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg

import SoapySDR
from SoapySDR import *  # enums

pg.setConfigOptions(antialias=False)

YMIN_REL, YMAX_REL = -3.0, 40.0

class Spectrum(QtWidgets.QWidget):
    def __init__(self,
                 fc=741.5e6, fs=2.4e6, N=65536, gain=20,
                 symbol_rate=2_048_000, rolloff=0.35,
                 edge_guard_hz=250e3, plateau_percentile=99.0,
                 noise_span_hz=200e3):
        super().__init__()
        self.fc, self.fs, self.N, self.gain = float(fc), float(fs), int(N), gain
        self.sr = float(symbol_rate); self.alpha = float(rolloff)
        self.edge_guard_hz = float(edge_guard_hz)
        self.pctl = float(plateau_percentile)
        self.noise_span_hz = float(noise_span_hz)

        self.noise_ref = None
        self.calibrating = True
        self.calib_start = time.time()

        # beacon occupied BW
        self.bw_hz = self.sr * (1.0 + self.alpha)

        # --- SDR init (SoapySDR with HackRF) ---
        # Try to find a HackRF via enumeration and use serial if available.
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        hack_devs = [d for d in devs if str(d.get("driver", "")).lower().startswith("hackrf")]

        if hack_devs:
            info = hack_devs[0]
            # Build args: include serial if present, otherwise use driver only
            args = {"driver": "hackrf"}
            if "serial" in info:
                # some Soapy entries use 'serial' or 'device' keys — copy what's available
                args["serial"] = info["serial"]
            elif "device" in info:
                args["device"] = info["device"]
            print("Opening HackRF with args:", args)
        else:
            # fallback: try plain hackrf driver (may still work)
            args = {"driver": "hackrf"}
            print("No HackRF detected by enumerate(); falling back to args:", args)

        try:
            self.sdr = SoapySDR.Device(args)
        except Exception as e:
            raise RuntimeError(f"Failed to open HackRF with args={args}: {e}")

        # Set sample rate (HackRF supports up to 10e6 typically)
        self.sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        # Start left for calibration (same approach as original)
        self.sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc - self.fs/2)
        # Set gain (driver-dependent semantics)
        try:
            self.sdr.setGain(SOAPY_SDR_RX, 0, self.gain)
        except Exception:
            # some drivers require setting specific gain elements; ignore failure here
            pass

        # Setup streaming (complex float32)
        self.rxStream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self.sdr.activateStream(self.rxStream)

        # DSP
        self.win = np.ones(self.N, dtype=np.float32)
        self.freq_axis_hz = np.linspace(-self.fs/2, self.fs/2, self.N, endpoint=False)
        self.freq_axis = (self.freq_axis_hz + self.fc) / 1e6
        self.rbw = self.fs / self.N

        # UI
        self.setWindowTitle("HackRF — Noise-calibrated spectrum (fc at right edge)")
        layout = QtWidgets.QVBoxLayout(self)

        self.plot = pg.PlotWidget()
        self.plot.hideButtons()
        self.plot.showGrid(x=True, y=True, alpha=1)
        self.plot.setLabel('bottom', 'Frequency (MHz)')
        self.plot.setLabel('left', 'dB above noise')

        # GOLD spectrum
        self.curve = self.plot.plot(self.freq_axis,
                                    np.full(self.N, -120.0),
                                    pen=pg.mkPen(color=(212, 175, 55), width=1))

        # plateau line + label
        self.top_line = pg.InfiniteLine(angle=0, movable=False,
                                        pen=pg.mkPen((230, 80, 80), width=2))
        self.plot.addItem(self.top_line)
        self.top_label = pg.TextItem(color=(0, 0, 139), anchor=(1, 0))
        self.plot.addItem(self.top_label)

        # BIG overlay number
        self.big_text = pg.TextItem("", color=(0, 0, 139), anchor=(0.5, 0.5))
        self.big_text.setZValue(200)
        self.big_text.setFont(QtGui.QFont("Arial", 128, QtGui.QFont.Bold))
        self.plot.addItem(self.big_text)

        layout.addWidget(self.plot)
        self.status = QtWidgets.QLabel(); layout.addWidget(self.status)

        # calibration span markers
        self.span_left = pg.InfiniteLine(angle=90, movable=False,
                                         pen=pg.mkPen((100, 180, 255), style=QtCore.Qt.DashLine))
        self.span_right = pg.InfiniteLine(angle=90, movable=False,
                                          pen=pg.mkPen((100, 180, 255), style=QtCore.Qt.DashLine))
        self.plot.addItem(self.span_left); self.plot.addItem(self.span_right)
        self.span_left.hide(); self.span_right.hide()

        # continuous beacon edge guard lines
        self.beacon_left = pg.InfiniteLine(angle=90, movable=False,
                                           pen=pg.mkPen((0, 255, 255), style=QtCore.Qt.DashLine))
        self.beacon_right = pg.InfiniteLine(angle=90, movable=False,
                                            pen=pg.mkPen((0, 255, 255), style=QtCore.Qt.DashLine))
        self.plot.addItem(self.beacon_left); self.plot.addItem(self.beacon_right)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self.timer.start(50)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self._update_title("CALIBRATING noise floor...")

    def _fmt_rbw(self):
        rbw = self.rbw
        return f"{rbw:.2f} Hz" if rbw < 1e3 else (f"{rbw/1e3:.2f} kHz" if rbw < 1e6 else f"{rbw/1e6:.2f} MHz")

    def _update_title(self, extra=""):
        self.setWindowTitle(
            f"HackRF — fc={self.fc/1e6:.6f} MHz  span={self.fs/1e6:.1f} MHz  RBW≈{self._fmt_rbw()}  {extra}"
        )
        self.status.setText(self.windowTitle())

    def _autoscale_y(self, line_db, target_frac=0.80, floor_ref=0.0,
                     min_span=10.0, max_span=50.0, below_floor=1.5):
        span = (line_db - floor_ref) / max(target_frac, 1e-3)
        span = max(min_span, min(max_span, span))
        ymin = floor_ref - below_floor
        ymax = ymin + span
        self.plot.setYRange(ymin, ymax, padding=0.0)

    def _read_samples(self):
        buff = np.empty(self.N, np.complex64)
        sr = self.sdr.readStream(self.rxStream, [buff], len(buff))
        if sr.ret > 0:
            return buff
        return None

    def _update_frame(self):
        x = self._read_samples()
        if x is None:
            self.status.setText("Read error"); return

        x -= np.mean(x)
        X = np.fft.fftshift(np.fft.fft(x * self.win))
        P_db = 20*np.log10(np.abs(X)/self.N + 1e-12)

        if self.calibrating:
            span_bins = int(round(self.noise_span_hz / self.rbw))
            L = int(0.1*self.N)          # 10% into spectrum from left
            R = L + span_bins

            self.span_left.setPos((self.freq_axis_hz[L] + (self.fc - self.fs/2))/1e6)
            self.span_right.setPos((self.freq_axis_hz[R] + (self.fc - self.fs/2))/1e6)
            self.span_left.show(); self.span_right.show()

            self.curve.setData((self.freq_axis_hz + (self.fc - self.fs/2))/1e6, P_db)
            self._update_title("CALIBRATING noise floor...")

            if time.time() - self.calib_start >= 3.0:
                self.noise_ref = float(np.mean(P_db[L:R]))
                self.calibrating = False
                self.span_left.hide(); self.span_right.hide()
                # set center frequency to fc after calibration
                self.sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
                self._update_title(f"Calibration done | Floor {self.noise_ref:.1f} dB")

        else:
            P_rel = P_db - self.noise_ref
            P_rel = np.maximum(P_rel, -3.0)
            self.curve.setData(self.freq_axis, P_rel)

            half_bins = max(1, int(round(0.5 * self.bw_hz / self.rbw)))
            mid = self.N // 2
            L = max(0, mid - half_bins); R = min(self.N - 1, mid + half_bins)

            guard_bins = max(1, int(round(self.edge_guard_hz / self.rbw)))
            Li = min(R, L + guard_bins); Ri = max(L, R - guard_bins)
            if Ri <= Li: Li, Ri = L, R
            central = P_rel[Li:Ri+1]
            y_level = float(np.percentile(central, self.pctl)) if central.size else float(np.max(P_rel[L:R+1]))

            self.top_line.setPos(y_level)
            self._autoscale_y(y_level, target_frac=0.6, floor_ref=0.0,
                              min_span=8.0, max_span=60.0, below_floor=1.5)

            right_freq_MHz = float((self.freq_axis_hz[R] + self.fc) / 1e6)
            self.top_label.setPos(right_freq_MHz, y_level)

            vr = self.plot.viewRange()
            ymin, ymax = vr[1]
            xmid = self.fc / 1e6
            ymid = ymin + 0.35 * (ymax - ymin)
            self.big_text.setText(f"{y_level:.1f}")
            self.big_text.setPos(xmid, ymid)

            self.beacon_left.setPos((self.freq_axis_hz[Li] + self.fc)/1e6)
            self.beacon_right.setPos((self.freq_axis_hz[Ri] + self.fc)/1e6)

    def closeEvent(self, ev):
        self.timer.stop()
        try:
            self.sdr.deactivateStream(self.rxStream)
            self.sdr.closeStream(self.rxStream)
        except Exception:
            pass
        ev.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = Spectrum(fc=741.5e6, fs=2.048e6*2, N=4096, gain=40,
                 symbol_rate=2_048_000, rolloff=0.35,
                 edge_guard_hz=500e3, plateau_percentile=99.0,
                 noise_span_hz=200e3)
    w.resize(1120, 600); w.show()
    import signal as _signal; _signal.signal(_signal.SIGINT, _signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
