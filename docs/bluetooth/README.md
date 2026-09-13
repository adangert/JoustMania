# Bluetooth adapters and PS Move controllers

[Back to the main README](../../README.md) · [Adapter results](adapter-results.md) · [CSR buying guide](csr-adapters.md)

## Recommended hardware

Our recommended dongle is the **[Feasycom FSC-BP119](https://www.amazon.com/dp/B07KK843ZK)**: CSR8510 A10, Bluetooth 4.0, Class 1, with an external antenna. Its [manufacturer specifications](https://www.feasycom.com/fsc-bp119/) identify the chipset, and its [manual](https://m.feasycom.net/Content/upload/pdf/202313049/BP119-User-Manual_V1.2.pdf) describes standard HCI mode and Linux support. The Amazon listing also identifies FSC-BP119 and CSR8510 A10. This is a purchasing recommendation based on documented hardware and promising CSR testing, **not a completed Feasycom benchmark**.

Other identified CSR adapters are reasonable alternatives; start with the [model-specific buying guide](csr-adapters.md). An external antenna is desirable for range, but a large antenna, a newer Bluetooth version, or a brand name does not establish controller timing. Verify the arriving hardware in System Debug. No single model has yet passed a measured outdoor range or extended endurance test in this series.

The Cirago CSR sample worked well nearby at measured counts of one, two, four and seven, including both Move generations. It performed very poorly during the distance test. Many Realtek samples instead needed five active all-Central links for good ZCM1 timing. That makes CSR the preferred chipset candidate for smaller or changing groups, while long-range CSR performance still needs validation.

## Controller models and roles

**ZCM1 (PS3)** and **ZCM2 (PS4)** here mean the two PlayStation Move generations, not DualShock gamepads. Both use the Bluetooth Classic controller path being tested. Only two ZCM2 units were available: good one/two-unit or mixed-group results cannot prove performance for seven ZCM2 units.

Central and Peripheral describe the adapter's role on each link. Pairing does not guarantee a particular role. JoustMania allows negotiation rather than repeatedly forcing a role. System Debug offers a one-time switch for actively connected controllers; switches can fail or reduce the number of simultaneous links available. A failed request is not proof the controller is defective.

All current Cirago captures used Central links. Earlier CSR testing on a different setup found that forcing Peripheral could limit connections to two per adapter, while allowing Central increased capacity. Those historical limits do not override the seven Central connections observed on Cirago. On one Hakimonoe Realtek sample, six all-Central links performed substantially better than six with one Peripheral. Compare roles at the same count and location.

## Pairing and adapter selection

Connect one Move controller by USB at a time and use the normal pairing flow. Pairing assigns that controller to an adapter; it does not mean an active wireless connection already exists. Disconnect USB and connect wirelessly before evaluating Bluetooth traffic.

System Debug displays a single-selection control beside the adapter name. It defaults to the next adapter selected by the pairing algorithm. The algorithm fills adapters toward five controllers each, then uses round robin once every available adapter reaches that target. Counts include connected controllers and pairing reservations in the current session. Select a different available adapter to override the next pairing; after a successful pair, the override clears and the next automatic choice is shown. Five is a distribution target motivated by the tested Realteks, not a universal hardware limit.

A saved pairing, known battery value, or loaded controller object does not establish current input traffic. Check active connection status and advancing updates. Pair a controller again if its saved adapter is no longer present. **Unpair** on a controller's row removes its pairing individually. **Identify** turns an actively connected controller white briefly so it can be matched to its row. Role and Identify controls are unavailable for disconnected controllers.

## Reading System Debug

Updates/s measures how many reports the application processes over time. Evenly spaced reports feel different from bursts with long pauses, even at the same average rate. Report gaps therefore complement update rate; neither alone measures full motion-to-game-response latency.

| Indicator | Meaning | Green | Yellow | Red |
|---|---|---:|---:|---:|
| p95 report gap | 95th percentile of application report intervals in the rolling window | ≤22 ms | >22–30 ms | >30 ms |
| Longest gap (10 s) | Largest completed report interval in the rolling ten-second window | ≤30 ms | >30–50 ms | >50 ms |

These colors are practical thresholds derived from gameplay observations, not Bluetooth specifications. Interpret them with controller status and actual play. A disconnected controller can have stale historical data. The longest-gap value is not a lifetime maximum; a stall disappears after it leaves the window. Immediately after moving controllers or changing count, the window may still contain the previous configuration.

Raw HCI captures show packets reaching the host Bluetooth interface, whereas application gaps include host scheduling and input processing. These are different measurement layers. Zero HCI RX/TX error counters do not prove there were no over-the-air retransmissions or interference.

## What the chipset tests suggest

- **CSR:** strongest lead for flexible counts. Cirago handled both generations with good nearby timing at the recorded counts; distance performance failed. Other CSR models still need individual validation.
- **Realtek RTL8761BU family:** repeated ZCM1 count-dependent behavior across brands, often poor below five and much better with five all-Central links. Some samples accept six; others only five in the attempts made. ZCM2 generally did better, but not every role/load combination was good.
- **Realtek RTL8851BU combo:** also improved at five, despite a different firmware family. Its distance test degraded. Wi-Fi coexistence may be a factor because this is a combined radio device.
- **Actions and Barrot samples:** poor timing in the tested configurations; the QGOO Actions adapter had especially poor ZCM2 results. Do not extend this verdict to every product from those vendors.
- **AICSemi AIC8800D80 combo:** one ZCM1 initially looked promising, but two and seven performed poorly. Mixed ZCM2 results depended on role and still had substantial pauses.

See [the full catalog](adapter-results.md) for model identities, prices and evidence limits.

## The Realtek five-link behavior

The repeated observation is real in this test setup; the cause is unresolved. Controller firmware may change scheduling or polling behavior as active links increase. Different role mixtures can also alter scheduling. Bluetooth Classic permits dynamic polling behavior, but there is no established rule that five controllers must be connected for good timing. [Bluetooth Classic link-manager specification](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-61/out/en/br-edr-controller/link-manager-protocol-specification.html)

All samples used the same Pi/software environment, so this has not isolated adapter firmware from Linux behavior or USB/host batching. The different RTL8851BU firmware showing a similar improvement also argues against blaming only one RTL8761BU firmware revision. No independent report establishing this exact five-Move threshold was found. The [xpadneo dongle notes](https://github.com/atar-axis/xpadneo/blob/master/docs/BT_DONGLES.md) describe problems with Realtek firmware `dfc6d922`, but concern Xbox reconnections, not this count threshold.

Verified scan disabling did not improve the original test. USB autosuspend was already off; removing the camera did not resolve the four-Central behavior. Experimental QoS changes did not establish a fix and could worsen timing. BLE connection-interval settings are not a solution for these Classic streams. No proven low-power/high-power toggle fixes this issue.

## Power, buffers and range

A diagnostic inquiry-power value applies to inquiry transmissions, not necessarily the power used by a connected controller link. The GAROGYI box advertised +8 dBm while queried inquiry/current/max-link values were 0 dBm. Those were controller-reported values, not laboratory measurements of radiated output. Do not infer RF class or real playing distance from one power query.

ACL MTU such as `310:10` means a host/controller ACL packet data length of 310 bytes and ten available buffers. It is not the maximum controller count or direct application report size. Cirago's smaller buffer length coexisted with better low-count timing than many adapters reporting `1021:6`; bigger MTU is not a quality ranking.

A range claim needs both ends of the link and its test conditions. Sena's published range table changes antennas at both ends; Move controllers retain their own antennas. Walls, people, interference, adapter placement and antenna orientation affect play. Measure a usable gameplay radius using actual report gaps rather than treating “still connected” as success. [Sena range and RF specifications](https://www.senanetworks.eu/media/77/61/e0/1682433150/BT-UD100_Brochure.pdf)

## Pi controls and troubleshooting

The bottom controls are ordered Wi-Fi hotspot, Internal Bluetooth, Reset Bluetooth Controllers, then Soft Restart JoustMania. Internal Bluetooth reflects the current boot state; a pending configuration change is shown separately. Confirming its popup saves the setting and reboots the Pi. Cancel makes no change. Pairings are preserved. Soft Restart restarts the application without rebooting; resetting controllers clears pairing information, so use individual Unpair for one device.

If a combo adapter first appears as removable media, it may need device-mode switching and firmware before Bluetooth appears. The tested BrosTrend AIC8800D80 required this path; the setup scripts provide its driver/firmware support. Re-run the project setup when installing a supported adapter rather than installing a Windows driver on the Pi.

For poor play, first confirm active input, model and roles. Test nearby with fixed controller positions and count. Change one variable at a time, allow the rolling window to settle, and repeat a five-second capture. Record averages, per-controller variation, the worst pause and subjective play. Keep distance tests short for comparison, then run a separately planned endurance test. Initial [internal Pi Bluetooth results](adapter-results.md#internal-raspberry-pi-5-bluetooth) show poor ZCM1 timing under heavier load, with better subjective ZCM2 play. Outdoor range remains untested.
