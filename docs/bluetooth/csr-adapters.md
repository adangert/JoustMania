# Long-range CSR Bluetooth adapters for PS Move

[Back to the guide](README.md) · [Full test catalog](adapter-results.md)

**Recommended: [Feasycom FSC-BP119 on Amazon](https://www.amazon.com/dp/B07KK843ZK).** The supplied Amazon listing identifies FSC-BP119 and CSR8510 A10, matching the manufacturer's specifications. It combines the preferred CSR family with an external antenna. This recommendation is based on published hardware and our Cirago CSR results; the Feasycom itself has not yet been benchmarked in this series.

Sena UD100-G03, already ordered, is the first planned external-antenna comparison. Identified CSR alternatives below are candidates rather than interchangeable guarantees. Prices and availability were reviewed September 12, 2026. Stock and shipped revisions can change.

The [setup tiers](README.md#setup-tiers) use Feasycom or comparable CSR hardware for the standard 14-player target and Sena UD100-G03 for the proposed larger-space pro tier. Those multi-adapter capacities and range differences remain to be tested; tier pricing is separate from individual retail dongle prices.

## Findings from the Cirago sample

The sample reports CSR8510 A10, USB `0a12:0001`, Cambridge Silicon Radio manufacturer 10, Bluetooth HCI/LMP 4.0 and revision/subversion `22bb`. Its printed retail model and power class have not been confirmed. Manufacturer and USB identity are stronger evidence together than a retail title, but they are not physical inspection of the silicon.

Five-second recordings directly covered one, two, four and seven active controllers. Three, five and six were not separately captured. The four-controller test contained two ZCM1 and two ZCM2 devices; the seven-controller tests covered both seven ZCM1 and five ZCM1 plus two ZCM2. All recorded links in these runs were Central. Consequently, the evidence supports promising flexibility across measured counts and both Move generations, not a universal guarantee for every CSR adapter, role configuration, or controller type.

## Priority candidates

All distances in this section are supplier claims under favorable conditions, not measured PS Move playing radii.

| Priority | Exact product | CSR evidence | Radio and antenna claims | Purchase route / status |
|---|---|---|---|---|
| 1 | Sena Parani UD100-G03 | Sena specifies CSR; Home Assistant identifies CSR8510A10 | BT4.0, Class 1; removable RP-SMA antenna; 300 m stock-to-stock claim | [Amazon](https://www.amazon.com/dp/B0161B5ATM); already ordered, $40.08 paid |
| 2 | Feasycom FSC-BP119 | Manufacturer explicitly specifies CSR8510 A10 | BT4.0, Class 1, 18.5 dBm claim, external 2 dBi antenna, 100 m open-air claim | [Amazon](https://www.amazon.com/dp/B07KK843ZK); exact listing identified; live stock unresolved |
| 3 | Ezurio/Laird BT820 | Manufacturer specifies QCA (CSR) 8510 | BT4.0, +8 dBm maximum, internal antenna, 100 m claim | [Manufacturer and distributor links](https://www.ezurio.com/part/bt820); distributor stock displayed; NRND |
| 4 | StarTech USBBT1EDR4 | Current datasheet specifies CSR8510A10; older manual says A06 | BT4.0, Class 1, compact antenna, 50 m claim | [Amazon](https://www.amazon.com/dp/B00FCK307I); exact listing verified, current checkout stock/price unresolved |
| 5 | USconverters CRSBT40 | Supplier explicitly specifies CSR8510 A10 | BT4.0, Class 1, +9.75 dBm, internal chip antenna, 50 m claim | [Direct store](https://www.usconverters.com/usb-bluetooth-4-ble-low-energy-dongle); displayed $19 and In Stock |
| Existing order | StarTech USBBT1EDR2 | Current manufacturer page says CSR BC0401PC08; old manual conflicts | BT2.1+EDR, Class 1, chip antenna, 100 m claim | [Amazon](https://www.amazon.com/dp/B007019TZY); already ordered, $17.95 paid |

### Sena UD100-G03

This is the most practical first test because it is already ordered and has a replaceable antenna. Sena's brochure distinguishes +19 dBm basic-rate EIRP from +6 dBm EDR EIRP. Its 300–1000 m range table changes antennas at both ends: those numbers cannot be transferred directly to an unmodified Move controller. The stock antenna is 1 dBi; optional configurations include 3/5 dBi dipoles and a 9 dBi patch.[1]

Sena's Linux support notes say BlueZ can operate the device, while one explicitly limits official Linux support. This is compatible with treating it as a normal Linux Bluetooth candidate, without promising vendor support for the Pi configuration.[2] Start with the stock antenna; compare against Cirago in the same location before attributing an improvement to antenna gain. Home Assistant's first-hand compatibility list identifies the G03 as CSR8510A10.[3]

### Feasycom FSC-BP119

The manufacturer identifies CSR8510 A10, Class 1, external 2 dBi antenna and 18.5 dBm transmit power. Its manual explicitly states default HCI mode and Linux compatibility: it is a host Bluetooth adapter rather than merely a USB-powered audio transmitter.[4][5]

This is the closest additional candidate to the desired combination of Cirago-like chipset and an external antenna. The specification does not establish whether its power figure is conducted output, EIRP, or modulation-specific; do not compare it numerically with Sena's EIRP as though they were identical measurements. Qualcomm lists roughly +10 dBm maximum for the chip itself, so the whole-adapter figure needs board-level context.[6]

The [Amazon listing B07KK843ZK](https://www.amazon.com/dp/B07KK843ZK) explicitly identifies FSC-BP119 and CSR8510 A10. It resolves the earlier missing retail link; current checkout stock and price were not verified. The manufacturer also provides an inquiry route. An older announcement confirms historical Amazon distribution.[7] Home Assistant developers identify this model as their primary development adapter, useful Linux evidence but not a seven-Move benchmark.[3]

### Ezurio/Laird BT820

Ezurio explicitly identifies CSR8510, standard USB HCI, Linux host-stack compatibility, an internal antenna and +8 dBm maximum output. The product is marked Not Recommended for New Design. Its page displayed distributor stock at DigiKey and other distributors, offering a more traceable sourcing route than anonymous marketplace dongles.[8]

This is a useful controlled comparison from another vendor, but the internal antenna and modest specified output mean that better room-to-room range than Cirago is unproven. Purchase the packaged BT820 dongle, not the related bare BT800 module. Current unit price and shipment terms need the distributor checkout; a manufacturer stock feed is not a reservation.

### StarTech USBBT1EDR4 and USBBT1EDR2

The BT4.0 USBBT1EDR4 is a distinct product from the already-ordered BT2.1 USBBT1EDR2 and the previously tested Realtek StarTech BT5.3 sample. Current BT4.0 documentation identifies CSR8510A10 and a 50 m range; an older manual identifies CSR8510A06. Both support CSR family confidence but leave shipped revision uncertain.[9][10]

The BT2.1 product has a similar discrepancy: the current page identifies BC0401PC08, while an older combined manual names CSR8510A06.[11][12] Record the arriving unit's actual HCI identity. Its older Bluetooth version is not evidence that ZCM2 cannot work; actual pairing and traffic must settle compatibility. Neither StarTech should be purchased under a generic brand-only search because nearby variants use different chips.

### USconverters CRSBT40

The supplier specifies CSR8510 A10, Class 1, +9.75 dBm, -91 dBm sensitivity, an integrated antenna and Linux/BlueZ operation. The direct page displayed $19 and In Stock. This is a reasonably priced, explicitly identified CSR candidate, but its 50 m claim is conditional and its tiny antenna does not establish a meaningful upgrade over Cirago.[13]

## Industrial and older alternatives

### LM Technologies LM540

LM's datasheets identify CSR BlueCore4 ROM, Bluetooth 2.1+EDR, USB HCI, Linux BlueZ, +17.6 dBm and an SMA antenna. The stated maximum is up to 787 m with a 2 dBi antenna. Packaging differs: some part numbers omit the antenna, so the exact suffix matters.[14]

The manufacturer's catalog marks LM540 EOL.[15] RS retains a [LM540-0546 listing](https://int.rsdelivers.com/product/lm-technologies/lm540-0546/lm-technologies-usb-bluetooth-dongle-class-1/1245559), but stock was unavailable in the retrieved page. This is an old-stock opportunity, not a dependable easy purchase. The similarly named LM1010 is Broadcom according to LM's own compatibility matrix, not a CSR substitute.[16]

### m2m Germany Blue-1000-HCI V2

The manufacturer lists Bluetooth 2.1+EDR Class 1, CSR BlueCore and a host-stack HCI version, with a claim of up to 750 m. This is a legitimate industrial lead.[17] The suffix **HCI** is essential: the ordinary Blue-1000 documentation describes an onboard stack and virtual serial-port application interface. That serial version is not a drop-in replacement for the Pi's usual Bluetooth controller.[18]

The [manufacturer product page](https://www.m2mgermany.de/shop/produkt/blue-1000-hci-long-range-bluetooth-dongle-version-2) is the purchase/inquiry route. Current US shipment, exact chip revision and single-unit stock were not established. Its industrial positioning and sourcing friction put it behind the already-ordered Sena.

### TRENDnet TBW-106UB v2.0R

TRENDnet specifies BT4.0 Class 1, 100 m and 20 dBm maximum for this discontinued revision. Home Assistant identifies tested TBW-106UB hardware as CSR8510A10.[19][3] This makes the exact older revision interesting as used or remaining stock. The replacement TBW-110UB is a separate device; the CSR identification must not be carried over to it. Manufacturer maximum-power claims have not been measured here.

### LogiLink BT0015 / BT0037 / BT0048

Manufacturer-branded datasheets identify CSR BC8510 for these older compact adapters. BT0015 and BT0037 claim Class 1 and 100 m; BT0048 is a USB-C variant claiming 50 m.[20][21][22] These are secondary regional sourcing candidates with internal antennas. Their current US inventory and exact shipped revisions remain unverified. Multiple similar listings are not evidence of multiple independent radio designs.

### Edimax EB-DGC1

Edimax explicitly identifies CSR and Class 1 with a 150 m claim, and explicitly marks this Bluetooth 2.0+EDR product end-of-life.[23] It is worth recognizing if one is already available, but not worth prioritizing over supported purchase channels. Its older family and untested ZCM2 behavior make it exploratory.

## Products and claims to filter out

Feasycom **FSC-BP309** is advertised as a USB CDC serial data transceiver supporting SPP/BLE; a CSR chip and long antenna do not make that firmware a general-purpose HCI adapter.[24] Similarly, LM058 is an RS232 cable-replacement product, and the ordinary Blue-1000 must not be confused with Blue-1000-HCI.[18][25]

KOAMTAC sells a CSR8510 Class 1 dongle with a 30 m claim, but its KDC-specific package explicitly restricts the intended device use and points other buyers to a retail package.[26] It is not a strong range upgrade. Generic CSR-labelled adapters also deserve caution: Linux itself contains detection and workarounds for devices that impersonate CSR.[27] A USB ID of `0a12:0001` alone is therefore insufficient purchasing evidence.

The Cirago retail BTA8000 documentation lists an 82-foot range and +6 dBm output.[28] The tested Cirago's exact retail model has not been identified, so those values must not be assigned to the sample. Its poor distance test also does not prove its power class: Qualcomm's CSR8510 supports several classes, and finished adapter design determines the practical radio behavior.[6]

## Recommended purchase and test sequence

Use the Sena already on order first. Test one, two, four, five and seven ZCM1 links with the same placement, then mixed ZCM1/ZCM2 configurations. Preserve five-second captures for quick comparisons; allow the displayed ten-second gap window to settle after changing counts or positions. Test roles separately rather than changing count and role at once.

If the Sena retains good timing and improves distance, that supports a specific model recommendation and makes buying another inexpensive unverified dongle less useful. For a second external-antenna design, use the linked FSC-BP119 listing, verifying the delivered model and CSR/HCI identity. BT820 is the next useful traceable vendor comparison. The compact StarTech BT4.0 and CRSBT40 are lower-cost chip-family checks, not proven range solutions.

At distance, record actual separation, intervening rooms, antenna orientation, adapter position, Wi-Fi state and controller models. A link that remains connected but develops 500 ms gaps is a failed gameplay range test. Compare update rates, p95, p99 and longest gap together; record subjective gameplay alongside them. Repeat the same test after bringing controllers back to establish recovery.

The current conclusion is **CSR is the leading chipset candidate for flexible PS Move timing on this Pi; a long-range CSR model remains to be validated**. No manufacturer or independent source found here demonstrates this exact seven-controller JoustMania workload across all roles and distances. Home Assistant's connection-capacity numbers concern its own BLE tests and must not be substituted for Classic PS Move capacity.[3]

## Sources

Sources accessed September 12, 2026 unless an older document date is stated. Manufacturer claims are not laboratory measurements of the purchased sample.

1. Sena Networks, [UD100 brochure](https://www.senanetworks.eu/media/77/61/e0/1682433150/BT-UD100_Brochure.pdf), RF specifications and antenna-to-antenna range table.
2. Sena Networks, [Can I use UD100 on a Linux system?](https://support.senanetworks.com/hc/en-us/articles/227839668-Can-I-use-UD100-on-a-Linux-system), October 26, 2016.
3. Home Assistant, [Bluetooth integration documentation](https://www.home-assistant.io/integrations/bluetooth/), adapter identities and its own testing methodology.
4. Feasycom, [FSC-BP119 product specifications](https://www.feasycom.com/fsc-bp119/).
5. Feasycom, [BP119 User Manual V1.2](https://m.feasycom.net/Content/upload/pdf/202313049/BP119-User-Manual_V1.2.pdf), HCI mode and host OS support.
6. Qualcomm, [CSR8510 specifications](https://www.qualcomm.com/bluetooth/products/csr8510) and [CSR8510 A10 product brief](https://docs.qualcomm.com/doc/80-CT903-1/80-CT903-1_REV_AC_CSR8510_A10_Product_Brief.pdf).
7. Feasycom, [Latest Events](https://www.feasycom.com/fr/feasycom-latest-events/), March 10, 2022; historical Amazon distribution only.
8. Ezurio, [BT820 product and support page](https://www.ezurio.com/part/bt820), silicon, HCI, power, lifecycle and distributor links.
9. StarTech, [USBBT1EDR4 datasheet](https://media.startech.com/cms/pdfs/usbbt1edr4_datasheet.pdf).
10. StarTech, [USBBT1EDR4 manual](https://sgcdn.startech.com/005329/media/sets/usbbt1edr4_manual/usbbt1edr4.pdf), December 12, 2017.
11. StarTech, [USBBT1EDR2 current specifications](https://www.startech.com/en-eu/networking-io/usbbt1edr2).
12. StarTech, [USBBTxEDR2 combined manual](https://sgcdn.startech.com/005329/media/sets/USBBTxEDR2_Manual/USBBTxEDR2.pdf).
13. USconverters, [CRSBT40 specifications and direct offer](https://www.usconverters.com/usb-bluetooth-4-ble-low-energy-dongle).
14. LM Technologies, [LM540 datasheet](https://www.lm-technologies.com/lm_downloads/LM540_DATASHEET.pdf) and [2015 specification](https://www.lm-technologies.com/wp-content/downloads/wireless%20adapters/LM540/Datasheet/LM540_Datasheet.pdf).
15. LM Technologies, [product catalog](https://www.lm-technologies.com/lm_downloads/LM_CATALOGUE_FULL.pdf), LM540 EOL designation.
16. LM Technologies, [driver compatibility matrix](https://wiki.lm-technologies.com/driver-compatibility/).
17. m2m Germany, [Blue-1000-HCI V2 product](https://www.m2mgermany.de/shop/produkt/blue-1000-hci-long-range-bluetooth-dongle-version-2).
18. m2m Germany, [Blue-1000 datasheet hosted by Techship](https://techship.com/download/m2m-usb-dongle-blue-1000-data-sheet/), onboard stack / virtual serial interface.
19. TRENDnet, [TBW-106UB v2.0R specifications and lifecycle](https://www.trendnet.com/products/USB-adapters/TBW-106UB).
20. LogiLink, [BT0015 manufacturer datasheet mirror](https://elektronik-lavpris.dk/files/sup12/124657_1479799469.pdf).
21. LogiLink, [BT0037 manufacturer datasheet via Techly](https://www.techly.com/amfilerating/file/download/file_id/6939/).
22. LogiLink, [BT0048 manufacturer document mirror](https://manualmachine.com/logilink/bt0048/8130277-user-manual/).
23. Edimax, [EB-DGC1 legacy product](https://edimax.com/edimax/merchandise/merchandise_detail/data/edimax/me/home_legacy_bluetooth_adapters/eb-dgc1/).
24. Feasycom, [adapter product catalog](https://www.feasycom.net/bluetooth-dongle-adapter/), BP309 USB CDC description.
25. LM Technologies, [LM058v2 datasheet via Farnell](https://www.farnell.com/datasheets/1917696.pdf), RS232/SPP application.
26. KOAMTAC, [KDC-specific CSR dongle](https://store.koamtac.com/products/koamtac-bluetooth-dongle-for-kdc).
27. Linux kernel, [btusb driver](https://github.com/torvalds/linux/blob/master/drivers/bluetooth/btusb.c), CSR clone detection.
28. Cirago, [BTA8000 manufacturer specifications](https://cirago.com/bta8000.php); retail-model match to the tested sample remains unconfirmed.
