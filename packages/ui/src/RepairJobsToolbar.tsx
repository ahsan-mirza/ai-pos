import type { ReactNode } from "react";
import { TableToolbar, type TableFilter } from "./FilterDrawer";
import type { SelectOption } from "./Select";

export interface RepairJobsToolbarProps {
  search: string;
  onSearch: (value: string) => void;
  status: string;
  onStatus: (value: string) => void;
  statusOptions: readonly SelectOption[];
  /** Value restored by Clear all. Defaults to an empty status. */
  statusCleared?: string;
  type?: string;
  onType?: (value: string) => void;
  typeOptions?: readonly SelectOption[];
  from?: string;
  to?: string;
  onFrom?: (value: string) => void;
  onTo?: (value: string) => void;
  technician?: string;
  onTechnician?: (value: string) => void;
  technicianOptions?: readonly SelectOption[];
  warranty?: boolean;
  onWarranty?: (value: boolean) => void;
  /** Extra drawer content that is not one of the filters above. */
  more?: ReactNode;
  onClear?: () => void;
  clearVisible?: boolean;
  moreActive?: boolean;
  action?: ReactNode;
}

/** Search stays visible. Status, type, dates, technician and warranty open in the shared filter drawer. */
export function RepairJobsToolbar({
  search,
  onSearch,
  status,
  onStatus,
  statusOptions,
  statusCleared = "",
  type,
  onType,
  typeOptions,
  from,
  to,
  onFrom,
  onTo,
  technician,
  onTechnician,
  technicianOptions,
  warranty = false,
  onWarranty,
  more,
  onClear,
  action,
}: RepairJobsToolbarProps) {
  const filters: TableFilter[] = [
    {
      id: "status",
      label: "Status",
      value: status,
      clearedValue: statusCleared,
      onChange: onStatus,
      options: statusOptions,
    },
  ];
  if (typeOptions != null && onType != null && type != null) {
    filters.push({ id: "type", label: "Repair type", value: type, onChange: onType, options: typeOptions });
  }
  if (onFrom != null && onTo != null) {
    filters.push({ id: "from", label: "Received from", kind: "date", value: from ?? "", onChange: onFrom });
    filters.push({ id: "to", label: "Received to", kind: "date", value: to ?? "", onChange: onTo });
  }
  if (technicianOptions != null && onTechnician != null && technician != null) {
    filters.push({
      id: "technician",
      label: "Technician",
      value: technician,
      onChange: onTechnician,
      options: technicianOptions,
    });
  }
  if (onWarranty) {
    filters.push({
      id: "warranty",
      label: "Warranty repair",
      kind: "toggle",
      value: warranty ? "true" : "false",
      clearedValue: "false",
      onChange: (value) => onWarranty(value === "true"),
    });
  }

  return (
    <TableToolbar
      search={{ value: search, onChange: onSearch, label: "Search repair jobs", placeholder: "Search repairs..." }}
      filters={filters}
      extra={more}
      actions={action}
      onClearAll={onClear}
    />
  );
}
