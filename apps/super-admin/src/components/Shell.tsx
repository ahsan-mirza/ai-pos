import { Building2, Inbox, LogOut, ShieldCheck } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../lib/session";

const links = [
  { to: "/tenants", label: "Tenants", icon: Building2 },
  { to: "/requests", label: "Change requests", icon: Inbox },
];

export function Shell() {
  const { operator, signOut } = useSession();
  return (
    <div className="min-h-screen bg-canvas text-charcoal">
      <header className="sticky top-0 z-30 border-b border-white/10 bg-charcoal text-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-6">
          <span className="flex items-center gap-2 font-semibold">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent">
              <ShieldCheck size={16} aria-hidden="true" />
            </span>
            QIOS Console
          </span>
          <nav className="flex gap-1">
            {links.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `inline-flex h-9 items-center gap-2 rounded-full px-4 text-sm font-semibold ${isActive ? "bg-white text-charcoal" : "text-white/70 hover:text-white"}`
                }
              >
                <Icon size={15} aria-hidden="true" /> {label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-white/70">
              {operator?.full_name} <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase">{operator?.role}</span>
            </span>
            <button type="button" onClick={signOut} className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-white/70 hover:bg-white/10 hover:text-white">
              <LogOut size={15} aria-hidden="true" /> Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
