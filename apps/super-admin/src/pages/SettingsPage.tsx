import { Mail, MessageCircle, Users, type LucideIcon } from "lucide-react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../lib/session";

/** WhatsApp, email, and console users live here, listed the same way catalog categories are. */
export function SettingsPage() {
  const { pathname } = useLocation();
  const { operator } = useSession();
  const groups: { title: string; sections: { to: string; label: string; hint: string; icon: LucideIcon }[] }[] = [
    {
      title: "Contact & Communication",
      sections: [
        {
          to: "/settings/whatsapp",
          label: "WhatsApp Sales Contact",
          hint: "Footer number, email, and the chat button",
          icon: MessageCircle,
        },
        { to: "/settings/email", label: "Email", hint: "Outgoing mailbox for password resets", icon: Mail },
      ],
    },
  ];
  if (operator?.role === "ADMIN") {
    groups.push({
      title: "Access",
      sections: [{ to: "/settings/users", label: "Users", hint: "Console operators and their roles", icon: Users }],
    });
  }
  if (pathname === "/settings" || pathname === "/settings/landing") return <Navigate to="/settings/whatsapp" replace />;

  return (
    <section className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="h-fit rounded-card bg-charcoal p-5 text-white">
        <h2 className="mb-4 text-lg font-semibold">Settings</h2>
        {groups.map((group) => (
          <div key={group.title}>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/50">{group.title}</p>
            <ul className="space-y-2">
              {group.sections.map((section) => (
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
                        <span className={`mt-1 block text-xs ${isActive ? "text-white/80" : "text-white/50"}`}>
                          {section.hint}
                        </span>
                      </>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>
      <div className="min-w-0">
        <Outlet />
      </div>
    </section>
  );
}
