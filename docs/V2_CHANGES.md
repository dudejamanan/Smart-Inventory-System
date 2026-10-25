# v2 audit and checkpoint plan

Baseline: v1.0 at a1a9f1d. On 2026-10-25, `python -m pytest -q` in the Python 3.11 venv: **28 passed, 1 warning in 46.63 s**. No baseline behavior was changed for M0. The v1 reference is preserved by tag v1.0; ongoing work is on branch v2.

The supplied CODEX_PROMPT_v2 is useful: its F1–F7 correctly identify limits of a single worker/session, UID-only personnel, session-lenient shelf removals, PC-only authentication, empty-reference vision, and sandbox-only notifications. Its M2 checkpoint is deliberate. **This delivery stops after M2**; it does not claim to implement the ledger/reconciliation/Telegram/anchor/UI requirements of M3–M8.

## Milestones

- M0: audit, baseline, tag/branch, this plan.
- M1: strict v2 protocol, clock-driven v2 simulator, fixed-buffer firmware core, result feedback, prewarning/dead-man, button, telemetry, watchdog and four compile variants; retain explicit v1 regression coverage.
- M2: atomic validated EEPROM whitelist, offline badge/item decisions, bounded replay with durable deduplication, backend synchronization, hardware tools, checkpoint guide and actual verification report. Stop for physical flashing/testing.
- M3 onward: multiple TTL sessions, real item registry/ledger and clearances; strict reconciliation; Telegram; reveal/rectified vision; optional people detection; modular dashboard. Not part of this checkpoint.

## Integration boundary

The M2 application uses v2 wire messages but retains the v1 single-session, session-lenient PC policy until M3/M4. The board itself has no BUSY or local online session toggle. An adapter maps PC badge decisions to result codes and mirrors successful FB results into the existing DB. Item issuing through the online UI is deliberately unavailable until the ledger exists. Offline item levels can be validated with the conformance tool's explicitly disposable fixtures, not mistaken for an audited inventory ledger.

## Design constraints to resolve in code

1. 100 entries need 500 bytes of staging RAM if EEPROM is untouched until END. Share that staging buffer with the offline replay ring; reject whitelist replacement until pending replay is acknowledged, and abort staging if the PC disappears. This preserves the last valid EEPROM image and keeps global RAM within 1100 B even with two readers.
2. CRC16-CCITT-FALSE covers version, count and little-endian hash/flag bytes. FNV-1a hashes uppercase UID characters. Hash collisions are refused during synchronization; hashes are identifiers, not authentication secrets.
3. EEPROM magic is invalidated before commit and written last. Interrupted commits fail closed on next boot. A separate wear-conscious persistent boot counter makes replay deduplication unambiguous across boots. RAM events cannot survive physical power loss; a full ring fails closed rather than overwriting unacknowledged events.
4. One global PW timer represents the earliest unresolved grace deadline; M4 must aggregate pending removals rather than extending the deadline with each new removal. DEADMAN is a single alarm reason with the SHELF_BREACH pattern, not two duplicate alarm events.
5. Firmware below 2.0 is incompatible and is denied online authentication by the v2 app, with a clear banner. Use the v1.0 tag when retaining old firmware.

See DECISIONS for detailed choices and V2_VERIFICATION for the completed checkpoint results.
