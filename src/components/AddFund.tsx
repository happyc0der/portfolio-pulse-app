import { useEffect, useRef, useState } from 'react';

type Result = { uuid: string; name: string; website: string; category: string; status?: string | null; is_investor: boolean };

const BATCH = 4;

const domain = (website: string) => website.replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/.*$/, '');

// Add a fund live: search akta.pro as you type, then let akta build the portfolio from funding
// rounds that list the investor, pull 90 days of news, and open the new fund.
export default function AddFund({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Result[]>([]);
  const [searching, setSearching] = useState(false);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Keep the highlighted suggestion visible while moving with the arrow keys.
  useEffect(() => { listRef.current?.children[active]?.scrollIntoView({ block: 'nearest' }); }, [active]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2 || busy) { setResults([]); return; }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true); setError('');
      try {
        const response = await fetch(`/api/akta/search?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        const data = await response.json();
        setResults(data.results ?? []); setActive(0);
        if (data.error) setError(data.error);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') setError('Search is unavailable right now.');
      } finally { setSearching(false); }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query, busy]);

  const build = async (fund: Result) => {
    setBusy(true); setError(''); setResults([]); setQuery(fund.name);
    setProgress(`akta.pro is finding companies whose funding rounds list ${fund.name}…`);
    try {
      const response = await fetch('/api/funds/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uuid: fund.uuid, name: fund.name, website: fund.website }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not build this portfolio.');
      if (!data.existing) {
        // Small batches stay inside the host's 30 s request limit. A failed batch is retried once,
        // then skipped, so one slow company doesn't stop the whole fund.
        let start: number | null = 0;
        while (start !== null) {
          setProgress(`Found ${data.company_count} companies${data.total_matches ? ` (of ${data.total_matches} on record)` : ''}. Pulling 90 days of news · ${start} of ${data.company_count}`);
          let payload: { next_start?: number | null } | null = null;
          for (let attempt = 0; attempt < 2 && !payload; attempt++) {
            try {
              const refresh: Response = await fetch(`/api/funds/${encodeURIComponent(data.slug)}/refresh?start=${start}&count=${BATCH}`, { method: 'POST' });
              if (refresh.ok) payload = await refresh.json();
            } catch { /* retried below */ }
          }
          start = payload ? payload.next_start ?? null : start + BATCH < data.company_count ? start + BATCH : null;
        }
      }
      // Open the fund only once the backend serves it, so the page never lands on a stale 404.
      setProgress('Ranking signals…');
      for (let attempt = 0; attempt < 6; attempt++) {
        const check = await fetch(`/api/funds/${encodeURIComponent(data.slug)}`).catch(() => null);
        if (check?.ok) break;
        await new Promise(resolve => window.setTimeout(resolve, 1500));
      }
      window.location.assign(`/fund/${encodeURIComponent(data.slug)}`);
    } catch (e) {
      setError((e as Error).message); setBusy(false); setProgress('');
    }
  };

  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape' && !busy) onClose();
    if (!results.length) return;
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => Math.min(i + 1, results.length - 1)); }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(i - 1, 0)); }
    if (event.key === 'Enter') { event.preventDefault(); void build(results[active]); }
  };

  return <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-24" onClick={() => !busy && onClose()}>
    <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-xl" onClick={e => e.stopPropagation()} onKeyDown={onKey}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-800">Add a fund</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">Search any investor. akta.pro builds its portfolio from the funding rounds that list it.</p>
        </div>
        {!busy && <button onClick={onClose} className="text-sm text-slate-400 hover:text-slate-200" aria-label="Close">✕</button>}
      </div>
      <input ref={inputRef} value={query} disabled={busy} onChange={e => setQuery(e.target.value)} placeholder="Try “sequoia”, “lightspeed” or “a16z”"
        className="mt-4 w-full rounded-lg border border-slate-200 bg-transparent px-3 py-2.5 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-indigo-400" />
      {searching && <p className="mt-3 text-xs text-slate-400">Searching akta.pro…</p>}
      {results.length > 0 && <ul ref={listRef} className="mt-3 max-h-80 overflow-y-auto rounded-lg border border-slate-200">
        {results.map((result, index) => <li key={result.uuid}>
          <button onClick={() => void build(result)} onMouseEnter={() => setActive(index)}
            className={`flex w-full items-center gap-3 px-3 py-2.5 text-left ${index === active ? 'bg-slate-100' : ''}`}>
            <img src={`https://www.google.com/s2/favicons?domain=${domain(result.website)}&sz=64`} alt="" className="h-6 w-6 rounded" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-slate-800">{result.name}</span>
              <span className="block truncate text-xs text-slate-500">{[result.category, domain(result.website)].filter(Boolean).join(' · ')}</span>
            </span>
            {result.is_investor && <span className="rounded-full border border-indigo-300 px-2 py-0.5 text-[10px] font-medium text-indigo-300">Investor</span>}
          </button>
        </li>)}
      </ul>}
      {!searching && !busy && query.trim().length >= 2 && results.length === 0 && !error && <p className="mt-3 text-xs text-slate-500">No matches in akta.pro yet. Try the firm's full name.</p>}
      {busy && <div className="mt-4 flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-3"><span className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" /><p className="text-sm text-slate-600">{progress}</p></div>}
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      <p className="mt-4 text-[11px] leading-5 text-slate-500">Building a portfolio uses about 35 akta.pro credits: the company list, then news and headcount data for 25 companies. Data: akta.pro company search and List Generation.</p>
    </div>
  </div>;
}
