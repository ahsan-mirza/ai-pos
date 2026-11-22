# Laundry POS operator workflows

The Windows register is the operational workstation. Business Pro configures templates, machines, and supervision. Both use the laundry API.

The floor shows Dashboard, Order intake, Scan garment, Sorting, Production, Machines, Quality, Rework, Packing, Ready orders, Incidents, Order lookup, and Shift summary. A station is visible only when the signed-in permissions allow it.

## Scan

1. The scanner or the scan field receives the tag.
2. The API resolves the tag inside the tenant and branch.
3. The garment card shows the order, customer, service, colour, fabric, care, condition, stage, location, batch, and open incidents.
4. The operator chooses the permitted action.
5. The API writes one event and returns the new stage.

A scan by itself does not advance the garment.

## Stations

- Intake finds an order, registers a garment when authorized, and reprints a tag.
- Sorting shows the service and condition, then assigns a configured category and the next batch.
- Production lists waiting and in-progress work. Start and complete go through the transition API.
- Machines start a cycle on an available, compatible machine. The operator enters the measured load when the machine has a capacity.
- Quality records the checklist and pass, fail, rework, or manager review.
- Packing scans each garment into its own order and completes only when the counts reconcile.
- Ready orders are operationally ready. An unpaid balance stays on the order.

## Offline

Stage changes, batch membership, and machine assignment need the server. While the register is offline those actions stay disabled and the floor says production needs the server. The register does not show a stage as confirmed before the server accepts it. Express orders and deposits stay offline-unsafe, as they did in Phase 2.
