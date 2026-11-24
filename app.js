/* U.S. Economic Indicators Dashboard
 * Renders summary.json (signals, KPI cards) first, then series.json (charts).
 * No framework; Chart.js 4 + date-fns adapter are vendored under /vendor. */
(() => {
  'use strict';

  const root = document.documentElement;
  const $ = (sel, el = document) => el.querySelector(sel);
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const DAY = 864e5;

  /* ------------------------------------------------------------ formatting */
  const nfCache = new Map();
  const nf = (d) => {
    if (!nfCache.has(d)) nfCache.set(d, new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
    return nfCache.get(d);
  };
  const MINUS = '\u2212';
  const fmt = (v, d = 1, signed = false) => {
    if (v == null || Number.isNaN(v)) return '\u2014';
    const s = nf(d).format(Math.abs(v));
    if (v < 0 && Number(s.replace(/,/g, '')) !== 0) return MINUS + s;
    return (signed && v > 0 ? '+' : '') + s;
  };
  const parseDate = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d || 1); };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const fmtPeriod = (iso, freq) => {
    const d = parseDate(iso);
    if (freq === 'Q') return `Q${Math.floor(d.getMonth() / 3) + 1} ${d.getFullYear()}`;
    if (freq === 'M') return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
    return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  };
  const deltaUnit = (u) => (u === '%' || u === 'pp' ? ' pp' : u === 'k' ? 'k' : ' pts');
  const valueHTML = (v, unit, d, signed) => {
    const u = unit === '%' ? '%' : unit === 'pp' ? ' pp' : unit === 'k' ? 'k' : '';
    return `${fmt(v, d, signed)}${u ? `<span class="u">${u}</span>` : ''}`;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ------------------------------------------------------------ theme */
  const themeBtn = $('.theme-toggle');
  const mq = matchMedia('(prefers-color-scheme: dark)');
  const currentTheme = () => root.getAttribute('data-theme') || (mq.matches ? 'dark' : 'light');
  const syncTheme = () => {
    const t = currentTheme();
    themeBtn.setAttribute('aria-label', `Switch to ${t === 'dark' ? 'light' : 'dark'} theme`);
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute('content', t === 'dark' ? '#1c1612' : '#fbf6ef'));
    recolorCharts();
  };
  themeBtn.addEventListener('click', () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) { /* private mode */ }
    syncTheme();
  });
  mq.addEventListener?.('change', syncTheme);
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  const alphaHex = (hex, a) => {
    const m = /^#([0-9a-f]{6})$/i.exec(hex);
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  };
  const alpha = (color, a) => `color-mix(in srgb, ${color} ${Math.round(a * 100)}%, transparent)`;

  /* ------------------------------------------------------------ data */
  const getJSON = async (url) => {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
    return res.json();
  };
  const summaryP = getJSON('data/summary.json');
  const seriesP = getJSON('data/series.json');

  /* ------------------------------------------------------------ hero stamp */
  function renderStamp(s) {
    const ends = Object.values(s.fred).map((f) => f.observation_end).filter(Boolean).sort();
    const gen = new Date(s.generated_at);
    const when = gen.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
    $('#stamp').innerHTML =
      `<span>Data through <b>${fmtPeriod(ends[ends.length - 1], 'D')}</b></span>` +
      `<span>Refreshed <b><time datetime="${esc(s.generated_at)}">${esc(when)}</time></b></span>`;
  }

  /* ------------------------------------------------------------ signals */
  function meter(value, max, marker, tone, lo = 0) {
    const pct = Math.max(0, Math.min(1, (value - lo) / (max - lo))) * 100;
    const mk = ((marker - lo) / (max - lo)) * 100;
    return `<div class="meter ${tone}" aria-hidden="true"><i style="width:${pct.toFixed(1)}%"></i><b style="left:calc(${mk.toFixed(1)}% - 1px)"></b></div>`;
  }
  function renderSignals(s) {
    const { sahm, curve, inflation, real_rate } = s.signals;
    const k = Object.fromEntries(s.kpis.map((x) => [x.key, x]));
    const cards = [];

    const sTone = sahm.triggered ? 'bad' : sahm.value >= 0.3 ? 'warn' : 'ok';
    cards.push(`
      <article class="signal" aria-labelledby="sig-sahm">
        <div class="sig-top"><h3 class="sig-name" id="sig-sahm">Sahm rule</h3><span class="pill ${sTone}">${sahm.triggered ? 'Triggered' : sTone === 'warn' ? 'Rising' : 'Not triggered'}</span></div>
        <p class="sig-value">${fmt(sahm.value, 2)}<small>pp</small></p>
        ${meter(sahm.value, 1, sahm.threshold, sTone)}
        <div class="meter-scale"><span>0</span><span>trigger ${fmt(sahm.threshold, 2)}</span><span>1.00</span></div>
        <p class="sig-desc">How far unemployment's 3-month average sits above its low of the prior 12 months, as of ${fmtPeriod(sahm.date, 'M')}. Past-year high: ${fmt(sahm.max_12m, 2)} pp.</p>
      </article>`);

    const cTone = curve.inverted ? 'bad' : curve.spread < 0.25 ? 'warn' : 'ok';
    const li = curve.last_inversion;
    let cText = '';
    if (li && li.ongoing) cText = `Inverted since ${fmtPeriod(li.start, 'M')} (${nf(0).format(li.days)} days, low ${fmt(li.min, 2)} pp).`;
    else if (li) cText = `Last inversion ran ${fmtPeriod(li.start, 'M')} to ${fmtPeriod(li.end, 'M')} (${nf(0).format(li.days)} days, low ${fmt(li.min, 2)} pp) and ended ${nf(0).format(curve.days_since_inversion)} days ago.`;
    const ten = k.dgs10 ? k.dgs10.value : null;
    cards.push(`
      <article class="signal" aria-labelledby="sig-curve">
        <div class="sig-top"><h3 class="sig-name" id="sig-curve">Yield curve, 10y\u20132y</h3><span class="pill ${cTone}">${curve.inverted ? 'Inverted' : cTone === 'warn' ? 'Flat' : 'Positive slope'}</span></div>
        <p class="sig-value">${fmt(curve.spread, 2, true)}<small>pp</small></p>
        <p class="sig-desc">${ten != null ? `10-year ${fmt(ten, 2)}% vs 2-year ${fmt(ten - curve.spread, 2)}% on ${fmtPeriod(curve.date, 'D')}. ` : ''}${cText}</p>
      </article>`);

    const gap = inflation.gap;
    const iTone = gap <= 0.5 ? 'ok' : gap <= 1.5 ? 'warn' : 'bad';
    cards.push(`
      <article class="signal" aria-labelledby="sig-infl">
        <div class="sig-top"><h3 class="sig-name" id="sig-infl">Core inflation vs 2% goal</h3><span class="pill ${iTone}">${iTone === 'ok' ? 'Near goal' : iTone === 'warn' ? 'Above goal' : 'Well above goal'}</span></div>
        <p class="sig-value">${fmt(inflation.core_yoy, 1)}%<small>${fmt(gap, 1, true)} pp vs goal</small></p>
        ${meter(inflation.core_yoy, 6, inflation.target, iTone)}
        <div class="meter-scale"><span>0%</span><span>goal 2%</span><span>6%</span></div>
        <p class="sig-desc">Core CPI, 12-month change (${fmtPeriod(inflation.date, 'M')}).${k.cpi_yoy ? ` Headline CPI: ${fmt(k.cpi_yoy.value, 1)}%.` : ''}</p>
      </article>`);

    const rTone = real_rate.value >= 0 ? 'neutral' : 'warn';
    cards.push(`
      <article class="signal" aria-labelledby="sig-real">
        <div class="sig-top"><h3 class="sig-name" id="sig-real">Real policy rate</h3><span class="pill ${rTone}">${real_rate.value >= 0 ? 'Above inflation' : 'Below inflation'}</span></div>
        <p class="sig-value">${fmt(real_rate.value, 2, true)}<small>%</small></p>
        <p class="sig-desc">Effective fed funds rate minus core CPI inflation (${fmtPeriod(real_rate.date, 'M')}). Above zero, the policy rate sits higher than underlying inflation; below zero, money is cheap in real terms.</p>
      </article>`);
    $('#signal-grid').innerHTML = cards.join('');
  }

  /* ------------------------------------------------------------ KPI cards */
  function sparkSVG(values) {
    const v = values.filter((x) => x != null);
    if (v.length < 2) return '';
    const W = 100, H = 34, pad = 3;
    let min = Math.min(...v), max = Math.max(...v);
    if (min === max) { min -= 1; max += 1; }
    const x = (i) => (i / (values.length - 1)) * W;
    const y = (val) => pad + (1 - (val - min) / (max - min)) * (H - 2 * pad);
    const pts = values.map((val, i) => (val == null ? null : `${x(i).toFixed(2)},${y(val).toFixed(2)}`)).filter(Boolean);
    const zero = min < 0 && max > 0 ? `<line class="zero" x1="0" x2="${W}" y1="${y(0).toFixed(2)}" y2="${y(0).toFixed(2)}"/>` : '';
    const area = `M${pts[0]} L${pts.join(' L')} L${W},${H} L0,${H} Z`;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true" focusable="false">${zero}<path class="area" d="${area}"/><polyline class="line" points="${pts.join(' ')}"/></svg>`;
  }
  const ARROW_UP = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 1l4 7H1z"/></svg>';
  const ARROW_DN = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 9L1 2h8z"/></svg>';
  function renderKPIs(s) {
    $('#kpi-grid').innerHTML = s.kpis.map((k) => {
      const c = k.compare;
      const dlt = c.delta;
      let tone = '';
      if (k.good && dlt) tone = (dlt > 0) === (k.good === 'up') ? 'good' : 'bad';
      const arrow = dlt > 0 ? ARROW_UP : dlt < 0 ? ARROW_DN : '';
      const dText = `${fmt(dlt, k.decimals, true)}${deltaUnit(k.unit)}`;
      const vsLabel = c.date ? `vs ${fmtPeriod(c.date, k.freq)}` : c.label;
      const unitWord = k.unit === '%' ? 'percent' : k.unit === 'pp' ? 'percentage points' : k.unit === 'k' ? 'thousand jobs' : '';
      const sr = `${k.label}: ${fmt(k.value, k.decimals, k.signed)} ${unitWord}, ${fmtPeriod(k.date, k.freq)}. Change ${dText} ${vsLabel}.`;
      return `
        <a class="kpi" href="#chart-${k.chart}" aria-label="${esc(sr)} Go to chart.">
          <span class="kpi-label">${esc(k.label)}</span>
          <span class="kpi-value">${valueHTML(k.value, k.unit, k.decimals, k.signed)}</span>
          <span class="delta"><span class="chg ${tone}">${arrow}${dText}</span><span>${esc(vsLabel)}</span></span>
          ${k.note ? `<span class="kpi-note">${esc(k.note)}</span>` : ''}
          <span class="spark">${sparkSVG(k.spark)}</span>
          <span class="kpi-foot"><span>${fmtPeriod(k.date, k.freq)}</span><span>${esc(k.fred_id)}</span></span>
        </a>`;
    }).join('');
  }

  function renderNotes(s) {
    const ul = $('#data-notes');
    ul.innerHTML = (s.notes || []).map((n) => `<li>${esc(n)}</li>`).join('');
    if (s.source?.notice) $('#fred-notice').textContent = s.source.notice;
  }

  /* ------------------------------------------------------------ inversion table */
  function renderInversions(s) {
    const eps = s.signals.curve.episodes || [];
    if (!eps.length) return;
    const recs = s.recessions.map(([a, b]) => [parseDate(a), parseDate(b)]);
    const monthsBetween = (a, b) => (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth();
    const rows = eps.slice().reverse().map((e) => {
      const st = parseDate(e.start), en = parseDate(e.end);
      let rec = 'None';
      const during = recs.find(([a, b]) => a <= st && b >= st);
      const next = recs.find(([a]) => a > st && monthsBetween(en, a) <= 24);
      if (during) rec = 'During a recession';
      else if (next) rec = `${MONTHS[next[0].getMonth()]} ${next[0].getFullYear()}<br><span class="lead">${monthsBetween(st, next[0])} months after start</span>`;
      else if (e.ongoing) rec = 'Ongoing';
      return `<tr><td>${fmtPeriod(e.start, 'M')} –<br>${e.ongoing ? 'ongoing' : fmtPeriod(e.end, 'M')}</td><td class="r">${nf(0).format(e.days)}</td><td class="r neg">${fmt(e.min, 2)}</td><td>${rec}</td></tr>`;
    });
    $('#inv-table').innerHTML =
      '<caption class="sr">Yield-curve inversion spells and following recessions</caption>' +
      '<thead><tr><th scope="col">Inversion</th><th scope="col" class="r">Days</th><th scope="col" class="r">Low, pp</th><th scope="col">Next recession</th></tr></thead>' +
      `<tbody>${rows.join('')}</tbody>`;
    $('#inversions').hidden = false;
  }

  /* ------------------------------------------------------------ charts */
  const CHARTS = [
    { id: 'inflation', title: 'Inflation', wide: true, unit: '%', d: 1,
      what: '12-month change in consumer prices. The dashed line marks the Fed\u2019s 2% goal (formally defined on PCE inflation).',
      series: [{ key: 'cpi_yoy', label: 'CPI', color: '--c1' }, { key: 'core_yoy', label: 'Core CPI', color: '--c2' }],
      refs: [{ y: 2, label: '2% goal' }], fred: ['CPIAUCSL', 'CPILFESL'] },
    { id: 'labor', title: 'Unemployment rate', unit: '%', d: 1,
      what: 'Share of the labor force without a job and looking for one.',
      series: [{ key: 'unrate', label: 'Unemployment rate', color: '--c1' }], fred: ['UNRATE'] },
    { id: 'sahm', title: 'Sahm rule indicator', unit: 'pp', d: 2,
      what: 'Readings at or above 0.50 pp have marked the early months of every recession since 1970.',
      series: [{ key: 'sahm', label: 'Sahm indicator', color: '--c4' }], refs: [{ y: 0.5, label: '0.50 trigger', tone: '--neg' }], fred: ['UNRATE'] },
    { id: 'jobs', title: 'Monthly job gains', wide: true, unit: 'k', d: 0, robust: true,
      what: 'Change in nonfarm payroll employment, thousands of jobs, with a 3-month average.',
      series: [{ key: 'payrolls_chg', label: 'Monthly change', type: 'bar' }, { key: 'payrolls_3mma', label: '3-mo average', color: '--c4' }], fred: ['PAYEMS'] },
    { id: 'rates', title: 'Interest rates', wide: true, unit: '%', d: 2,
      what: 'The Fed\u2019s policy rate, Treasury yields at two and ten years, and the average 30-year fixed mortgage rate.',
      series: [
        { key: 'fedfunds', label: 'Fed funds', color: '--c1', stepped: true },
        { key: 'dgs2', label: '2-yr Treasury', color: '--c4' },
        { key: 'dgs10', label: '10-yr Treasury', color: '--c2' },
        { key: 'mortgage30', label: '30-yr mortgage', color: '--c3' }],
      fred: ['FEDFUNDS', 'DGS2', 'DGS10', 'MORTGAGE30US'] },
    { id: 'curve', title: 'Yield curve: 10y \u2212 2y spread', unit: 'pp', d: 2,
      what: 'Below zero the curve is inverted, which has preceded each recession since the late 1970s.',
      series: [{ key: 'spread_10y2y', label: '10y \u2212 2y', color: '--c2', fillZero: true }], refs: [{ y: 0, label: '' }], fred: ['DGS10', 'DGS2'] },
    { id: 'gdp', title: 'Real GDP growth', unit: '%', d: 1, robust: true,
      what: 'Quarter-over-quarter change in inflation-adjusted output, at a compound annual rate.',
      series: [{ key: 'gdp_saar', label: 'Real GDP, SAAR', type: 'bar' }], fred: ['GDPC1'] },
    { id: 'sentiment', title: 'Consumer sentiment', unit: '', d: 1, wide: true,
      what: 'University of Michigan index of consumer sentiment (1966 Q1 = 100).',
      series: [{ key: 'umcsent', label: 'Sentiment index', color: '--c3' }], fred: ['UMCSENT'] },
  ];
  const UNIT_SUFFIX = { '%': '%', pp: ' pp', k: 'k', '': '' };

  let SERIES = null, RECESSIONS = [];
  const charts = new Map(); // id -> {chart, def, el}
  const DEFS = new WeakMap(); // canvas -> chart definition (read by the overlay plugin)
  let rangeYears = Number(root.getAttribute('data-range') ?? 10);
  if (![1, 5, 10, 0].includes(rangeYears)) rangeYears = 10;

  /** Columnar JSON -> Chart.js points; isolated missing months become gaps. */
  function toPoints(col) {
    const pts = [];
    for (let i = 0; i < col.t.length; i++) {
      const x = parseDate(col.t[i]).getTime();
      if (i > 0) {
        const gap = (x - pts[pts.length - 1].x) / DAY;
        if (gap > 55 && gap < 66 && col.t.length > 24) {
          const prevGap = i > 1 ? (parseDate(col.t[i - 1]) - parseDate(col.t[i - 2])) / DAY : 31;
          if (prevGap < 35) pts.push({ x: pts[pts.length - 1].x + gap * DAY / 2, y: null });
        }
      }
      pts.push({ x, y: col.v[i] });
    }
    return pts;
  }

  function niceStep(span, target = 4) {
    const raw = span / target;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const n = raw / mag;
    return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
  }

  /** Visible x-window and a y-range fitted to it (robustly for bar charts). */
  function windowFor(entry) {
    const { chart, def } = entry;
    const ds = chart.data.datasets;
    let first = Infinity, last = -Infinity;
    ds.forEach((d) => { const a = d.$all; if (a.length) { first = Math.min(first, a[0].x); last = Math.max(last, a[a.length - 1].x); } });
    const span = last - first;
    const xmin = rangeYears ? Math.max(first, new Date(last).setFullYear(new Date(last).getFullYear() - rangeYears)) : first;
    const pad = (last - xmin) * 0.012;
    let vals = [];
    ds.forEach((d) => { for (const p of d.$all) if (p.x >= xmin && p.y != null) vals.push(p.y); });
    (def.refs || []).forEach((r) => vals.push(r.y));
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const clipped = [];
    if (def.robust) {
      const bar = ds.find((d) => d.type === 'bar');
      const bv = bar.$all.filter((p) => p.x >= xmin && p.y != null).map((p) => p.y).sort((a, b) => a - b);
      if (bv.length > 12) {
        const q = (p) => bv[Math.round(p * (bv.length - 1))];
        const q05 = q(0.05), q95 = q(0.95), spread = Math.max(q95 - q05, 1e-9);
        const rlo = Math.min(q05 - spread, 0), rhi = Math.max(q95 + spread, 0);
        if (lo < rlo || hi > rhi) {
          for (const p of bar.$all) if (p.x >= xmin && p.y != null && (p.y < rlo || p.y > rhi)) clipped.push(p);
          lo = Math.max(lo, rlo); hi = Math.min(hi, rhi);
        }
      }
    }
    if (lo === hi) { lo -= 1; hi += 1; }
    const step = niceStep(hi - lo, matchMedia('(min-width: 560px)').matches ? 5 : 4);
    const tickD = Math.max(0, Math.ceil(-Math.log10(step) - 1e-9));
    return { xmin: xmin - pad, xmax: last + pad, ymin: Math.floor(lo / step) * step, ymax: Math.ceil(hi / step) * step, step, tickD, clipped, span, lastX: last };
  }

  function applyRange(entry, animate) {
    const w = windowFor(entry);
    const { chart, def, el } = entry;
    // Ship only the visible window (plus one point of lead-in) to Chart.js:
    // cheaper to draw and avoids stale off-screen geometry on range changes.
    chart.data.datasets.forEach((d) => {
      const a = d.$all;
      let lo = 0, hi = a.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (a[mid].x < w.xmin) lo = mid + 1; else hi = mid; }
      d.data = a.slice(Math.max(0, lo - 1));
    });
    const o = chart.options.scales;
    o.x.min = w.xmin; o.x.max = w.xmax;
    o.y.min = w.ymin; o.y.max = w.ymax; o.y.ticks.stepSize = w.step; chart.$tickD = w.tickD;
    const yrs = (w.xmax - w.xmin) / (365.25 * DAY);
    o.x.time.unit = yrs <= 1.6 ? 'month' : yrs <= 3.5 ? 'quarter' : 'year';
    const bar = chart.data.datasets.find((d) => d.type === 'bar');
    if (bar) bar.maxBarThickness = yrs <= 1.6 ? 18 : yrs <= 6 ? 7 : undefined;
    chart.update(animate && !reduceMotion ? undefined : 'none');
    const note = $('.clip-note', el);
    if (w.clipped.length) {
      const list = w.clipped.slice(0, 4).map((p) => `${fmtPeriod(new Date(p.x).toISOString().slice(0, 10), def.id === 'gdp' ? 'Q' : 'M')} ${fmt(p.y, def.d, true)}${UNIT_SUFFIX[def.unit]}`);
      note.textContent = `Off scale: ${list.join(' · ')}${w.clipped.length > 4 ? ` and ${w.clipped.length - 4} more` : ''}.`;
      note.hidden = false;
    } else note.hidden = true;
  }

  /* Recession bands, reference lines, and a crosshair, drawn in one plugin. */
  const overlay = {
    id: 'econOverlay',
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales: { x } } = chart;
      ctx.save();
      ctx.fillStyle = css('--band');
      for (const [s, e] of RECESSIONS) {
        const x0 = Math.max(a.left, x.getPixelForValue(s)), x1 = Math.min(a.right, x.getPixelForValue(e));
        if (x1 > a.left && x0 < a.right) ctx.fillRect(x0, a.top, Math.max(1.5, x1 - x0), a.bottom - a.top);
      }
      ctx.restore();
    },
    afterDatasetsDraw(chart) {
      const def = DEFS.get(chart.canvas);
      const { ctx, chartArea: a, scales: { y } } = chart;
      ctx.save();
      for (const r of def.refs || []) {
        const py = Math.round(y.getPixelForValue(r.y)) + 0.5;
        if (py < a.top || py > a.bottom) continue;
        ctx.strokeStyle = r.tone ? css(r.tone) : css('--zero');
        ctx.setLineDash(r.y === 0 && !r.label ? [] : [5, 4]);
        ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.moveTo(a.left, py); ctx.lineTo(a.right, py); ctx.stroke();
        if (r.label) {
          ctx.setLineDash([]);
          ctx.font = '600 11px Inter, system-ui, sans-serif';
          ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
          const tw = ctx.measureText(r.label).width;
          ctx.fillStyle = alphaHex(css('--surface'), 0.85);
          ctx.beginPath(); ctx.roundRect(a.left + 2, py - 17, tw + 10, 15, 4); ctx.fill();
          ctx.fillStyle = r.tone ? css(r.tone) : css('--ink-2');
          ctx.fillText(r.label, a.left + 7, py - 4);
        }
      }
      const act = chart.tooltip?.getActiveElements?.() || [];
      if (act.length) {
        const px = act[0].element.x;
        ctx.strokeStyle = css('--zero'); ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
      }
      ctx.restore();
    },
  };

  /* Interaction: nearest point *per dataset* by date, so series with different
     frequencies (daily yields, monthly fed funds) all show in one tooltip. */
  function registerInteraction() {
    // Pin the tooltip to the top of the plot so a finger or cursor never hides the data.
    Chart.Tooltip.positioners.chartTop = function (items) {
      if (!items.length) return false;
      const a = this.chart.chartArea;
      const x = items[0].element.x;
      return { x: x + (x > (a.left + a.right) / 2 ? -8 : 8), y: a.top + 2, xAlign: x > (a.left + a.right) / 2 ? 'right' : 'left', yAlign: 'top' };
    };
    Chart.Interaction.modes.dateNearest = function (chart, e) {
      const pos = Chart.helpers.getRelativePosition(e, chart);
      const x = chart.scales.x.getValueForPixel(pos.x);
      const items = [];
      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        if (meta.hidden || !ds.data.length) return;
        let lo = 0, hi = ds.data.length - 1;
        while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (ds.data[mid].x < x) lo = mid; else hi = mid; }
        const idx = Math.abs(ds.data[lo].x - x) <= Math.abs(ds.data[hi].x - x) ? lo : hi;
        const p = ds.data[idx];
        if (p.y == null || Math.abs(p.x - x) > ds.$tol) return;
        items.push({ element: meta.data[idx], datasetIndex: di, index: idx });
      });
      return items;
    };
  }

  function colorsFor(def) {
    return def.series.map((s) => (s.type === 'bar' ? { pos: css('--c2'), neg: css('--neg') } : { line: css(s.color) }));
  }

  function buildChart(entry) {
    const { def, el } = entry;
    const canvas = $('canvas', el);
    DEFS.set(canvas, def);
    const cols = colorsFor(def);
    const datasets = def.series.map((s, i) => {
      const data = toPoints(SERIES[s.key]);
      const gaps = []; for (let j = 1; j < Math.min(data.length, 400); j++) gaps.push(data[data.length - j].x - data[data.length - j - 1].x);
      gaps.sort((a, b) => a - b);
      const tol = (gaps[gaps.length >> 1] || 30 * DAY) * 1.6;
      if (s.type === 'bar') {
        return { type: 'bar', label: s.label, data, $all: data, $tol: tol, order: 2,
          backgroundColor: (c) => (c.raw && c.raw.y < 0 ? cols[i].neg : cols[i].pos),
          borderWidth: 0, borderRadius: 2, barPercentage: 0.9, categoryPercentage: 1, grouped: false };
      }
      const ds = { type: 'line', label: s.label, data, $all: data, $tol: tol, order: 1, borderColor: cols[i].line, borderWidth: 2,
        pointRadius: 0, pointHoverRadius: 4, pointHoverBorderWidth: 2, pointHoverBackgroundColor: css('--surface'),
        tension: 0, stepped: s.stepped ? 'after' : false, spanGaps: false };
      if (s.fillZero) {
        ds.fill = { target: { value: 0 }, above: alpha(css('--c2'), 0.16), below: alpha(css('--neg'), 0.28) };
      }
      return ds;
    });
    const muted = css('--muted');
    const chart = new Chart(canvas, {
      data: { datasets },
      options: {
        parsing: false, normalized: true, responsive: true, maintainAspectRatio: false,
        animation: false, // first paint is static; range changes animate (enabled below)
        interaction: { mode: 'dateNearest', intersect: false },
        layout: { padding: { top: 4, right: 2 } },
        events: ['mousemove', 'mouseout', 'click', 'touchstart', 'touchmove'],
        scales: {
          x: { type: 'time', time: { unit: 'year', tooltipFormat: 'MMM d, yyyy', displayFormats: { month: 'MMM yy', quarter: 'MMM yy', year: 'yyyy' } },
            grid: { display: false }, border: { color: css('--line') },
            ticks: { color: muted, maxRotation: 0, autoSkip: true, autoSkipPadding: 14, font: { size: 11 } } },
          y: { position: 'right', grid: { color: css('--grid'), drawTicks: false }, border: { display: false },
            ticks: { color: muted, padding: 6, font: { size: 11 }, callback(v) { return `${fmt(v, this.chart.$tickD ?? 0)}${UNIT_SUFFIX[def.unit]}`; } } },
        },
        plugins: {
          legend: { display: false },
          decimation: { enabled: false },
          tooltip: {
            backgroundColor: alphaHex(css('--surface'), 0.94), titleColor: css('--ink'), bodyColor: css('--ink-2'), borderColor: css('--line'), borderWidth: 1,
            position: 'chartTop', padding: 10, cornerRadius: 10, boxPadding: 4, usePointStyle: true, caretSize: 0, displayColors: true,
            titleFont: { weight: '600', size: 12.5 }, bodyFont: { size: 12.5 },
            callbacks: {
              title: (items) => {
                if (!items.length) return '';
                const f = def.id === 'gdp' ? 'Q' : ['rates', 'curve'].includes(def.id) ? 'D' : 'M';
                return fmtPeriod(new Date(items[0].raw.x).toISOString().slice(0, 10), f);
              },
              label: (c) => ` ${c.dataset.label}: ${fmt(c.raw.y, def.d, def.unit === 'k' || def.unit === 'pp')}${UNIT_SUFFIX[def.unit]}`,
              labelColor: (c) => {
                const col = c.dataset.type === 'bar' ? (c.raw.y < 0 ? css('--neg') : css('--c2')) : c.dataset.borderColor;
                return { borderColor: col, backgroundColor: col };
              },
            },
          },
        },
      },
      plugins: [overlay],
    });
    entry.chart = chart;
    const last = def.series.map((s) => { const c = SERIES[s.key]; return c.v[c.v.length - 1]; });
    canvas.setAttribute('aria-label', `${def.title} chart. Latest: ${def.series.map((s, i) => `${s.label} ${fmt(last[i], def.d)}${UNIT_SUFFIX[def.unit]}`).join(', ')}. Recessions shaded.`);
    applyRange(entry, false);
    if (!reduceMotion) chart.options.animation = { duration: 450, easing: 'easeOutQuart' };
  }

  function recolorCharts() {
    charts.forEach((entry) => {
      const { chart, def } = entry;
      if (!chart) return;
      const cols = colorsFor(def);
      chart.data.datasets.forEach((ds, i) => {
        if (ds.type === 'line') {
          ds.borderColor = cols[i].line; ds.pointHoverBackgroundColor = css('--surface');
          if (def.series[i].fillZero) ds.fill = { target: { value: 0 }, above: alpha(css('--c2'), 0.16), below: alpha(css('--neg'), 0.28) };
        } else ds.backgroundColor = (c) => (c.raw && c.raw.y < 0 ? cols[i].neg : cols[i].pos);
      });
      const o = chart.options, muted = css('--muted');
      o.scales.x.ticks.color = muted; o.scales.y.ticks.color = muted; o.scales.x.border.color = css('--line'); o.scales.y.grid.color = css('--grid');
      Object.assign(o.plugins.tooltip, { backgroundColor: alphaHex(css('--surface'), 0.94), titleColor: css('--ink'), bodyColor: css('--ink-2'), borderColor: css('--line') });
      chart.update('none');
    });
  }

  function chartCard(def) {
    const legend = def.series.map((s) => {
      const c = SERIES[s.key];
      const last = c.v[c.v.length - 1];
      const sw = s.type === 'bar' ? '<i class="box" style="background:var(--c2)"></i>' : `<i style="color:var(${s.color})"></i>`;
      return `<li>${sw}${esc(s.label)} <b>${fmt(last, def.d, def.unit === 'k' || def.unit === 'pp')}${UNIT_SUFFIX[def.unit]}</b></li>`;
    });
    (def.refs || []).filter((r) => r.label).forEach((r) => legend.push(`<li><i class="dash" style="color:var(${r.tone || '--zero'})"></i>${esc(r.label)}</li>`));
    legend.push('<li><i class="box" style="background:var(--band);outline:1px solid var(--line)"></i>Recession</li>');
    const asOf = def.series.map((s) => SERIES[s.key].t.at(-1)).sort().at(-1);
    const freq = def.id === 'gdp' ? 'Q' : ['rates', 'curve'].includes(def.id) ? 'D' : 'M';
    const links = def.fred.map((id) => `<a href="https://fred.stlouisfed.org/series/${id}" target="_blank" rel="noopener">${id}<span class="sr"> on FRED (opens in a new tab)</span></a>`).join(', ');
    const el = document.createElement('article');
    el.className = `chart-card${def.wide ? ' wide' : ''}`;
    el.id = `chart-${def.id}`;
    el.setAttribute('aria-labelledby', `h-${def.id}`);
    el.innerHTML = `
      <h3 id="h-${def.id}">${esc(def.title)}</h3>
      <p class="what">${esc(def.what)}</p>
      <ul class="legend">${legend.join('')}</ul>
      <div class="canvas-box"><canvas role="img" aria-label="${esc(def.title)} chart"></canvas></div>
      <p class="clip-note" hidden></p>
      <div class="chart-foot"><span>Latest: ${fmtPeriod(asOf, freq)}</span><span>FRED: ${links}</span></div>`;
    return el;
  }

  function renderCharts(series) {
    SERIES = series.series;
    RECESSIONS = series.recessions.map(([a, b]) => {
      const e = parseDate(b);
      return [parseDate(a).getTime(), new Date(e.getFullYear(), e.getMonth() + 1, 1).getTime()];
    });
    registerInteraction();
    Chart.defaults.font.family = 'Inter, "Inter Fallback", system-ui, sans-serif';
    const grid = $('#chart-grid');
    const io = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        const entry = charts.get(en.target.id);
        if (entry && !entry.chart) buildChart(entry);
      });
    }, { rootMargin: '300px 0px' }) : null;
    CHARTS.forEach((def) => {
      if (!def.series.every((s) => SERIES[s.key]?.t?.length)) return;
      const el = chartCard(def);
      grid.appendChild(el);
      const entry = { def, el, chart: null };
      charts.set(el.id, entry);
      if (io) io.observe(el); else buildChart(entry);
    });
  }

  /* ------------------------------------------------------------ range bar */
  const rangeBtns = document.querySelectorAll('.rangebar button');
  function syncRange() {
    rangeBtns.forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.range) === rangeYears)));
  }
  rangeBtns.forEach((b) => b.addEventListener('click', () => {
    rangeYears = Number(b.dataset.range);
    try { localStorage.setItem('econ-range', String(rangeYears)); } catch (e) { /* ignore */ }
    syncRange();
    charts.forEach((entry) => entry.chart && applyRange(entry, true));
  }));
  syncRange();

  /* ------------------------------------------------------------ boot */
  const fail = (where, err) => {
    console.error(err);
    where.innerHTML = '<p class="load-error" role="alert">Couldn\u2019t load the latest data. Please refresh in a moment.</p>';
  };
  summaryP.then((s) => {
    renderStamp(s); renderSignals(s); renderKPIs(s); renderNotes(s); renderInversions(s);
  }).catch((e) => { fail($('#signal-grid'), e); $('#kpi-grid').innerHTML = ''; $('#stamp').textContent = ''; });

  const chartLibReady = new Promise((resolve) => {
    if (window.Chart) resolve(); else window.addEventListener('DOMContentLoaded', resolve, { once: true });
  });
  Promise.all([seriesP, chartLibReady]).then(([series]) => {
    if (!window.Chart) throw new Error('Chart.js failed to load');
    renderCharts(series);
  }).catch((e) => fail($('#chart-grid'), e));

  syncTheme();
})();
