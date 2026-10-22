import { useEffect, useState } from "react";
import { env } from "../../config/env";

interface DemoRole {
  name: string;
  permissions: string[];
}

interface DemoUser {
  username: string;
  full_name: string;
  role: string;
  store_id: string | null;
  password: string | null;
  pin: string | null;
  has_portal_access: boolean;
  has_pos_access: boolean;
}

interface DemoFile {
  roles: DemoRole[];
  users: DemoUser[];
}

/** The demo users are seeded into the default store only: plain localhost, or its own subdomain. Other stores
 * (self-service signups) have just their owner, so the cards would never sign in there. */
const onDemoStore =
  !env.onTenantHost ||
  env.tenantDomain?.split(".")[0] === (import.meta.env.VITE_DEFAULT_TENANT?.trim().split(".")[0] || "demo");

/** Dev builds with VITE_SHOW_DEMO_ACCOUNTS=true only; production bundles never include the demo file. */
export const demoAccountsEnabled =
  import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true" && onDemoStore;

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function DemoAccounts({ onPick }: { onPick: (username: string, password: string) => void }) {
  const [demo, setDemo] = useState<DemoFile | null>(null);

  useEffect(() => {
    if (import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true") {
      void import("@ai-pos/catalog/demo-users.json").then((module) => setDemo(module.default as DemoFile));
    }
  }, []);

  if (demo === null) return null;
  const adminUsername = import.meta.env.VITE_DEMO_ADMIN_USERNAME?.trim() || "admin";
  const adminPassword = import.meta.env.VITE_DEMO_ADMIN_PASSWORD?.trim() || null;
  const permissionsFor = new Map(demo.roles.map((role) => [role.name, role.permissions]));
  const users = [...demo.users].sort((a, b) => Number(b.has_portal_access) - Number(a.has_portal_access));

  return (
    <section className="w-full max-w-5xl rounded-[28px] border border-line bg-white p-6" aria-label="Demo accounts">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Demo accounts</h2>
          <p className="text-sm text-charcoal/60">
            Click a portal account to fill the form. Register-only accounts unlock the cashier app with their PIN.
          </p>
        </div>
        <span className="rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold text-accent">Development only</span>
      </div>
      <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        <li>
          <button
            type="button"
            disabled={adminPassword === null}
            onClick={() => adminPassword && onPick(adminUsername, adminPassword)}
            className={`flex h-full w-full flex-col justify-start rounded-2xl bg-charcoal p-4 text-left text-white ring-accent transition ${
              adminPassword ? "hover:ring-2" : "cursor-default"
            }`}
          >
            <span className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-xs font-semibold">SA</span>
              <span>
                <span className="block font-medium">Super Admin</span>
                <span className="block text-xs text-white/60">@{adminUsername} · every permission, every store</span>
              </span>
            </span>
            {adminPassword ? (
              <span className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                <span className="text-white/50">Username</span>
                <span className="font-mono">{adminUsername}</span>
                <span className="text-white/50">Password</span>
                <span className="font-mono">••••••••</span>
              </span>
            ) : (
              <span className="mt-3 block text-xs text-white/60">
                Set <span className="font-mono">VITE_DEMO_ADMIN_PASSWORD</span> in the repo-root .env to sign in with one click.
                Password and PIN are <span className="font-mono">ADMIN_PASSWORD</span> /{" "}
                <span className="font-mono">ADMIN_PIN</span> in that same file.
              </span>
            )}
            <span className="mt-3 flex gap-1 text-[11px] font-semibold">
              <span className={`rounded-full px-2 py-0.5 ${adminPassword ? "bg-accent text-white" : "bg-white/10 text-white/40"}`}>
                Portal
              </span>
              <span className="rounded-full bg-white px-2 py-0.5 text-charcoal">POS</span>
            </span>
          </button>
        </li>
        {users.map((user) => {
          const portal = user.has_portal_access && user.password !== null;
          const permissions = permissionsFor.get(user.role) ?? [];
          return (
            <li key={user.username}>
              <button
                type="button"
                disabled={!portal}
                onClick={() => portal && user.password && onPick(user.username, user.password)}
                className={`flex h-full w-full flex-col justify-start rounded-2xl border p-4 text-left transition ${
                  portal ? "border-line hover:border-accent" : "cursor-default border-dashed border-line bg-surface"
                }`}
              >
                <span className="flex items-center gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full bg-charcoal text-xs font-semibold text-white">
                    {initials(user.full_name)}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-medium">{user.full_name}</span>
                    <span className="block text-xs text-charcoal/60">
                      {user.role} · {user.store_id ? "Downtown Flagship" : "All stores"}
                    </span>
                  </span>
                </span>
                <span className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                  <span className="text-charcoal/50">Username</span>
                  <span className="font-mono">{user.username}</span>
                  {user.password ? (
                    <>
                      <span className="text-charcoal/50">Password</span>
                      <span className="font-mono">{user.password}</span>
                    </>
                  ) : null}
                  {user.pin ? (
                    <>
                      <span className="text-charcoal/50">POS PIN</span>
                      <span className="font-mono">{user.pin}</span>
                    </>
                  ) : null}
                </span>
                <span className="mt-3 flex flex-wrap gap-1">
                  {permissions.map((permission) => (
                    <span key={permission} className="rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] text-charcoal/70">
                      {permission}
                    </span>
                  ))}
                </span>
                <span className="mt-3 flex gap-1 text-[11px] font-semibold">
                  <span className={`rounded-full px-2 py-0.5 ${portal ? "bg-accent text-white" : "bg-surface text-charcoal/40"}`}>
                    Portal
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 ${user.has_pos_access ? "bg-charcoal text-white" : "bg-surface text-charcoal/40"}`}
                  >
                    POS
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
