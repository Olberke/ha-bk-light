"""Constants for the BK-Light integration."""

from __future__ import annotations

DOMAIN = "bk_light"
DEVICE_NAME_PREFIX = "LED_BLE_"

# Actions
SERVICE_DISPLAY_CLOCK = "display_clock"
SERVICE_DISPLAY_TEXT = "display_text"
SERVICE_SCROLL_TEXT = "scroll_text"
SERVICE_STOP_ANIMATION = "stop_animation"
SERVICE_DISPLAY_IMAGE = "display_image"
SERVICE_PLAY_GIF = "play_gif"

# Common action attributes
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_BACKGROUND_COLOR = "background_color"

# Text attributes
ATTR_TEXT = "text"
ATTR_TEXT_COLOR = "text_color"
ATTR_FONT_SIZE = "font_size"
ATTR_AUTO_FIT = "auto_fit"
ATTR_HORIZONTAL_ALIGN = "horizontal_align"
ATTR_VERTICAL_ALIGN = "vertical_align"
ATTR_X_OFFSET = "x_offset"
ATTR_Y_OFFSET = "y_offset"

# Animation attributes
ATTR_DIRECTION = "direction"
ATTR_FPS = "fps"
ATTR_STEP = "step"
ATTR_GAP = "gap"
ATTR_REPEAT = "repeat"

# Image/GIF attributes
ATTR_MEDIA = "media"
ATTR_PATH = "path"  # Legacy YAML compatibility
ATTR_FIT = "fit"
ATTR_ROTATION = "rotation"
ATTR_MIRROR_HORIZONTAL = "mirror_horizontal"
ATTR_MIRROR_VERTICAL = "mirror_vertical"
ATTR_BRIGHTNESS = "brightness"
ATTR_RESAMPLING = "resampling"
ATTR_SPEED = "speed"
ATTR_MAX_FPS = "max_fps"

# Clock attributes
ATTR_CLOCK_STYLE = "style"
ATTR_CLOCK_FORMAT_24H = "format_24h"
ATTR_CLOCK_SHOW_DATE = "show_date"

# ACT1026
PANEL_WIDTH = 32
PANEL_HEIGHT = 32

# ACT1025:
# PANEL_WIDTH = 64
# PANEL_HEIGHT = 16

DEFAULT_CLOCK_STYLE = 1
DEFAULT_CLOCK_FORMAT_24H = True
DEFAULT_CLOCK_SHOW_DATE = True
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)
DEFAULT_FONT_SIZE = 20
DEFAULT_AUTO_FIT = True
DEFAULT_HORIZONTAL_ALIGN = "center"
DEFAULT_VERTICAL_ALIGN = "center"

DEFAULT_SCROLL_DIRECTION = "left"
DEFAULT_SCROLL_FPS = 8.0
DEFAULT_SCROLL_STEP = 1
DEFAULT_SCROLL_GAP = 8
DEFAULT_SCROLL_REPEAT = 1

DEFAULT_IMAGE_FIT = "contain"
DEFAULT_IMAGE_ROTATION = 0
DEFAULT_MIRROR_HORIZONTAL = False
DEFAULT_MIRROR_VERTICAL = False
DEFAULT_IMAGE_BRIGHTNESS = 1.0
DEFAULT_RESAMPLING = "lanczos"

DEFAULT_GIF_SPEED = 1.0
DEFAULT_GIF_MAX_FPS = 8.0
