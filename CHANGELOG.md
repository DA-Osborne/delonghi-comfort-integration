# Changelog

## 2.0.0

This is a large update. **It requires Home Assistant 2026.11 or newer.** Read "What existing installs will notice" before updating.

### What existing installs will notice

- **Entities that can never have data are removed.** The integration now creates an entity only when your model reports the property behind it. On the air conditioner this was developed against, the filter hours, power consumption, operating hours, error code and humidity setpoint entities are removed automatically, because the unit does not report them. Nothing is removed if the cloud's property list looks incomplete.
- **The "WiFi signal strength" sensor is gone.** The unit reports no Wi-Fi signal. What it did report was the signal strength of the Bluetooth link to the remote control, which now appears as **Remote signal strength**.
- **Duplicate entities are off by default on new installs.** The target temperature, device status, device mode, fan speed and silent mode sensors, the Device power switch and the Temperature setpoint number repeat the climate entity. Existing installs keep whatever you had enabled.
- **State attributes were trimmed.** The climate entity no longer copies every cloud property into its attributes (this also exposed the device's address and serial number). Templates that read those attributes need another source. The heater keeps only `current_power_level` and `MDH_Resources`.
- **The sensors that show the unit's status, mode, fan speed and silent mode are now enum sensors** with text states ("Cooling", "Fan only", "Auto"). Fan speed used to be a number.
- **Names changed.** The mode select is called "Mode", and the air conditioner's main entity takes the device name. Entity IDs did not change.
- **The device page shows the appliance's own model, hardware and firmware** (for example EL112) instead of the Wi-Fi module's.
- **The "Weekly schedule" binary sensor is renamed "Weekly schedule armed" and disabled by default.** It reads 0 while a schedule slot is running, so it is not a reliable "on" indicator. Use the new **Weekly schedule** sensor instead.

### Added

- **myEcoReal Feel** as a mode (shown as Auto on the climate card, and as an option on the Mode select), on models that report it.
- **myEcoReal Feel adjustment** (14 to 18, higher is warmer), **myEcoReal Feel comfort** (the comfort light), and **Remote temperature**, **Remote humidity**, **Remote signal strength**, and binary sensors for the remote being connected, docked and in use.
- **Vent swing** on the climate card.
- **Off timer**: minutes until the unit switches itself off (0 cancels), with a **Timer active** sensor.
- **Display temperature unit** (°C or °F on the unit's display).
- **Pipe temperature** (the evaporator pipe).
- **Alarm sensors**: tray full, probe failure, low humidity, frost protection and high temperature.
- **Weekly schedule** sensor: the schedule stored on the unit, decoded into days, times and settings. Read only.
- **Download diagnostics**: a useful utility to dump the machine's information (every property the unit reports, redacted) for adding further machine functionality.
- Fan speeds offered now follow the mode: dehumidify offers Auto only, and fan mode offers Low, Medium and High.
- The **Silent mode** switch is available only while the unit is on and cooling, which is the only mode where the unit accepts it. In dehumidify, fan and Real Feel mode the unit ignores the command and switching to those modes clears silent mode, so the switch is unavailable there and a command is refused with a message instead of showing a state the unit never takes.

### Fixed

- **Login failures** when the consent page declared its signature with `let`, `var` or double quotes.
- **API read failures** no longer turn into empty device lists. Setup retries, and a password the cloud rejects starts Home Assistant's re-authentication flow.
- **Power, mode and silent mode** show the commanded state while the unit confirms, and fall back to the real state if it does not.
- **Silent mode off** sends the value the cloud accepts.
- **Polling** defaults to 60 seconds, with limits of 30 to 300 seconds.
- **Temperature setpoint number** range corrected to 18 to 32.
- The device no longer lists itself as its own parent.
- Heater state icons for `0%` and `Day mode` are removed, because Home Assistant's icon validation rejects those state names. The heater entities use their default icon.
- The integration manifest and translation files follow Home Assistant's hassfest rules, and the hassfest and HACS checks run on push, pull request and manual start only.
- The heater path no longer crashes on missing or unexpected values, and its entities are created only for properties the heater reports.
- Home Assistant 2026.11's climate temperature rename is handled (`native_*` names), so there are no deprecation warnings.

### Known limits

- The weekly schedule can be read but not written from Home Assistant. In tests the unit applied a schedule's mode, fan speed and swing, but not its temperature or silent setting.
- Developed and tested against one air conditioner (appliance model EL112). The heater support has no test device.
