# O8.2 native Windows acceptance

Status: **NOT RUN**.

No Tauri process was started. No executable path, process id, process identity, window handle, or test data directory was recorded. The installed `com.aipos.desktop` register was not opened. No global mouse or keyboard input was sent.

## Why it was not run

Scenarios A through D need a dedicated acceptance identity and input that cannot land on another window. This run did not build or launch that acceptance binary. Browser preview, Rust library tests, and Vitest do not stand in for the native window.

The WebView blank-surface defect is unchanged. It was not reproduced in this run, and it was not cleared. A reload that restores a screen would not close it. It remains a native acceptance blocker.

| Scenario | Status |
| --- | --- |
| A. Startup, terminal identity, entitlement, unlock, profile, sidebar | NOT RUN |
| B. Bootstrap, allocation, disconnect, cash sale, restart without network | NOT RUN |
| C. Reconnect, pull, push, idempotency, second terminal, rejected staff | NOT RUN |
| D. Route render, error boundary, move, occlusion, minimize, focus, reload, restart, navigation | NOT RUN |

Desktop library tests in this run do not change this status. See `O8-FINAL-ACCEPTANCE-REPORT.md` for that count.
