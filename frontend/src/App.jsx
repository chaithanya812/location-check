import { useEffect, useState } from "react";
import { createAssessment, getAssessment, listAssessments, retryAssessment } from "./api.js";

// Two pages, chosen by the URL hash:  #/  -> list,  #/assessments/5 -> detail.
function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const match = hash.match(/^#\/assessments\/(\d+)$/);
  return match ? { page: "detail", id: Number(match[1]) } : { page: "list" };
}

export default function App() {
  const route = useHashRoute();
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <h1><a href="#/">Location Check</a></h1>
          <span className="tagline">Is this location worth pursuing? Scored from public data, with missing data shown, never guessed.</span>
        </div>
      </header>
      <main className="page">
        {route.page === "detail" ? <DetailPage id={route.id} /> : <ListPage />}
      </main>
    </>
  );
}

// ---------------- List page: new-assessment form + saved assessments ----------------

function ListPage() {
  const [assessments, setAssessments] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listAssessments().then(setAssessments).catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <NewAssessmentForm />
      <section className="card">
        <h2>Saved assessments</h2>
        {error && <p className="error">Could not load the list: {error}</p>}
        {assessments === null && !error && <p className="muted">Loading…</p>}
        {assessments?.length === 0 && <p className="muted">None yet. Check a location above and it will appear here.</p>}
        {assessments?.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Label</th><th>Location</th><th>Score</th><th>Verdict</th><th>Created</th></tr>
              </thead>
              <tbody>
                {assessments.map((a) => (
                  <tr key={a.id} className="clickable" onClick={() => (window.location.hash = `#/assessments/${a.id}`)}>
                    <td><a href={`#/assessments/${a.id}`}>{a.label}</a></td>
                    <td>{a.address ?? `${a.input_lat}, ${a.input_lon}`}</td>
                    <td className="num"><Score score={a.score} coverage={a.coverage} /></td>
                    <td>
                      <Verdict verdict={a.verdict} />
                      {a.run_count > 1 && <div className="muted">{a.run_count} runs</div>}
                    </td>
                    <td className="num muted">{formatTime(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

// Real inputs used while testing; handy for a quick demo.
const EXAMPLES = [
  { label: "Denver civic center", mode: "address", address: "1437 Bannock St, Denver, CO" },
  { label: "New Orleans", mode: "address", address: "1300 Perdido St, New Orleans, LA" },
  { label: "Pacific Ocean", mode: "coords", lat: "30", lon: "-140" },
];

function NewAssessmentForm() {
  const [label, setLabel] = useState("");
  const [mode, setMode] = useState("address");
  const [address, setAddress] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  function fillExample(ex) {
    setLabel(ex.label);
    setMode(ex.mode);
    setAddress(ex.address ?? "");
    setLat(ex.lat ?? "");
    setLon(ex.lon ?? "");
    setError(null);
  }

  async function onSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body = mode === "address"
      ? { label, address }
      : { label, lat: lat === "" ? null : Number(lat), lon: lon === "" ? null : Number(lon) };
    try {
      const saved = await createAssessment(body);
      window.location.hash = `#/assessments/${saved.id}`;
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h2>Check a location</h2>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="label">Label</label>
          <input id="label" value={label} onChange={(e) => setLabel(e.target.value)} required maxLength={100}
            placeholder="e.g. Denver site A" />
        </div>
        <div className="field">
          <label>Location as</label>
          <div className="segmented" role="group">
            <button type="button" className={mode === "address" ? "on" : ""} onClick={() => setMode("address")}>US address</button>
            <button type="button" className={mode === "coords" ? "on" : ""} onClick={() => setMode("coords")}>Latitude / longitude</button>
          </div>
        </div>
        {mode === "address" ? (
          <div className="field full">
            <label htmlFor="address">Address</label>
            <input id="address" value={address} onChange={(e) => setAddress(e.target.value)} required
              placeholder="1437 Bannock St, Denver, CO" />
          </div>
        ) : (
          <div className="coords full">
            <div className="field">
              <label htmlFor="lat">Latitude</label>
              <input id="lat" type="number" step="any" min="-90" max="90" value={lat} onChange={(e) => setLat(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="lon">Longitude</label>
              <input id="lon" type="number" step="any" min="-180" max="180" value={lon} onChange={(e) => setLon(e.target.value)} required />
            </div>
          </div>
        )}
        <div className="actions full">
          <button type="submit" className="primary" disabled={busy}>{busy ? "Checking…" : "Check location"}</button>
          {busy
            ? <span className="muted">Asking 4 public data sources. A slow source can take up to about 10 seconds.</span>
            : <span className="muted">
                Try an example:{" "}
                {EXAMPLES.map((ex, i) => (
                  <span key={ex.label}>{i > 0 && " · "}<button type="button" className="link" onClick={() => fillExample(ex)}>{ex.label}</button></span>
                ))}
              </span>}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

// ---------------- Detail page ----------------

function DetailPage({ id }) {
  const [assessment, setAssessment] = useState(null);
  const [error, setError] = useState(null);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    getAssessment(id).then(setAssessment).catch((e) => setError(e.message));
  }, [id]);

  async function onRetry() {
    setRetrying(true);
    setError(null);
    try {
      setAssessment(await retryAssessment(id));
    } catch (e) {
      setError(e.message);
    }
    setRetrying(false);
  }

  if (error) return <p className="error">{error}</p>;
  if (!assessment) return <p className="muted">Loading…</p>;

  const [latest, ...earlier] = assessment.runs;
  return (
    <>
      <p style={{ margin: 0 }}><a href="#/">← All assessments</a></p>
      <section className="card">
        <h2 style={{ marginBottom: 4 }}>{assessment.label}</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          {assessment.address ?? `${assessment.input_lat}, ${assessment.input_lon}`} · created {formatTime(assessment.created_at)}
        </p>
        <Summary run={latest} />
        <div className="actions" style={{ marginTop: 14 }}>
          <button className="secondary" onClick={onRetry} disabled={retrying}>
            {retrying ? "Fetching again…" : "Retry: fetch the data again"}
          </button>
          <span className="muted">A retry is saved as a new result. Earlier results are kept below.</span>
        </div>
      </section>

      <section className="card">
        <h2>Score breakdown <span className="muted">({formatTime(latest.created_at)})</span></h2>
        <FactorTable run={latest} />
      </section>

      {earlier.length > 0 && (
        <section className="card">
          <h2>Earlier results</h2>
          {earlier.map((run) => (
            <details key={run.id} className="run-history">
              <summary>
                {formatTime(run.created_at)}: score <Score score={run.score} coverage={run.coverage} />, <Verdict verdict={run.verdict} />
              </summary>
              <FactorTable run={run} />
            </details>
          ))}
        </section>
      )}
    </>
  );
}

function Summary({ run }) {
  return (
    <div className="summary">
      <div className="bigscore">{run.score ?? "—"}<small> / 100</small></div>
      <div>
        <Verdict verdict={run.verdict} />
        <div className="facts">
          <span>Based on <strong>{run.coverage}%</strong> of the scoring factors</span>
          <span className="meter" style={{ width: 160, display: "inline-block", alignSelf: "center" }}><span style={{ width: `${run.coverage}%` }} /></span>
        </div>
        <div className="muted" style={{ marginTop: 4 }}>
          {run.location_error
            ? <span className="error" style={{ display: "inline-block" }}>Could not locate this address: {run.location_error}</span>
            : <>Coordinates {run.lat.toFixed(5)}, {run.lon.toFixed(5)}{run.matched_address && <> · matched: {run.matched_address}</>}</>}
        </div>
      </div>
    </div>
  );
}

function FactorTable({ run }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Factor</th><th>Raw value</th><th>Points</th><th>Source</th><th>Rule</th></tr>
        </thead>
        <tbody>
          {run.factors.map((f) => (
            <tr key={f.id} className={f.status === "unavailable" ? "unavailable" : ""}>
              <td><strong>{f.label}</strong></td>
              <td>
                {f.status === "unavailable"
                  ? <><span className="badge-na">UNAVAILABLE</span><div className="muted">{f.error}</div></>
                  : `${f.value} ${f.unit}`}
              </td>
              <td className="num">
                {f.status === "unavailable"
                  ? <span className="muted">— not scored</span>
                  : <>{f.points} / {f.max_points}<div className="points-bar"><span style={{ width: `${(f.points / f.max_points) * 100}%` }} /></div></>}
              </td>
              <td>{f.source}</td>
              <td className="muted">{f.rule}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Verdict({ verdict }) {
  const cls = verdict === "Not enough data" ? "nodata" : verdict;
  return <span className={`pill ${cls}`}>{verdict}</span>;
}

function Score({ score, coverage }) {
  if (score === null || score === undefined) return <strong>—</strong>;
  return (
    <span className="score">
      <strong>{score}</strong> / 100
      {coverage < 100 && <span className="muted"> ({coverage}% of factors)</span>}
    </span>
  );
}

function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString() : "";
}
