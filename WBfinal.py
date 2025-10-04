import sys, time
import numpy as np
from collections import deque
from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg
from PyQt5 import QtGui
import SoapySDR
from SoapySDR import *

pg.setConfigOptions(antialias=True)  # smoother lines

class SDRWorker(QtCore.QThread):
    new_data = QtCore.pyqtSignal(np.ndarray)

    def __init__(self, fc=741.5e6, fs=3e6, N=8192, parent=None):
        super().__init__(parent)
        self.fc, self.fs, self.N = fc, fs, N
        self.running = True

    def run(self):
        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        airspy_devs = [d for d in devs if str(d.get("driver", "")).lower() == "airspy"]
        rtl_devs    = [d for d in devs if str(d.get("driver", "")).lower() == "rtlsdr"]
        hackrf_devs = [d for d in devs if str(d.get("driver", "")).lower() == "hackrf"]

        if airspy_devs:
            arg_str = "driver=airspy"
            sdr_type = "airspy"
        elif rtl_devs:
            arg_str = "driver=rtlsdr"
            sdr_type = "rtlsdr"
        elif hackrf_devs:
            arg_str = "driver=hackrf"
            sdr_type = "hackrf"
        else:
            print("No SDR detected!")
            return

        print(f"[SDR] Opening {sdr_type} with '{arg_str}'")
        sdr = SoapySDR.Device(arg_str)


        sdr.setSampleRate(SOAPY_SDR_RX, 0, self.fs)
        actual_fs = sdr.getSampleRate(SOAPY_SDR_RX, 0)
        print(f"Requested fs={self.fs/1e6:.3f} MHz, actual fs={actual_fs/1e6:.3f} MHz")
        sdr.setFrequency(SOAPY_SDR_RX, 0, self.fc)

        try:
            if sdr_type == "airspy":
                sdr.setGain(SOAPY_SDR_RX, 0, "LNA", 32)
                sdr.setGain(SOAPY_SDR_RX, 0, "VGA", 10)
            elif sdr_type == "rtlsdr":
                sdr.setGain(SOAPY_SDR_RX, 0, "TUNER", 30)
            elif sdr_type == "hackrf":
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

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.showFullScreen()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.setStyleSheet("background-color: black;")

        self.plot = pg.PlotWidget()
        self.plot.setBackground('k')
        self.plot.showGrid(x=True, y=True)
        self.plot.hideButtons()
        self.plot.setLabel("bottom", "Frequency (MHz)")
        self.plot.setLabel("left", "Relative Power (dB)")
        layout.addWidget(self.plot)

        self.plot.getAxis("bottom").setTextPen(pg.mkPen(color=(255, 255, 255)))
        self.plot.getAxis("left").setTextPen(pg.mkPen(color=(255, 255, 255)))
        self.plot.getAxis("bottom").setPen(pg.mkPen(color=(255, 255, 255)))
        self.plot.getAxis("left").setPen(pg.mkPen(color=(255, 255, 255)))

        self.freq_axis = np.linspace(
            self.fc - self.fs/2, self.fc + self.fs/2, self.N, endpoint=False
        ) / 1e6

        # Spectrum curve as a polyline
        self.curve = pg.PlotCurveItem(
            self.freq_axis,
            np.full(self.N, -120.0),
            pen=pg.mkPen((212, 175, 55), width=1),
            stepMode=False,
            fillLevel=None,
            brush=None,
            symbol=None
        )
        self.plot.addItem(self.curve)

        self.plot.setXRange(740, 743, padding=0)

        # Downlink frequency label
        lnb_lo = 9750e6
        downlink_center = (self.fc + lnb_lo) / 1e6
        self.downlink_label = pg.TextItem(
            text=f"{downlink_center:.3f} MHz",
            color=(0, 0, 128),
            anchor=(0.5, 1.2)
        )
        self.downlink_label.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
        self.plot.addItem(self.downlink_label)
        self.downlink_label.setPos(self.fc / 1e6, 0)

        # Beacon lines
        beacon_bw = 2e6
        beacon_start = self.fc - beacon_bw/2
        beacon_end   = self.fc + beacon_bw/2
        self.center_line = pg.InfiniteLine(pos=self.fc/1e6, angle=90, pen='r')
        self.start_line  = pg.InfiniteLine(pos=beacon_start/1e6, angle=90, pen='c')
        self.end_line    = pg.InfiniteLine(pos=beacon_end/1e6, angle=90, pen='c')
        self.plot.addItem(self.center_line)
        self.plot.addItem(self.start_line)
        self.plot.addItem(self.end_line)

        # Plateau lines (disabled by default)
        self.green_line  = pg.InfiniteLine(angle=0, pen=pg.mkPen('g', width=2))
        self.yellow_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('y', width=2))

        # Big text overlay for plateau
        self.big_text = pg.TextItem("", color=(255,255,255), anchor=(0.5, 0.5))
        self.big_text.setFont(QtGui.QFont("Arial", 100, QtGui.QFont.Bold))
        self.big_text.setZValue(200)
        self.plot.addItem(self.big_text)

        # Min/Max plateau text (corner HUD)
        self.plateau_min = None
        self.plateau_max = None

        self.text_max = pg.TextItem("", color=(0, 200, 0), anchor=(0, 0))  # bottom-left anchor
        self.text_max.setFont(QtGui.QFont("Arial", 42, QtGui.QFont.Bold))
        self.plot.addItem(self.text_max)

        self.text_min = pg.TextItem("", color=(200, 0, 0), anchor=(1, 0))  # bottom-right anchor
        self.text_min.setFont(QtGui.QFont("Arial", 42, QtGui.QFont.Bold))
        self.plot.addItem(self.text_min)

        # Place once and keep synced with view
        self.update_corner_labels()
        self.plot.getViewBox().sigRangeChanged.connect(lambda *a, **k: self.update_corner_labels())

        # Calibration state
        self.noise_locked = False
        self.noise_value = None
        self.calib_start = time.time()

        # Semi-dynamic Y scale
        self.current_ymax = 10

        # Plateau smoothing
        self.plateau_window = deque(maxlen=15)
        self.plateau_smooth = None
        self.plateau_alpha = 0.2

        # Worker
        self.worker = SDRWorker(fc=self.fc, fs=self.fs, N=self.N)
        self.worker.new_data.connect(self.update_curve)
        self.worker.start()

    # --- Corner labels helper ---
    def update_corner_labels(self):
        """Stick max/min labels in the top corners with padding; blank if no values yet."""
        try:
            (xmin, xmax), (ymin, ymax) = self.plot.viewRange()
        except Exception:
            return  # view not ready yet

        pad_x = 0.01 * (xmax - xmin)
        pad_y = 0.05 * (ymax - ymin)

        # Position near top-left / top-right
        self.text_max.setPos(xmin + pad_x, ymax - pad_y)
        self.text_min.setPos(xmax - pad_x, ymax - pad_y)

        # Safe text
        self.text_max.setText("" if self.plateau_max is None else f"{self.plateau_max:.1f}")
        self.text_min.setText("" if self.plateau_min is None else f"{self.plateau_min:.1f}")

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
            # Normalize spectrum
            P_rel = P_db - self.noise_value
            self.curve.setData(self.freq_axis, P_rel)

            # Plateau estimate (rolling median + EMA)
            plateau_y_raw = np.percentile(P_rel[beacon_mask], 98) if np.any(beacon_mask) else 0
            self.plateau_window.append(float(plateau_y_raw))
            plateau_median = np.median(self.plateau_window)

            if self.plateau_smooth is None:
                self.plateau_smooth = plateau_median
            else:
                a = self.plateau_alpha
                self.plateau_smooth = (1 - a) * self.plateau_smooth + a * plateau_median

            plateau_y = self.plateau_smooth

            # Plateau lines (if you later add them to the plot)
            self.green_line.setPos(0.0)
            self.yellow_line.setPos(plateau_y)

            # Big text
            self.big_text.setText(f"{plateau_y:.1f}")
            (xmin, xmax), (ymin, ymax) = self.plot.viewRange()
            xmid = self.fc / 1e6
            ymid = ymin + 0.4 * (ymax - ymin)
            self.big_text.setPos(xmid, ymid)

            # Update min/max
            if self.plateau_min is None or plateau_y < self.plateau_min:
                self.plateau_min = plateau_y
            if self.plateau_max is None or plateau_y > self.plateau_max:
                self.plateau_max = plateau_y

            # Semi-dynamic Y scaling (expand only)
            ymin = -1
            target_ymax = plateau_y / 0.8 if plateau_y != 0 else self.current_ymax
            if target_ymax > self.current_ymax:
                self.current_ymax = target_ymax
            self.plot.setYRange(ymin, self.current_ymax)

        else:
            self.curve.setData(self.freq_axis, P_db)

        # Keep corner labels positioned & updated every frame
        self.update_corner_labels()

    def closeEvent(self, ev):
        self.worker.stop()
        ev.accept()

    def mousePressEvent(self, event):
        QtWidgets.QApplication.quit()


def main():
        app = QtWidgets.QApplication(sys.argv)

        devs = [dict(d) for d in SoapySDR.Device.enumerate()]
        airspy_devs = [d for d in devs if str(d.get("driver", "")).lower() == "airspy"]
        rtl_devs    = [d for d in devs if str(d.get("driver", "")).lower() == "rtlsdr"]
        hackrf_devs = [d for d in devs if str(d.get("driver", "")).lower() == "hackrf"]

        if airspy_devs:
            print("Airspy detected")
            w = SpectrumViewer(fc=741.5e6, fs=6e6,    N=8192*5)
        elif rtl_devs:
            print("RTL-SDR detected")
            w = SpectrumViewer(fc=741.5e6, fs=2.048e6, N=8192*2)
        elif hackrf_devs:
            print("HackRF detected")
            w = SpectrumViewer(fc=741.5e6, fs=3e6,    N=8192*5)
        else:
            print("No SDR detected!")
            QtWidgets.QMessageBox.critical(
                None,
                "SDR Error",
                "No SDR device detected!\n\nPlease connect an SDR and restart."
            )
            return

        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
