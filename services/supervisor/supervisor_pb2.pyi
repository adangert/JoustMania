from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[ProcessStatus]
    STARTING: _ClassVar[ProcessStatus]
    RUNNING: _ClassVar[ProcessStatus]
    STOPPING: _ClassVar[ProcessStatus]
    STOPPED: _ClassVar[ProcessStatus]
    FAILED: _ClassVar[ProcessStatus]
UNKNOWN: ProcessStatus
STARTING: ProcessStatus
RUNNING: ProcessStatus
STOPPING: ProcessStatus
STOPPED: ProcessStatus
FAILED: ProcessStatus

class ProcessInfo(_message.Message):
    __slots__ = ("name", "pid", "status", "uptime_seconds", "restart_count", "last_error", "critical", "last_health_check_ago")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    UPTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
    RESTART_COUNT_FIELD_NUMBER: _ClassVar[int]
    LAST_ERROR_FIELD_NUMBER: _ClassVar[int]
    CRITICAL_FIELD_NUMBER: _ClassVar[int]
    LAST_HEALTH_CHECK_AGO_FIELD_NUMBER: _ClassVar[int]
    name: str
    pid: int
    status: ProcessStatus
    uptime_seconds: int
    restart_count: int
    last_error: str
    critical: bool
    last_health_check_ago: int
    def __init__(self, name: _Optional[str] = ..., pid: _Optional[int] = ..., status: _Optional[_Union[ProcessStatus, str]] = ..., uptime_seconds: _Optional[int] = ..., restart_count: _Optional[int] = ..., last_error: _Optional[str] = ..., critical: bool = ..., last_health_check_ago: _Optional[int] = ...) -> None: ...

class GetProcessStatusRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class GetProcessStatusResponse(_message.Message):
    __slots__ = ("info", "success", "error")
    INFO_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    info: ProcessInfo
    success: bool
    error: str
    def __init__(self, info: _Optional[_Union[ProcessInfo, _Mapping]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class GetAllProcessStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAllProcessStatusResponse(_message.Message):
    __slots__ = ("processes", "success", "error")
    PROCESSES_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    processes: _containers.RepeatedCompositeFieldContainer[ProcessInfo]
    success: bool
    error: str
    def __init__(self, processes: _Optional[_Iterable[_Union[ProcessInfo, _Mapping]]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class RestartProcessRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class RestartProcessResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class GetHealthSummaryRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetHealthSummaryResponse(_message.Message):
    __slots__ = ("all_healthy", "total_processes", "running_processes", "failed_processes", "unhealthy", "success", "error")
    ALL_HEALTHY_FIELD_NUMBER: _ClassVar[int]
    TOTAL_PROCESSES_FIELD_NUMBER: _ClassVar[int]
    RUNNING_PROCESSES_FIELD_NUMBER: _ClassVar[int]
    FAILED_PROCESSES_FIELD_NUMBER: _ClassVar[int]
    UNHEALTHY_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    all_healthy: bool
    total_processes: int
    running_processes: int
    failed_processes: int
    unhealthy: _containers.RepeatedCompositeFieldContainer[ProcessInfo]
    success: bool
    error: str
    def __init__(self, all_healthy: bool = ..., total_processes: _Optional[int] = ..., running_processes: _Optional[int] = ..., failed_processes: _Optional[int] = ..., unhealthy: _Optional[_Iterable[_Union[ProcessInfo, _Mapping]]] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class StreamUpdatesRequest(_message.Message):
    __slots__ = ("interval_seconds",)
    INTERVAL_SECONDS_FIELD_NUMBER: _ClassVar[int]
    interval_seconds: int
    def __init__(self, interval_seconds: _Optional[int] = ...) -> None: ...

class ProcessStatusUpdate(_message.Message):
    __slots__ = ("processes", "timestamp")
    PROCESSES_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    processes: _containers.RepeatedCompositeFieldContainer[ProcessInfo]
    timestamp: int
    def __init__(self, processes: _Optional[_Iterable[_Union[ProcessInfo, _Mapping]]] = ..., timestamp: _Optional[int] = ...) -> None: ...
