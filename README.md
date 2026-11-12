# De'Longhi Comfort Home Assistant Integration

## Revised Fork

This repository is a maintained revision of the original De'Longhi Comfort integration. It includes fixes and improvements verified with a working De'Longhi air conditioner:

- Updated Gigya consent-signature parsing for the current De'Longhi login response.
- Improved API error reporting, Home Assistant setup retries, and credential reauthentication.
- Added responsive power and silent-mode state confirmation, with silent mode disabled while the unit is off.
- Updated coordinator data handling and cloud polling defaults.

This fork supports Home Assistant 2024.8 and newer. It is an independent community project and is not affiliated with or endorsed by De'Longhi.

[![HACS](https://img.shields.io/badge/HACS-Custom%20repository-blue.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![GitHub release](https://img.shields.io/github/release/DA-Osborne/delonghi-comfort-integration.svg)](https://github.com/DA-Osborne/delonghi-comfort-integration/releases/)

This is an unofficial Home Assistant integration for compatible De'Longhi Comfort air conditioners and connected heaters. It communicates with De'Longhi's cloud service, so an internet connection is required.

## ⚠️ Disclaimer

**IMPORTANT**: This integration is provided "as-is" without any warranty or guarantee. The author takes no responsibility for any damage, data loss, or issues that may arise from using this integration. Use at your own risk.

This integration builds on work from:
- **[rtfpessoa/delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)** - Thank you for the initial client implementation
- **[duckwc/ECAMpy](https://github.com/duckwc/ECAMpy)** - Thanks for the authentication and token conversion code

## 🚀 Features

### Climate Control
- **Air conditioners**: Cool, Dry (dehumidify), Fan Only, Off, and myEcoReal Feel (shown as Auto) on models that have it
- **Vent swing**: Start or stop the flap swing on models that support it
- **Connected heaters**: Heat and Off
- **Temperature Control**: Set target temperature with precise control
- **Fan Speed Control**: Multiple fan speed settings
- **Status Updates**: Cloud polling, with commanded states reconciled as the service reports them

### Sensors
- **Room Temperature**: Current ambient temperature
- **Target Temperature**: Current temperature setpoint
- **Room Humidity**: Current humidity levels
- **Device Status**: Operating status (on/off/standby)
- **Device Mode**: Current operating mode
- **Fan Speed**: Current fan speed setting
- **Pipe Temperature**: Refrigerant pipe (evaporator) temperature, useful for seeing when the compressor is working
- **Remote Control**: Temperature and humidity measured by the CST remote, plus whether it is connected, docked and being used
- **myEcoReal Feel Comfort**: The comfort light colour (inactive, perfect, or not optimal)
- **Alarms**: Tray full, probe failure, low humidity, frost protection and high temperature
- **Timer and Schedule**: Whether the timer or weekly schedule is active

### Controls
- **Power Switch**: Turn device on/off
- **Temperature Controls**: Precise temperature adjustment
- **Mode Selection**: Easy switching between operating modes
- **Fan Speed Selection**: Control fan speed levels

Entities are created only for the properties your model reports, so a model without a given feature does not get an empty entity for it. Entities that repeat the climate entity (target temperature, status, mode, fan speed, silent mode sensors, the power switch and the temperature number) are disabled by default on new installs.

### Advanced Features
- **Configuration Flow**: Easy setup through Home Assistant UI
- **Account Discovery**: Finds devices associated with the configured account
- **Cloud Polling**: Configurable 60-second default interval (30-300 seconds)

## 📋 Requirements

- Home Assistant 2024.8.0 or newer
- De'Longhi Comfort account with registered devices
- Internet connection for cloud API access

## 🔧 Installation

### Method 1: HACS Custom Repository
1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add `https://github.com/DA-Osborne/delonghi-comfort-integration` as an Integration repository
5. Find "De'Longhi Comfort" in the list and install it
6. Restart Home Assistant

### Method 2: Manual Installation
1. **Download the integration**:
   ```bash
    git clone https://github.com/DA-Osborne/delonghi-comfort-integration.git
   ```

2. **Copy to custom_components**:
   Copy the `custom_components/delonghi_comfort` folder to your Home Assistant `custom_components` directory:
   ```
   config/
   └── custom_components/
       └── delonghi_comfort/
           ├── __init__.py
           ├── api.py
           ├── climate.py
           ├── config_flow.py
           ├── const.py
           ├── coordinator.py
           ├── manifest.json
           ├── number.py
           ├── select.py
           ├── sensor.py
           ├── switch.py
           └── translations/
               └── en.json
   ```

3. **Restart Home Assistant**

## ⚙️ Configuration

### Initial Setup
1. Navigate to **Settings** → **Devices & Services** in Home Assistant
2. Click **Add Integration**
3. Search for **De'Longhi Comfort**
4. Enter your De'Longhi Comfort account credentials:
   - **Username**: Your De'Longhi account email
   - **Password**: Your De'Longhi account password
   - **Language**: Select the language/locale used for account authentication

### Configuration Options
- **Scan Interval**: How often to poll the API (default: 60 seconds; 30-300 seconds)

## 🏠 Usage

### Dashboard Cards
Once configured, you'll have access to various entities:

#### Climate Entity
- `climate.delonghi_comfort_[device_id]`
- Full climate control with temperature, mode, and fan speed

#### Sensors
- `sensor.delonghi_comfort_[device_id]_room_temperature`
- `sensor.delonghi_comfort_[device_id]_room_humidity`
- `sensor.delonghi_comfort_[device_id]_target_temperature`
- `sensor.delonghi_comfort_[device_id]_device_status`

#### Controls
- `switch.delonghi_comfort_[device_id]_power`
- `number.delonghi_comfort_[device_id]_temperature`
- `select.delonghi_comfort_[device_id]_mode`
- `select.delonghi_comfort_[device_id]_fan_speed`

## 🐛 Troubleshooting

### Common Issues
1. **Authentication Errors**: Verify your De'Longhi account credentials
2. **No Devices Found**: Ensure devices are registered in the De'Longhi app
3. **Connection Timeouts**: Check internet connection and API status
4. **Slow Updates**: Adjust scan interval in configuration

### Debug Logging
Add to your `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.delonghi_comfort: debug
```

### Device API Inspection
  The repository includes `scripts/inspect_device.py` for local troubleshooting. It prompts for credentials (or reads `DELONGHI_USERNAME`, `DELONGHI_PASSWORD`, `DELONGHI_LANGUAGE` and `DELONGHI_DEVICE_INDEX` from the environment), lists account devices, and writes the selected device's raw property data to `scripts/delonghi_device_dump.json`. Use `--label NAME` to write `scripts/delonghi_device_dump_NAME.json` instead. The dump may contain device identifiers, network details, and property values; review and redact it before sharing. Generated dumps are excluded from Git.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Automated Workflows

This repository includes GitHub Actions for quality assurance and release management:

#### 🔍 Validation Workflow
- **Triggers**: Runs on every push to main/master and on pull requests
- **Validates**: 
  - Python syntax and compilation
  - Home Assistant manifest.json structure
  - HACS compatibility requirements
  - File structure integrity
  - Basic code quality checks

#### 🚀 Release Workflow
- **Triggers**: Runs when tags are pushed (e.g., `v1.0.0`) or manually triggered
- **Creates**:
  - `delonghi_comfort.zip` - Integration files only (for HACS/manual install)
  - `delonghi-comfort-integration-[version].zip` - Complete package with documentation
  - GitHub release with auto-generated release notes
- **Updates**: Automatically updates version in manifest.json to match the tag

To create a new release:
```bash
git tag v1.0.0
git push origin v1.0.0
```

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

### License Attribution

This project incorporates code from the following Apache 2.0 licensed projects:
- **[rtfpessoa/delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)** - Licensed under Apache 2.0
- **[duckwc/ECAMpy](https://github.com/duckwc/ECAMpy)** - Authentication and token conversion code

All modifications and additions to the original code are also licensed under Apache 2.0. See the NOTICE file for detailed attribution information.

## 🙏 Acknowledgments

- **[rtfpessoa](https://github.com/rtfpessoa)** for the original [delonghi-comfort-client](https://github.com/rtfpessoa/delonghi-comfort-client)
- **[duckwc](https://github.com/duckwc)** for the authentication code from [ECAMpy](https://github.com/duckwc/ECAMpy)
- The Home Assistant community for guidance and best practices

## 📞 Support

- Create an issue on GitHub for bug reports
- Check existing issues before creating new ones
- Provide logs and device information when reporting issues