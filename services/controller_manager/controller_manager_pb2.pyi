from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ControllerState(_message.Message):
    __slots__ = ("serial", "move_num", "battery", "trigger_pressed", "move_pressed", "ready", "team", "color", "accel", "gyro")
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
    def __init__(self, serial: _Optional[str] = ..., move_num: _Optional[int] = ..., battery: _Optional[int] = ..., trigger_pressed: bool = ..., move_pressed: bool = ..., ready: bool = ..., team: _Optional[int] = ..., color: _Optional[_Union[RGB, _Mapping]] = ..., accel: _Optional[_Union[Vector3, _Mapping]] = ..., gyro: _Optional[_Union[Vector3, _Mapping]] = ...) -> None: ...

class RGB(_message.Message):
    __slots__ = ("r", "g", "b")
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    r: int
    g: int
    b: int
    def __init__(self, r: _Optional[int] = ..., g: _Optional[int] = ..., b: _Optional[int] = ...) -> None: ...

class Vector3(_message.Message):
    __slots__ = ("x", "y", "z")
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    x: float
    y: float
    z: float
    def __init__(self, x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ...) -> None: ...

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
    def __init__(self, count: _Optional[int] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

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
    def __init__(self, controllers: _Optional[_Iterable[_Union[ControllerState, _Mapping]]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

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
    def __init__(self, controllers: _Optional[_Iterable[_Union[ControllerState, _Mapping]]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class StreamRequest(_message.Message):
    __slots__ = ("update_frequency_hz",)
    UPDATE_FREQUENCY_HZ_FIELD_NUMBER: _ClassVar[int]
    update_frequency_hz: int
    def __init__(self, update_frequency_hz: _Optional[int] = ...) -> None: ...

class ControllerStateUpdate(_message.Message):
    __slots__ = ("controllers", "timestamp")
    CONTROLLERS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    controllers: _containers.RepeatedCompositeFieldContainer[ControllerState]
    timestamp: int
    def __init__(self, controllers: _Optional[_Iterable[_Union[ControllerState, _Mapping]]] = ..., timestamp: _Optional[int] = ...) -> None: ...

class PairControllerRequest(_message.Message):
    __slots__ = ("color_index",)
    COLOR_INDEX_FIELD_NUMBER: _ClassVar[int]
    color_index: int
    def __init__(self, color_index: _Optional[int] = ...) -> None: ...

class PairControllerResponse(_message.Message):
    __slots__ = ("success", "error", "serial")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    serial: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., serial: _Optional[str] = ...) -> None: ...

class RemoveControllerRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: _Optional[str] = ...) -> None: ...

class RemoveControllerResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...
