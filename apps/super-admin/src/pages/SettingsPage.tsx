import { Mail, MessageCircle, type LucideIcon } from "lucide-react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

const sections: { to: string; label: string; hint: string; icon: LucideIcon }[] = [
  { to: "/settings/landing", label: "Landing", hint: "WhatsApp button on the public site", icon: MessageCircle },
  { to: "/settings/email", label: "Email", hint: "Outgoing mailbox for password resets", icon: Mail },
];

/** Landing and email live here, listed the same way catalog categories are. */
export function SettingsPage() {
  const { pathname } = useLocation();
  if (pathname === "/settings") return <Navigate to="/settings/landing" replace />;

  return (
    <section className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="h-fit rounded-card bg-charcoal p-5 text-white">
        <h2 className="mb-4 text-lg font-semibold">Settings</h2>
        <ul className="space-y-2">
          {sections.map((section) => (
            <li key={section.to}>
              <NavLink
                to={section.to}
                className={({ isActive }) =>
                  `block w-full rounded-2xl p-3 text-left transition ${isActive ? "bg-accent" : "bg-white/5 hover:bg-white/10"}`
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="flex items-center gap-2 font-medium">
                      <section.icon size={16} aria-hidden="true" />
                      {section.label}
                    </span>
                    <span className={`mt-1 block text-xs ${isActive ? "text-white/80" : "text-white/50"}`}>{section.hint}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </aside>
      <div className="min-w-0">
        <Outlet />
      </div>
    </section>
  );
}
