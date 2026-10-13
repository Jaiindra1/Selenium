import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Clock3, Download, ExternalLink, Search, Sparkles, Store, X } from "lucide-react";

const examples = [
  ["amazon.in", "Sony WH-1000XM5"],
  ["flipkart.com", "Google Pixel 9"],
  ["ebay.com", "Mechanical keyboard"],
];

function hostname(value) {
  try { return new URL(value).hostname.replace(/^www\./, ""); } catch { return value; }
}

function App() {
  const [website, setWebsite] = useState("");
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState([]);
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const completed = useMemo(() => history.filter((item) => item.status === "completed").length, [history]);

  async function loadHistory() {
    const response = await fetch("/api/scrapes");
    if (response.ok) setHistory(await response.json());
  }

  useEffect(() => { loadHistory().catch(() => setError("Could not load search history.")); }, []);

  async function openScrape(id) {
    setError("");
    const response = await fetch(`/api/scrapes/${id}`);
    const data = await response.json();
    if (!response.ok) return setError(data.error || "Could not load this search.");
    setActive(data);
  }

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setActive(null);
    try {
      const response = await fetch("/api/scrapes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ website, query }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "The search could not be completed.");
      await loadHistory();
      await openScrape(data.id);
    } catch (err) {
      setError(err.message);
      await loadHistory();
    } finally {
      setLoading(false);
    }
  }

  function useExample([store, term]) { setWebsite(store); setQuery(term); }

  return <div className="app-shell">
    <header className="nav">
      <a className="brand" href="#top" aria-label="DealScope home"><span className="brand-mark"><Sparkles size={18}/></span>DealScope</a>
      <div className="nav-status"><span></span> Research workspace</div>
    </header>

    <main id="top">
      <section className="hero">
        <div className="eyebrow">ECOMMERCE INTELLIGENCE</div>
        <h1>Find the signal<br/>in a sea of <em>deals.</em></h1>
        <p>Search a store, collect structured product details, and keep every finding in one calm workspace.</p>

        <form className="search-panel" onSubmit={submit}>
          <label><span>Store website</span><div className="input-wrap"><Store size={19}/><input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="amazon.in" required /></div></label>
          <label><span>What are you looking for?</span><div className="input-wrap"><Search size={19}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Noise cancelling headphones" required /></div></label>
          <button type="submit" disabled={loading}>{loading ? <><span className="spinner"/>Researching…</> : <>Start research <ArrowUpRight size={19}/></>}</button>
        </form>

        <div className="examples"><span>Try an example</span>{examples.map((item) => <button key={item.join()} onClick={() => useExample(item)}>{item[1]}</button>)}</div>
        {error && <div className="error" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss"><X size={16}/></button></div>}
      </section>

      <section className="workspace">
        <div className="section-head"><div><div className="eyebrow">YOUR RESEARCH</div><h2>Recent searches</h2></div><div className="metric"><strong>{completed}</strong><span>completed</span></div></div>
        {history.length === 0 ? <div className="empty"><Search size={28}/><h3>Your research starts here</h3><p>Run your first product search and the results will be saved in this workspace.</p></div> :
          <div className="history-grid">{history.map((item) => <button className="history-card" key={item.id} onClick={() => openScrape(item.id)}>
            <div className="history-icon">{hostname(item.website).charAt(0).toUpperCase()}</div>
            <div className="history-copy"><strong>{item.query}</strong><span>{hostname(item.website)}</span><small><Clock3 size={13}/>{new Date(item.createdAt).toLocaleString()}</small></div>
            <div className={`status ${item.status}`}>{item.status === "completed" ? `${item.productCount} items` : item.status}</div>
          </button>)}</div>}
      </section>

      {active && <section className="results">
        <div className="section-head"><div><div className="eyebrow">RESULTS FROM {hostname(active.website).toUpperCase()}</div><h2>{active.query}</h2></div>{active.reportUrl && <a className="download" href={active.reportUrl}><Download size={17}/> Download PDF</a>}</div>
        {active.products.length === 0 ? <div className="empty"><h3>No products were extracted</h3><p>The store may require verification or a site-specific selector.</p></div> :
        <div className="product-grid">{active.products.map((product, index) => <article className="product-card" key={`${product.product_url}-${index}`}>
          <div className="product-image">{product.image_url ? <img src={product.image_url} alt="" loading="lazy"/> : <Store size={28}/>}</div>
          <div className="product-body"><span className="source">{product.brand || hostname(active.website)}</span><h3>{product.name}</h3><div className="product-meta"><strong>{product.price || "Price unavailable"}</strong>{product.rating && <span>★ {product.rating}</span>}</div>
          {product.product_url && <a href={product.product_url} target="_blank" rel="noreferrer">View product <ExternalLink size={14}/></a>}</div>
        </article>)}</div>}
      </section>}
    </main>
    <footer><span>DealScope</span><p>Research responsibly. Store availability and prices may change.</p></footer>
  </div>;
}

export default App;
