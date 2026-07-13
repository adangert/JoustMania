#!/usr/bin/env python3
"""Record update rates from the shared-memory controller manager."""

import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import psutil
import controller_manager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument(
        "--output",
        default="controller-manager-{}.json".format(time.strftime("%Y%m%d-%H%M%S")),
    )
    args = parser.parse_args()

    manager = controller_manager.get_manager()
    deadline = time.monotonic() + 10
    while not manager.active_controller_indices() and time.monotonic() < deadline:
        time.sleep(0.1)
    controller_indices = manager.active_controller_indices()
    if not controller_indices:
        raise SystemExit("No PS Move controllers were found")

    connected = manager.connected_controllers()
    update_counts = {controller.serial: 0 for controller in connected}
    manager_process = psutil.Process(controller_manager.get_manager_process_pid())
    manager_process.cpu_percent(None)
    started = time.monotonic()
    print("Recording {} controllers for {} seconds".format(
        len(controller_indices),
        args.duration,
    ))
    next_progress = 10
    while time.monotonic() - started < args.duration:
        for controller in connected:
            if controller.read_update() is not None:
                update_counts[controller.serial] += 1
        elapsed = time.monotonic() - started
        if elapsed >= next_progress:
            print("{} seconds complete".format(next_progress))
            next_progress += 10
        time.sleep(0.001)

    elapsed = time.monotonic() - started
    controllers = []
    for controller_index in controller_indices:
        serial = manager.index_to_serial[controller_index]
        updates = update_counts[serial]
        controllers.append({
            "serial": serial,
            "controller_index": controller_index,
            "updates": updates,
            "updates_per_second": updates / elapsed,
            "usb": bool(manager.usb[controller_index]),
            "bluetooth": bool(manager.bluetooth[controller_index]),
        })

    rates = [item["updates_per_second"] for item in controllers if item["bluetooth"]]
    record = {
        "implementation": "JoustMania ControllerManager",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": elapsed,
        "controller_count": len(controllers),
        "manager_cpu_percent": manager_process.cpu_percent(None),
        "system": {
            "platform": platform.platform(),
            "python": sys.version,
        },
        "rate_summary": {
            "minimum": min(rates) if rates else None,
            "mean": statistics.fmean(rates) if rates else None,
            "maximum": max(rates) if rates else None,
            "spread": max(rates) - min(rates) if rates else None,
        },
        "controllers": sorted(controllers, key=lambda item: item["serial"]),
    }

    output = Path(args.output).resolve()
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record["rate_summary"], indent=2))
    print("Manager CPU: {:.1f}%".format(record["manager_cpu_percent"]))
    print("Saved manager result to {}".format(output))
    controller_manager.stop_manager()


if __name__ == "__main__":
    main()
