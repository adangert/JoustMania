from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class GetSettingsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetSettingsResponse(_message.Message):
    __slots__ = ("settings", "success", "error")
    class SettingsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    settings: _containers.ScalarMap[str, str]
    success: bool
    error: str
    def __init__(
        self,
        settings: _Mapping[str, str] | None = ...,
        success: bool = ...,
        error: str | None = ...,
    ) -> None: ...

class GetSettingRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: str | None = ...) -> None: ...

class GetSettingResponse(_message.Message):
    __slots__ = ("key", "value", "success", "error")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    success: bool
    error: str
    def __init__(
        self,
        key: str | None = ...,
        value: str | None = ...,
        success: bool = ...,
        error: str | None = ...,
    ) -> None: ...

class UpdateSettingRequest(_message.Message):
    __slots__ = ("key", "value", "source")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    source: str
    def __init__(
        self, key: str | None = ..., value: str | None = ..., source: str | None = ...
    ) -> None: ...

class UpdateSettingResponse(_message.Message):
    __slots__ = ("success", "error", "old_value", "new_value")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    OLD_VALUE_FIELD_NUMBER: _ClassVar[int]
    NEW_VALUE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    old_value: str
    new_value: str
    def __init__(
        self,
        success: bool = ...,
        error: str | None = ...,
        old_value: str | None = ...,
        new_value: str | None = ...,
    ) -> None: ...

class SubscribeRequest(_message.Message):
    __slots__ = ("keys",)
    KEYS_FIELD_NUMBER: _ClassVar[int]
    keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, keys: _Iterable[str] | None = ...) -> None: ...

class SettingChangeEvent(_message.Message):
    __slots__ = ("key", "old_value", "new_value", "source", "timestamp")
    KEY_FIELD_NUMBER: _ClassVar[int]
    OLD_VALUE_FIELD_NUMBER: _ClassVar[int]
    NEW_VALUE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    key: str
    old_value: str
    new_value: str
    source: str
    timestamp: int
    def __init__(
        self,
        key: str | None = ...,
        old_value: str | None = ...,
        new_value: str | None = ...,
        source: str | None = ...,
        timestamp: int | None = ...,
    ) -> None: ...
