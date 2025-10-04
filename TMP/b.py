#!/usr/bin/env python3
# minimal_hackrf_fft.py
# Very simple HackRF spectrum plot using SoapySDR + PyQtGraph

import sys, numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

class Spectrum(QtWidgets.QWidget):
    def __init__(self, fc=100e6, fs=2e6, N=4096, gain=20):
        super().__init__()
        self.fc, self.fs, self.N, self.gain = fc, fs, N, gain

        # --- SDR init ---
        args = {"driver": "hackrf"}
        self.sdr = SoapySDR.Device(args)
        self.sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        self.sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
        self.sdr.setGain(SOAPY_SDR_RX, 0, self.gain)
        self.rxStream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self.sdr.activateStream(self.rxStream)

        # --- UI ---
        layout = QtWidgets.QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.curve = self.plot.plot(np.zeros(self.N), pen='y')
        layout.addWidget(self.plot)

        # --- Timer ---
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_fft)
        self.timer.start(100)

    def update_fft(self):
        buff = np.empty(self.N, np.complex64)
        sr = self.sdr.readStream(self.rxStream, [buff], len(buff))
        if sr.ret > 0:
            X = np.fft.fftshift(np.fft.fft(buff))
            P = 20*np.log10(np.abs(X) + 1e-12)
            self.curve.setData(P)

    def closeEvent(self, ev):
        self.timer.stop()
        self.sdr.deactivateStream(self.rxStream)
        self.sdr.closeStream(self.rxStream)
        ev.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = Spectrum(fc=100e6, fs=2e6, N=16384, gain=20)
    w.resize(800,400)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
