# Model Changes (Planned and Recorded)

This file records planned, in-progress, and completed model changes for the Copilot/AI runtime used by sessions operating on this repository.

- Audit log file: `copilot_runtime_audit.json` (contains runtime notices/events)

---

## Change: model-switch-2026-08-15-01
- id: model-switch-2026-08-15-01
- from_model: mai-code-1.1-flash
- to_model: gpt-5-mini
- reported_at: 2026-08-15T05:57:45.075-07:00
- recorded_at: 2026-08-15T05:59:10-07:00
- status: recorded
- owner: Copilot (session: copilotcli:/13bf663c-7ffd-4b3b-bdce-804108283663)
- rationale: Runtime model update for improved general capability; reported by environment.
- notes:
  - A corresponding audit entry was written to `copilot_runtime_audit.json`.
  - If this change requires follow-up (tests, validation runs), add a new entry with the status `planned` and assign an owner.

---

## How to use this file
- Add a new section for each planned or executed model change.
- Use a stable `id` prefix like `model-switch-YYYY-MM-DD-n`.
- Fields:
  - `from_model`, `to_model`
  - `reported_at` (when the runtime reported the switch)
  - `planned_date` (if a future/planned change)
  - `status` (planned | in-progress | recorded | validated | reverted)
  - `owner` (person or automation responsible)
  - `rationale`, `notes`

---

## Planned changes
(Empty — add entries here when planning future switches.)

---

## Validation checklist (for each recorded change)
- [ ] Run full test suite (if available)
- [ ] Smoke test critical automation flows
- [ ] Ensure session-specific audit entries exist

---

File created by Copilot on user request; see `copilot_runtime_audit.json` for original runtime notice(s).
