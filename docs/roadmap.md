# Roadmap and engineering backlog

[Back to OpenSwarm](../README.md)

Implementation milestones describe code paths, not a completed hardware validation
matrix. See the hardware procedure for the evidence needed per board and driver.

## Safety and authentication

Unchecked items remain open work, not implemented guarantees. Framework reliability is the
current priority; no authentication or independent hardware safety system has been
added in this iteration.

- [x] Application command leases: implemented and tested in software, including
  expiry while transport heartbeats continue. Physical stopping behavior still needs testing.
- [ ] Independent local supervision and nonblocking stepper/UART/sensor scheduling;
  the existing 500 ms watchdog is a software transport timeout, not a hardware guarantee.
- [ ] Complete per-driver stop/hold/release conformance and physical validation,
  including raw pins and loaded-arm behavior. Existing custom STOP callbacks and
  type-specific stop paths do not establish physical emergency-stop behavior.
- [ ] Authenticated controller sessions, exclusive ownership, replay protection,
  and confirmed delivery/execution for critical commands. Sequence numbers and
  command leases already exist; authenticated replay protection is separate.
- [ ] WebSocket origin checks and session authentication; binding localhost alone
  does not authenticate a browser client.
- [ ] Operator-disconnect/input leases and stale-sensor interlocks.
- [ ] Loaded-arm mechanical limits, calibrated pulse ranges, power-budget checks,
  and physical emergency-stop validation.

## TODO: remaining framework and hardware work

- [ ] Board compile matrix and hardware verification for ESP32/S2/S3/C3, Nano RP2040
  Connect, Pico W, UNO R4 WiFi, UNO WiFi Rev2, and Nano 33 IoT. The S2/C3 UART reference
  is now guarded but those targets have not been built in this iteration.
- [ ] Timer-driven servo output on UNO/Nano and servo-library fallback paths;
  explicit rejection when ESP32/RP2040 servo slots are exhausted.
- [ ] Complete UNO/Nano UART implementation and encoder slots beyond two; deduplicate
  common HAL driver code after the board compilation matrix is established.
- [ ] Real VL53L0X initialization/ranging and INA219 shunt calibration; sensor-specific
  polling periods and explicit hardware read failures instead of plausible fallback values.
- [ ] Correct multi-interface/subnet discovery on Linux and reconnection across address
  changes; negotiate protocol capabilities and complete telemetry/metadata capacity reporting.
- [ ] Joint-position feedback/calibration, buffered multi-node trajectories, and
  real localization before physical autonomous fleet operation.
- [ ] Complete arm emulator state/STOP/watchdog behavior and browser interaction testing.
- [ ] Vendor browser assets for offline use and extract embedded UI code into packaged assets.
- [ ] Version CAD source deliberately (`3Dmodels/` is currently ignored), avoid deleting
  unrelated STL files, and verify solid geometry, fit, and slicer-derived print times.

## Project Roadmap

- [x] **Step 1 (ESP32):** ESP32 Slave Library (`hal_esp32.h` — Full Sensor, Actuator, Bus & Custom Driver Suite)
- [x] **Master Core:** Linux Master Python SDK & CLI (`openswarm-master`) + Live Hardware Verification
- [x] **Step 2 (RP2040):** RP2040 Slave Support (`hal_rp2040.h` — Arduino Nano RP2040 Connect / Pico W + Onboard 6-Axis IMU)
- [x] **Step 3 (Linux Slave):** Linux Slave Agent (`slaves/linux/` — `openswarm-slave` for Arduino UNO Q, Portenta X8, Raspberry Pi, Jetson, and Linux PC)
- [x] **Step 4 (Arduino UNO):** Arduino UNO Slave Support (`hal_uno.h` — UNO R4 WiFi, UNO WiFi Rev2)
- [x] **Step 5 (Arduino Nano):** Arduino Nano Slave Support (`hal_nano.h` — Nano 33 IoT)
- [x] **HydraArm application:** Four joints distributed across ESP32, RP2040 and
  Raspberry Pi, with browser/terminal control and episode recording/playback.
- [ ] **Additional application — AI Vision Sorter:** Laptop-camera perception and
  coordinated sorting behavior using controllers exposed through OpenSwarm.

> [!NOTE]
> Boards **without native Wi-Fi** (UNO R3, UNO R4 Minima, Classic Nano, Nano Every) are intentionally not supported yet.

---
