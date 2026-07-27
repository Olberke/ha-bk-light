# BK-Light LED Matrix for Home Assistant

Custom integration for BK-Light RGB LED matrices using Bluetooth Low Energy.

## Current features

- Automatic discovery of `LED_BLE_*` devices
- BK-Light BLE handshake and image transfer
- Static text
- Scrolling text
- Static images
- GIF animations
- Fully guided Home Assistant action UI
- ACT1026 panel size: 32×32 pixels
- Prepared animation frames stored in RAM before playback

## Installation for development

Copy:

```text
custom_components/bk_light
```

to:

```text
/config/custom_components/bk_light
```

Restart Home Assistant and add **BK-Light LED Matrix** under
**Settings → Devices & services**.

## Local media

For the visual media picker, store images and GIF files below:

```text
/media/
```

Legacy YAML paths below `/config/www/bk_light/` remain supported.

## Available actions

- `bk_light.display_text`
- `bk_light.scroll_text`
- `bk_light.display_image`
- `bk_light.play_gif`
- `bk_light.stop_animation`

## Animation note

Animations currently transfer complete confirmed PNG frames over BLE. For the
ACT1026, approximately 8–10 FPS is usually smoother and more reliable than
higher frame rates. Native panel-side scrolling is not yet implemented.

## Development status

The integration is under active development and has been tested with an
ACT1026 32×32 panel.
