# Bluetooth adapter test results

[Guide](README.md) · [CSR recommendations](csr-adapters.md) · [Download catalog CSV](adapter-catalog.csv)

## Scope and interpretation

September 2026 tests on a Raspberry Pi 5, Linux `6.18.34+rpt-rpi-2712`, BlueZ 5.82. These are individual purchased samples, not vendor-wide certifications. Prices are historical purchase prices, not live offers; Techkey BT853's $10.99 is an estimate. Model descriptions can cover changing hardware. USB/HCI and kernel firmware identification are recorded evidence; physical chip markings were not inspected.

Most later captures requested five seconds and sampled roughly 4.3–4.6 seconds between endpoints. Updates/s uses application counters. Unless explicitly identified as HCI timing below, p95 means the average displayed overlapping rolling ten-second application percentile. A five-second capture can include earlier gap history. Figures below are rounded per-controller ranges; an average across controllers is explicitly labeled. These short tests do not establish endurance, an exact maximum capacity, measured average pairing time or outdoor range.

## Full sample catalog

“Search” links identify a shopping query, not a verified purchased listing. Two Hakimonoe units were identified physically by one versus two antennas; the BT11/BT548 name-to-unit mapping remains unconfirmed. The ZEXMTE 150/200 m labels are advertisements, not measured ranges.

| ID | Adapter | Price | Chipset / firmware family | USB ID | HCI/LMP | ACL bytes:buffers | Amazon |
|---|---|---:|---|---|---|---|---|
| A01 | GAROGYI BT5.3 Pro Class 1 | 6.99 | Realtek / RTL8761BU family | 0bda:a729 | 5.1 | 1021:6 | [Candidate listing](https://www.amazon.com/dp/B0BTW9BWSV) |
| A02 | QGOO BT831 green-08 | 6.99 | Actions (992) | 10d7:b012 | 5.3 | 679:6 | [Search](https://www.amazon.com/s?k=QGOO+BT831+green-08) |
| A03 | UGREEN 35059 BT5.4 long range | 9.49 | Barrot (2279) | 33fa:0010 | 5.4 | 679:9 | [Listing](https://www.amazon.com/dp/B0CJXZJGVC) |
| A04 | INTELBRAS AX900 + BT5.4 | 9.99 | Unknown | — | — | — | [Search](https://www.amazon.com/s?k=INTELBRAS+AX900+%2B+BT5.4) |
| A17 | Techkey BT853 (previously called BT863) | 10.99* | Realtek / RTL8761BU family | 0bda:a760 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Techkey+BT853+%28previously+called+BT863%29) |
| A05 | KAIY BT6.0 | 11.99 | Barrot (2279) | 33fa:0012 | code 0x0e | 679:9 | [Search](https://www.amazon.com/s?k=KAIY+BT6.0) |
| A06 | Krisnorey BT5.4 | 16.14 | Realtek / RTL8761BU family | 0bda:a728 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Krisnorey+BT5.4) |
| A07 | Krisnorey BT6.0 | 16.96 | Realtek / RTL8761BU family | 0bda:a760 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Krisnorey+BT6.0) |
| A08 | Hakimonoe BT5.4 single antenna | 17.09 | Realtek / RTL8761BU family | 0bda:a728 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Hakimonoe+BT5.4+single+antenna) |
| A09 | TP-Link UB500 Plus | 17.99 | Realtek / RTL8761BU family | 2357:0604 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=TP-Link+UB500+Plus) |
| A10 | Hakimonoe BT5.4 dual antenna | 18.99 | Realtek / RTL8761BU family | 0bda:a728 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Hakimonoe+BT5.4+dual+antenna) |
| A11 | BrosTrend AX900 + BT5.4 | 19.99 | AICSemi / AIC8800D80 | 368b:8d81 active | 5.4 | 1021:9 | [Search](https://www.amazon.com/s?k=BrosTrend+AX900+%2B+BT5.4) |
| A12 | ASUS USB-BT600 | 21.83 | Realtek (93); exact silicon unverified | 0b05:1d70 | code 0x0e | 1021:6 | [Search](https://www.amazon.com/s?k=ASUS+USB-BT600) |
| A13 | ZEXMTE BT6.0 single antenna 150 m | 21.99 | Realtek / RTL8761BU family | 0bda:a760 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=ZEXMTE+BT6.0+single+antenna+150+m) |
| A14 | UGREEN AX900 + BT5.4 | 23.99 | Realtek / RTL8851BU | 0bda:b851 | 5.3 | 1021:8 | [Search](https://www.amazon.com/s?k=UGREEN+AX900+%2B+BT5.4) |
| A15 | ZEXMTE BT6.0 dual antenna 200 m | 25.99 | Realtek / RTL8761BU family | 0bda:a760 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=ZEXMTE+BT6.0+dual+antenna+200+m) |
| A16 | StarTech BT5.3 Class 1 (printed model unknown) | 25.99 | Realtek / RTL8761BU family | 2c0a:8761 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=StarTech+BT5.3+Class+1+%28printed+model+unknown%29) |
| A18 | Techkey BT833 | Unknown | Realtek; family inferred from reported revision | 0bda:a729 | 5.1 | 1021:6 | [Search](https://www.amazon.com/s?k=Techkey+BT833) |
| A22 | Cirago (printed model unknown) | Unknown | Reports CSR8510 A10 / CSR (10) | 0a12:0001 | 4.0 | 310:10 | [Search](https://www.amazon.com/s?k=Cirago+%28printed+model+unknown%29) |

Most kernel-identified RTL8761BU samples loaded `rtl8761bu_fw.bin` plus configuration, reporting firmware `0xdfc6d922`, HCI/LMP 5.1, revision `dfc6` and subversion `d922`, despite different advertised Bluetooth versions. A18's family is inferred from revision rather than a saved firmware-loader trace. A12 ASUS instead reported revision `000e` / subversion `8761`, with no matching firmware-download evidence. A14 RTL8851BU loaded firmware `0x048ad230`. Do not infer identical RF performance solely from matching firmware.

A11 BrosTrend first enumerated as storage `a69c:5732`, then firmware-loader `a69c:8d80`, then active `368b:8d81`. Setup provides the AIC8800 driver/firmware path. Its USB link was 480 Mbit/s, as was A14's; most standalone dongles used 12 Mbit/s. USB speed is not Bluetooth report rate.

## Results by sample

### A01 — GAROGYI BT5.3 Pro Class 1

Five ZCM1 Central: ~80–88/s; lower counts often ~60–67/s. User could not exceed five. One/two ZCM2 and mixed groups playable.

### A02 — QGOO BT831 green-08

One ZCM1 ~66/s, p95 ~32 ms; seven ~65–75/s with similarly poor gaps. ZCM2 difficult to connect, then no new updates in one five-second run.

### A03 — UGREEN 35059 BT5.4 long range

One ZCM1 ~61/s, p95 ~36 ms. Seven mixed Central poor; all-Peripheral improved rates but gaps remained poor. Two ZCM2 within a seven-device mixed group judged unusable.

### A04 — INTELBRAS AX900 + BT5.4

Awaiting delivery; no hardware or performance evidence.

### A17 — Techkey BT853 (previously called BT863)

Six ZCM1 Central ~86–87/s, p95 ~17 ms. User: five or six good; one ~65/s and p95 ~32 ms; two Peripheral looked good.

### A05 — KAIY BT6.0

Seven mixed Central: ZCM1 ~36–39/s with p95 ~44–46 ms; ZCM2 ~65/s and p95 ~39 ms. Poor.

### A06 — Krisnorey BT5.4

Five ZCM1 Central ~80–87/s, p95 ~17–18 ms. Mixed five including two ZCM2 good; ZCM2 ~151–155/s, p95 ~9 ms. Below five problematic.

### A07 — Krisnorey BT6.0

Five ZCM1 Central ~79–87/s, p95 ~19–20 ms. User: only five works, not six; failed sixth-link cause not established.

### A08 — Hakimonoe BT5.4 single antenna

Six ZCM1 Central ~82–86/s, p95 ~20–33 ms; worst gap ~72 ms. Five needed per observation; six connected, but not uniformly green.

### A09 — TP-Link UB500 Plus

Five ZCM1 Central ~79–86/s, p95 ~17–20 ms. User only connected five; no definitive hard-capacity trace.

### A10 — Hakimonoe BT5.4 dual antenna

Six all-Central ~83–86/s, p95 ~18–21 ms. Six with one Peripheral ~62–75/s, p95 ~28–30 ms; one controller identity differed between runs.

### A11 — BrosTrend AX900 + BT5.4

One ZCM1 ~80/s, p95 ~24 ms; two ~53–59/s, p95 ~43–47 ms. Seven mixed-role ZCM1 ~15–22/s, p95 ~156–172 ms. ZCM2 Peripheral better than Central but large pauses persisted.

### A12 — ASUS USB-BT600

Six ZCM1 Central ~82–86/s, p95 ~17–22 ms. User observed five-link improvement. Different reported firmware identity from most RTL8761BU units.

### A13 — ZEXMTE BT6.0 single antenna 150 m

Hardware intake only; no performance capture.

### A14 — UGREEN AX900 + BT5.4

Two/three ZCM1 Central p95 ~28–32 ms; five ~17–21 ms. Five at distance averaged ~69.8/s and p95 ~28.7 ms; worst gap ~62 ms. Wi-Fi was active at intake.

### A15 — ZEXMTE BT6.0 dual antenna 200 m

Five ZCM1 Central ~77–80/s, p95 ~21–24 ms; worst gap ~65 ms. Listing claims RTL616; kernel loads RTL8761BU firmware family.

### A16 — StarTech BT5.3 Class 1 (printed model unknown)

Five ZCM1 Central ~74–88/s, p95 ~17–24 ms; worst gap ~56 ms. Not the older CSR StarTech models.

### A18 — Techkey BT833

User: one good (role unspecified), Central needs five. Five Central verified, no quantitative timing capture.

### A22 — Cirago (printed model unknown)

Good measured nearby timing at 1, 2, 4 and 7; seven mixed controllers supported. Distance test very poor for both generations.

## Cirago measurements

All these runs used adapter-Central links. ZCM1 means PS3 Move; ZCM2 means PS4 Move. Each rate and p95 entry below is an average across the controllers of that model, with individual readings retained in the portable [measurement CSV](cirago-measurements.csv).

| Configuration | ZCM1 updates/s | ZCM1 p95 ms | ZCM2 updates/s | ZCM2 p95 ms |
|---|---:|---:|---:|---:|
| One ZCM1 | 85.8 | 20.1 | — | — |
| Two ZCM1 | 87.2 | 20.0 | — | — |
| Two ZCM1 + two ZCM2 | 85.2 | 16.8 | 189.9 | 9.0 |
| Seven ZCM1 | 79.9 | 23.8 | — | — |
| Five ZCM1 + two ZCM2 | 82.6 | 23.9 | 112.5 | 16.2 |
| Five ZCM1 + two ZCM2 at distance | 11.2 | 461.1 | 31.2 | 219.1 |

The mixed seven-controller nearby test's worst displayed gap was 35.5 ms for ZCM1 and 24.9 ms for ZCM2. At distance the overall worst gap reached 1339.5 ms while all seven remained active. Placement and obstacles were not measured. The four-controller run followed the distance run, but its placement was unspecified; it should not be presented as a four-controller distance success. Three, five and six have not been separately measured on this sample. No CSR Peripheral capture is included here.

## GAROGYI timing and mixed-controller evidence

In an earlier same-pair HCI comparison, five Central links yielded about 80 reports/s per tracked controller and HCI p95 gaps of 19.0/19.8 ms. Four Central links yielded about 59/s and 36 ms p95; two Peripheral links yielded about 87/s but 24.3/24.6 ms p95. This explains why a higher average rate could still feel less smooth. HCI gaps are measured at the host interface, not over the air or at the application layer.

One/two ZCM2 controllers were responsive during play. With two Central ZCM2, application averages were about 388/396 updates/s and HCI p95 about 8.1 ms. In mixed four-Central testing, ZCM1 fell to about 57–65/s with 40 ms HCI p95 while ZCM2 remained around 257/s with 8.1 ms p95. At mixed five-Central, ZCM1 improved to about 80–87/s with 16.1 ms p95 and ZCM2 slowed to about 158/s with 8.2–8.3 ms p95. More total traffic redistributed timing differently by model.

Some earlier captures contained shared host-side pauses (including about 0.92 seconds in the mixed-five run and a larger pause in a two-Peripheral ZCM2 run). Good steady-state percentiles must not conceal those outliers. Indoor bench recordings exist, but distance was not measured and an earlier QoS experiment confounds part of the ZCM1 history. The mixed bench comparison was limited to its first 30 seconds. No outdoor test or clean range rating follows from these records.

## Buying status and remaining tests

| Product | Status | Role in comparison |
|---|---|---|
| Feasycom FSC-BP119 | Recommended; no sample benchmark yet | CSR8510 A10 with external antenna; [Amazon](https://www.amazon.com/dp/B07KK843ZK) |
| StarTech USBBT1EDR2 | Ordered; $17.95 in recorded cart | Older CSR Class 1; shipped revision and ZCM2 compatibility to verify |
| Sena UD100-G03 | Ordered; $40.08 in recorded cart | External-antenna CSR range candidate |
| Plugable USB-BT4LE | Ordered; $11.95 in recorded cart | Broadcom comparison, not CSR |
| INTELBRAS AX900 + BT5.4 | Awaiting delivery | Chipset unknown |
| Internal Pi Bluetooth | Pending test | No result yet |
| Panda PAU0B AC600 | Excluded accidental purchase | Wi-Fi adapter, not part of Bluetooth comparison |

Some Realtek sixth connections reportedly took around 20 seconds, whereas the first five connected readily. This is an observation, not a measured mean connection time. Further work should record repeatable pairing/reconnection timings, all requested counts and roles, distance with measured separation, and sustained game sessions.

## Evidence provenance

The tables summarize local adapter intake records A01–A22, short application snapshots and passive btmon captures collected September 2026. The public CSVs preserve identities and selected measurements without controller addresses, order details or raw packet payloads. The Cirago CSV includes capture timestamps for traceability; the original captures remain in the local testing archive. Empty or untested fields are intentional and must not be treated as zero performance.
