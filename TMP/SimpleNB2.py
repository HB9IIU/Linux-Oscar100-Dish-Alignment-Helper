#!/usr/bin/env python3
# qo100_nb_rtlsdr_spectrum_touch_beaconzoom.py
# QO-100 Narrowband spectrum viewer with beacon markers + touchscreen controls
# - Fullscreen
# - FFT averaging (smooth trace)
# - Cyan = CW beacons (10,489.500 / 10,490.000 MHz)
# - Green = BPSK beacon (10,489.750 MHz) -> FIXED marker
# - Touchscreen buttons:
#     - Zoom + / Zoom -
#     - Offset - / Offset + (adjust LO correction live, moves spectrum vs fixed markers)
#     - Center X (snap view to beacon)
#     - Zoom Beacon (zoom directly onto beacon, factor configurable)

import sys
import numpy as np
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
import SoapySDR
from SoapySDR import *

# -------------------------------------------------
# USER SETTINGS (fixed constants)

# AMSAT-DL beacons (MHz) — NB bandplan
NB_LOWER_CW_DL  = 10489.500   # lower CW beacon
NB_BPSK_DL      = 10489.750   # middle BPSK beacon
NB_UPPER_CW_DL  = 10490.000   # upper CW beacon

# LNB LO nominal
LNB_LO_NOMINAL_MHZ = 9750.000

# SDR parameters
SAMPLE_RATE = 2.4e6           # Hz
FFT_SIZE    = 8192*4          # bins
GAIN_TUNER  = 40              # dB
GAIN_MIXER  = None
GAIN_LNA    = None
RTL_PPM     = 0.0             # ppm correction
AVG_FRAMES  = 8               # average N FFT frames

OFFSET_STEP_KHZ = 0.1         # step size for offset correction (0.1 kHz)
ZOOM_BEACON_FACTOR = 0.05     # fraction of NB span to zoom around beacon
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

        # PPM correction
        try:
            sdr.setFrequencyCorrection(SOAPY_SDR_RX, 0, float(RTL_PPM))
        except Exception:
            pass

        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        # Gains
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
        self.plot.setLabel("left", "Power (dB)")
        layout.addWidget(self.plot)

        # Initial axis & SDR center freq
        self.update_axis()

        self.curve = self.plot.plot(
            self.freq_axis,
            np.full(self.N, -120.0),
            pen=pg.mkPen(color=(220, 220, 220), width=1)
        )

        # Set initial view: full NB band
        self.plot.setXRange(self.nb_lower_if, self.nb_upper_if, padding=0)

        # Marker lines (fixed!)
        self.line_cw_lo = pg.InfiniteLine(pos=self.nb_lower_if, angle=90, pen=pg.mkPen('c', width=2))
        self.line_bpsk  = pg.InfiniteLine(pos=self.nb_bpsk_if,  angle=90, pen=pg.mkPen('g', width=2))
        self.line_cw_hi = pg.InfiniteLine(pos=self.nb_upper_if, angle=90, pen=pg.mkPen('c', width=2))
        self.plot.addItem(self.line_cw_lo)
        self.plot.addItem(self.line_bpsk)
        self.plot.addItem(self.line_cw_hi)

        # Averaging buffer
        self.fft_buffer = np.zeros((AVG_FRAMES, self.N))
        self.idx = 0

        # --- Touch buttons ---
        btn_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(btn_layout)

        # Zoom in/out
        btn_zoom_in = QtWidgets.QPushButton("Zoom +")
        btn_zoom_in.setFixedHeight(80)
        btn_zoom_in.clicked.connect(self.zoom_in)
        btn_layout.addWidget(btn_zoom_in)

        btn_zoom_out = QtWidgets.QPushButton("Zoom -")
        btn_zoom_out.setFixedHeight(80)
        btn_zoom_out.clicked.connect(self.zoom_out)
        btn_layout.addWidget(btn_zoom_out)

        # Offset adjust
        btn_offset_minus = QtWidgets.QPushButton("Offset -")
        btn_offset_minus.setFixedHeight(80)
        btn_offset_minus.clicked.connect(self.offset_minus)
        btn_layout.addWidget(btn_offset_minus)

        btn_offset_plus = QtWidgets.QPushButton("Offset +")
        btn_offset_plus.setFixedHeight(80)
        btn_offset_plus.clicked.connect(self.offset_plus)
        btn_layout.addWidget(btn_offset_plus)

        # Center
        btn_center = QtWidgets.QPushButton("Center X")
        btn_center.setFixedHeight(80)
        btn_center.clicked.connect(self.center_beacon)
        btn_layout.addWidget(btn_center)

        # Zoom Beacon
        btn_zoom_beacon = QtWidgets.QPushButton("Zoom Beacon")
        btn_zoom_beacon.setFixedHeight(80)
        btn_zoom_beacon.clicked.connect(self.zoom_beacon)
        btn_layout.addWidget(btn_zoom_beacon)

        # Start SDR thread
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    # --- Axis recompute ---
    def update_axis(self):
        LNB_LO_CORR_MHZ = LNB_LO_NOMINAL_MHZ + (self.lnb_lo_adj_khz / 1000.0)
        self.nb_lower_if = NB_LOWER_CW_DL - LNB_LO_CORR_MHZ
        self.nb_bpsk_if  = NB_BPSK_DL     - LNB_LO_CORR_MHZ
        self.nb_upper_if = NB_UPPER_CW_DL - LNB_LO_CORR_MHZ

        self.fc = self.nb_bpsk_if * 1e6
        self.freq_axis = np.linspace(
            self.fc - self.fs/2, self.fc + self.fs/2, self.N, endpoint=False
        ) / 1e6

        # Update curve X-data if curve already exists
        if hasattr(self, "curve"):
            ydata = self.curve.yData if self.curve.yData is not None else np.full(self.N, -120.0)
            self.curve.setData(self.freq_axis, ydata)

    # --- Curve update ---
    def update_curve(self, P_db):
        self.fft_buffer[self.idx % AVG_FRAMES, :] = P_db
        self.idx += 1
        avg_P = self.fft_buffer.mean(axis=0)
        self.curve.setData(self.freq_axis, avg_P)

    # --- Button actions ---
    def zoom_in(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        center = (xmin + xmax) / 2
        span = (xmax - xmin) * 0.9
        self.plot.setXRange(center - span/2, center + span/2)

    def zoom_out(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        center = (xmin + xmax) / 2
        span = (xmax - xmin) * 1.1
        self.plot.setXRange(center - span/2, center + span/2)

    def offset_minus(self):
        self.lnb_lo_adj_khz -= OFFSET_STEP_KHZ
        print(f"LNB_LO_ADJ_KHZ = {self.lnb_lo_adj_khz:.1f} kHz")
        self.update_axis()

    def offset_plus(self):
        self.lnb_lo_adj_khz += OFFSET_STEP_KHZ
        print(f"LNB_LO_ADJ_KHZ = {self.lnb_lo_adj_khz:.1f} kHz")
        self.update_axis()

    def center_beacon(self):
        xmin, xmax = self.plot.getViewBox().viewRange()[0]
        span = xmax - xmin
        self.plot.setXRange(self.nb_bpsk_if - span/2, self.nb_bpsk_if + span/2)

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
