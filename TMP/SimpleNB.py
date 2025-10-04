#!/usr/bin/env python3
# simple_rtlsdr_qo100_nb_spectrum_fullscreen.py
# Very simple fullscreen QO-100 NB spectrum plot with RTL-SDR + SoapySDR

import sys
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc=739.75e6, fs=2.4e6, N=8192, parent=None):
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
        sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", 30)

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
    def __init__(self, fc=739.75e6, fs=2.4e6, N=8192):
        super().__init__()
        self.fc, self.fs, self.N = fc, fs, N

        # --- Fullscreen ---
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
            pen=pg.mkPen(color=(255, 215, 0), width=1)  # gold
        )
        self.plot.setXRange(self.fc/1e6 - self.fs/2e6,
                            self.fc/1e6 + self.fs/2e6,
                            padding=0)

        # Start SDR worker
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    def update_curve(self, P_db):
        self.curve.setData(self.freq_axis, P_db)

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    # NB beacon IF ~739.75 MHz
    w = SpectrumViewer(fc=739.75e6, fs=2.4e6, N=8192*2)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
