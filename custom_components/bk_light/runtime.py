"""Runtime management for BK-Light displays."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .display_session import BkLightError, BleDisplaySession

_LOGGER = logging.getLogger(__name__)

ANIMATION_START_TIMEOUT = 20.0
THROUGHPUT_SAMPLE_FRAMES = 5


@dataclass(slots=True)
class BkLightRuntimeData:
    """Runtime data for one BK-Light config entry."""

    session: BleDisplaySession

    _animation_task: asyncio.Task[None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _control_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
        repr=False,
    )
    _last_animation_error: str | None = field(
        default=None,
        init=False,
    )

    @property
    def animation_running(self) -> bool:
        """Return whether an animation is active."""
        return (
            self._animation_task is not None
            and not self._animation_task.done()
        )

    @property
    def last_animation_error(self) -> str | None:
        """Return the most recent animation error."""
        return self._last_animation_error

    async def async_start_animation(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        frames: Sequence[bytes],
        fps: float,
        repeat: int,
    ) -> None:
        """Start a fixed-rate animation, such as scrolling text."""
        if not frames:
            raise ValueError("Animation contains no frames")
        if fps <= 0:
            raise ValueError("FPS must be greater than zero")
        if repeat < 0:
            raise ValueError("Repeat must not be negative")

        frame_interval = 1.0 / fps

        await self._async_start_animation_task(
            hass=hass,
            entry=entry,
            frames=tuple(frames),
            durations=tuple(frame_interval for _ in frames),
            repeat=repeat,
            name=f"BK-Light scrolling text {entry.title}",
            requested_fps=fps,
        )

    async def async_start_timed_animation(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        frames: Sequence[bytes],
        durations: Sequence[float],
        repeat: int,
    ) -> None:
        """Start an animation with an individual duration per frame."""
        if not frames:
            raise ValueError("Animation contains no frames")
        if len(frames) != len(durations):
            raise ValueError(
                "Animation frame and duration counts do not match"
            )
        if repeat < 0:
            raise ValueError("Repeat must not be negative")
        if any(duration <= 0 for duration in durations):
            raise ValueError(
                "Every animation duration must be greater than zero"
            )

        shortest_duration = min(durations)
        requested_fps = 1.0 / shortest_duration

        await self._async_start_animation_task(
            hass=hass,
            entry=entry,
            frames=tuple(frames),
            durations=tuple(float(value) for value in durations),
            repeat=repeat,
            name=f"BK-Light GIF animation {entry.title}",
            requested_fps=requested_fps,
        )

    async def async_stop_animation(self) -> None:
        """Stop the current animation and reset the BLE transport."""
        async with self._control_lock:
            await self._async_cancel_animation_locked(
                disconnect_after_cancel=True,
            )

    async def async_close(self) -> None:
        """Stop the animation and close the BLE session."""
        async with self._control_lock:
            await self._async_cancel_animation_locked(
                disconnect_after_cancel=False,
            )
            await self.session.async_close()

    async def _async_start_animation_task(
        self,
        *,
        hass: HomeAssistant,
        entry: ConfigEntry,
        frames: tuple[bytes, ...],
        durations: tuple[float, ...],
        repeat: int,
        name: str,
        requested_fps: float,
    ) -> None:
        """Replace the current animation and wait for its first frame."""
        started: asyncio.Future[None] = (
            asyncio.get_running_loop().create_future()
        )

        async with self._control_lock:
            await self._async_cancel_animation_locked(
                disconnect_after_cancel=True,
            )
            self._last_animation_error = None

            task = entry.async_create_background_task(
                hass,
                self._async_play_timed_frames(
                    frames=frames,
                    durations=durations,
                    repeat=repeat,
                    started=started,
                    requested_fps=requested_fps,
                ),
                name=name,
                eager_start=True,
            )

            self._animation_task = task
            task.add_done_callback(self._handle_animation_done)

        try:
            async with asyncio.timeout(ANIMATION_START_TIMEOUT):
                await asyncio.shield(started)
        except TimeoutError as err:
            await self.async_stop_animation()
            raise BkLightError(
                "Der erste Animationsframe konnte nicht rechtzeitig "
                "übertragen werden"
            ) from err
        except asyncio.CancelledError:
            await self.async_stop_animation()
            raise
        except Exception:
            await self.async_stop_animation()
            raise

    async def _async_cancel_animation_locked(
        self,
        *,
        disconnect_after_cancel: bool,
    ) -> None:
        """Cancel the animation while the control lock is held."""
        task = self._animation_task
        self._animation_task = None

        if task is not None and not task.done():
            task.cancel()

            with suppress(asyncio.CancelledError):
                await task

        # Cancelling an active GATT write can leave the protocol state dirty.
        # A clean reconnect guarantees a complete handshake for the next action.
        if disconnect_after_cancel and self.session.is_connected:
            await self.session.async_disconnect()

    async def _async_play_timed_frames(
        self,
        *,
        frames: tuple[bytes, ...],
        durations: tuple[float, ...],
        repeat: int,
        started: asyncio.Future[None],
        requested_fps: float,
    ) -> None:
        """Play prepared protocol frames using per-frame timing."""
        loop = asyncio.get_running_loop()

        completed_iterations = 0
        sent_frames = 0
        total_transfer_time = 0.0
        throughput_warning_logged = False

        try:
            while repeat == 0 or completed_iterations < repeat:
                for frame, duration in zip(
                    frames,
                    durations,
                    strict=True,
                ):
                    frame_started = loop.time()

                    await self.session.send_frame(
                        frame,
                        delay=0.0,
                    )

                    transfer_time = loop.time() - frame_started
                    sent_frames += 1
                    total_transfer_time += transfer_time

                    if not started.done():
                        started.set_result(None)

                    remaining = duration - transfer_time
                    if remaining > 0:
                        await asyncio.sleep(remaining)

                    if (
                        not throughput_warning_logged
                        and sent_frames >= THROUGHPUT_SAMPLE_FRAMES
                    ):
                        average_transfer = (
                            total_transfer_time / sent_frames
                        )
                        sustainable_fps = (
                            1.0 / average_transfer
                            if average_transfer > 0
                            else requested_fps
                        )
                        shortest_duration = min(durations)

                        if average_transfer > shortest_duration:
                            throughput_warning_logged = True
                            _LOGGER.warning(
                                (
                                    "%s: requested up to %.1f FPS, but one "
                                    "confirmed BK-Light frame takes %.1f ms "
                                    "on average. Sustainable throughput is "
                                    "about %.1f FPS."
                                ),
                                self.session.address,
                                requested_fps,
                                average_transfer * 1000.0,
                                sustainable_fps,
                            )

                completed_iterations += 1

        except asyncio.CancelledError:
            if not started.done():
                started.cancel()

            _LOGGER.debug(
                "%s: BK-Light animation cancelled",
                self.session.address,
            )
            raise

        except Exception as err:
            self._last_animation_error = (
                f"{type(err).__name__}: {err}"
            )

            if not started.done():
                started.set_exception(err)
            else:
                _LOGGER.exception(
                    "%s: BK-Light animation stopped after %d frame(s)",
                    self.session.address,
                    sent_frames,
                )

            with suppress(Exception):
                await self.session.async_disconnect()

    @callback
    def _handle_animation_done(
        self,
        task: asyncio.Task[None],
    ) -> None:
        """Clear the stored task and consume its exception."""
        if self._animation_task is task:
            self._animation_task = None

        if task.cancelled():
            return

        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return

        if exception is not None:
            _LOGGER.error(
                "%s: animation task ended unexpectedly: %s",
                self.session.address,
                exception,
                exc_info=(
                    type(exception),
                    exception,
                    exception.__traceback__,
                ),
            )
