import { useEffect, useState } from "react";

interface DemoUser {
  username: string;
  full_name: string;
  role: string;
  pin: string | null;
  has_pos_access: boolean;
}

interface DemoFile {
  roles: { name: string; permissions: string[] }[];
  users: DemoUser[];
}

/** Dev builds with VITE_SHOW_DEMO_ACCOUNTS=true only; release bundles never include the demo file. */
export const demoCashiersEnabled = import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true";

export function DemoCashiers({ onPick }: { onPick: (username: string, pin: string) => void }) {
  const [demo, setDemo] = useState<DemoFile | null>(null);

  useEffect(() => {
    if (import.meta.env.DEV && import.meta.env.VITE_SHOW_DEMO_ACCOUNTS === "true") {
      void import("@ai-pos/catalog/demo-users.json").then((module) => setDemo(module.default as DemoFile));
    }
  }, []);

  if (demo === null) return null;
  const permissionsFor = new Map(demo.roles.map((role) => [role.name, role.permissions]));
  const cashiers = demo.users.filter((user) => user.has_pos_access && user.pin !== null);

  return (
    <section className="mt-8 w-full max-w-3xl" aria-label="Demo cashiers">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white/80">Demo cashiers</h2>
        <span className="rounded-full bg-primary/20 px-3 py-1 text-[11px] font-semibold text-primary">Development only</span>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {cashiers.map((user) => (
          <li key={user.username}>
            <button
              type="button"
              onClick={() => user.pin && onPick(user.username, user.pin)}
              className="flex h-full w-full flex-col justify-start rounded-2xl bg-white/5 p-4 text-left transition hover:bg-white/10"
            >
              <span className="flex items-baseline justify-between gap-2">
                <span className="font-medium">{user.full_name}</span>
                <span className="text-xs text-white/50">{user.role}</span>
              </span>
              <span className="mt-1 block font-mono text-xs text-white/70">
                {user.username} · PIN {user.pin}
              </span>
              <span className="mt-2 flex flex-wrap gap-1">
                {(permissionsFor.get(user.role) ?? []).map((permission) => (
                  <span key={permission} className="rounded-full bg-white/10 px-2 py-0.5 font-mono text-[10px] text-white/70">
                    {permission}
                  </span>
                ))}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-white/40">Super Admin: username admin, PIN is ADMIN_PIN in the repo-root .env.</p>
    </section>
  );
}
