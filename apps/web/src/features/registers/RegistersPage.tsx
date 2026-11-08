import { actionHoverClass, useLocale } from "@ai-pos/ui";
import {
  activationBusinessCode,
  businessCodeLabel,
  businessCodePhrase,
  type BusinessSettings,
  type Device,
  type DeviceActivationKey,
  type DeviceKey,
} from "@ai-pos/shared-types";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Check, Copy, Download, KeyRound, MonitorSmartphone, Plus, RotateCw, ShieldOff, X } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { Modal } from "../../components/ui/Modal";
import { Toast } from "../../components/ui/Toast";
import { env } from "../../config/env";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { formatDate, storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

function seen(device: Device): { label: string; live: boolean } {
  if (device.revoked_at) return { label: "Revoked", live: false };
  if (!device.last_seen_at) return { label: "Never connected", live: false };
  const minutes = (Date.now() - new Date(device.last_seen_at).getTime()) / 60_000;
  if (minutes < 10) return { label: "Online", live: true };
  return { label: `Seen ${formatDate(device.last_seen_at)}`, live: false };
}

export function RegistersPage() {
  const { user } = useAuth();
  const { stores } = useStores();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState<DeviceKey | null>(null);
  const [activation, setActivation] = useState<{ device: Device; key: DeviceActivationKey } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      setDevices(await apiGet<Device[]>("/api/v1/devices"));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load registers."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (device: Device, action: "rotate" | "revoke") => {
    const accepted =
      action === "revoke"
        ? await confirm({
            title: "Revoke register",
            message: `Revoke ${device.code}? It stops syncing until it gets a new key.`,
            confirmLabel: "Revoke",
            tone: "danger",
          })
        : await confirm({
            title: "Issue a new key",
            message: `Issue a new key for ${device.code}? The old key stops working immediately.`,
            confirmLabel: "Issue key",
            tone: "danger",
          });
    if (!accepted) return;
    try {
      if (action === "rotate") setIssued(await apiPost<DeviceKey>(`/api/v1/devices/${device.id}/rotate`, {}));
      else {
        await apiPost<Device>(`/api/v1/devices/${device.id}/revoke`, {});
        setToast(`${device.code} revoked.`);
      }
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the register."));
    }
  };

  const issueActivation = async (device: Device) => {
    try {
      const key = await apiPost<DeviceActivationKey>(`/api/v1/devices/${device.id}/activation-key`, {});
      setActivation({ device, key });
    } catch (caught) {
      setError(errorMessage(caught, "Could not create an activation key."));
    }
  };

  const rows = devices ?? [];
  const online = rows.filter((device) => seen(device).live).length;

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Registered tills</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.filter((device) => !device.revoked_at).length}</p>
          <p className="mt-2 text-xs text-white/50">Each has its own key and invoice series</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Online now</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{online}</p>
          <p className="mt-2 text-xs text-white/80">Synced in the last 10 minutes</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Invoices numbered offline</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {rows.reduce((sum, device) => sum + device.last_invoice_value, 0)}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">Across every register series</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Registers</h2>
            <p className="text-sm text-charcoal/60">Keys replace the shared API key and bind each till to its branch.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={`${env.apiBaseUrl}/api/download/installer/win`}
              className={`inline-flex items-center justify-center rounded-full border border-gray-200 bg-white px-6 py-2.5 text-sm font-medium text-black ${actionHoverClass("neutral")}`}
            >
              <Download size={16} aria-hidden="true" className="-ml-2 mr-1.5" />
              Download POS app
            </a>
            <PrimaryButton onClick={() => setCreating(true)}>
              <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" />
              Register a till
            </PrimaryButton>
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Register</th>
                <th className="pb-3 font-medium">Branch</th>
                <th className="pb-3 font-medium">Invoice series</th>
                <th className="pb-3 text-right font-medium">Last number</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
                <th className="pb-3 font-medium">Key</th>
                <th className="pb-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((device) => {
                const state = seen(device);
                return (
                  <tr key={device.id} className={`border-t border-line ${device.revoked_at ? "opacity-50" : ""}`}>
                    <td className="py-3">
                      <span className="flex items-center gap-2 font-medium">
                        <MonitorSmartphone size={16} aria-hidden="true" className="text-charcoal/50" />
                        {device.code}
                      </span>
                      <span className="block text-xs text-charcoal/50">{device.name}</span>
                    </td>
                    <td className="py-3">{device.store_code}</td>
                    <td className="py-3 font-mono text-xs">{device.invoice_prefix}-NNNNNN</td>
                    <td className="py-3 text-right tabular-nums">{device.last_invoice_value}</td>
                    <td className="py-3 pl-6">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          state.live ? "bg-accent text-white" : "bg-surface text-charcoal/60 ring-1 ring-line"
                        }`}
                      >
                        {state.label}
                      </span>
                    </td>
                    <td className="py-3 font-mono text-xs text-charcoal/60">…{device.key_hint}</td>
                    <td className="py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          title="Generate activation key"
                          aria-label={`Generate activation key for ${device.code}`}
                          onClick={() => void issueActivation(device)}
                          className={`inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-xs font-semibold ${actionHoverClass("success")}`}
                        >
                          <KeyRound size={14} aria-hidden="true" /> Activate
                        </button>
                        <button
                          type="button"
                          title="Issue a new key"
                          aria-label={`Issue a new key for ${device.code}`}
                          onClick={() => void act(device, "rotate")}
                          className={`flex h-9 w-9 items-center justify-center rounded-full border border-line ${actionHoverClass("warning")}`}
                        >
                          <RotateCw size={15} aria-hidden="true" />
                        </button>
                        {!device.revoked_at ? (
                          <button
                            type="button"
                            title="Revoke"
                            aria-label={`Revoke ${device.code}`}
                            onClick={() => void act(device, "revoke")}
                            className={`flex h-9 w-9 items-center justify-center rounded-full border border-line ${actionHoverClass("danger")}`}
                          >
                            <ShieldOff size={15} aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {devices !== null && rows.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No registers yet. Registers on the shared key keep working in dev.</p>
          ) : null}
        </div>
      </div>

      {creating ? (
        <CreateRegisterModal
          stores={stores}
          defaultStore={user?.store_id ?? stores[0]?.id ?? ""}
          onClose={() => setCreating(false)}
          onCreated={(result) => {
            setCreating(false);
            void issueActivation(result.device);
            void load();
          }}
        />
      ) : null}
      {issued ? <KeyModal issued={issued} onClose={() => setIssued(null)} /> : null}
      {activation ? (
        <ActivationModal
          device={activation.device}
          activation={activation.key}
          stores={stores}
          onClose={() => setActivation(null)}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function CreateRegisterModal({
  stores,
  defaultStore,
  onClose,
  onCreated,
}: {
  stores: ReturnType<typeof useStores>["stores"];
  defaultStore: string;
  onClose: () => void;
  onCreated: (result: DeviceKey) => void;
}) {
  const { t } = useLocale();
  const { profile } = useCapabilities();
  const [storeId, setStoreId] = useState(defaultStore);
  const [code, setCode] = useState("R01");
  const [name, setName] = useState("Front counter");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onCreated(await apiPost<DeviceKey>("/api/v1/devices", { store_id: storeId, code: code.trim(), name: name.trim() }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not register the till."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Register a till"
      subtitle={t(businessCodePhrase(profile, "activateHint"))}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || !storeId || !code.trim()} onClick={() => void save()}>
            {busy ? "Registering…" : "Register and get activation key"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <SelectField label="Branch" value={storeId} options={storeOptions(stores)} placeholder="Choose a branch" onChange={setStoreId} />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Code"
            value={code}
            maxLength={12}
            hint="Letters and digits, e.g. R01"
            onChange={(event) => setCode(event.target.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase())}
          />
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

/** Copies the exact string the user can see. "Copied" is only for a successful write. */
async function copyVisible(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // The page may be denied clipboard permission. Fall through to the older command.
  }
  try {
    const area = document.createElement("textarea");
    area.value = value;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

function ActivationModal({
  device,
  activation,
  stores,
  onClose,
}: {
  device: Device;
  activation: DeviceActivationKey;
  stores: ReturnType<typeof useStores>["stores"];
  onClose: () => void;
}) {
  const { t } = useLocale();
  const { profile } = useCapabilities();
  const reduced = useReducedMotion() === true;
  const titleId = useId();
  const label = businessCodeLabel(profile);
  const [visible, setVisible] = useState(true);
  const [businessCode, setBusinessCode] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "key" | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);
  const expired = new Date(activation.expires_at).getTime() <= Date.now();
  const mismatched = activation.device_id !== device.id;
  const foreignBranch = stores.length > 0 && !stores.some((store) => store.id === device.store_id);
  const keyBlocked = mismatched || foreignBranch || expired;
  const close = () => {
    if (reduced) onClose();
    else setVisible(false);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (reduced) onClose();
      else setVisible(false);
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose, reduced]);

  useEffect(() => {
    let live = true;
    apiGet<BusinessSettings>("/api/v1/settings")
      .then((row) => {
        if (!live) return;
        const saved = activationBusinessCode(row.store_code);
        if (saved === null) setLoadError(businessCodePhrase(profile, "missing"));
        else setBusinessCode(saved);
      })
      .catch(() => {
        if (live) setLoadError(businessCodePhrase(profile, "missing"));
      });
    return () => {
      live = false;
    };
  }, [profile]);

  const copy = (kind: "code" | "key", value: string) => {
    setCopied(null);
    setCopyError(null);
    void copyVisible(value).then((ok) => {
      if (ok) setCopied(kind);
      else setCopyError(kind === "code" ? businessCodePhrase(profile, "copyFailed") : businessCodePhrase(profile, "keyCopyFailed"));
    });
  };

  const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];
  return (
    <AnimatePresence onExitComplete={onClose}>
      {visible ? (
        <motion.div
          key="activation"
          className="fixed inset-0 z-50 flex items-center justify-center bg-charcoal/40 p-3 backdrop-blur-[8px] sm:p-4"
          role="presentation"
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduced ? undefined : { opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.18 }}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="flex max-h-[min(90dvh,34rem)] w-full max-w-md flex-col overflow-hidden rounded-3xl border border-gray-100 bg-white shadow-2xl dark:border-gray-800 dark:bg-[#222026]"
            initial={reduced ? false : { opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? undefined : { opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: reduced ? 0 : 0.22, ease }}
          >
            <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
              <div className="min-w-0">
                <h2 id={titleId} className="text-lg font-semibold">
                  {t("Activate {code}", { code: device.code })}
                </h2>
                <p className="mt-0.5 text-xs leading-5 text-charcoal/60">{t(businessCodePhrase(profile, "activateHint"))}</p>
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={close}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/70 hover:bg-gray-100"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="min-h-0 overflow-y-auto px-4 py-3 sm:px-5">
              <dl className="space-y-3">
                <div className="rounded-2xl bg-surface px-3 py-2.5 sm:px-4">
                  <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">{t(label)}</dt>
                  <dd className="mt-1 flex items-center justify-between gap-3">
                    <span className="min-w-0 break-all font-mono text-base font-semibold tracking-tight sm:text-lg">
                      {loadError ? t(loadError) : businessCode ?? t("Loading…")}
                    </span>
                    <CopyChip
                      copied={copied === "code"}
                      label={copied === "code" ? t(businessCodePhrase(profile, "copied")) : t(businessCodePhrase(profile, "copy"))}
                      disabled={businessCode === null || loadError !== null}
                      onClick={() => businessCode && copy("code", businessCode)}
                    />
                  </dd>
                </div>
                <div className="rounded-2xl bg-charcoal px-3 py-2.5 text-white sm:px-4">
                  <dt className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-white/50">
                    <KeyRound size={14} aria-hidden="true" /> {t("Activation key")}
                  </dt>
                  <dd className="mt-1 flex items-center justify-between gap-3">
                    <span className="min-w-0 break-all font-mono text-lg font-semibold tracking-[0.08em] sm:text-xl sm:tracking-[0.12em]">
                      {mismatched || foreignBranch ? "—" : activation.activation_key}
                    </span>
                    <CopyChip
                      tone="dark"
                      copied={copied === "key"}
                      label={copied === "key" ? t(businessCodePhrase(profile, "copied")) : t(businessCodePhrase(profile, "copy"))}
                      disabled={keyBlocked}
                      onClick={() => {
                        if (!keyBlocked) copy("key", activation.activation_key);
                      }}
                    />
                  </dd>
                </div>
              </dl>
              {mismatched ? <p className="mt-2 text-sm text-danger">{t("This key does not belong to this register.")}</p> : null}
              {foreignBranch ? <p className="mt-2 text-sm text-danger">{t("This register is not in the selected branch.")}</p> : null}
              {expired ? <p className="mt-2 text-sm text-danger">{t(businessCodePhrase(profile, "expired"))}</p> : null}
              {copyError ? <p className="mt-2 text-sm text-danger" role="alert">{t(copyError)}</p> : null}
              <p className="mt-3 text-xs leading-5 text-charcoal/60 sm:text-sm">
                {t("Valid until {when}. The key works once. Generating a new key cancels this one.", {
                  when: formatDate(activation.expires_at),
                })}
              </p>
            </div>
            <footer className="flex items-center justify-end border-t border-line px-4 py-3 sm:px-5">
              <PrimaryButton onClick={close} className="h-11 min-w-[7.5rem]">
                {t("Done")}
              </PrimaryButton>
            </footer>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

function CopyChip({
  label,
  copied,
  disabled,
  onClick,
  tone = "light",
}: {
  label: string;
  copied: boolean;
  disabled?: boolean;
  onClick: () => void;
  tone?: "light" | "dark";
}) {
  const reduced = useReducedMotion() === true;
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      whileTap={reduced || disabled ? undefined : { scale: 0.98 }}
      className={`inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-semibold disabled:opacity-40 ${
        tone === "dark"
          ? "bg-white/10 text-white hover:bg-white/15"
          : `border border-line bg-white ${actionHoverClass("neutral")}`
      }`}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={copied ? "copied" : "copy"}
          className="inline-flex items-center gap-1.5"
          initial={reduced ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduced ? undefined : { opacity: 0, y: -4 }}
          transition={{ duration: reduced ? 0 : 0.18 }}
        >
          {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
          {label}
        </motion.span>
      </AnimatePresence>
    </motion.button>
  );
}

function KeyModal({ issued, onClose }: { issued: DeviceKey; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  return (
    <Modal
      title={`Key for ${issued.device.code}`}
      subtitle="Copy it now. It cannot be shown again."
      onClose={onClose}
      footer={<PrimaryButton onClick={onClose}>Done</PrimaryButton>}
    >
      <div className="rounded-2xl bg-charcoal p-4 text-white">
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/50">
          <KeyRound size={14} aria-hidden="true" /> DEVICE_KEY
        </p>
        <p className="mt-2 flex items-center justify-between gap-3">
          <span className="min-w-0 break-all font-mono text-sm">{issued.key}</span>
          <button
            type="button"
            onClick={() => {
              setCopied(false);
              setCopyError(null);
              void copyVisible(issued.key).then((ok) => {
                if (ok) setCopied(true);
                else setCopyError("Could not copy the key. Select it and copy it manually.");
              });
            }}
            aria-label={copied ? "Copied" : "Copy key"}
            title={copied ? "Copied" : "Copy key"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white/80 hover:bg-white/10"
          >
            {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
          </button>
        </p>
      </div>
      {copyError ? <p className="mt-2 text-sm text-danger">{copyError}</p> : null}
      <p className="mt-4 text-sm text-charcoal/60">
        Invoices from this till are numbered <span className="font-mono">{issued.device.invoice_prefix}-000001</span> onward.
      </p>
    </Modal>
  );
}
