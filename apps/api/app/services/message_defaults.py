"""Default message templates, shared by the migration seed and the service's lazy seeding."""

DEFAULT_TEMPLATES: dict[str, tuple[str, str, str]] = {
    "receipt": (
        "Digital receipt",
        "Your receipt {{invoice}}",
        "Thank you for shopping at {{store}}. Invoice {{invoice}}, total {{total}}. "
        "Keep this for returns and warranty.",
    ),
    "statement": (
        "Statement of account",
        "Statement of account, {{customer}}",
        "Dear {{customer}}, your balance with {{business}} is {{balance}} ({{overdue}} overdue). "
        "Please contact us with any questions.",
    ),
    "overdue_reminder": (
        "Overdue reminder",
        "Payment reminder: {{overdue}} overdue",
        "Dear {{customer}}, invoices totalling {{overdue}} are past due (oldest {{days}} days). "
        "Kindly arrange payment. Thank you, {{business}}.",
    ),
    "warranty_expiry": (
        "Warranty expiring",
        "Your warranty ends on {{expires}}",
        "Hi {{customer}}, the warranty on your {{product}} ({{serial}}) ends on {{expires}}. "
        "Ask us about extended cover.",
    ),
    "repair_ready": (
        "Repair ready",
        "Your device is ready",
        "Hi {{customer}}, your {{device}} (ticket {{ticket}}) is ready for collection at {{store}}.",
    ),
    "repair_estimate": (
        "Repair estimate",
        "Approve the repair of your {{device}}",
        "Hi {{customer}}, the repair of your {{device}} (ticket {{ticket}}) at {{store}} comes to {{amount}}. "
        "Approve or decline here: {{link}}",
    ),
    "layaway_reminder": (
        "Layaway reminder",
        "Layaway {{number}} reminder",
        "Hi {{customer}}, {{balance}} is left on layaway {{number}}; goods are held until {{expires}}.",
    ),
    "reorder_due": (
        "Scheduled reorder",
        "Your scheduled reorder is due",
        "Your scheduled reorder for {{plan}} is due on {{date}}. Please confirm your usual order.",
    ),
    "coupon_issued": (
        "Your offer",
        "A code for you: {{code}}",
        "Hi {{customer}}, {{offer}} is ready. Use code {{code}} at the till. {{reason}}.",
    ),
}

DEFAULT_EVENTS: dict[str, bool] = {
    "receipt": False,
    "statement": True,
    "overdue_reminder": True,
    "warranty_expiry": True,
    "repair_ready": True,
    "repair_estimate": True,
    "layaway_reminder": True,
    "reorder_due": True,
    "coupon_issued": True,
}
