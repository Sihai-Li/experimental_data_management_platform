import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Status = 'loading' | 'ready' | 'unavailable';
function App() {
  const [api, setApi] = useState<Status>('loading');
  const [db, setDb] = useState<Status>('loading');
  const [revision, setRevision] = useState('—');
  const [checked, setChecked] = useState('Not checked yet');
  async function refresh() {
    setApi('loading'); setDb('loading'); setRevision('—');
    const check = async (url: string, setter: (s: Status) => void) => {
      try {
        const response = await fetch(url, {signal: AbortSignal.timeout(5000)});
        const body = await response.json();
        setter(response.ok && body.status === 'ok' ? 'ready' : 'unavailable');
        if (response.ok && body.schema_revision) setRevision(body.schema_revision);
      } catch { setter('unavailable'); }
    };
    await Promise.all([check('/api/health/live', setApi), check('/api/health/ready', setDb)]);
    setChecked(new Date().toLocaleTimeString('en-US'));
  }
  useEffect(() => { void refresh(); }, []);
  const label = {loading:'Checking',ready:'Ready',unavailable:'Not ready'};
  return <main>
    <header><span className="mark">LD</span><span>LAB DATA PLATFORM</span><span className="phase">P02 · Development</span></header>
    <section className="intro"><p className="eyebrow">RECORDING DATA / FOUNDATION</p><h1>Reliable data starts with accurate storage.</h1><p>A foundation for parsing, validating, and storing neuronal recording files.</p></section>
    <section className="panel"><div className="heading"><div><h2>Environment status</h2><p>Check API connectivity and database readiness.</p></div><button onClick={() => void refresh()} disabled={api === 'loading' || db === 'loading'}>Refresh status</button></div>
      <div className="cards">{[['Backend API',api],['PostgreSQL',db]].map(([name,state]) => <article key={name}><span>{name}</span><strong className={state}>{label[state as Status]}</strong></article>)}<article><span>Schema revision</span><strong>{revision}</strong></article></div>
      <p className="foot">Last checked: {checked} · Live health checks</p>
    </section>
    <section className="scope"><h2>Current phase</h2><p>Read-only MAT validation and the database schema are available. Uploads, data search, and authorized downloads are planned for subsequent phases.</p><div className="tags"><span>6,001 time points</span><span>1 ms resolution</span><span>Original files preserved</span></div></section>
  </main>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
