import type { VoidPolicy } from "@ai-pos/shared-types";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toggle } from "../../components/ui/Toggle";
import { ChoiceList } from "./policyFields";

/** Void, waste, and prepaid-refund rules for restaurants, cafes, and quick service. */
export function RestaurantVoidPolicySettings({
  policy,
  onChange,
}: {
  policy: VoidPolicy;
  onChange: (policy: VoidPolicy) => void;
}) {
  return (
    <section id="void-policy" className="space-y-4 rounded-2xl border border-line p-4 lg:col-span-2">
      <div>
        <h3 className="font-semibold">Void, cancellation & waste</h3>
        <p className="text-sm text-charcoal/60">
          What happens when a ticket is cancelled after the kitchen has it, and how a prepaid table or online order is refunded.
        </p>
      </div>
      <Toggle
        checked={policy.manager_pin_after_dispatch}
        onChange={(manager_pin_after_dispatch) => onChange({ ...policy, manager_pin_after_dispatch })}
        label="Manager PIN after kitchen dispatch"
        description="A manager approves order cancellations once the kitchen has the ticket."
      />
      <div>
        <p className="mb-2 text-sm font-medium">Cancelled food and drink</p>
        <SegmentedControl
          label="Cancelled stock"
          value={policy.cancelled_stock}
          options={[
            { value: "wasted", label: "Wasted / scrapped" },
            { value: "restock", label: "Returned to unopened bar stock" },
          ]}
          onChange={(cancelled_stock) => onChange({ ...policy, cancelled_stock })}
        />
      </div>
      <ChoiceList
        title="Void reason codes"
        items={policy.reasons}
        locked={() => false}
        onChange={(reasons) => onChange({ ...policy, reasons })}
      />
      <div>
        <p className="mb-2 text-sm font-medium">Prepaid table and online orders</p>
        <SegmentedControl
          label="Prepaid refund"
          value={policy.prepaid_refund}
          options={[
            { value: "original", label: "Cash or card refund" },
            { value: "voucher", label: "Store voucher" },
          ]}
          onChange={(prepaid_refund) => onChange({ ...policy, prepaid_refund })}
        />
      </div>
    </section>
  );
}
