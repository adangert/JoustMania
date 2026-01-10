from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class ControllerState(_message.Message):
    __slots__ = (
        "serial",
        "move_num",
        "battery",
        "trigger_pressed",
        "move_pressed",
        "ready",
        "team",
        "color",
        "accel",
        "gyro",
    )
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    MOVE_NUM_FIELD_NUMBER: _ClassVar[int]
    BATTERY_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_PRESSED_FIELD_NUMBER: _ClassVar[int]
    MOVE_PRESSED_FIELD_NUMBER: _ClassVar[int]
    READY_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    ACCEL_FIELD_NUMBER: _ClassVar[int]
    GYRO_FIELD_NUMBER: _ClassVar[int]
    serial: str
    move_num: int
    battery: int
    trigger_pressed: bool
    move_pressed: bool
    ready: bool
    team: int
    color: RGB
    accel: Vector3
    gyro: Vector3
    def __init__(
        self,
        serial: str | None = ...,
        move_num: int | None = ...,
        battery: int | None = ...,
        trigger_pressed: bool = ...,
        move_pressed: bool = ...,
        ready: bool = ...,
        team: int | None = ...,
        color: RGB | _Mapping | None = ...,
        accel: Vector3 | _Mapping | None = ...,
        gyro: Vector3 | _Mapping | None = ...,
    ) -> None: ...

class RGB(_message.Message):
    __slots__ = ("r", "g", "b")
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    r: int
    g: int
    b: int
    def __init__(
        self, r: int | None = ..., g: int | None = ..., b: int | None = ...
    ) -> None: ...

class Vector3(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(
        self, x: float | None = ..., y: float | None = ..., z: float | None = ...
    ) -> None: ...

class GetControllerCountRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetControllerCountResponse(_message.Message):
    __slots__ = ("count", "success", "error")
    COUNT_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    count: int
    success: bool
    error: str
    def __init__(
        self, count: int | None = ..., success: bool = ..., error: str | None = ...
    ) -> None: ...

class GetReadyControllersRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetReadyControllersResponse(_message.Message):
    __slots__ = ("controllers", "success", "error")
    CONTROLLERS_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    controllers: _containers.RepeatedCompositeFieldContainer[ControllerState]
    success: bool
    error: str
    def __init__(
        self,
        controllers: _Iterable[ControllerState | _Mapping] | None = ...,
        success: bool = ...,
        error: str | None = ...,
    ) -> None: ...

class GetControllersRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetControllersResponse(_message.Message):
    __slots__ = ("controllers", "success", "error")
    CONTROLLERS_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    controllers: _containers.RepeatedCompositeFieldContainer[ControllerState]
    success: bool
    error: str
    def __init__(
        self,
        controllers: _Iterable[ControllerState | _Mapping] | None = ...,
        success: bool = ...,
        error: str | None = ...,
    ) -> None: ...

class StreamRequest(_message.Message):
    __slots__ = ("update_frequency_hz",)
    UPDATE_FREQUENCY_HZ_FIELD_NUMBER: _ClassVar[int]
    update_frequency_hz: int
    def __init__(self, update_frequency_hz: int | None = ...) -> None: ...

class ControllerStateUpdate(_message.Message):
    __slots__ = ("controllers", "timestamp")
    CONTROLLERS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    controllers: _containers.RepeatedCompositeFieldContainer[ControllerState]
    timestamp: int
    def __init__(
        self,
        controllers: _Iterable[ControllerState | _Mapping] | None = ...,
        timestamp: int | None = ...,
    ) -> None: ...

class PairControllerRequest(_message.Message):
    __slots__ = ("color_index",)
    COLOR_INDEX_FIELD_NUMBER: _ClassVar[int]
    color_index: int
    def __init__(self, color_index: int | None = ...) -> None: ...

class PairControllerResponse(_message.Message):
    __slots__ = ("success", "error", "serial")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    serial: str
    def __init__(
        self, success: bool = ..., error: str | None = ..., serial: str | None = ...
    ) -> None: ...

class RemoveControllerRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: str | None = ...) -> None: ...

class RemoveControllerResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...
