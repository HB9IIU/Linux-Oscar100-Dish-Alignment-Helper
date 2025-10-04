# Satellite Dish Alignment Helper for OSCAR-100 Amateurs

These two applications are designed to help amateur radio operators align their satellite dish for **OSCAR-100 (QO-100)** reception.

They are intended to run on a **Raspberry Pi** (tested on **Raspberry Pi 4**) together with an SDR receiver such as:  
- RTL-SDR  
- Airspy R2  
- HackRF  

A more detailed description will be added soon.

---

## Installation

Open a terminal on your Raspberry Pi and run:

```bash
cd ~
curl -L -o installer.sh \
  https://raw.githubusercontent.com/HB9IIU/Linux-Oscar100-Dish-Alignment-Helper/refs/heads/main/installer.sh
chmod 777 installer.sh
./installer.sh
