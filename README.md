# BK-Light LED Matrix for Home Assistant

Custom Home Assistant integration for controlling a BK-Light RGB LED matrix
over Bluetooth Low Energy.

The integration has been tested with an ACT1026 panel featuring a 32 x 32 pixel
RGB LED matrix.

## Features

- Automatic Bluetooth discovery for devices named `LED_BLE_*`
- Configuration through the Home Assistant user interface
- BK-Light BLE handshake
- Automatic reconnection
- Static text
- Scrolling text
- Static images
- Animated GIFs
- Media selection through the Home Assistant media browser
- Image scaling, rotation and mirroring
- Animation cancellation
- German and English translations
- Full support for the visual automation editor

## Supported hardware

Tested hardware:

- Model: ACT1026
- Resolution: 32 x 32 pixels
- Bluetooth name: `LED_BLE_*`

Other BK-Light devices using the same protocol may work, but have not
necessarily been tested.

## Installation with HACS

1. Open HACS in Home Assistant.
2. Open **Integrations**.
3. Open the three-dot menu.
4. Select **Custom repositories**.
5. Add the following repository:

       https://github.com/olberke/ha-bk-light

6. Select **Integration** as the repository type.
7. Install **BK-Light LED Matrix**.
8. Restart Home Assistant completely.

Do not edit `/config/custom_components/bk_light` directly after installing the
integration through HACS. HACS manages this directory and may overwrite manual
changes.

## Configuration

The integration supports automatic Bluetooth discovery.

To configure it manually:

1. Open **Settings**.
2. Open **Devices & services**.
3. Select **Add integration**.
4. Search for **BK-Light LED Matrix**.
5. Select the discovered Bluetooth device.

The device must be switched on and within Bluetooth range of Home Assistant.

## Actions

The integration provides the following Home Assistant actions:

- `bk_light.display_text`
- `bk_light.scroll_text`
- `bk_light.display_image`
- `bk_light.play_gif`
- `bk_light.stop_animation`

The visual automation editor is the recommended way to configure these
actions. It provides display selection, color pickers, sliders, media selection
and translated option names.

## Static text example

Replace `YOUR_CONFIG_ENTRY_ID` with the config-entry ID of the configured
BK-Light display. When using the visual editor, the display can be selected
from a menu instead.

    action: bk_light.display_text
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      text: "Hello!"
      text_color: [255, 255, 255]
      background_color: [0, 0, 0]
      font_size: 20
      auto_fit: true
      horizontal_align: center
      vertical_align: center
      x_offset: 0
      y_offset: 0

Starting a static-text action stops any currently running scrolling-text or GIF
animation.

## Scrolling text example

    action: bk_light.scroll_text
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      text: "Home Assistant"
      text_color: [255, 255, 255]
      background_color: [0, 0, 0]
      font_size: 20
      auto_fit: true
      vertical_align: center
      direction: left
      fps: 8
      step: 1
      repeat: 1
      gap: 8
      y_offset: 0

For scrolling text:

- `direction` can be `left` or `right`.
- `fps` can be between 1 and 12.
- Approximately 8 to 10 FPS is recommended.
- `repeat: 0` means that the animation repeats indefinitely.
- `step` controls the number of pixels moved per frame.

## Images and GIFs

Images and GIFs can be selected through the Home Assistant media browser.

The recommended directory is:

    /media/bk_light/

Legacy file paths remain supported through:

    /config/www/bk_light/

A legacy `path` value is relative to `/config/www/bk_light/`.

Example:

    action: bk_light.display_image
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      path: "bild.PNG"
      fit: contain
      background_color: [0, 0, 0]
      brightness: 1.0
      resampling: lanczos
      rotation: 0
      mirror_horizontal: false
      mirror_vertical: false

The legacy path resolver also considers differences in uppercase and lowercase
file names.

### Media directory configuration

The existing `/config/www/bk_light` directory can optionally be exposed through
the Home Assistant media browser:

    homeassistant:
      media_dirs:
        bk_light: /config/www/bk_light

Restart Home Assistant after changing `configuration.yaml`.

## GIF example

    action: bk_light.play_gif
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"
      path: "animation.gif"
      fit: contain
      background_color: [0, 0, 0]
      brightness: 1.0
      resampling: nearest
      rotation: 0
      mirror_horizontal: false
      mirror_vertical: false
      speed: 1.0
      max_fps: 8
      repeat: 0

For GIF playback:

- `speed: 1.0` uses the original GIF timing.
- `max_fps` can be between 1 and 12.
- Approximately 8 to 10 FPS is recommended.
- `repeat: 0` repeats indefinitely.
- GIF frames are prepared before playback starts.
- Fast GIFs are limited to the configured maximum Bluetooth frame rate.

## Stop an animation

    action: bk_light.stop_animation
    data:
      config_entry_id: "YOUR_CONFIG_ENTRY_ID"

This stops the currently running scrolling-text or GIF animation.

Starting another text, image or animation action also stops the previous
animation for the selected display.

## Image fitting

Available fitting modes:

- `contain`: show the complete image and preserve its aspect ratio
- `cover`: fill the complete panel and crop if required
- `stretch`: resize the image directly to 32 x 32 pixels

Available resampling modes:

- `nearest`: recommended for pixel art
- `lanczos`: recommended for photographs and smooth graphics

Supported rotations:

- `0`
- `90`
- `180`
- `270`

## Troubleshooting

### Device is not discovered

Check that:

- the panel is switched on;
- the Bluetooth name begins with `LED_BLE_`;
- the panel is within Bluetooth range;
- a Bluetooth adapter or Bluetooth proxy is available to Home Assistant;
- the device is not currently connected to another application.

### Enable debug logging

Add the following configuration to `configuration.yaml`:

    logger:
      logs:
        custom_components.bk_light: debug

Restart Home Assistant and inspect the logs for entries containing `bk_light`.

### HACS update does not appear active

After downloading or updating the integration through HACS, restart Home
Assistant completely. Reloading only the integration may not reload all Python
modules.

## Technical notes

Animations are currently implemented by transmitting complete 32 x 32 image
frames over Bluetooth Low Energy.

Native scrolling-text or native animation commands provided by the panel
protocol are not currently used.

## Credits and attribution

This Home Assistant integration uses protocol knowledge and derived components
from the BK-Light toolkit created by
[Puparia](https://github.com/Pupariaa).

Original project:

[Pupariaa/Bk-Light-AppBypass](https://github.com/Pupariaa/Bk-Light-AppBypass)

The original project is distributed under the MIT License.

Copyright (c) 2025 Puparia (Pupariaa)

When reusing this toolkit or derivatives, credit:

    Puparia / https://github.com/Pupariaa

and link back to the original repository.

See [NOTICE.md](NOTICE.md) for additional attribution information.

## License

This project is distributed under the MIT License. See [LICENSE](LICENSE) for
details.
