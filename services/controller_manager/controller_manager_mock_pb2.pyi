from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MovementRequest(_message.Message):
    __slots__ = ("serial", "accel_x", "accel_y", "accel_z")
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    ACCEL_X_FIELD_NUMBER: _ClassVar[int]
    ACCEL_Y_FIELD_NUMBER: _ClassVar[int]
    ACCEL_Z_FIELD_NUMBER: _ClassVar[int]
    serial: str
    accel_x: float
    accel_y: float
    accel_z: float
    def __init__(self, serial: _Optional[str] = ..., accel_x: _Optional[float] = ..., accel_y: _Optional[float] = ..., accel_z: _Optional[float] = ...) -> None: ...

class MovementResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class DeathRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: _Optional[str] = ...) -> None: ...

class DeathResponse(_message.Message):
    __slots__ = ("success", "accel_magnitude")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACCEL_MAGNITUDE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    accel_magnitude: float
    def __init__(self, success: bool = ..., accel_magnitude: _Optional[float] = ...) -> None: ...

class ButtonRequest(_message.Message):
    __slots__ = ("serial", "button", "pressed")
    class Button(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TRIGGER: _ClassVar[ButtonRequest.Button]
        MOVE: _ClassVar[ButtonRequest.Button]
        SELECT: _ClassVar[ButtonRequest.Button]
        START: _ClassVar[ButtonRequest.Button]
    TRIGGER: ButtonRequest.Button
    MOVE: ButtonRequest.Button
    SELECT: ButtonRequest.Button
    START: ButtonRequest.Button
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    BUTTON_FIELD_NUMBER: _ClassVar[int]
    PRESSED_FIELD_NUMBER: _ClassVar[int]
    serial: str
    button: ButtonRequest.Button
    pressed: bool
    def __init__(self, serial: _Optional[str] = ..., button: _Optional[_Union[ButtonRequest.Button, str]] = ..., pressed: bool = ...) -> None: ...

class ButtonResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class ColorRequest(_message.Message):
    __slots__ = ("serial", "r", "g", "b")
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    R_FIELD_NUMBER: _ClassVar[int]
    G_FIELD_NUMBER: _ClassVar[int]
    B_FIELD_NUMBER: _ClassVar[int]
    serial: str
    r: int
    g: int
    b: int
    def __init__(self, serial: _Optional[str] = ..., r: _Optional[int] = ..., g: _Optional[int] = ..., b: _Optional[int] = ...) -> None: ...

class ColorResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class ResetRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: _Optional[str] = ...) -> None: ...

class ResetResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class ListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListResponse(_message.Message):
    __slots__ = ("serials", "count")
    SERIALS_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    serials: _containers.RepeatedScalarFieldContainer[str]
    count: int
    def __init__(self, serials: _Optional[_Iterable[str]] = ..., count: _Optional[int] = ...) -> None: ...
