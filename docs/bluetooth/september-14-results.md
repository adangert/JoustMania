# September 14: CSR, Broadcom and dual-adapter comparisons

[Main guide](README.md) · [Full catalog](adapter-results.md)

## Recommendation and scope

**Feasycom FSC-BP119 is the leading tested choice and the Tier 2 recommendation.**
It delivered similar nearby timing to the other CSR samples and more encouraging
distance results in these recordings. The user described its distance play as
pretty good. Dual Feasycom maintained traffic on 12 PS3 Moves, six per adapter,
both nearby and at distance. The proposed 14-player setup, expansion beyond it,
outdoor coverage, low-count Feasycom operation and endurance remain unverified.
Sena's expected range advantage was not observed; the former third setup tier
has been removed. This is a recommendation for the tested setup, not proof that
all Feasycom units outperform all other adapters.

These recordings were taken on September 14, 2026, on the same Pi 5 test setup.
Every recorded link in the tables was **Central**. Each capture requested five
seconds; sampled counter spans ranged from about 3.4 to 5.7 seconds. Updates/s
is the application counter delta divided by that actual span, averaged across
the indicated group. The p95 column averages displayed **rolling ten-second**
percentiles; it is not a pooled or capture-only percentile. Longest gap is the
largest displayed rolling-window value, which can include earlier history.
Missing percentiles are excluded, never treated as zero; incomplete statistics
are noted below. These are delivery gaps, not measured motion-to-game latency.

“Nearby” identifies the ordinary baseline runs before the requested distance
runs; exact placement was not logged. Distance, obstacles, antenna orientation
and adapter separation were not measured. Controller sets and counts changed
between some runs. Compare these as exploratory observations, not a controlled
range ranking. No radiated-power measurement, average pairing-time study or
long endurance run was performed. Raw HCI/application evidence remains in the
local test archive alongside per-capture summaries. Controller addresses and
raw Bluetooth traffic are not published here.

## Hardware observed

| Sample | User-identified product | USB ID | HCI manufacturer / product | HCI revision / LMP subversion | ACL buffers |
|---|---|---|---|---|---|
| A24 | Feasycom FSC-BP119 | 0a12:0001 | CSR (10), CSR8510 A10 | 0x22bb / 0x22bb | 310:10 |
| A20 | Sena UD100-G03 | 0a12:0001 | CSR (10), no USB product string | 0x2031 / 0x2031 | 310:10 |
| A25 | TRENDnet, exact model unconfirmed | 0a12:0001 | CSR (10), CSR8510 A10 | 0x22bb / 0x22bb | 310:10 |
| A26 | StarTech CSR, exact model unconfirmed | 0a12:0001 | CSR (10), CSR8510 A10 | 0x22bb / 0x22bb | 310:10 |
| A21 | Plugable USB-BT4LE | 0a5c:21e8 | Broadcom (15), BCM20702A0 | 0x1000 / 0x220e | 1021:8 |

All report Bluetooth 4.0. Both Feasycom units report the same firmware identity
and have distinct Bluetooth addresses. Hardware labels and silicon markings
were not photographed in these runs. Feasycom, Sena and Plugable model names
follow user identification and prior orders. Do not assume the TRENDnet is
TBW-106UB or the StarTech is USBBT1EDR2/USBBT1EDR4 from their HCI identity; A26
may correspond to the earlier A19 StarTech order. It is distinct from the
previously tested StarTech Realtek sample A16. Shared USB/HCI identities do not
establish identical antennas, RF performance or firmware behavior.

## Single-adapter baselines

| Adapter / configuration | PS Move group | Average updates/s | Mean displayed p95 (ms) | Longest displayed gap (ms) |
|---|---|---:|---:|---:|
| Feasycom — nearby | 7 ZCM1 (7 total) | 78.3 | 24.6 | 52.4 |
| Feasycom — nearby mixed | 5 ZCM1 (7 total) | 82.9 | 23.9 | 41.4 |
| Feasycom — nearby mixed | 2 ZCM2 (7 total) | 106.2 | 16.5 | 41.4 |
| Sena — nearby | 7 ZCM1 (7 total) | 79.4 | 24.0 | 47.8 |
| Sena — nearby mixed | 5 ZCM1 (7 total) | 81.1 | 24.0 | 40.5 |
| Sena — nearby mixed | 2 ZCM2 (7 total) | 109.0 | 16.4 | 32.8 |
| TRENDnet — nearby | 7 ZCM1 (7 total) | 78.2 | 25.0 | 40.9 |
| StarTech CSR — nearby | 6 ZCM1 (6 total) | 81.1 | 19.9 | 41.4 |
| Plugable — nearby | 7 ZCM1 (7 total) | 70.7 | 31.7 | 56.7 |

The mixed Feasycom and Sena groups each contained five PS3 Moves and two PS4
Moves. Their nearby results were very similar. The user considered the Plugable
Broadcom result poor: its roughly 32 ms p95 was consistent across seven PS3
Moves, compared with roughly 24 ms for the seven-controller CSR samples.

One PS3 controller delivered about 60 updates/s on both Feasycom and TRENDnet
at seven total controllers, but about 80/s in the six-controller StarTech run.
This does not establish a defective controller: adapter, load and scheduling
changed. It is a useful controller-specific observation to revisit.

## Single-adapter distance

| Adapter / configuration | PS Move group | Average updates/s | Mean displayed p95 (ms) | Longest displayed gap (ms) |
|---|---|---:|---:|---:|
| Feasycom — distance | 5 ZCM1 (6 total) | 36.0 | 79.3 | 308.0 |
| Feasycom — distance | 1 ZCM2 (6 total) | 55.0 | 45.9 | 115.4 |
| Sena — distance | 5 ZCM1 (7 total) | 13.5 | 229.3 | 1055.6 |
| Sena — distance | 2 ZCM2 (7 total) | 5.9 | 382.8 | 688.4 |
| TRENDnet — distance | 6 ZCM1 (6 total) | 27.3 | 100.4 | 359.7 |
| StarTech CSR — distance | 6 ZCM1 (6 total) | 32.6 | 95.2 | 419.4 |

Feasycom had six active controllers (five PS3, one PS4), Sena had seven (five
PS3, two PS4), and TRENDnet and StarTech each had six PS3 controllers. A second
PS4 was absent from the Feasycom distance capture; a previously present PS3
was absent from the TRENDnet capture. Their absence was observed at capture
time, not proven to have been caused by distance. The PS3 sets also differed.

The user thought Feasycom looked pretty good overall and Sena looked worse.
Feasycom's recorded group averages were better than the other new CSR distance
samples, but pauses still reached hundreds of milliseconds. TRENDnet and
StarTech both degraded substantially; neither is established as a range upgrade.

## Sena and Feasycom together: severe Sena stalls

Seven PS3 Moves were connected to each adapter, 14 total. Three separate
five-second recordings showed a large change on Sena while its links remained
connected. Placement and any user changes between captures were not logged.

| Adapter / configuration | PS Move group | Average updates/s | Mean displayed p95 (ms) | Longest displayed gap (ms) |
|---|---|---:|---:|---:|
| Sena — simultaneous R01 | 7 ZCM1 (14 total) | 80.7 | 23.9 | 46.2 |
| Feasycom — simultaneous R01 | 7 ZCM1 (14 total) | 66.7 | 29.2 | 72.8 |
| Sena — simultaneous R02 | 7 ZCM1 (14 total) | 11.4 | 2567.0 | 8598.5 |
| Feasycom — simultaneous R02 | 7 ZCM1 (14 total) | 77.1 | 25.2 | 41.0 |
| Sena — simultaneous R03 | 7 ZCM1 (14 total) | 0.1 | 5420.7 | 13828.5 |
| Feasycom — simultaneous R03 | 7 ZCM1 (14 total) | 72.8 | 26.5 | 55.4 |

By R03, five Sena controllers delivered zero new updates across the sampled
interval and the other two delivered one each. One last-report age approached
19.65 seconds. Its R03 p95 average includes only five controllers with available
statistics; missing values on the others do not mean good timing. The displayed
13.83-second gap is an interval between reports represented in the rolling
history, not a claim that the capture itself lasted that long.

All 14 remained active in the sampled diagnostics. No disconnect, role-change
or mode-change events appeared in those captures, and cumulative HCI RX/TX
error counters did not increase. This establishes severe input stalls despite
connected status, **not their cause**. Interference, controller firmware and
host behavior were not isolated. No conclusion that the Sena permanently failed
or cannot coexist with any other adapter follows from this experiment.

## Two Feasycom adapters

| Adapter / configuration | PS Move group | Average updates/s | Mean displayed p95 (ms) | Longest displayed gap (ms) |
|---|---|---:|---:|---:|
| Feasycom hci0 — nearby | 6 ZCM1 (12 total) | 86.1 | 18.2 | 35.4 |
| Feasycom hci1 — nearby | 6 ZCM1 (12 total) | 83.0 | 20.0 | 40.0 |
| Feasycom hci0 — distance | 6 ZCM1 (12 total) | 47.9 | 54.5 | 220.5 |
| Feasycom hci1 — distance | 6 ZCM1 (12 total) | 53.0 | 45.5 | 292.5 |

All 12 were PS3 Moves, six per adapter, and remained active and Central in both
captures. No disconnects, role changes or additional HCI errors were observed.
Nearby timing was consistent. Distance reduced both adapters' rates, with pauses
up to 292.5 ms, but neither showed the near-total Sena stall. This six-plus-six
result is promising; it is not a seven-plus-seven or long-session validation.

Across all September 14 captures tabulated here, RX/TX error counter deltas were
zero. Some adapters already had cumulative TX errors before a capture. Those
counters are not a measurement of over-the-air packet loss, and zero new errors
did not prevent the Sena stall.

## Pairing policy motivated by these tests

Fill identified Realtek adapters to five first, one at a time. Next round robin
across every non-Realtek adapter to six, including CSR, Broadcom, Cypress and
unknown future chipsets. Then bring remaining Realteks to six by round robin.
Only after all available adapters reach six does round robin use seventh slots.
With no Realteks, all adapters participate from the first pairing; with only
Realteks, round robin starts after each has five. Automatic selection skips an
adapter at seven; manual selection can override the next assignment.

These are distribution targets, not promises of hardware capacity or validated
performance at every count. The policy does not move existing connections,
force link roles or automatically infer a lower capacity from pairing failures.
It applies to either Move generation and cannot guarantee that every Realtek
accepts a sixth link. Use the manual selector if a device cannot reach its target.
See [pairing and adapter selection](README.md#pairing-and-adapter-selection)
for reservation counting and the one-time debug-page override.
