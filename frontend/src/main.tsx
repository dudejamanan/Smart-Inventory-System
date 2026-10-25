import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Row = Record<string, any>;
async function api(path: string, method = "GET", body?: unknown): Promise<any> {
  const response = await fetch("/api/" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-Warehouse-Request": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let error;
    try {
      error = JSON.parse(text);
    } catch {
      throw new Error(text);
    }
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    );
  }
  return response.json();
}
const date = (ts: number) => new Date(ts * 1000).toLocaleString();
const human = (s: string) => s.replaceAll("_", " ").toLowerCase();
function Badge({ value }: { value: string }) {
  return (
    <span
      className={
        "badge " +
        (value?.includes("ABSENT") ||
        value?.includes("CRITICAL") ||
        value?.includes("OFFLINE") ||
        value?.includes("FAILED")
          ? "bad"
          : value === "PRESENT" || value === "OK" || value === "ACKNOWLEDGED"
            ? "good"
            : "")
      }
    >
      {human(value || "unknown")}
    </span>
  );
}

function App() {
  const [page, setPage] = useState("Live"),
    [signed, setSigned] = useState(false),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [status, setStatus] = useState<Row>({}),
    [incidents, setIncidents] = useState<Row[]>([]),
    [slots, setSlots] = useState<Row[]>([]),
    [detail, setDetail] = useState<Row | null>(null),
    [tick, setTick] = useState(0);
  async function refresh() {
    try {
      const [s, i, sl] = await Promise.all([
        api("status"),
        api("incidents"),
        api("slots"),
      ]);
      setStatus(s);
      setIncidents(i);
      setSlots(sl);
      setSigned(true);
    } catch (e) {
      if (String(e).includes("Sign in")) setSigned(false);
      else setError(String(e));
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    const match = location.hash.match(/^#incidents\/(\d+)$/);
    if (signed && match) {
      setPage("Incidents");
      api("incidents/" + match[1])
        .then(setDetail)
        .catch((e) => setError(String(e)));
    }
  }, [signed]);
  useEffect(() => {
    if (!signed) return;
    let ws: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout>;
    let alive = true;
    const connect = () => {
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`,
      );
      ws.onmessage = () => {
        refresh();
        setTick((t) => t + 1);
      };
      ws.onclose = () => {
        if (alive) retry = setTimeout(connect, 2000);
      };
    };
    connect();
    const timer = setInterval(refresh, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
      clearTimeout(retry);
      ws?.close();
    };
  }, [signed]);
  const act = async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
      await refresh();
      setTick((t) => t + 1);
    } catch (e) {
      setError(String(e));
    }
  };
  const acknowledge = () =>
    act(async () => {
      await api("alarm/ack", "POST");
      const open = incidents.filter(
        (i) => i.status === "OPEN" && i.severity === "CRITICAL",
      );
      for (const i of open) await api(`incidents/${i.id}/ack`, "POST");
    });
  if (!signed)
    return (
      <main className="login">
        <div className="brand-mark">W</div>
        <h1>Warehouse security</h1>
        <p>Sign in to monitor the gate and shelves.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await api("login", "POST", { password });
              await refresh();
            });
          }}
        >
          <label>
            Admin password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button>Sign in</button>
        </form>
        <p className="hint">
          Simulation without a configured password: leave the field empty.
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </main>
    );
  return (
    <div className="app">
      <aside>
        <a className="brand" href="#" onClick={() => setPage("Live")}>
          <span className="brand-mark">W</span>
          <span>
            Warehouse<small>Security console</small>
          </span>
        </a>
        <nav>
          {[
            "Live",
            "Incidents",
            "Personnel",
            "Inventory",
            "Calibration",
            "Settings",
            "System health",
          ].map((p, i) => (
            <button
              key={p}
              className={page === p ? "selected" : ""}
              onClick={() => {
                setPage(p);
                setDetail(null);
              }}
            >
              <span>{["◉", "⚑", "♙", "▦", "⌖", "⚙", "◷"][i]}</span>
              {p}
              {p === "Incidents" && (
                <b>{incidents.filter((i) => i.status === "OPEN").length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="aside-bottom">
          <i className={status.serial?.connected ? "dot" : "dot bad-dot"} />{" "}
          {status.serial?.connected ? "Gate connected" : "Gate disconnected"}
          <small>
            {status.simulate
              ? "Simulation environment"
              : "Hardware environment"}
          </small>
          <button
            className="text-button"
            onClick={() =>
              act(async () => {
                await api("logout", "POST");
                setSigned(false);
              })
            }
          >
            Sign out
          </button>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <p className="breadcrumb">Warehouse / {page}</p>
            <h1>{page === "Live" ? "Floor overview" : page}</h1>
          </div>
          <div className="header-meta">
            <span>
              {new Date().toLocaleDateString(undefined, {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </span>
            {status.simulate && <Badge value="SIMULATION" />}
          </div>
        </header>
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError("")}>Dismiss</button>
          </div>
        )}
        {status.checkpoint && (
          <div className="warning">
            Hardware test checkpoint: item issuing and strict removal
            reconciliation are not enabled yet. Online access still uses the
            existing single-worker policy.
          </div>
        )}
        {status.serial?.error && (
          <div className="error" role="alert">
            {status.serial.error}
          </div>
        )}
        {status.prewarn && (
          <div className="warning" role="alert">
            Removal awaiting declaration. The gate controller will escalate if
            the grace timer expires.
          </div>
        )}
        {status.alarm && (
          <div className="alarm" role="alert">
            <div>
              <strong>Security alarm active</strong>
              <p>
                Review the incident and acknowledge when the area is secure.
              </p>
            </div>
            <button onClick={acknowledge}>Acknowledge alarm</button>
          </div>
        )}
        {status.notifier === "TwilioNotifier" &&
          status.whatsapp_remaining_s === 0 && (
            <div className="warning">
              Send any WhatsApp message to the sandbox number to reopen the
              session.
            </div>
          )}
        {status.shelf_camera && status.shelf_camera !== "OK" && (
          <div className="warning">
            Shelf camera: {human(status.shelf_camera)}. Check the camera before
            relying on shelf detection.
          </div>
        )}
        {page === "Live" && (
          <>
            <section className="gate-strip">
              <div>
                <span className="caption">Gate access</span>
                <strong>
                  {status.session ? "Worker checked in" : "No active session"}
                </strong>
              </div>
              <div>
                <span className="caption">Current worker</span>
                <strong>
                  {status.session?.name || "Unattended warehouse"}
                </strong>
              </div>
              <div>
                <span className="caption">Failed scans</span>
                <strong>
                  {status.fail_counter || 0}
                  <small> consecutive</small>
                </strong>
              </div>
              <div>
                <span className="caption">Shelf camera</span>
                <Badge value={status.shelf_camera} />
              </div>
            </section>
            <div className="live-layout">
              <section className="panel shelf-panel">
                <div className="panel-title">
                  <h2>Shelf monitor</h2>
                  <span>
                    <i className="dot" /> Live view
                  </span>
                </div>
                <img
                  className="shelf"
                  src="/api/shelf/stream"
                  alt="Live shelf camera with slot and marker annotations"
                />
                <div className="slots">
                  {slots.map((s) => (
                    <div key={s.id}>
                      <div>
                        <strong>{s.name}</strong>
                        <small>Marker #{s.marker_id}</small>
                      </div>
                      <Badge value={status.slots?.[s.id] || "UNKNOWN"} />
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel">
                <div className="panel-title">
                  <h2>Gate camera</h2>
                  <Badge value={status.gate_camera} />
                </div>
                <img
                  className="gate-image"
                  src={"/api/gate/latest.jpg?t=" + Math.floor(tick / 2)}
                  alt="Latest gate camera frame"
                />
                <div className="gate-note">
                  <h3>
                    {status.session
                      ? "Session in progress"
                      : "Ready for a card"}
                  </h3>
                  <p>
                    {status.session
                      ? "Tap the same card again to check out."
                      : "Authorized workers can tap their RFID card to check in."}
                  </p>
                </div>
              </section>
            </div>
            <section className="panel">
              <div className="panel-title">
                <h2>Recent activity</h2>
                <button
                  className="text-button"
                  onClick={() => setPage("Incidents")}
                >
                  View all incidents
                </button>
              </div>
              <IncidentTable
                rows={incidents.slice(0, 5)}
                open={async (i) => {
                  setDetail(await api("incidents/" + i));
                  setPage("Incidents");
                }}
              />
            </section>
            {status.simulate && <Simulator act={act} />}
          </>
        )}
        {page === "Incidents" &&
          (detail ? (
            <section className="panel">
              <button className="text-button" onClick={() => setDetail(null)}>
                Back to incidents
              </button>
              <div className="panel-title">
                <h2>
                  Incident #{detail.id}: {human(detail.kind)}
                </h2>
                <Badge value={detail.status} />
              </div>
              <p>
                {date(detail.ts)} · {detail.uid || "No worker"} ·{" "}
                {detail.severity}
              </p>
              <div className="evidence">
                {detail.evidence.map((e: Row) => (
                  <article key={e.id}>
                    {e.kind === "clip" ? (
                      <video src={e.url} controls />
                    ) : (
                      <img src={e.url} alt={e.kind} />
                    )}
                    <strong>{e.kind}</strong>
                    <code>SHA-256 {e.sha256}</code>
                    <a href={e.url} download>
                      Download evidence
                    </a>
                  </article>
                ))}
              </div>
              {detail.evidence.length === 0 && (
                <p>
                  Evidence is still being captured, unavailable, or expired
                  under the retention policy.
                </p>
              )}
              <h3>Notifications</h3>
              {detail.notifications.map((n: Row) => (
                <p key={n.id}>
                  {n.kind}: <Badge value={n.status} /> · {n.attempts} attempts ·{" "}
                  {n.provider_sid || "No provider ID"}{" "}
                  {n.error_code && `Error ${n.error_code}`}
                </p>
              ))}
              <label>
                <input
                  type="checkbox"
                  checked={detail.keep}
                  onChange={(e) =>
                    setDetail({ ...detail, keep: e.target.checked })
                  }
                />{" "}
                Keep evidence beyond retention period
              </label>
              <label>
                Notes
                <textarea
                  value={detail.notes || ""}
                  onChange={(e) =>
                    setDetail({ ...detail, notes: e.target.value })
                  }
                />
              </label>
              <div className="actions">
                <button
                  onClick={() =>
                    act(() =>
                      api("incidents/" + detail.id, "PATCH", {
                        keep: detail.keep,
                        notes: detail.notes,
                      }),
                    )
                  }
                >
                  Save notes
                </button>
                <button
                  onClick={() =>
                    act(async () => {
                      await api(`incidents/${detail.id}/ack`, "POST");
                      setDetail(await api("incidents/" + detail.id));
                    })
                  }
                >
                  Acknowledge
                </button>
                <button
                  className="secondary"
                  onClick={() =>
                    act(async () =>
                      setDetail(await api("incidents/" + detail.id)),
                    )
                  }
                >
                  Refresh evidence
                </button>
              </div>
            </section>
          ) : (
            <>
              <section className="panel">
                <IncidentTable
                  rows={incidents}
                  open={async (id) => setDetail(await api("incidents/" + id))}
                />
              </section>
              <FailedScans tick={tick} />
            </>
          ))}
        {page === "Personnel" && (
          <>
            <Manager
              resource="personnel"
              title="Personnel"
              fields={["name", "uid", "active"]}
              defaults={{ name: "", uid: "", active: true }}
              act={act}
              tick={tick}
              enrolled={status.enrolled_uid}
            />
            {status.zones_enabled && <ZonePermissions act={act} tick={tick} />}
          </>
        )}
        {page === "Inventory" && (
          <>
            {status.zones_enabled && (
              <Manager
                resource="zones"
                title="Zones"
                fields={["name"]}
                defaults={{ name: "" }}
                act={act}
                tick={tick}
              />
            )}
            <Manager
              resource="inventory"
              title="Inventory items"
              fields={["name", "marker_id", "notes"]}
              defaults={{ name: "", marker_id: 0, notes: "" }}
              act={act}
              tick={tick}
            />
            <Manager
              resource="slots"
              title="Shelf slots"
              fields={[
                "name",
                "marker_id",
                "item_id",
                "roi_x",
                "roi_y",
                "roi_w",
                "roi_h",
                "zone_id",
              ]}
              defaults={{
                name: "",
                marker_id: 0,
                item_id: null,
                roi_x: 0,
                roi_y: 0,
                roi_w: 0.3,
                roi_h: 0.5,
                zone_id: null,
              }}
              act={act}
              tick={tick}
            />
          </>
        )}
        {page === "Calibration" && <CalibrationPanel slots={slots} act={act} />}
        {page === "Settings" && <Settings act={act} />}
        {page === "System health" && (
          <>
            <section className="panel health">
              <h2>Connection health</h2>
              {[
                [
                  "Serial link",
                  status.serial?.connected ? "Connected" : "Disconnected",
                ],
                ["Malformed serial lines", status.serial?.malformed],
                ["Firmware", status.serial?.firmware?.fw || "Awaiting BOOT"],
                ["Last reset", status.serial?.firmware?.rst || "Unknown"],
                [
                  "Free RAM (board)",
                  status.simulate
                    ? "Synthetic: not a measurement"
                    : (status.serial?.telemetry?.ram ?? "Unavailable"),
                ],
                [
                  "Maximum loop time (µs)",
                  status.simulate
                    ? "Synthetic: not a measurement"
                    : (status.serial?.telemetry?.lp ?? "Unavailable"),
                ],
                ["Offline events pending", status.serial?.telemetry?.off ?? 0],
                [
                  "Offline whitelist",
                  status.offline_whitelist?.state || "Unknown",
                ],
                ["Cached badge count", status.offline_whitelist?.count ?? 0],
                [
                  "Whitelist diagnostic",
                  status.offline_whitelist?.error || "None",
                ],
                ["Gate camera", status.gate_camera],
                ["Shelf camera", status.shelf_camera],
                ["Notification provider", status.notifier],
                [
                  "WhatsApp session",
                  Math.floor(status.whatsapp_remaining_s / 3600) +
                    "h " +
                    Math.floor((status.whatsapp_remaining_s % 3600) / 60) +
                    "m remaining",
                ],
                ["Uptime", status.uptime_s + " seconds"],
              ].map(([k, v]) => (
                <div key={k}>
                  <span>{k}</span>
                  <strong>{v}</strong>
                </div>
              ))}
              <h3>Hardware output test</h3>
              <button
                className="secondary"
                onClick={() => act(() => api("offline/sync", "POST"))}
              >
                Retry offline whitelist sync
              </button>
              <div className="actions">
                {["green", "red", "buzzer"].map((w) => (
                  <button
                    key={w}
                    onClick={() => act(() => api("test/" + w, "POST"))}
                  >
                    Test {w}
                  </button>
                ))}
              </div>
              <p>
                Verify each light or sound physically. A queued command is not
                proof of an electrical response.
              </p>
            </section>
            <EventLog tick={tick} />
          </>
        )}
        <footer>
          Smart Warehouse Access & Inventory Security System
          <span>Alarm decisions run on the gate controller</span>
        </footer>
      </main>
    </div>
  );
}
type Act = (fn: () => Promise<unknown>) => Promise<void>;
function IncidentTable({
  rows,
  open,
}: {
  rows: Row[];
  open: (id: number) => void;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Time</th>
            <th>Severity</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.id}>
              <td>
                <strong>{human(i.kind)}</strong>
                <small>
                  #{i.id} {i.uid || ""}
                </small>
              </td>
              <td>{date(i.ts)}</td>
              <td>
                <Badge value={i.severity} />
              </td>
              <td>
                <Badge value={i.status} />
              </td>
              <td>
                <button className="text-button" onClick={() => open(i.id)}>
                  Review
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <p className="empty">
          No incidents recorded. New alerts will appear here.
        </p>
      )}
    </div>
  );
}
function Manager({
  resource,
  title,
  fields,
  defaults,
  act,
  tick,
  enrolled,
}: {
  resource: string;
  title: string;
  fields: string[];
  defaults: Row;
  act: Act;
  tick: number;
  enrolled?: string;
}) {
  const [rows, setRows] = useState<Row[]>([]),
    [edit, setEdit] = useState<Row>({ ...defaults }),
    [id, setId] = useState<number | null>(null);
  useEffect(() => {
    api(resource).then(setRows);
  }, [resource, tick]);
  useEffect(() => {
    if (enrolled) setEdit((e) => ({ ...e, uid: enrolled }));
  }, [enrolled]);
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>{title}</h2>
        {resource === "personnel" && (
          <button
            className="secondary"
            onClick={() => act(() => api("personnel/enrol", "POST"))}
          >
            Enrol next scanned card
          </button>
        )}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {fields.map((f) => (
                <th key={f}>{human(f)}</th>
              ))}
              <th>Record ID / actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                {fields.map((f) => (
                  <td key={f}>{String(r[f] ?? "—")}</td>
                ))}
                <td>
                  <small>#{r.id}</small>
                  <button
                    className="text-button"
                    onClick={() => {
                      setId(r.id);
                      setEdit(Object.fromEntries(fields.map((f) => [f, r[f]])));
                    }}
                  >
                    Edit
                  </button>
                  <button
                    className="text-button danger"
                    onClick={() =>
                      act(async () => {
                        await api(`${resource}/${r.id}`, "DELETE");
                        setRows(await api(resource));
                      })
                    }
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{id ? "Edit record #" + id : "Add record"}</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(async () => {
            await api(
              resource + (id ? "/" + id : ""),
              id ? "PUT" : "POST",
              edit,
            );
            setEdit({ ...defaults });
            setId(null);
            setRows(await api(resource));
          });
        }}
      >
        <div className="form-grid">
          {fields.map((f) => (
            <label key={f}>
              {human(f)}
              {typeof defaults[f] === "boolean" ? (
                <input
                  type="checkbox"
                  checked={edit[f]}
                  onChange={(e) => setEdit({ ...edit, [f]: e.target.checked })}
                />
              ) : (
                <input
                  required={!["notes", "zone_id", "item_id"].includes(f)}
                  type={
                    typeof defaults[f] === "number" ||
                    ["zone_id", "item_id"].includes(f)
                      ? "number"
                      : "text"
                  }
                  step="any"
                  value={edit[f] ?? ""}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      [f]:
                        e.target.type === "number"
                          ? e.target.value === ""
                            ? null
                            : Number(e.target.value)
                          : f === "uid"
                            ? e.target.value.toUpperCase()
                            : e.target.value,
                    })
                  }
                />
              )}
            </label>
          ))}
        </div>
        <div className="actions">
          <button>{id ? "Save changes" : "Add record"}</button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setId(null);
              setEdit({ ...defaults });
            }}
          >
            Clear form
          </button>
        </div>
      </form>
    </section>
  );
}
function CalibrationPanel({ slots, act }: { slots: Row[]; act: Act }) {
  const [slot, setSlot] = useState(0),
    [roi, setRoi] = useState<Row | null>(null),
    [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (slots.length && !slot) setSlot(slots[0].id);
  }, [slots]);
  const point = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
      y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
    };
  };
  return (
    <section className="panel">
      <h2>Define the shelf slots</h2>
      <p>
        Select a slot, then drag a rectangle around its box area. Remove the box
        before capturing its empty reference.
      </p>
      <label>
        Shelf slot
        <select
          value={slot}
          onChange={(e) => {
            setSlot(Number(e.target.value));
            setRoi(null);
          }}
        >
          {slots.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} · marker {s.marker_id}
            </option>
          ))}
        </select>
      </label>
      <div
        ref={box}
        className="calibration-image"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          setStart(point(e));
          setRoi(null);
        }}
        onPointerMove={(e) => {
          if (start) {
            const p = point(e);
            setRoi({
              roi_x: Math.min(p.x, start.x),
              roi_y: Math.min(p.y, start.y),
              roi_w: Math.abs(p.x - start.x),
              roi_h: Math.abs(p.y - start.y),
            });
          }
        }}
        onPointerUp={() => setStart(null)}
      >
        <img
          draggable={false}
          src="/api/shelf/stream"
          alt="Drag to select a region of interest"
        />
        {roi && (
          <div
            className="roi"
            style={{
              left: roi.roi_x * 100 + "%",
              top: roi.roi_y * 100 + "%",
              width: roi.roi_w * 100 + "%",
              height: roi.roi_h * 100 + "%",
            }}
          />
        )}
      </div>
      <div className="actions">
        <button
          disabled={!roi || !slot}
          onClick={() =>
            act(() =>
              api("calibration/slot", "POST", { slot_id: slot, ...roi }),
            )
          }
        >
          Save selected region
        </button>
        <button
          disabled={!slot}
          className="secondary"
          onClick={() =>
            act(() =>
              api("calibration/empty-reference", "POST", { slot_id: slot }),
            )
          }
        >
          Capture empty reference
        </button>
      </div>
      <h3>Print markers</h3>
      <p>
        Use item markers 0–29; anchor markers 40–49 stay fixed to the shelf. Use
        the marker PDF tool for accurate physical sizes.
      </p>
      {slots.map((s) => (
        <a
          className="marker-link"
          key={s.id}
          href={`/api/markers/${s.marker_id}.png`}
          target="_blank"
          rel="noreferrer"
        >
          Download marker #{s.marker_id}
        </a>
      ))}
    </section>
  );
}
function Settings({ act }: { act: Act }) {
  const [settings, setSettings] = useState<Row>({});
  useEffect(() => {
    api("settings").then(setSettings);
  }, []);
  return (
    <section className="panel">
      <h2>Detection and alarm settings</h2>
      <p>
        Alarm and detection thresholds apply immediately. Restart after changing
        camera sources, capture rate or serial settings. Keep credentials in
        .env. Gate authentication and watchdog timer changes also require
        matching firmware.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(() => api("settings", "PUT", settings));
        }}
      >
        <div className="form-grid">
          {Object.entries(settings).map(([k, v]) => (
            <label key={k}>
              {human(k)}
              {typeof v === "boolean" ? (
                <input
                  type="checkbox"
                  checked={v}
                  onChange={(e) =>
                    setSettings({ ...settings, [k]: e.target.checked })
                  }
                />
              ) : (
                <input
                  type={typeof v === "number" ? "number" : "text"}
                  step="any"
                  value={v}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      [k]:
                        typeof v === "number"
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                />
              )}
            </label>
          ))}
        </div>
        <button>Save settings</button>
      </form>
    </section>
  );
}
function Simulator({ act }: { act: Act }) {
  return (
    <section className="panel">
      <h2>Simulation controls</h2>
      <p>
        Exercise the same event engine and vision pipeline without hardware.
      </p>
      <div className="actions">
        <button
          onClick={() =>
            act(() =>
              api("sim/control", "POST", { action: "scan", uid: "A1B2C3D4" }),
            )
          }
        >
          Tap Aarav's card
        </button>
        <button
          className="secondary"
          onClick={() =>
            act(() =>
              api("sim/control", "POST", { action: "scan", uid: "DEADBEEF" }),
            )
          }
        >
          Tap unknown card
        </button>
        {["absent", "occluded", "present"].map((state) => (
          <button
            className="secondary"
            key={state}
            onClick={() =>
              act(() =>
                api("sim/control", "POST", {
                  action: "slot",
                  marker_id: 0,
                  state,
                }),
              )
            }
          >
            Bay 1: {state}
          </button>
        ))}
      </div>
    </section>
  );
}
function EventLog({ tick }: { tick: number }) {
  const [events, setEvents] = useState<Row[]>([]);
  useEffect(() => {
    api("events?limit=25").then(setEvents);
  }, [tick]);
  return (
    <section className="panel">
      <h2>Event log</h2>
      <div className="event-log">
        {events.map((e) => (
          <div key={e.id}>
            <time>{date(e.ts)}</time>
            <strong>{e.type}</strong>
            <code>{e.payload_json}</code>
          </div>
        ))}
      </div>
    </section>
  );
}
function ZonePermissions({ act, tick }: { act: Act; tick: number }) {
  const [people, setPeople] = useState<Row[]>([]),
    [zones, setZones] = useState<Row[]>([]),
    [person, setPerson] = useState(0),
    [allowed, setAllowed] = useState<number[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api("personnel"), api("zones")])
      .then(([p, z]) => {
        setPeople(p);
        setZones(z);
        if (p.length && !person) setPerson(p[0].id);
      })
      .catch((e) => setError(String(e)));
  }, [tick]);
  useEffect(() => {
    if (person)
      api(`personnel/${person}/zones`)
        .then((v) => setAllowed(v.zone_ids))
        .catch((e) => setError(String(e)));
  }, [person]);
  return (
    <section className="panel">
      <h2>Zone permissions</h2>
      <p>
        Restricted removals create a warning. An active worker session still
        keeps the buzzer quiet.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Worker
        <select
          value={person}
          onChange={(e) => setPerson(Number(e.target.value))}
        >
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          act(() =>
            api(`personnel/${person}/zones`, "PUT", { zone_ids: allowed }),
          );
        }}
      >
        {zones.map((z) => (
          <label key={z.id}>
            {z.name} (#{z.id})
            <input
              type="checkbox"
              checked={allowed.includes(z.id)}
              onChange={(e) =>
                setAllowed(
                  e.target.checked
                    ? [...allowed, z.id]
                    : allowed.filter((id) => id !== z.id),
                )
              }
            />
          </label>
        ))}
        <button disabled={!person}>Save permissions</button>
      </form>
    </section>
  );
}
function FailedScans({ tick }: { tick: number }) {
  const [rows, setRows] = useState<Row[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    api("failed-scans?limit=30")
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, [tick]);
  return (
    <section className="panel">
      <h2>Failed scans</h2>
      {error && <p role="alert">{error}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>UID</th>
              <th>Time</th>
              <th>Consecutive count</th>
              <th>Photo</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.uid}</td>
                <td>{date(r.ts)}</td>
                <td>{r.counter}</td>
                <td>
                  {r.photo_path ? (
                    <a
                      href={`/api/failed-scans/${r.id}/photo`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View photo
                    </a>
                  ) : (
                    "Unavailable or capturing"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="empty">No failed scans recorded.</p>
        )}
      </div>
    </section>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
