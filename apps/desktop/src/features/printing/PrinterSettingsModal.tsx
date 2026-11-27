import { Select } from "@ai-pos/ui";
import { renderReceipt, type ReceiptDoc } from "@ai-pos/receipt";
import { Printer, RefreshCw, X, ZoomIn } from "lucide-react";
import { memo, useCallback, useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  inTauri,
  listBluetoothPrinters,
  listSerialPorts,
  listWindowsPrinters,
  openCashDrawer,
  probePrinter,
  savePrinterSettings,
  type BluetoothSerialPort,
  type InstalledPrinter,
  type SerialPort,
  type PrinterSettings,
} from "../../lib/tauri";
import { registerIdentity } from "./saleReceipt";
import { BROWSER_PRINTER, loadPrinter, printExactReceipt } from "./print";
import {
  DISCOVERING,
  NONE_FOUND,
  RENDER_FAILED,
  acceptsSavedName,
  applySelection,
  canTestDrawer,
  canTestPrint,
  connectionMessage,
  dedupePrinters,
  diagnosticStages,
  foundMessage,
  inkBytes,
  networkAddressError,
  printerDetail,
  queueOperational,
  REGISTER_VIEW_ONLY,
  saveFeedback,
  selectionWarning,
  TEST_SUBMITTED,
  PRINT_FAILURE,
  testReceiptPrompt,
  CONNECTED,
  type DiagnosticStage,
} from "./printerSelection";
import { drawerConnection, drawerMismatch, drawerProfile, profilesFor } from "./drawerProfiles";
import {
  BLUETOOTH_EMPTY,
  GENERIC_ESCPOS,
  MTP3_LABEL,
  SERIAL_EMPTY,
  TCP_OPEN_NOTICE,
  USB_VIA_WINDOWS,
  activeConnection,
  allowsRawEscpos,
  comPortError,
  connectionChoices,
  isUsbQueue,
  labelProfile,
  settingsForConnection,
  type ConnectionChoice,
} from "./printerConnections";
import { layoutWidth, settingsPreviewReceipt } from "./settingsPreview";
import { businessCurrency } from "../checkout/currency";

interface PrinterSettingsModalProps {
  sample: ReceiptDoc;
  onClose: () => void;
  onSaved: (message: string) => void;
  /** Used by tests so the first render shows a known register without waiting for the desktop shell. */
  initialDraft?: PrinterSettings;
  initialQueues?: InstalledPrinter[];
  initialLoading?: boolean;
  /** Cashiers can view status. Changing the saved configuration needs register-management permission. */
  canSave?: boolean;
  initialBusy?: boolean;
}

const transports = connectionChoices;

export function PrinterSettingsModal({
  onClose,
  onSaved,
  initialDraft,
  initialQueues,
  initialLoading,
  canSave = true,
  initialBusy = false,
}: PrinterSettingsModalProps) {
  const titleId = useId();
  const queueLabelId = useId();
  const desktop = inTauri();
  const request = useRef(0);
  const saving = useRef(false);
  const remembered = useRef({ tcp: "", windows: "", serial: "", bluetooth: "" });
  const [bluetoothPorts, setBluetoothPorts] = useState<BluetoothSerialPort[]>([]);
  const [serialPorts, setSerialPorts] = useState<SerialPort[]>([]);
  const [draft, setDraft] = useState<PrinterSettings>(initialDraft ?? BROWSER_PRINTER);
  const [persisted, setPersisted] = useState(initialDraft?.address ?? "");
  const [busy, setBusy] = useState(initialBusy);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [queues, setQueues] = useState<InstalledPrinter[]>(() => dedupePrinters(initialQueues ?? []));
  const [queuesError, setQueuesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(initialLoading ?? desktop);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [zoomPreview, setZoomPreview] = useState(false);
  const togglePreviewZoom = useCallback(() => setZoomPreview((open) => !open), []);
  const [confirmKick, setConfirmKick] = useState(false);
  const [stages, setStages] = useState<DiagnosticStage[]>([]);
  const [confirmTest, setConfirmTest] = useState(false);
  const printing = useRef(false);

  const refreshQueues = async () => {
    if (!desktop) return;
    const ticket = ++request.current;
    setLoading(true);
    setQueuesError(null);
    try {
      const listed = dedupePrinters(await listWindowsPrinters());
      if (ticket !== request.current) return;
      setQueues(listed);
    } catch (caught) {
      if (ticket !== request.current) return;
      setQueuesError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (ticket === request.current) setLoading(false);
    }
  };

  useEffect(() => {
    const seed = (loaded: PrinterSettings) => {
      if (loaded.transport === "tcp" || loaded.transport === "windows") {
        remembered.current[loaded.transport] = loaded.address;
      }
      if (loaded.transport === "serial" && loaded.connection_kind === "serial") remembered.current.serial = loaded.address;
      else if (loaded.transport === "serial") remembered.current.bluetooth = loaded.address;
      const previous = loaded.previous_address ?? "";
      if (previous && networkAddressError(previous) === null) remembered.current.tcp ||= previous;
      else if (previous) remembered.current.windows ||= previous;
    };
    if (initialDraft) {
      seed(initialDraft);
      return;
    }
    void loadPrinter().then((loaded) => {
      seed(loaded);
      setDraft(loaded);
      setPersisted(loaded.address);
    });
    void refreshQueues();
  }, []);

  useEffect(() => {
    if (!desktop || draft.transport !== "serial") return;
    if (draft.connection_kind === "serial") {
      void listSerialPorts()
        .then(setSerialPorts)
        .catch(() => setSerialPorts([]));
      return;
    }
    void listBluetoothPrinters()
      .then(setBluetoothPorts)
      .catch(() => setBluetoothPorts([]));
  }, [desktop, draft.transport, draft.connection_kind]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const patch = (next: Partial<PrinterSettings>) => {
    setDraft((current) => ({ ...current, ...next }));
    setError(null);
    setStatus(null);
  };

  const switchTransport = (id: ConnectionChoice) => {
    if (busy || id === activeConnection(draft)) return;
    const current = activeConnection(draft);
    if (current === "network") remembered.current.tcp = draft.address;
    if (current === "windows" || current === "usb") remembered.current.windows = draft.address;
    if (current === "bluetooth") remembered.current.bluetooth = draft.address;
    if (current === "serial") remembered.current.serial = draft.address;
    const previous = draft.transport === "none" ? draft.previous_address ?? "" : draft.address.trim() || draft.previous_address || "";
    patch({
      ...settingsForConnection(id, remembered.current),
      previous_address: previous,
      verification: "candidate",
    });
  };

  const moveConnection = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft" && event.key !== "Home" && event.key !== "End") return;
    const target = event.target;
    if (!(target instanceof HTMLElement) || target.getAttribute("role") !== "tab") return;
    event.preventDefault();
    const current = transports.findIndex((item) => item.id === activeConnection(draft));
    const nextIndex =
      event.key === "Home" ? 0
      : event.key === "End" ? transports.length - 1
      : event.key === "ArrowRight" ? (current + 1) % transports.length
      : (current - 1 + transports.length) % transports.length;
    const next = transports[nextIndex];
    if (!next) return;
    switchTransport(next.id);
    event.currentTarget.querySelector<HTMLButtonElement>(`[data-connection="${next.id}"]`)?.focus();
  };

  const persist = async (): Promise<PrinterSettings | null> => {
    if (!canSave) {
      setError(REGISTER_VIEW_ONLY);
      return null;
    }
    if (!desktop) {
      setError("Printer settings are stored on the register. Open the desktop app to change them.");
      return null;
    }
    if (draft.transport === "tcp") {
      const invalid = networkAddressError(draft.address);
      if (invalid) {
        setError(invalid);
        return null;
      }
    }
    if (draft.transport === "serial") {
      const invalid = comPortError(draft.address, draft.connection_kind === "serial" ? "serial" : "bluetooth");
      if (invalid) {
        setError(invalid);
        return null;
      }
    }
    if (draft.transport === "ble") {
      setError("Bluetooth Low Energy printing needs a documented GATT service. This device is not saved as a receipt printer.");
      return null;
    }
    if (draft.transport === "windows" && !acceptsSavedName(draft.address, queues, persisted)) {
      setError(draft.address.trim() ? "Select an installed Windows printer." : "Select a printer.");
      return null;
    }
    if (![1, 2, 3].includes(draft.copies)) {
      setError("Copies per sale must be 1, 2, or 3.");
      return null;
    }
    try {
      const saved = await savePrinterSettings(draft);
      setDraft(saved);
      setPersisted(saved.address);
      return saved;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return null;
    }
  };

  const save = async (): Promise<boolean> => {
    if (saving.current || busy) return false;
    saving.current = true;
    setBusy(true);
    const saved = await persist();
    if (!saved) {
      saving.current = false;
      return false;
    }
    let message = saveFeedback(saved, queues);
    const selected = queues.find((queue) => queue.name === saved.address.trim());
    if (saved.transport === "windows" && queueOperational(selected)) {
      try {
        const probe = await probePrinter();
        if (connectionMessage(probe) === CONNECTED) message = CONNECTED;
      } catch {
        // The configuration is already stored. A later status check can report the printer.
      }
    }
    setBusy(false);
    saving.current = false;
    onSaved(message);
    onClose();
    return true;
  };

  const selectedQueue = () => queues.find((queue) => queue.name === draft.address.trim());
  const testDocument = () => settingsPreviewReceipt(registerIdentity(), businessCurrency());

  const showStages = (rendered: boolean, ink: number, submitted: boolean) => {
    const queue = selectedQueue();
    setStages(
      diagnosticStages({
        queue,
        missing: draft.address.trim() !== "" && !queue,
        rendered,
        ink,
        submitted,
        lineCount: testDocument().lines.length,
      }),
    );
  };

  const validateConnection = async () => {
    if (!desktop) {
      setError("Printer validation runs on the desktop register.");
      return;
    }
    if (!(await persist())) return;
    try {
      const probe = await probePrinter();
      const message = connectionMessage(probe);
      if (message === CONNECTED) setStatus(CONNECTED);
      else setStatus(message);
      showStages(false, 0, false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const renderPreview = async () => {
    setError(null);
    try {
      const rendered = await renderReceipt(testDocument(), layoutWidth(draft.paper_dots));
      const bits = rendered.bits();
      const ink = inkBytes(bits);
      setPreviewUrl(rendered.canvas.toDataURL("image/png"));
      showStages(true, ink, false);
      if (ink === 0) setError(RENDER_FAILED);
      else setStatus(`Receipt preview has visible content (${ink} ink bytes, ${rendered.width} dots wide). Nothing was sent to the printer.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  };

  const testPrint = async () => {
    if (printing.current || busy) return;
    printing.current = true;
    if (desktop && !(await persist())) {
      printing.current = false;
      return;
    }
    const document = testDocument();
    let ink = 0;
    try {
      const rendered = await renderReceipt(document, layoutWidth(draft.paper_dots));
      ink = inkBytes(rendered.bits());
      setPreviewUrl(rendered.canvas.toDataURL("image/png"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      showStages(false, 0, false);
      printing.current = false;
      return;
    }
    if (ink === 0) {
      showStages(true, 0, false);
      setError(RENDER_FAILED);
      printing.current = false;
      return;
    }
    const outcome = await printExactReceipt(document, layoutWidth(draft.paper_dots));
    showStages(true, ink, outcome.printed);
    printing.current = false;
    if (!outcome.printed) setError(outcome.message || PRINT_FAILURE);
    else setStatus(TEST_SUBMITTED);
  };

  const testDrawer = async () => {
    if (printing.current || busy) return;
    printing.current = true;
    try {
      await openCashDrawer();
      setStatus("Drawer kick command submitted. Open/closed state: Not reported.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      printing.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    void renderReceipt(settingsPreviewReceipt(registerIdentity(), businessCurrency()), layoutWidth(draft.paper_dots))
      .then((rendered) => {
        if (!cancelled && inkBytes(rendered.bits()) > 0) setPreviewUrl(rendered.canvas.toDataURL("image/png"));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [draft.paper_dots]);

  const addressLabel = "Printer IP address";
  const warning = draft.transport === "windows" && !loading ? selectionWarning(draft.address, queues) : null;
  const selected = queues.find((queue) => queue.name === draft.address.trim());
  const missingName = warning && !selected ? draft.address.trim() : "";
  const discovery =
    loading ? DISCOVERING : queuesError ? queuesError : queues.length === 0 ? NONE_FOUND : foundMessage(queues.length);
  const printDisabled = !canSave || draft.transport === "ble" || (draft.transport === "windows" && !canTestPrint(draft, queues));
  const drawerDisabled = draft.transport === "none" || draft.transport === "serial" || draft.transport === "ble";
  const usbMode = activeConnection(draft) === "usb";
  const shownQueues = usbMode ? queues.filter(isUsbQueue) : queues;
  const selectedQueueNow = selectedQueue();
  const mtp3 = selectedQueueNow
    ? labelProfile(`${selectedQueueNow.name} ${selectedQueueNow.driver} ${selectedQueueNow.manufacturer ?? ""}`)
    : null;
  const connection = drawerConnection(draft.drawer_connection);
  const kickDisabled = !canTestDrawer(draft, queues);
  const mismatch = drawerMismatch({
    drawer_profile: draft.drawer_profile,
    host_voltage: draft.host_voltage,
    model: `${draft.address} ${selectedQueueNow?.driver ?? ""} ${selectedQueueNow?.name ?? ""}`,
  });
  const drawerPolicyDisabled = !canSave || connection === "none" || (connection === "printer" && drawerDisabled);
  const shownError = !canSave && error === REGISTER_VIEW_ONLY ? null : error;

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card flex max-h-[min(92dvh,52rem)] w-full max-w-5xl flex-col">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-white">
            <Printer size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Receipt Printer & Cash Drawer
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">This register only. Preview and tests do not create a sale.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <form
          className="mt-4 flex min-h-0 flex-1 flex-col overflow-hidden"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto lg:grid-cols-[minmax(0,1.35fr)_17rem]">
          <div className="space-y-4">
          <div
            className="flex flex-nowrap gap-1 overflow-x-auto rounded-3xl bg-charcoal p-1"
            role="tablist"
            aria-label="Printer connection"
            onKeyDown={(event) => moveConnection(event)}
          >
            {transports.map(({ id, label }) => {
              const selected = activeConnection(draft) === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  data-connection={id}
                  aria-selected={selected}
                  tabIndex={selected ? 0 : -1}
                  disabled={busy}
                  onClick={() => switchTransport(id)}
                  className={`shrink-0 whitespace-nowrap rounded-full px-3 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:opacity-40 ${
                    selected ? "bg-primary text-white" : "text-white/70 hover:text-white"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          {draft.transport === "windows" ? (
            <div className="space-y-2">
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <span id={queueLabelId} className="mb-1.5 block text-sm font-medium">
                    {usbMode ? "Select USB printer" : "Select Windows printer"}
                  </span>
                  <Select
                    labelledBy={queueLabelId}
                    icon={Printer}
                    searchable
                    placeholder="Select a printer"
                    disabled={busy}
                    value={draft.address}
                    onChange={(value) => {
                      const chosen = queues.find((queue) => queue.name === value);
                      if (!chosen) return;
                      patch({
                        ...applySelection(chosen),
                        protocol: allowsRawEscpos(chosen) && draft.protocol === "escpos" ? "escpos" : "",
                      });
                    }}
                    options={[
                      ...shownQueues.map((queue) => ({
                        value: queue.name,
                        label: queue.name,
                        hint: printerDetail(queue),
                        badge: (
                          <span className="shrink-0 text-xs font-semibold text-charcoal/70 dark:text-zinc-300">{queue.statusLabel}</span>
                        ),
                      })),
                      ...(missingName
                        ? [
                            {
                              value: missingName,
                              label: missingName,
                              hint: "Not installed",
                              badge: (
                                <span className="shrink-0 text-xs font-semibold text-red-600 dark:text-red-400">Not installed</span>
                              ),
                            },
                          ]
                        : []),
                    ]}
                  />
                </div>
                <button
                  type="button"
                  aria-label="Refresh printers"
                  title="Refresh printers"
                  onClick={() => void refreshQueues()}
                  disabled={busy || loading}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-line text-charcoal hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-800 dark:text-zinc-100"
                >
                  <RefreshCw size={18} aria-hidden="true" className={loading ? "animate-spin" : ""} />
                </button>
              </div>
              <p role="status" aria-live="polite" aria-busy={loading} className="text-sm text-charcoal/70 dark:text-zinc-300">
                {discovery}
              </p>
              {selected ? <p className="text-sm text-charcoal/60 dark:text-zinc-400">{printerDetail(selected)}</p> : null}
              {usbMode ? <p className="text-sm text-charcoal/60 dark:text-zinc-400">{USB_VIA_WINDOWS}</p> : null}
              {selected && allowsRawEscpos(selected) ? (
                <fieldset>
                  <legend className="text-sm font-medium">Printing language</legend>
                  <div className="mt-2 flex gap-2">
                    {(
                      [
                        ["", "Windows driver"],
                        ["escpos", "ESC/POS"],
                      ] as const
                    ).map(([protocol, label]) => (
                      <button
                        key={label}
                        type="button"
                        aria-pressed={(draft.protocol || "") === protocol}
                        disabled={!canSave || busy}
                        onClick={() => patch({ protocol, verification: "candidate" })}
                        className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                          (draft.protocol || "") === protocol
                            ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900"
                            : "bg-surface dark:bg-zinc-800/60 text-charcoal dark:text-zinc-100 hover:bg-charcoal/10 dark:hover:bg-white/10"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {draft.protocol === "escpos" ? <p className="mt-2 text-sm text-charcoal/60 dark:text-zinc-400">{GENERIC_ESCPOS}</p> : null}
                </fieldset>
              ) : null}
              <ul className="sr-only">
                {shownQueues.map((queue) => (
                  <li key={queue.name}>
                    {queue.name} {queue.statusLabel} {printerDetail(queue)}
                  </li>
                ))}
              </ul>
              {warning ? (
                <p
                  role={selected?.compatibility === "candidate" ? "status" : "alert"}
                  className={`text-sm font-medium ${selected?.compatibility === "candidate" ? "text-charcoal/80 dark:text-zinc-200" : "text-red-600 dark:text-red-400"}`}
                >
                  {warning}
                </p>
              ) : null}
              {selected ? (
                <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1 rounded-2xl bg-surface px-3 py-3 text-sm dark:bg-zinc-800/60">
                  <dt className="text-charcoal/60 dark:text-zinc-400">Selected printer</dt>
                  <dd className="break-words">{selected.name}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Classification</dt>
                  <dd>{selected.statusLabel}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Queue status</dt>
                  <dd>{selected.availability || "Unknown"}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Driver</dt>
                  <dd className="break-words">{selected.driver || "Driver not reported"}{selected.driverVersion ? ` · ${selected.driverVersion}` : ""}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Port</dt>
                  <dd className="break-words">{selected.port || "Port not reported"}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Connection</dt>
                  <dd>{selected.connection || "Connection not reported"}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Capabilities</dt>
                  <dd>{selected.capabilities || "Not reported"}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Print transport</dt>
                  <dd>{selected.printTransport || "Not selected"}</dd>
                  <dt className="text-charcoal/60 dark:text-zinc-400">Drawer</dt>
                  <dd>{selected.supportsDrawerKick ? "Kick profile verified" : "Not verified"} · sensor Not reported</dd>
                </dl>
              ) : null}
              <label className="flex items-center justify-between gap-3 text-sm font-medium">
                Automatic discovery
                <input
                  type="checkbox"
                  checked={draft.auto_discover !== false}
                  disabled={!canSave || busy}
                  onChange={(event) => patch({ auto_discover: event.target.checked })}
                  className="h-5 w-5 accent-primary disabled:opacity-40"
                />
              </label>
              <p className="text-sm text-charcoal/60 dark:text-zinc-400">
                Printer status is separate from the cash drawer. A missing printer does not turn off a separate drawer, and a missing drawer does not turn off receipt printing.
              </p>
            </div>
          ) : draft.transport === "tcp" ? (
            <label className="block text-sm font-medium" htmlFor="printer-address">
              {addressLabel}
              <input
                id="printer-address"
                autoComplete="off"
                spellCheck={false}
                value={draft.address}
                disabled={!canSave || busy}
                onChange={(event) => patch({ address: event.target.value, connection_kind: draft.connection_kind === "wifi" ? "wifi" : "network" })}
                placeholder="192.168.1.50 or 192.168.1.50:9100"
                className="modal-input mt-1.5 font-normal tabular-nums"
              />
              <span className="mt-1.5 block font-normal text-charcoal/60 dark:text-zinc-400">
                Ethernet and Wi-Fi use this address. Port 9100 is the default raw port. {TCP_OPEN_NOTICE} The network is not scanned.
              </span>
            </label>
          ) : draft.transport === "serial" && draft.connection_kind === "serial" ? (
            <div className="space-y-2 text-sm">
              <p>{SERIAL_EMPTY}</p>
              {serialPorts.length > 0 ? (
                <label className="block font-medium">
                  COM port
                  <select
                    className="modal-input mt-1.5 font-normal"
                    value={draft.address}
                    disabled={!canSave || busy}
                    onChange={(event) => patch({ transport: "serial", connection_kind: "serial", address: event.target.value, protocol: "escpos", verification: "candidate" })}
                  >
                    <option value="">Select a port</option>
                    {serialPorts.map((item) => (
                      <option key={item.port} value={item.port}>
                        {item.port} · {item.device}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="block font-medium" htmlFor="serial-port">
                  COM port
                  <input
                    id="serial-port"
                    autoComplete="off"
                    spellCheck={false}
                    value={draft.address}
                    disabled={!canSave || busy}
                    onChange={(event) => patch({ transport: "serial", connection_kind: "serial", address: event.target.value, protocol: "escpos", verification: "candidate" })}
                    placeholder="COM4"
                    className="modal-input mt-1.5 font-normal"
                  />
                </label>
              )}
              <p className="text-charcoal/60 dark:text-zinc-400">{GENERIC_ESCPOS}</p>
            </div>
          ) : draft.transport === "serial" || draft.transport === "ble" ? (
            <div className="space-y-2 text-sm">
              <p>{BLUETOOTH_EMPTY}</p>
              <p>Pairing stays in Windows. AxizPOS does not bypass pairing.</p>
              {bluetoothPorts.length > 0 ? (
                <label className="block font-medium">
                  Paired Bluetooth serial port
                  <select
                    className="modal-input mt-1.5 font-normal"
                    value={draft.address}
                    disabled={!canSave || busy}
                    onChange={(event) => {
                      const chosen = bluetoothPorts.find((item) => item.port === event.target.value);
                      patch({
                        transport: "serial",
                        connection_kind: "bluetooth-classic",
                        address: event.target.value,
                        bluetooth_identity: chosen?.device ?? "",
                        verification: "candidate",
                      });
                    }}
                  >
                    <option value="">Select a port</option>
                    {bluetoothPorts.map((item) => (
                      <option key={item.port} value={item.port}>
                        {item.port} · {item.device} · {item.pairing} · {item.protocol}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className="block font-medium" htmlFor="bluetooth-port">
                  Bluetooth serial port
                  <input
                    id="bluetooth-port"
                    autoComplete="off"
                    spellCheck={false}
                    value={draft.address}
                    disabled={!canSave || busy}
                    onChange={(event) => patch({ transport: "serial", connection_kind: "bluetooth-classic", address: event.target.value, verification: "candidate" })}
                    placeholder="COM5"
                    className="modal-input mt-1.5 font-normal"
                  />
                </label>
              )}
              <p className="text-charcoal/60 dark:text-zinc-400">
                Bluetooth Low Energy is not treated as a receipt printer. {`A GATT write is sent only for a documented printing service, and none is registered.`}
              </p>
            </div>
          ) : (
            <p className="rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-3 text-sm text-charcoal/70 dark:text-zinc-300">
              Without a receipt printer, Print receipt opens the system print dialog instead.
            </p>
          )}

          <fieldset>
            <legend className="text-sm font-medium">Paper width</legend>
            <div className="mt-2 flex gap-2">
              {(
                [
                  [576, "80 mm"],
                  [384, "58 mm"],
                ] as const
              ).map(([dots, label]) => (
                <button
                  key={dots}
                  type="button"
                  aria-pressed={draft.paper_dots === dots}
                  disabled={!canSave || busy}
                  onClick={() => patch({ paper_dots: dots })}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    draft.paper_dots === dots ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-surface dark:bg-zinc-800/60 text-charcoal dark:text-zinc-100 hover:bg-charcoal/10 dark:hover:bg-white/10"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {mtp3 ? <p className="mt-2 text-sm text-charcoal/60 dark:text-zinc-400">{MTP3_LABEL}</p> : null}
          </fieldset>

          <div className="space-y-2 rounded-2xl bg-surface dark:bg-zinc-800/60 p-3">
            <div className="flex items-start justify-between gap-3 px-1 text-sm font-medium">
              <span>
                Ask before printing a sale receipt
                <span className="mt-1 block font-normal text-charcoal/60 dark:text-zinc-400">
                  Pay always asks after the payment is saved. Yes prints that receipt. No skips printing. The answer is
                  not saved, and this register cannot print or skip the next sale on its own.
                </span>
              </span>
              <input
                type="checkbox"
                checked
                disabled
                readOnly
                aria-label="Ask before printing a sale receipt"
                className="mt-0.5 h-5 w-5 accent-primary"
              />
            </div>
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Drawer connection
              <Select
                size="sm"
                className="w-56"
                aria-label="Drawer connection"
                disabled={!canSave}
                value={connection}
                onChange={(value) => {
                  const profile = drawerProfile(draft.drawer_profile);
                  patch({
                    drawer_connection: value,
                    ...(value !== "printer" && profile.connection === "printer" ? { drawer_profile: "" } : {}),
                  });
                }}
                options={[
                  { value: "printer", label: "Through receipt printer" },
                  { value: "separate", label: "Separate device" },
                  { value: "none", label: "None" },
                ]}
              />
            </label>
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Open the cash drawer for cash payments
              <input
                type="checkbox"
                checked={connection !== "none" && draft.drawer_kick}
                disabled={drawerPolicyDisabled}
                onChange={(event) => patch({ drawer_kick: event.target.checked })}
                className="h-5 w-5 accent-primary disabled:opacity-40"
              />
            </label>
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Open the cash drawer for card and other payments
              <input
                type="checkbox"
                checked={connection !== "none" && draft.open_on_non_cash === true}
                disabled={drawerPolicyDisabled}
                onChange={(event) => patch({ open_on_non_cash: event.target.checked })}
                className="h-5 w-5 accent-primary disabled:opacity-40"
              />
            </label>
            {connection === "none" ? (
              <p className="px-1 text-sm text-charcoal/60 dark:text-zinc-400">
                Drawer kick is off. Receipt printer settings stay as they are. No drawer command is sent.
              </p>
            ) : null}
            {connection === "printer" ? (
              <>
                <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
                  Cash drawer
                  <Select
                    size="sm"
                    className="w-72"
                    aria-label="Cash drawer"
                    disabled={!canSave}
                    value={draft.drawer_profile ?? ""}
                    onChange={(value) => {
                      const profile = drawerProfile(value);
                      patch({
                        drawer_profile: value,
                        ...(profile.lockedPin != null
                          ? { drawer_pin: profile.lockedPin, drawer_on: profile.on, drawer_off: profile.off }
                          : {}),
                      });
                    }}
                    options={profilesFor("printer").map((profile) => ({ value: profile.id, label: profile.label }))}
                  />
                </label>
                <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
                  Printer drawer-port voltage
                  <Select
                    size="sm"
                    className="w-40"
                    aria-label="Printer drawer-port voltage"
                    disabled={!canSave}
                    value={draft.host_voltage ?? ""}
                    onChange={(value) => patch({ host_voltage: value })}
                    options={[
                      { value: "", label: "Unconfirmed" },
                      { value: "24", label: "24V" },
                      { value: "12", label: "12V" },
                    ]}
                  />
                </label>
                <p className="px-1 text-sm text-charcoal/60 dark:text-zinc-400">{drawerProfile(draft.drawer_profile).note}</p>
                {mismatch ? (
                  <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-300">
                    {mismatch}
                  </p>
                ) : null}
                <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
                  Drawer connector
                  <Select
                    size="sm"
                    className="w-36"
                    aria-label="Drawer connector"
                    disabled={!canSave || drawerDisabled || drawerProfile(draft.drawer_profile).lockedPin != null}
                    value={String(drawerProfile(draft.drawer_profile).lockedPin ?? draft.drawer_pin ?? 0)}
                    onChange={(value) => patch({ drawer_pin: Number(value) })}
                    options={[
                      { value: "0", label: "Pin 2" },
                      { value: "1", label: "Pin 5" },
                    ]}
                  />
                </label>
              </>
            ) : null}
            {connection === "separate" ? (
              <>
                <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
                  Controller
                  <Select
                    size="sm"
                    className="w-56"
                    aria-label="Drawer controller"
                    disabled={!canSave}
                    value={draft.drawer_controller_kind ?? ""}
                    onChange={(value) => patch({ drawer_controller_kind: value, drawer_profile: "" })}
                    options={[
                      { value: "", label: "Not chosen" },
                      { value: "usb", label: "USB controller" },
                      { value: "serial", label: "Serial / COM" },
                      { value: "network", label: "Network controller" },
                      { value: "vendor", label: "Vendor controller" },
                    ]}
                  />
                </label>
                <label className="block px-1 text-sm font-medium">
                  Controller address
                  <input
                    value={draft.drawer_controller_address ?? ""}
                    disabled={!canSave}
                    aria-label="Drawer controller address"
                    placeholder={draft.drawer_controller_kind === "serial" ? "COM1" : "Host or device id"}
                    onChange={(event) => patch({ drawer_controller_address: event.target.value })}
                    className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-sm dark:bg-zinc-900"
                  />
                </label>
                <p className="px-1 text-sm text-charcoal/60 dark:text-zinc-400">
                  No verified USB, serial, network, or vendor drawer command is installed. Save stores the choice and does not send a pulse. An RJ11/RJ12 drawer still needs a compatible controller. Open/closed: Not reported.
                </p>
              </>
            ) : null}
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Copies per sale
              <Select
                size="sm"
                className="w-24"
                aria-label="Copies"
                disabled={!canSave || busy}
                value={String(draft.copies)}
                onChange={(value) => patch({ copies: Number(value) })}
                options={[1, 2, 3].map((count) => ({ value: String(count), label: String(count) }))}
              />
            </label>
          </div>

          {shownError ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {shownError}
            </p>
          ) : null}
          {status ? (
            <p role="status" className="text-sm font-medium">
              {status}
            </p>
          ) : null}

          {!canSave ? (
            <p role="status" className="text-sm text-charcoal/70 dark:text-zinc-300">
              {REGISTER_VIEW_ONLY}
            </p>
          ) : null}

          {stages.length > 0 ? (
            <table className="w-full text-sm">
              <caption className="mb-1 text-left font-medium">Diagnostic stages</caption>
              <tbody>
                {stages.map((item) => (
                  <tr key={item.stage}>
                    <th scope="row" className="py-0.5 pr-3 text-left font-normal text-charcoal/70 dark:text-zinc-300">
                      {item.stage}
                    </th>
                    <td>{item.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          </div>
          <ReceiptPreview
            url={previewUrl}
            zoom={zoomPreview}
            paper={draft.paper_dots === 384 ? "58 mm" : "80 mm"}
            onZoom={togglePreviewZoom}
          />
          </div>

          {confirmTest ? (
            <div className="rounded-2xl bg-surface dark:bg-zinc-800/60 p-3 text-sm">
              <p>{testReceiptPrompt(draft.address || selectedQueue()?.name || "")}</p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setConfirmTest(false);
                    void testPrint();
                  }}
                  disabled={printDisabled}
                  className="rounded-full bg-charcoal px-4 py-2 font-semibold text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
                >
                  Send test receipt
                </button>
                <button type="button" onClick={() => setConfirmTest(false)} disabled={busy} className="rounded-full border border-line px-4 py-2 font-semibold">
                  Cancel
                </button>
              </div>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-2 pt-2">
            {draft.transport === "windows" ? (
              <button
                type="button"
                onClick={() => void validateConnection()}
                disabled={!draft.address.trim()}
                className="rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-800"
              >
                Validate connection
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void renderPreview()}
              className="rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-800"
            >
              Test receipt rendering
            </button>
            <button
              type="button"
              onClick={() => {
                if (!canSave) {
                  setError(REGISTER_VIEW_ONLY);
                  return;
                }
                setConfirmTest(true);
              }}
              disabled={printDisabled}
              className="rounded-full border border-line px-4 py-2 text-sm font-semibold hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-800"
            >
              Print test receipt
            </button>
            <button
              type="button"
              onClick={() => setConfirmKick(true)}
              disabled={!canSave || kickDisabled}
              title={kickDisabled ? mismatch || "Drawer kick stays off until the profile, voltage, and ESC/POS path match." : "Send one drawer pulse"}
              className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white hover:brightness-110 disabled:opacity-40"
            >
              Test drawer kick
            </button>
          </div>
          {confirmKick ? (
            <div className="rounded-2xl bg-surface p-3 text-sm dark:bg-zinc-800/60">
              <p>
                Send one drawer pulse to {draft.address || "the selected printer"} on its DK port
                {draft.host_voltage ? ` at ${draft.host_voltage}V` : ""}. This uses the same command as a cash sale. Open/closed stays Not reported.
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setConfirmKick(false);
                    void testDrawer();
                  }}
                  disabled={kickDisabled}
                  className="rounded-full bg-primary px-4 py-2 font-semibold text-white disabled:opacity-40"
                >
                  Send one pulse
                </button>
                <button type="button" onClick={() => setConfirmKick(false)} disabled={busy} className="rounded-full border border-line px-4 py-2 font-semibold">
                  Cancel
                </button>
              </div>
            </div>
          ) : null}
          <div className="mt-3 flex items-center justify-end gap-3 border-t border-line pt-3">
            <div className="flex gap-3">
              <button type="button" onClick={onClose} disabled={busy} className="modal-cancel">
                Cancel
              </button>
              <button type="submit" disabled={busy || !canSave} className="modal-save">
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

const ReceiptPreview = memo(function ReceiptPreview({
  url,
  zoom,
  paper,
  onZoom,
}: {
  url: string | null;
  zoom: boolean;
  paper: string;
  onZoom: () => void;
}) {
  return (
    <aside className="space-y-2 rounded-2xl border border-line bg-surface p-3 dark:border-zinc-800 dark:bg-zinc-800/40">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Receipt preview</h3>
        <button
          type="button"
          onClick={onZoom}
          disabled={!url}
          className="inline-flex h-9 items-center gap-1 rounded-full border border-line px-3 text-xs font-semibold disabled:opacity-40"
        >
          <ZoomIn size={14} aria-hidden="true" />
          {zoom ? "Shrink" : "Zoom"}
        </button>
      </div>
      <p className="text-xs text-charcoal/60 dark:text-zinc-400">{paper} sample. Nothing is printed and the drawer stays closed.</p>
      {url ? (
        <img
          src={url}
          alt="Receipt preview"
          className={`mx-auto w-auto rounded-xl border border-line bg-white ${zoom ? "max-h-[32rem]" : "max-h-64"}`}
        />
      ) : (
        <p className="text-sm text-charcoal/60 dark:text-zinc-400">The sample receipt appears here when the preview is ready.</p>
      )}
    </aside>
  );
});
