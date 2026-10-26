import { useEffect, useState } from "react";
type Row = Record<string, any>;
export function Ledger({
  load,
  tick,
}: {
  load: (path: string) => Promise<any>;
  tick: number;
}) {
  const [items, setItems] = useState<Row[]>([]),
    [people, setPeople] = useState<Row[]>([]),
    [transactions, setTransactions] = useState<Row[]>([]),
    [checks, setChecks] = useState<Row[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      load("inventory"),
      load("ledger"),
      load("reconciliations"),
      load("personnel"),
    ])
      .then(([i, t, r, p]) => {
        if (active) {
          setItems(i);
          setTransactions(t);
          setChecks(r);
          setPeople(p);
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      active = false;
    };
  }, [tick]);
  const table = (rows: Row[], fields: string[]) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {fields.map((f) => (
              <th key={f}>
                {(
                  {
                    ts: "Time",
                    due_ts: "Due",
                    holder_id: "Holder",
                    personnel_id: "Worker",
                    item_id: "Item",
                    reader: "Reader #",
                  } as Row
                )[f] || f.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {fields.map((f) => (
                <td key={f}>
                  {r[f] == null
                    ? "—"
                    : ["ts", "due_ts"].includes(f)
                      ? new Date(r[f] * 1000).toLocaleString()
                      : ["holder_id", "personnel_id"].includes(f)
                        ? people.find((p) => p.id === r[f])?.name || `#${r[f]}`
                        : f === "item_id"
                          ? items.find((i) => i.id === r[f])?.name || `#${r[f]}`
                          : f === "reader"
                            ? String(r[f] + 1)
                            : String(r[f] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p>No records yet.</p>}
    </div>
  );
  return (
    <>
      <section className="panel">
        <h2>Items and current holders</h2>
        <p>
          Badge on reader #1, then item on reader #2. The first permitted item
          tap issues it; a later tap returns it. A return by another worker is
          recorded.
        </p>
        {error && <p role="alert">{error}</p>}
        {table(items, [
          "id",
          "name",
          "status",
          "holder_id",
          "due_ts",
          "min_level",
        ])}
      </section>
      <section className="panel">
        <h2>Issue / return history</h2>
        <a href="/api/ledger.csv">Download CSV (latest 10,000 records)</a>
        {table(transactions, [
          "id",
          "ts",
          "kind",
          "personnel_id",
          "item_id",
          "reader",
          "note",
        ])}
      </section>
      <section className="panel">
        <h2>Declared versus observed</h2>
        {table(checks, [
          "id",
          "ts",
          "slot_id",
          "item_id",
          "verdict",
          "tx_id",
          "delta_ms",
          "incident_id",
        ])}
      </section>
    </>
  );
}
