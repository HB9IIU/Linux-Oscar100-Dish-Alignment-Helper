#!/usr/bin/env python3
# show_hackrf_simple.py — minimal HackRF detect + info (SoapySDR)

import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

def main():
    devs = SoapySDR.Device.enumerate()
    # convert each to a plain dict for safe key access
    devs = [dict(d) for d in devs]

    # filter hackrf devices
    hack_devs = [d for d in devs if str(d.get("driver","")).lower().startswith("hackrf")]

    if not hack_devs:
        print("No HackRF devices found. Devices enumerated:")
        for d in devs:
            print(d)
        return

    for i, info in enumerate(hack_devs):
        print(f"\n=== HackRF #{i} ===")
        for k,v in sorted(info.items()):
            print(f"{k:12}: {v}")

        # open device (use minimal args)
        args = {"driver": info.get("driver")}
        if "serial" in info:
            args["serial"] = info["serial"]
        sdr = SoapySDR.Device(args)

        print("\nSample rates:", sdr.listSampleRates(SOAPY_SDR_RX, 0))
        print("Frequencies  :", sdr.listFrequencies(SOAPY_SDR_RX, 0))
        print("Gains        :", sdr.listGains(SOAPY_SDR_RX, 0))

        # small stream test (setup -> activate -> deactivate -> close)
        try:
            stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
            sdr.activateStream(stream)
            print("Stream activation: OK")
            sdr.deactivateStream(stream)
            sdr.closeStream(stream)
        except Exception as e:
            print("Stream test failed:", e)

if __name__ == "__main__":
    main()
