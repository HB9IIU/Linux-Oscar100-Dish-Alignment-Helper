#!/usr/bin/env python3
# step1_rtlsdr_nb_fullscreen_zoomed_avg.py
# QO-100 NB spectrum viewer (739.550–739.800 MHz)
# - Fullscreen
# - Zoomed to NB transponder edges
# - Configurable gains
# - FFT averaging for smoother display

import sys
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

# -------------------------------------------------
# USER SETTINGS
CENTER_FREQ = 739.75e6   # Hz, NB beacon center IF
SAMPLE_RATE = 2.4e6      # Hz, typical RTL-SDR stable max
FFT_SIZE    = 8192*4     # FFT bins (higher = smoother trace)
GAIN_TUNER  = 30         # dB, tuner gain (0–50 typical)
GAIN_MIXER  = None       # optional, if supported
GAIN_LNA    = None       # optional, if supported
AVG_FRAMES  = 14          # average over N FFT frames
# -------------------------------------------------

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc=CENTER_FREQ, fs=SAMPLE_RATE, N=FFT_SIZE, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        # Open RTL-SDR
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        rtl_devs = [d for d in devs if str(d.get("driver", "")).lower() == "rtlsdr"]
        if rtl_devs:
            args = {"driver": "rtlsdr"}
            if "serial" in rtl_devs[0]:
                args["serial"] = rtl_devs[0]["serial"]
            print("Opening RTL-SDR with args:", args)
        else:
            args = {"driver": "rtlsdr"}
            print("No RTL-SDR detected, using fallback args")

        sdr = SoapySDR.Device(args)
        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        # Apply gains if supported
        try:
            if GAIN_TUNER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", GAIN_TUNER)
            if GAIN_MIXER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "MIXER", GAIN_MIXER)
            if GAIN_LNA is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "LNA", GAIN_LNA)
        except Exception as e:
            print("Gain setting not supported:", e)

        rx = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rx)

        buff = np.empty(self.N, np.complex64)
        win = np.hanning(self.N).astype(np.complex64)

        while self.running:
            sr = sdr.readStream(rx, [buff], len(buff), timeoutUs=100000)
            if sr.ret > 0:
                x = buff[:sr.ret] * win[:sr.ret]
                X = np.fft.fftshift(np.fft.fft(x, n=self.N))
                P_db = 20*np.log10(np.abs(X) + 1e-12)
                self.new_data.emit(P_db)

        sdr.deactivateStream(rx)
        sdr.closeStream(rx)

    def stop(self):
        self.running = False
        self.wait()

class SpectrumViewer(QtWidgets.QWidget):
    def __init__(self, fc=CENTER_FREQ, fs=SAMPLE_RATE, N=FFT_SIZE):
        super().__init__()
        self.fc, self.fs, self.N = fc, fs, N

        # Fullscreen
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "Power (dB)")
        layout.addWidget(self.plot)

        # Frequency axis
        self.freq_axis = np.linspace(
            self.fc - self.fs/2, self.fc + self.fs/2, self.N, endpoint=False
        ) / 1e6

        self.curve = self.plot.plot(
            self.freq_axis,
            np.full(self.N, -120.0),
            pen=pg.mkPen(color=(200, 200, 200), width=1)  # light grey trace
        )

        # Zoom to NB band edges
        self.plot.setXRange(739.550, 739.800, padding=0)

        # Averaging buffer
        self.fft_buffer = np.zeros((AVG_FRAMES, self.N))
        self.idx = 0

        # Start SDR thread
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    def update_curve(self, P_db):
        # Insert into buffer
        self.fft_buffer[self.idx % AVG_FRAMES, :] = P_db
        self.idx += 1
        # Average
        avg_P = self.fft_buffer.mean(axis=0)
        self.curve.setData(self.freq_axis, avg_P)

    def keyPressEvent(self, e):
        if e.key() in (QtCore.Qt.Key_Q, QtCore.Qt.Key_Escape):
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
