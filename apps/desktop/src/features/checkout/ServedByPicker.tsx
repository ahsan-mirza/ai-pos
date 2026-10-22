import { UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { staffApi, type RegisterStaff } from "../../lib/retailClient";
import type { SalesAssociate } from "./cart";

interface ServedByPickerProps {
  storeId: string;
  cashierId: string;
  cashierName: string;
  associate: SalesAssociate | null;
  disabled: boolean;
  onChange: (associate: SalesAssociate | null) => void;
}

/** "Served by": names the stylist who helped the customer so commissions credit them, not the cashier. */
export function ServedByPicker({ storeId, cashierId, cashierName, associate, disabled, onChange }: ServedByPickerProps) {
  const [staff, setStaff] = useState<RegisterStaff[]>([]);

  useEffect(() => {
    let cancelled = false;
    staffApi
      .list(storeId)
      .then((rows) => {
        if (!cancelled) setStaff(rows);
      })
      .catch(() => {
        if (!cancelled) setStaff([]);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId]);

  const others = staff.filter((member) => member.id !== cashierId);
  if (others.length === 0 && associate === null) return null;
  return (
    <label className="flex items-center gap-2 px-4 pb-2 text-xs text-zinc-500 dark:text-white/50">
      <UserRound size={14} aria-hidden="true" className="shrink-0" />
      <span className="shrink-0 font-semibold uppercase tracking-wider">Served by</span>
      <select
        aria-label="Served by"
        disabled={disabled}
        value={associate?.id ?? ""}
        onChange={(event) => {
          const member = staff.find((row) => row.id === event.target.value);
          onChange(member ? { id: member.id, name: member.full_name } : null);
        }}
        className="h-8 min-w-0 flex-1 rounded-full border border-zinc-200 bg-white px-3 text-xs font-medium text-zinc-900 focus:border-primary focus:outline-none dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-white"
      >
        <option value="">{cashierName} (cashier)</option>
        {others.map((member) => (
          <option key={member.id} value={member.id}>
            {member.full_name}
            {member.role_name ? ` · ${member.role_name}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
