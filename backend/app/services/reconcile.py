"""RAM-only declared/observed rules. Callers hold the authorization lock.

Commands are sent before queued persistence. The UNO owns the final grace deadline.
"""


class Reconciler:
    def __init__(self, config, send, emit, clock):
        self.c, self.send, self.emit, self.clock = config, send, emit, clock
        self.tokens = {}
        self.pending = {}
        self.returns = {}
        self.present = {}
        self.armed = None

    def prewarn(self):
        deadlines = [
            p["deadline"] for p in self.pending.values() if p["mode"] == "removal"
        ]
        earliest = min(deadlines) if deadlines else None
        if earliest == self.armed:
            return
        if self.armed is not None:
            self.send({"t": "PW", "on": 0})
        self.armed = earliest
        if earliest is not None:
            import math

            self.send(
                {"t": "PW", "on": 1, "s": max(1, math.ceil(earliest - self.clock()))}
            )

    def result(self, slot, verdict, observed, tx=None, alarm=False, warning=False):
        if alarm:
            self.send({"t": "ALARM", "on": 1, "why": "SHELF_BREACH"})
        self.emit(
            "reconcile",
            {
                "slot_id": slot["id"],
                "item_id": slot.get("item_id"),
                "verdict": verdict,
                "observed_ts": observed,
                "tx_token": tx.get("token") if tx else None,
                "delta_ms": round((tx["ts"] - observed) * 1000) if tx else None,
                "alarm": alarm,
                "warning": warning,
                "inside": slot.get("inside", []),
            },
        )

    def observed(self, slot, old, new, has_session):
        now = self.clock()
        sid, item = slot["id"], slot.get("item_id")
        if new not in {"ABSENT", "PRESENT"}:
            return
        previous = self.present.get(sid)
        self.present[sid] = new
        if previous == new:
            return
        if new == "ABSENT":
            tx = self.tokens.get(item)
            if tx and 0 <= now - tx["ts"] <= self.c.issue_token_ttl_s:
                self.tokens.pop(item)
                if tx["kind"] == "ISSUE":
                    self.result(slot, "MATCHED", now, tx)
                    return
                if tx["kind"] == "DENIED":
                    self.result(slot, "DENIED_REMOVAL", now, tx, alarm=True)
                    return
            if not has_session:
                self.result(slot, "NO_SESSION", now, alarm=True)
            else:
                self.pending[sid] = dict(
                    slot=slot,
                    observed=now,
                    deadline=now + self.c.removal_grace_s,
                    mode="removal",
                )
                self.prewarn()
        else:
            # Replacing an undeclared item does not erase the pending removal.
            ret = self.returns.pop(item, None)
            if ret:
                self.result(slot, "RETURN_MATCHED", now, ret)
            elif old == "ABSENT" and slot.get("issued"):
                self.pending[-sid] = dict(
                    slot=slot,
                    observed=now,
                    deadline=now + self.c.return_grace_s,
                    mode="unscanned_return",
                )

    def declared(self, tx, slots):
        item, now = tx["item_id"], self.clock()
        if tx["kind"] in {"ISSUE", "DENIED"}:
            candidates = [
                (sid, p)
                for sid, p in self.pending.items()
                if p["mode"] == "removal" and p["slot"].get("item_id") == item
            ]
            if candidates:
                sid, p = min(candidates, key=lambda pair: pair[1]["observed"])
                if tx["kind"] == "ISSUE" and now <= p["deadline"]:
                    self.pending.pop(sid)
                    self.result(p["slot"], "LATE_MATCH", p["observed"], tx)
                elif tx["kind"] == "DENIED":
                    self.pending.pop(sid)
                    self.result(
                        p["slot"], "DENIED_REMOVAL", p["observed"], tx, alarm=True
                    )
                else:
                    # A late declaration cannot authorize a second removal.
                    self.tick()
                self.prewarn()
            else:
                self.tokens[item] = tx
        elif tx["kind"] in {"RETURN", "RETURN_OTHER"}:
            self.tokens.pop(item, None)
            for sid, p in list(self.pending.items()):
                if p["mode"] == "unscanned_return" and p["slot"].get("item_id") == item:
                    self.pending.pop(sid)
                    self.result(p["slot"], "RETURN_MATCHED", p["observed"], tx)
                    return
            slot = next((s for s in slots.values() if s.get("item_id") == item), None)
            if slot and self.present.get(slot["id"]) == "PRESENT":
                self.result(slot, "RETURN_MATCHED", now, tx)
            elif slot:
                self.returns[item] = tx | {
                    "deadline": now + self.c.return_place_s,
                    "slot": slot,
                }

    def tick(self):
        now = self.clock()
        for sid, p in list(self.pending.items()):
            if now >= p["deadline"]:
                self.pending.pop(sid)
                self.result(
                    p["slot"],
                    "UNISSUED" if p["mode"] == "removal" else "RETURN_UNSCANNED",
                    p["observed"],
                    alarm=p["mode"] == "removal",
                    warning=p["mode"] != "removal",
                )
        for item, tx in list(self.returns.items()):
            if now >= tx["deadline"]:
                self.returns.pop(item)
                self.result(
                    tx["slot"], "RETURN_NOT_OBSERVED", tx["ts"], tx, warning=True
                )
        self.tokens = {
            i: t
            for i, t in self.tokens.items()
            if now - t["ts"] <= self.c.issue_token_ttl_s
        }
        self.prewarn()
