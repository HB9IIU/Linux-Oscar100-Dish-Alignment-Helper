#!/usr/bin/env python3
# qo100_nb_rtlsdr_spectrum_touch_SNR.py
# QO-100 Narrowband spectrum viewer (RTL-SDR)
# - Noise floor fixed at 0 dB, spectrum shows SNR directly
# - Green = BPSK beacon center (10,489.750 MHz)
# - Cyan = CW beacons (10,489.500 / 10,490.000 MHz)
# - Yellow dashed = 0 dB noise reference
# - Touchscreen buttons for zoom, offset, centering

import sys
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

# Noise estimation window
NOISE_WINDOW_KHZ = 10.0   # ±10 kHz
EXCLUDE_KHZ      = 3.0    # exclude ±3 kHz around beacon
# -------------------------------------------------


class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc, fs=SAMPLE_RATE, N=FFT_SIZE, parent=None):
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

        try:
            sdr.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(RTL_PPM))
        except Exception:
            pass

        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        try:
            if GAIN_TUNER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", GAIN_TUNER)
            if GAIN_MIXER is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "MIXER", GAIN_MIXER)
            if GAIN_LNA is not None:
                sdr.setGain(SOAPY_SDR_RX, 0, "LNA", GAIN_LNA)
        except Exception:
            pass

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
                P_db = P_db - 10*np.log10(rbw)   # RBW correction
                self.new_data.emit(P_db)

        sdr.deactivateStream(rx)
        sdr.closeStream(rx)

    def stop(self):
        self.running = False
        self.wait()


class SpectrumViewer(QtWidgets.QWidget):
    def __init__(self, lnb_lo_adj_khz=53.0, fs=SAMPLE_RATE, N=FFT_SIZE):
        super().__init__()
        self.fs, self.N = fs, N
        self.lnb_lo_adj_khz = lnb_lo_adj_khz

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
        self.plot.setYRange(-5, 40)  # SNR view

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

        # Buttons with lighter style
        btn_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(btn_layout)

        button_style = """
            QPushButton {
                background-color: #3498db;
                color: white;
                font-size: 18px;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton:pressed {
                background-color: #217dbb;
            }
        """

        for text, slot in [
            ("Zoom +", self.zoom_in),
            ("Zoom -", self.zoom_out),
            ("Offset -", self.offset_minus),
            ("Offset +", self.offset_plus),
            ("Center X", self.center_full),
            ("Zoom Beacon", self.zoom_beacon),
        ]:
            btn = QtWidgets.QPushButton(text)
            btn.setFixedHeight(60)  # smaller than before
            btn.setStyleSheet(button_style)
            btn.clicked.connect(slot)
            btn_layout.addWidget(btn)

        # SDR thread
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

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
        self.update_axis()

    def offset_plus(self):
        self.lnb_lo_adj_khz += OFFSET_STEP_KHZ
        self.update_axis()

    def center_full(self):
        self.plot.setXRange(*self.full_span, padding=0)

    def zoom_beacon(self):
        span = (self.nb_upper_if - self.nb_lower_if) * ZOOM_BEACON_FACTOR
        self.plot.setXRange(self.nb_bpsk_if - span/2, self.nb_bpsk_if + span/2)

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = SpectrumViewer()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
