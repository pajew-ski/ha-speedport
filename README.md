# Speedport Integration for Home Assistant (Maintained Fork)

[![hacs_badge](https://img.shields.io/badge/hacs-Default-41BDF5.svg)](https://hacs.xyz)
[![GitHub](https://img.shields.io/github/license/pajew-ski/hacs-speedport?color=red)](https://github.com/pajew-ski/hacs-speedport/blob/main/LICENSE)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/pajew-ski/hacs-speedport?color=green)](https://github.com/pajew-ski/hacs-speedport/releases/latest)

> **This is an actively maintained fork of the [original Speedport integration](https://github.com/Andre0512/speedport) by [@Andre0512](https://github.com/Andre0512), which is no longer maintained.**
> If you are currently using the original integration, you can switch to this fork to continue receiving updates and bug fixes.

Telekom Speedport Integration for Home Assistant based
on [speedport-api](https://github.com/Andre0512/speedport-api.git).

## Features

- Track presence of connected devices
- Turn on/off wifi (guest/office/normal)
- Reconnect, reboot, wps on
- Sensors (IP-Addresses, Upload/Download, Connection, ...)

## Supported devices

* Speedport Smart 3
* Speedport Smart 4

## Installation

> **Important:** If you have the original (unmaintained) Speedport integration installed, remove it first before installing this fork. Both use the same `speedport` domain and cannot coexist.

**Method 1:** [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=pajew-ski&repository=hacs-speedport&category=integration)

**Method 2:** [HACS](https://hacs.xyz/) > Integrations > Add Integration > **Speedport (maintained fork)** > Install

**Method 3:** Manually copy `speedport` folder from [latest release](https://github.com/pajew-ski/hacs-speedport/releases/latest) to `config/custom_components` folder.

_Restart Home Assistant_

## Switching from the original integration

1. Remove the original **Speedport** integration via HACS
2. Restart Home Assistant
3. Install this fork using one of the methods above
4. Restart Home Assistant

Your existing configuration and entities will be preserved since the domain name is identical.

## Configuration

**Method 1**: [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=speedport)

**Method 2**: Settings > Devices & Services > Add Integration > **Speedport**
_If the integration is not in the list, you need to clear the browser cache._

### Further Information

If you have email notifications enabled, make sure you have the "A security related event has occurred" option unchecked
or you will receive a lot of emails, see [#1](https://github.com/Andre0512/speedport/issues/1).
