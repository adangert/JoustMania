"""Manages communication between PSMoveAPI and JoustMania's per-controller
gameplay processes. Native controller access is handled in a dedicated API
process, while shared state carries controller input, color, and rumble between
processes.
"""

import atexit
import ctypes
from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time


MAX_CONTROLLERS = 64
_VECTOR_SIZE = MAX_CONTROLLERS * 3


class ControllerManager:
    """Holds controller data shared by the API and JoustMania processes.
    Frequent motion updates need low-overhead communication that does not
    serialize every report. RawArray objects store numeric controller data,
    Manager proxies map controller serials to indexes, and Events control API
    startup and shutdown.

    Used in:

    - controller_manager.py: publish upstream events and apply output
    - piparty.py: pass the manager when starting controller workers
    - controller_process.py: attach each worker to the existing manager
    """

    def __init__(self, manager):
        self.serial_to_index = manager.dict()
        self.index_to_serial = manager.list([""] * MAX_CONTROLLERS)
        self.status = manager.dict()
        self.stop_event = multiprocessing.Event()
        self.ready_event = multiprocessing.Event()

        self.active = multiprocessing.RawArray(ctypes.c_ubyte, MAX_CONTROLLERS)
        self.usb = multiprocessing.RawArray(ctypes.c_ubyte, MAX_CONTROLLERS)
        self.bluetooth = multiprocessing.RawArray(ctypes.c_ubyte, MAX_CONTROLLERS)
        self.state_sequence = multiprocessing.RawArray(ctypes.c_ulonglong, MAX_CONTROLLERS)
        self.buttons = multiprocessing.RawArray(ctypes.c_uint, MAX_CONTROLLERS)
        self.pressed = multiprocessing.RawArray(ctypes.c_uint, MAX_CONTROLLERS)
        self.released = multiprocessing.RawArray(ctypes.c_uint, MAX_CONTROLLERS)
        self.trigger = multiprocessing.RawArray(ctypes.c_float, MAX_CONTROLLERS)
        self.accelerometer = multiprocessing.RawArray(ctypes.c_float, _VECTOR_SIZE)
        self.gyroscope = multiprocessing.RawArray(ctypes.c_float, _VECTOR_SIZE)
        self.battery = multiprocessing.RawArray(ctypes.c_int, MAX_CONTROLLERS)

        self.leds = multiprocessing.RawArray(ctypes.c_ubyte, _VECTOR_SIZE)
        self.rumble = multiprocessing.RawArray(ctypes.c_ubyte, MAX_CONTROLLERS)

    def active_controller_indices(self):
        return [
            controller_index
            for controller_index in range(MAX_CONTROLLERS)
            if self.active[controller_index]
        ]

    def connected_serials(self):
        return [
            self.index_to_serial[controller_index]
            for controller_index in self.active_controller_indices()
        ]

    def connected_controllers(self):
        return [
            Controller(self.index_to_serial[controller_index], self)
            for controller_index in self.active_controller_indices()
        ]

    def count_connected(self):
        return len(self.active_controller_indices())

    def get_or_assign_controller_index(self, serial):
        """Returns the shared-state index assigned to a controller serial."""
        existing = self.serial_to_index.get(serial)
        if existing is not None:
            return existing

        for controller_index in range(MAX_CONTROLLERS):
            if not self.index_to_serial[controller_index]:
                self.index_to_serial[controller_index] = serial
                self.serial_to_index[serial] = controller_index
                return controller_index
        raise RuntimeError(
            "More than {} controllers are connected".format(MAX_CONTROLLERS)
        )


_shared_object_manager = None
_controller_manager = None
_api_process = None
_api_process_owner_pid = None


def _write_vector_to_shared_state(values, controller_index, vector):
    """Copies an upstream x, y, z vector into one controller's shared state."""
    offset = controller_index * 3
    values[offset] = vector.x
    values[offset + 1] = vector.y
    values[offset + 2] = vector.z


def _mark_state_write_started(manager, controller_index):
    """Marks a controller index as being written by making its sequence odd."""
    manager.state_sequence[controller_index] += 1


def _mark_state_write_finished(manager, controller_index):
    """Publishes a completed controller state by making its sequence even."""
    manager.state_sequence[controller_index] += 1


def _check_write_in_progress(manager, controller_index) -> bool:
    """Returns True while the API process is writing this controller index."""
    return manager.state_sequence[controller_index] % 2 == 1


def _binding_paths():
    """Returns paths into the adjacent PSMoveAPI checkout used by this module.
    _api_process_main() loads the Python ctypes binding and native library from
    these paths, while pair_controller() uses the build path for the upstream
    pairing executable.
    """
    checkout = Path(__file__).resolve().parent.parent / "psmoveapi"
    return checkout / "bindings" / "python", checkout / "build"


def _api_process_main(manager):
    """Runs a PSMoveAPI instance used by this integration for all controllers.
    start_manager() launches this function in a background process and passes
    the shared ControllerManager to it. Controller input and output are copied
    through that manager for the per-controller processes in
    controller_process.py. Each psmove_api.update() call enters the native
    library, which invokes the registered ctypes callbacks for controller
    events.
    """
    # The delayed import keeps the ctypes binding and libpsmoveapi.so inside
    # the API process. Other JoustMania processes only use shared state.
    bindings, library = _binding_paths()
    if str(bindings) not in sys.path:
        sys.path.insert(0, str(bindings))
    os.environ.setdefault("PSMOVEAPI_LIBRARY_PATH", str(library))

    try:
        import psmoveapi
    except (ImportError, OSError) as error:
        manager.status["error"] = repr(error)
        manager.ready_event.set()
        raise RuntimeError(
            "Could not load the current PSMove API ctypes binding. Run setup.sh first."
        ) from error

    local_controller_indices = {}

    def controller_index_for(serial):
        controller_index = local_controller_indices.get(serial)
        if controller_index is None:
            controller_index = manager.get_or_assign_controller_index(serial)
            local_controller_indices[serial] = controller_index
        return controller_index

    class PSMoveEventReceiver(psmoveapi.PSMoveAPI):
        """Extends psmoveapi.PSMoveAPI with JoustMania's controller callbacks.
        The upstream binding calls these methods after native PSMoveAPI reports
        connection, input, or disconnection events. Input is copied into the
        ControllerManager, while requested color and rumble are copied back to
        the upstream ctypes controller structure.

        Used in:

        - controller_manager.py: run the PSMoveAPI event loop
        """

        def on_connect(self, psmove_controller):
            """Registers an upstream controller in JoustMania shared state.
            The upstream binding calls this method after a native controller is
            discovered and provides its ctypes-backed controller wrapper.
            """
            controller_index = controller_index_for(psmove_controller.serial)
            manager.active[controller_index] = 1
            manager.usb[controller_index] = int(psmove_controller.usb)
            manager.bluetooth[controller_index] = int(psmove_controller.bluetooth)

        def on_update(self, psmove_controller):
            """Exchanges input and output with an upstream controller callback.
            psmove_api.update() enters native PSMoveAPI, which invokes the
            ctypes callback that leads here. Input fields are copied into
            shared state before requested color and rumble are copied into the
            upstream ControllerStruct. Native PSMoveAPI applies those output
            fields after this callback returns.
            """
            controller_index = controller_index_for(psmove_controller.serial)
            manager.active[controller_index] = 1
            manager.usb[controller_index] = int(psmove_controller.usb)
            manager.bluetooth[controller_index] = int(psmove_controller.bluetooth)

            _mark_state_write_started(manager, controller_index)
            manager.buttons[controller_index] = psmove_controller.buttons
            manager.pressed[controller_index] |= psmove_controller.pressed
            manager.released[controller_index] |= psmove_controller.released
            manager.trigger[controller_index] = psmove_controller.trigger
            _write_vector_to_shared_state(
                manager.accelerometer,
                controller_index,
                psmove_controller.accelerometer,
            )
            _write_vector_to_shared_state(
                manager.gyroscope,
                controller_index,
                psmove_controller.gyroscope,
            )
            manager.battery[controller_index] = psmove_controller.battery
            _mark_state_write_finished(manager, controller_index)

            # These assignments update the upstream ctypes ControllerStruct.
            # Native PSMoveAPI sends them after this callback returns.
            offset = controller_index * 3
            psmove_controller.color = psmoveapi.RGB(
                manager.leds[offset] / 255.0,
                manager.leds[offset + 1] / 255.0,
                manager.leds[offset + 2] / 255.0,
            )
            psmove_controller.rumble = manager.rumble[controller_index] / 255.0

        def on_disconnect(self, psmove_controller):
            """Marks an upstream controller as disconnected in shared state.
            Its serial-to-index mapping remains available so a reconnecting
            controller can continue using the same controller index.
            """
            controller_index = local_controller_indices.get(psmove_controller.serial)
            if controller_index is not None:
                manager.active[controller_index] = 0
                manager.usb[controller_index] = 0
                manager.bluetooth[controller_index] = 0

    try:
        # Constructing PSMoveEventReceiver through psmoveapi.PSMoveAPI registers
        # these ctypes callbacks and initializes native libpsmoveapi access.
        psmove_api = PSMoveEventReceiver()

        # The API process is ready after upstream initialization succeeds.
        manager.status["pid"] = os.getpid()
        manager.status.pop("error", None)
        manager.ready_event.set()
        while not manager.stop_event.is_set():
            # Upstream update enters libpsmoveapi and dispatches the callbacks above.
            psmove_api.update()
            time.sleep(0.001)
    except Exception as error:
        manager.status["error"] = repr(error)
        manager.ready_event.set()
        raise
    finally:
        if "psmove_api" in locals():
            del psmove_api


def start_manager():
    """Starts the API process and returns its shared ControllerManager.
    multiprocessing.Process calls _api_process_main() in the background with
    the same shared arrays used by JoustMania's controller processes. A child
    controller process reuses the inherited manager instead of starting
    another API process.
    """
    global _shared_object_manager, _controller_manager
    global _api_process, _api_process_owner_pid
    if _controller_manager is not None and _api_process_owner_pid not in (None, os.getpid()):
        return _controller_manager
    if _api_process is not None and _api_process.is_alive():
        return _controller_manager

    if _shared_object_manager is None:
        _shared_object_manager = multiprocessing.Manager()
    if _controller_manager is None:
        _controller_manager = ControllerManager(_shared_object_manager)

    _controller_manager.stop_event.clear()
    _controller_manager.ready_event.clear()
    _controller_manager.status.pop("error", None)
    _api_process = multiprocessing.Process(
        target=_api_process_main,
        args=(_controller_manager,),
        name="PSMoveAPI-manager",
        daemon=True,
    )
    _api_process.start()
    _api_process_owner_pid = os.getpid()
    if not _controller_manager.ready_event.wait(timeout=10):
        stop_manager()
        raise RuntimeError("PS Move API process did not start within 10 seconds")
    if "error" in _controller_manager.status:
        error = _controller_manager.status["error"]
        stop_manager()
        raise RuntimeError("PS Move API process failed to start: {}".format(error))
    return _controller_manager


def stop_manager():
    global _api_process
    if _api_process is None:
        return
    if _api_process_owner_pid != os.getpid():
        return
    _controller_manager.stop_event.set()
    _api_process.join(timeout=3)
    if _api_process.is_alive():
        _api_process.terminate()
        _api_process.join()
    _api_process = None


atexit.register(stop_manager)


def use_manager(manager):
    """Attaches a spawned controller process to the existing manager."""
    global _controller_manager
    _controller_manager = manager


def get_manager():
    """Returns the controller manager, starting its API process if needed."""
    return start_manager()


def get_manager_process_pid():
    start_manager()
    return _controller_manager.status.get("pid")


def pair_controller(host_address):
    """Pairs USB controllers with the selected host using the upstream CLI."""
    _, build = _binding_paths()
    command = [str(build / "psmove"), "pair"]
    environment = os.environ.copy()
    if host_address:
        # Tell PSMoveAPI to pair with the least-loaded adapter selected by JoustMania.
        environment["PSMOVE_PREFER_BLUETOOTH_HOST_ADDRESS"] = host_address.lower()

    stop_manager()
    try:
        # Upstream returns its final C pairing boolean directly as the exit status.
        paired = subprocess.run(command, check=False, env=environment).returncode == 1
        if paired and sys.platform.startswith("linux"):
            # Upstream can start BlueZ before its new registration is visible.
            # Reload it while the API process is stopped, then allow adapters to settle.
            subprocess.run(
                ["systemctl", "restart", "bluetooth.service"],
                check=True,
            )
            time.sleep(2)
        return paired
    finally:
        start_manager()


def count_connected():
    return get_manager().count_connected()


def connected_serials():
    return get_manager().connected_serials()


@dataclass(frozen=True)
class ControllerState:
    """Represents an immutable controller input snapshot returned by
    Controller.read_update() when a complete new update is available. Menu and
    game code can read its buttons, trigger, motion, battery, and connection
    state without accessing the native upstream controller.
    """

    serial: str
    buttons: int
    pressed: int
    released: int
    trigger: int
    acceleration: tuple[float, float, float]
    gyroscope: tuple[float, float, float]
    battery: int
    usb: bool
    bluetooth: bool


class Controller:
    """Provides other JoustMania processes with access to one controller through
    the shared ControllerManager. Each instance identifies a controller by its
    serial and controller index, receives input copied by the API process, and
    sends color and rumble changes back through the manager without opening the
    physical controller or creating another PSMoveAPI instance. This is a
    JoustMania shared-state interface, not the upstream ctypes controller passed
    to PSMoveEventReceiver callbacks.

    Used by:

    - Creating connections for the main process and controller workers:
      - controller_manager.py
      - controller_process.py
    - Menu input, connection handling, pairing, and status:
      - piparty.py
      - pair.py
      - win_pair.py
    - Shared and specialized game behavior:
      - games/game.py
      - games/commander.py
    - Pairing, input, motion, and color utilities:
      - manualpair.py
      - controller_filter_utils.py
      - joust_test.py
      - color_tests/
    - Shared state, output, and process ownership tests:
      - test_controller.py
    """

    def __init__(self, serial, manager=None):
        if manager is not None:
            self.manager = manager
        elif _controller_manager is not None:
            self.manager = _controller_manager
        else:
            self.manager = get_manager()
        controller_index = self.manager.serial_to_index.get(serial)
        if controller_index is None:
            raise ValueError("PS Move controller {} is not connected".format(serial))
        self.serial = serial
        self.index = controller_index
        self.last_state_sequence = self.manager.state_sequence[self.index]

    @property
    def usb(self):
        return bool(self.manager.usb[self.index])

    @property
    def bluetooth(self):
        return bool(self.manager.bluetooth[self.index])

    @property
    def battery(self):
        return self.manager.battery[self.index]

    def read_update(self) -> ControllerState | None:
        """Returns the next complete state snapshot, or None if nothing changed.
        The API process marks the sequence odd while writing and even after the
        shared state is complete. A changed sequence during the copy causes a
        retry so game code does not receive values from different updates.
        """
        while True:
            sequence = self.manager.state_sequence[self.index]
            if _check_write_in_progress(self.manager, self.index):
                return None
            if sequence == self.last_state_sequence:
                return None

            state = self._copy_shared_state()
            if _check_write_in_progress(self.manager, self.index):
                continue
            if sequence != self.manager.state_sequence[self.index]:
                continue

            self.manager.pressed[self.index] = 0
            self.manager.released[self.index] = 0
            self.last_state_sequence = sequence
            return state

    def _copy_shared_state(self):
        """Copies the shared values after read_update() finds an even sequence."""
        offset = self.index * 3
        return ControllerState(
            serial=self.serial,
            buttons=self.manager.buttons[self.index],
            pressed=self.manager.pressed[self.index],
            released=self.manager.released[self.index],
            trigger=round(self.manager.trigger[self.index] * 255),
            acceleration=tuple(self.manager.accelerometer[offset:offset + 3]),
            gyroscope=tuple(self.manager.gyroscope[offset:offset + 3]),
            battery=self.manager.battery[self.index],
            usb=bool(self.manager.usb[self.index]),
            bluetooth=bool(self.manager.bluetooth[self.index]),
        )

    def set_color(self, red, green, blue):
        """Stores a requested color for the API process to apply upstream.
        This method only writes JoustMania shared state. PSMoveEventReceiver
        later copies the values into the upstream ctypes controller structure.
        """
        offset = self.index * 3
        for index, value in enumerate((red, green, blue)):
            self.manager.leds[offset + index] = max(0, min(255, round(value)))

    def set_rumble(self, value):
        """Stores requested rumble for the API process to apply upstream.
        This method only writes JoustMania shared state. PSMoveEventReceiver
        later copies the value into the upstream ctypes controller structure.
        """
        self.manager.rumble[self.index] = max(0, min(255, round(value)))


def connected_controllers():
    return get_manager().connected_controllers()
