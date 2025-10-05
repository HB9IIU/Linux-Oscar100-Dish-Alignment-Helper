#!/usr/bin/env python3
import sys, os, socket
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

# -------------------------- USER SETTINGS --------------------------
NB_BPSK_DL  = 10489.750   # MHz
LNB_LO_NOMINAL_MHZ = 9750.000 # MHz

SAMPLE_RATE = 2.4e6       # Hz
FFT_SIZE    = 8192
GAIN_TUNER  = 30
RTL_PPM     = 0.0

AVG_FRAMES  = 8
OFFSET_FILE = "lnb_offset.txt"
DISPLAY_OFFSET_MHZ = 10000.0

UDP_IP   = "127.0.0.1"
UDP_PORT = 7355            # SDR++ network source port
# -------------------------------------------------------------------

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc, fs=SAMPLE_RATE, N=FFT_SIZE, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        # ---- UDP socket ----
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # ---- Open SDR ----
        print(f"[SDR] Opening RTL-SDR (driver=rtlsdr)")
        sdr = SoapySDR.Device("driver=rtlsdr")
        try:
            sdr.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(RTL_PPM))
        except Exception:
            pass

        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)
        sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", GAIN_TUNER)

        # ---- Streaming ----
        rx = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        sdr.activateStream(rx)

        buff = np.empty(self.N, np.complex64)
        win = np.hanning(self.N).astype(np.complex64)
        rbw = self.fs / self.N

        print(f"[NET] Sending I/Q via UDP to {UDP_IP}:{UDP_PORT}")

        while self.running:
            sr = sdr.readStream(rx, [buff], len(buff), timeoutUs=100000)
            if sr.ret > 0:
                # ---- Send raw IQ over UDP ----
                # keep packet size below MTU (1500 bytes)
                chunk = buff[:sr.ret].tobytes()
                for i in range(0, len(chunk), 1400):
                    sock.sendto(chunk[i:i+1400], (UDP_IP, UDP_PORT))

                # ---- Spectrum for plotting ----
                x = buff[:sr.ret] * win[:sr.ret]
                X = np.fft.fftshift(np.fft.fft(x, n=self.N)) / self.N
                P_db = 10 * np.log10(np.abs(X)**2 + 1e-20)
                P_db = P_db - 10*np.log10(rbw)
                self.new_data.emit(P_db)

        sdr.deactivateStream(rx)
        sdr.closeStream(rx)
        sock.close()

    def stop(self):
        self.running = False
        self.wait()


class SpectrumViewer(QtWidgets.QWidget):
    def __init__(self, fs=SAMPLE_RATE, N=FFT_SIZE):
        super().__init__()
        self.fs, self.N = fs, N

        # ---- Nominal IF center ----
        self.nb_bpsk_if_nom = NB_BPSK_DL - LNB_LO_NOMINAL_MHZ
        self.fc_nominal_hz  = self.nb_bpsk_if_nom * 1e6

        # ---- Fullscreen UI ----
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()

        layout = QtWidgets.QVBoxLayout(self)
        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "SNR (dB)")
        layout.addWidget(self.plot)

        self.curve = self.plot.plot(
            np.linspace(0, self.fs/1e6, self.N),
            np.full(self.N, -50.0),
            pen=pg.mkPen(color=(0, 255, 0), width=1)
        )

        # ---- SDR thread ----
        self.worker = SDRWorker(fc=self.fc_nominal_hz, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    def update_curve(self, P_db):
        self.curve.setData(P_db)

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = SpectrumViewer()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
