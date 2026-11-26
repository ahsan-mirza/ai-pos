# HP Standard Duty Cash Drawer

Date: 26-11-2026

Status: **BLOCKED** for a physical kick. **PASSED WITH LIMITATIONS** for the electrical gate already in the register.

No new photograph was attached in this pass. The identification below is the one already recorded from the HP cash-drawer user guide and the earlier compatibility note. It was not re-measured on a bench.

## Identification

| Item | Record |
| --- | --- |
| Name | HP Standard Duty Cash Drawer |
| Model | VB400-BL1616 |
| Assembly | 661672-001 |
| Spare | 661843-001 |
| Interface | Printer-driven drawer. Connector on the drawer is RJ45 |
| Cable | An Epson printer needs an RJ12-to-RJ45 cable. This was not photographed here |
| Direct USB | Not present in the recorded specification. Do not plug the drawer cable into a PC USB port |
| Serial or network controller | Not identified |
| Voltage | 24V drawer-kick, from the printer port, not from the PC |
| Pulse | ESC/POS, connector pin 2, 25 on / 250 off units, only after the cashier confirms 24V |
| Sensor | Not exposed. Open/closed stays Not reported |

## MTP-3

The MTP-3 drawer output is labelled DC12V/1A. That label does not make it compatible with this 24V drawer. AxizPOS refuses a 12V confirmation against the HP profile and sends no pulse. A physical kick of the HP drawer from an MTP-3 was not attempted.

## This pass

1. The model on file remains VB400-BL1616.
2. The cable and a separate controller were not on the bench.
3. The 24V printer-port rule is covered by `cash_drawer::tests::hp_drawer_pulses_only_on_a_confirmed_24v_printer_port`.
4. Choosing the HP profile on a separate USB controller is refused and sends nothing.
5. No authorized test kick was sent.
6. No photograph of a physical result was taken.

Physical acceptance is **BLOCKED** until the drawer, a confirmed 24V printer drawer port or a documented controller, and one observed kick are available.
