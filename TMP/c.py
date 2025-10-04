#!/usr/bin/env python3
# hackrf_stream_test.py
# Minimal HackRF stream test with SoapySDR

import numpy as np
import SoapySDR
from SoapySDR import *

def main():
    # Find HackRF
    devs = [dict(d) for d in SoapySDR.Device.enumerate()]
    hack_devs = [d for d in devs if str(d.get("driver", "")).lower() == "hackrf"]

    if hack_devs:
        args = {"driver": "hackrf"}
        if "serial" in hack_devs[0]:
            args["serial"] = hack_devs[0]["serial"]
        print("Opening HackRF with args:", args)
    else:
        print("No HackRF detected, trying fallback args")
        args = {"driver": "hackrf"}

    # Open device
    sdr = SoapySDR.Device(args)
    sdr.setSampleRate(SOAPY_SDR_RX, 0, 10e6)
    sdr.setFrequency(SOAPY_SDR_RX, 0, 700e6)
    sdr.setGain(SOAPY_SDR_RX, 0, 20)

    # Setup stream
    rxStream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
    sdr.activateStream(rxStream)

    print("Starting stream... (Ctrl+C to stop)")
    buff = np.empty(16384*2, np.complex64)

    try:
        while True:
            sr = sdr.readStream(rxStream, [buff], len(buff))
            if sr.ret > 0:
                print(f"✔ Got {sr.ret} samples, first={buff[0]}")
            elif sr.ret == SOAPY_SDR_TIMEOUT:
                print("⏱ Timeout")
            elif sr.ret == SOAPY_SDR_OVERFLOW:
                print("❌ Overflow")
            else:
                print(f"❌ Error: {sr.ret}")
    except KeyboardInterrupt:
        print("Stopping...")

    # Cleanup
    sdr.deactivateStream(rxStream)
    sdr.closeStream(rxStream)

if __name__ == "__main__":
    main()
