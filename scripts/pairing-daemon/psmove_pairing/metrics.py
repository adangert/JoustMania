"""Prometheus metrics for PS Move pairing daemon."""

from prometheus_client import Counter, Gauge, Histogram

# Pairing metrics
pairing_attempts_total = Counter(
    "psmove_pairing_attempts_total",
    "Total pairing attempts",
)
pairing_success_total = Counter(
    "psmove_pairing_success_total",
    "Successful pairings",
)
pairing_failed_total = Counter(
    "psmove_pairing_failed_total",
    "Failed pairings",
)
pairing_adapter_selected_total = Counter(
    "psmove_pairing_adapter_selected_total",
    "Adapter selections for load-balanced pairing",
    ["adapter"],
)
pairing_adapter_device_count = Gauge(
    "psmove_pairing_adapter_device_count_at_selection",
    "Device count on adapter when selected for pairing",
    ["adapter"],
)
pairing_polls_total = Counter(
    "psmove_pairing_polls_total",
    "Total polling cycles",
)
pairing_usb_controllers = Gauge(
    "psmove_pairing_usb_controllers",
    "Currently connected USB controllers",
)
pairing_duration_seconds = Histogram(
    "psmove_pairing_duration_seconds",
    "Time to complete pairing",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)
calibration_duration_seconds = Histogram(
    "psmove_pairing_calibration_duration_seconds",
    "Time to calibrate controller",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Bluetooth monitoring metrics (host-level HCI layer)
# Note: These are distinct from controller_* metrics in controller-manager
# which measure the application layer (psmoveapi). These measure the raw
# Bluetooth HCI layer on the host.
bluetooth_device_rssi_dbm = Gauge(
    "bluetooth_device_rssi_dbm",
    "Bluetooth device signal strength in dBm (host HCI layer)",
    ["serial", "hci_adapter"],
)
bluetooth_device_connected = Gauge(
    "bluetooth_device_connected",
    "Bluetooth device connection status at HCI layer (1=connected, 0=disconnected)",
    ["serial", "hci_adapter"],
)
bluetooth_device_last_seen = Gauge(
    "bluetooth_device_last_seen_timestamp",
    "Unix timestamp when device was last seen connected at HCI layer",
    ["serial", "hci_adapter"],
)
bluetooth_adapter_connections = Gauge(
    "bluetooth_adapter_connections",
    "Number of controllers per adapter",
    ["hci_adapter"],
)
