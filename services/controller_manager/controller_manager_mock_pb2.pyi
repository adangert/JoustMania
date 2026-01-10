from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

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
    def __init__(
        self,
        serial: str | None = ...,
        accel_x: float | None = ...,
        accel_y: float | None = ...,
        accel_z: float | None = ...,
    ) -> None: ...

class MovementResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...

class DeathRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: str | None = ...) -> None: ...

class DeathResponse(_message.Message):
    __slots__ = ("success", "accel_magnitude")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ACCEL_MAGNITUDE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    accel_magnitude: float
    def __init__(self, success: bool = ..., accel_magnitude: float | None = ...) -> None: ...

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
    def __init__(
        self,
        serial: str | None = ...,
        button: ButtonRequest.Button | str | None = ...,
        pressed: bool = ...,
    ) -> None: ...

class ButtonResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...

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
    def __init__(
        self,
        serial: str | None = ...,
        r: int | None = ...,
        g: int | None = ...,
        b: int | None = ...,
    ) -> None: ...

class ColorResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...

class ResetRequest(_message.Message):
    __slots__ = ("serial",)
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    serial: str
    def __init__(self, serial: str | None = ...) -> None: ...

class ResetResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...

class ListRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListResponse(_message.Message):
    __slots__ = ("serials", "count")
    SERIALS_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    serials: _containers.RepeatedScalarFieldContainer[str]
    count: int
    def __init__(
        self, serials: _Iterable[str] | None = ..., count: int | None = ...
    ) -> None: ...
