#!/usr/bin/env python3
# hackrf_datv_spectrum_relative.py
# HackRF DATV spectrum viewer with fixed noise reference at 0 dB

import sys, time
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
from PyQt5 import QtGui
import SoapySDR
from SoapySDR import *

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc=741.5e6, fs=3e6, N=8192, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        # Detect HackRF
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        hack_devs = [d for d in devs if str(d.get("driver", "")).lower() == "hackrf"]

        if hack_devs:
            args = {"driver": "hackrf"}
            if "serial" in hack_devs[0]:
                args["serial"] = hack_devs[0]["serial"]
            print("Opening HackRF with args:", args)
        else:
            args = {"driver": "hackrf"}
            print("No HackRF detected, using fallback args")

        sdr = SoapySDR.Device(args)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        try:
            sdr.setGain(SOAPY_SDR_RX, 0, "LNA", 32)
            sdr.setGain(SOAPY_SDR_RX, 0, "VGA", 10)
        except Exception:
            sdr.setGain(SOAPY_SDR_RX, 0, 40)

        rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rxStream)

        buff = np.empty(self.N, np.complex64)
        win = np.hanning(self.N).astype(np.complex64)

        while self.running:
            sr = sdr.readStream(rxStream, [buff], len(buff), timeoutUs=100000)
            if sr.ret > 0:
                x = buff[:sr.ret] * win[:sr.ret]
                X = np.fft.fftshift(np.fft.fft(x, n=self.N))
                P_db = 20*np.log10(np.abs(X) + 1e-12)
                self.new_data.emit(P_db)

        sdr.deactivateStream(rxStream)
        sdr.closeStream(rxStream)

    def stop(self):
        self.running = False
        self.wait()


class SpectrumViewer(QtWidgets.QWidget):
    def __init__(self, fc=741.5e6, fs=3e6, N=8192):
        super().__init__()
        self.fc, self.fs, self.N = fc, fs, N

        # Fullscreen + black frame
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.setStyleSheet("background-color: black;")

        # Plot
        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "Relative Power (dB)")
        layout.addWidget(self.plot)

        # Axis
        self.freq_axis = np.linspace(
            self.fc - self.fs/2, self.fc + self.fs/2, self.N, endpoint=False
        ) / 1e6
        self.curve = self.plot.plot(
            self.freq_axis,
            np.full(self.N, -120.0),
            pen=pg.mkPen(color=(212, 175, 55), width=1)  # gold
        )
        # --- Add downlink frequency label at center ---
        lnb_lo = 9750e6  # LNB local oscillator in Hz
        downlink_center = (self.fc + lnb_lo) / 1e6  # in MHz

        self.downlink_label = pg.TextItem(
            text=f"{downlink_center:.3f} MHz",
            color=(0, 0, 128),
            anchor=(0.5, 1.2)  # center align, just below top of plot
        )
        self.downlink_label.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        self.plot.addItem(self.downlink_label)
        self.downlink_label.setPos(self.fc / 1e6, 0)  # place at x=center freq



        # Beacon lines
        beacon_bw = 2e6
        beacon_start = self.fc - beacon_bw/2
        beacon_end = self.fc + beacon_bw/2
        self.center_line = pg.InfiniteLine(pos=self.fc/1e6, angle=90, pen='r')
        self.start_line = pg.InfiniteLine(pos=beacon_start/1e6, angle=90, pen='c')
        self.end_line = pg.InfiniteLine(pos=beacon_end/1e6, angle=90, pen='c')
        self.plot.addItem(self.center_line)
        self.plot.addItem(self.start_line)
        self.plot.addItem(self.end_line)

        # Plateau lines
        self.green_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('g', width=2))
        self.yellow_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('y', width=2))
        self.plot.addItem(self.green_line)
        self.plot.addItem(self.yellow_line)

        # Big text overlay for plateau
        self.big_text = pg.TextItem("", color=(0, 0, 139), anchor=(0.5, 0.5))  # navy blue
        self.big_text.setFont(QtGui.QFont("Arial", 96, QtGui.QFont.Bold))
        self.big_text.setZValue(200)  # on top
        self.plot.addItem(self.big_text)

        # Calibration state
        self.noise_locked = False
        self.noise_value = None
        self.calib_start = time.time()

        # Worker
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    def update_curve(self, P_db):
        beacon_bw = 2e6
        left_mask = self.freq_axis < (self.fc - beacon_bw/2) / 1e6
        beacon_mask = (self.freq_axis >= (self.fc - beacon_bw/4) / 1e6) & \
                      (self.freq_axis <= (self.fc + beacon_bw/4) / 1e6)

        if not self.noise_locked:
            if time.time() - self.calib_start >= 3.0:
                if np.any(left_mask):
                    self.noise_value = np.percentile(P_db[left_mask], 95)
                    self.noise_locked = True
                    print(f"Noise reference locked at {self.noise_value:.2f} dB")

        if self.noise_locked and self.noise_value is not None:
            # Normalize spectrum so noise reference = 0 dB
            P_rel = P_db - self.noise_value
            self.curve.setData(self.freq_axis, P_rel)

            # Update plateau lines
            plateau_y = np.percentile(P_rel[beacon_mask], 98) if np.any(beacon_mask) else 0
            self.green_line.setPos(0.0)          # noise floor at 0 dB
            self.yellow_line.setPos(plateau_y)

            # Update big text at center
            self.big_text.setText(f"{plateau_y:.1f}")
            xmid = self.fc / 1e6
            ymin, ymax = self.plot.viewRange()[1]
            ymid = ymin + 0.4 * (ymax - ymin)
            self.big_text.setPos(xmid, ymid)


            # Adjust y-range so yellow is ~80% high
            ymin = -1
            ymax = plateau_y / 0.8
            self.plot.setYRange(ymin, ymax)
        else:
            # Pre-lock: still raw FFT
            self.curve.setData(self.freq_axis, P_db)

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = SpectrumViewer(fc=741.5e6, fs=3e6, N=8192*5)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
