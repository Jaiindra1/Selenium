import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import express from "express";
import { assertPublicStoreUrl } from "./url-safety.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const dataDir = process.env.DATA_DIR || path.join(root, "data");
const reportDir = process.env.REPORT_DIR || path.join(dataDir, "reports");
fs.mkdirSync(reportDir, { recursive: true });

const db = new Database(path.join(dataDir, "dealscope.db"));
db.pragma("journal_mode = WAL");
db.exec(`CREATE TABLE IF NOT EXISTS scrapes (
  id TEXT PRIMARY KEY,
  website TEXT NOT NULL,
  query TEXT NOT NULL,
  status TEXT NOT NULL,
  product_count INTEGER NOT NULL DEFAULT 0,
  products_json TEXT NOT NULL DEFAULT '[]',
  report_path TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
)`);

const app = express();
app.use(express.json({ limit: "32kb" }));

const selectPublic = `SELECT id, website, query, status, product_count AS productCount,
  error, created_at AS createdAt, completed_at AS completedAt FROM scrapes`;

function runScraper(website, query) {
  const executable = process.env.PYTHON_BIN || (process.platform === "win32" ? "py" : "python3");
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [path.join(root, "api_scrape.py"), website, query], {
      cwd: root,
      env: {
        ...process.env,
        HEADLESS: "true",
        REPORT_DIR: reportDir,
        PYTHONIOENCODING: "utf-8",
        PYTHONUTF8: "1",
      },
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", () => {
      const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
      try {
        const result = JSON.parse(lines.at(-1) || "{}");
        if (!result.ok) reject(new Error(result.error || stderr || "Scrape failed"));
        else resolve(result.data);
      } catch (error) {
        reject(new Error(stderr || error.message || "Scraper returned an invalid response"));
      }
    });
  });
}

app.get("/api/health", (_req, res) => res.json({ ok: true }));

app.get("/api/scrapes", (_req, res) => {
  res.json(db.prepare(`${selectPublic} ORDER BY created_at DESC LIMIT 30`).all());
});

app.get("/api/scrapes/:id", (req, res) => {
  const row = db.prepare(`SELECT * FROM scrapes WHERE id = ?`).get(req.params.id);
  if (!row) return res.status(404).json({ error: "Scrape not found" });
  res.json({
    id: row.id, website: row.website, query: row.query, status: row.status,
    productCount: row.product_count, products: JSON.parse(row.products_json),
    error: row.error, createdAt: row.created_at, completedAt: row.completed_at,
    reportUrl: row.report_path ? `/api/scrapes/${row.id}/report` : null,
  });
});

app.get("/api/scrapes/:id/report", (req, res) => {
  const row = db.prepare("SELECT report_path, query FROM scrapes WHERE id = ?").get(req.params.id);
  if (!row?.report_path || !fs.existsSync(row.report_path)) {
    return res.status(404).json({ error: "Report not found" });
  }
  res.download(row.report_path, `dealscope-${row.query.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.pdf`);
});

app.post("/api/scrapes", async (req, res) => {
  const websiteInput = String(req.body.website || "").trim();
  const query = String(req.body.query || "").trim();
  if (!websiteInput || !query || websiteInput.length > 300 || query.length > 120) {
    return res.status(400).json({ error: "Enter a store URL and a product search term" });
  }

  let website;
  try {
    website = await assertPublicStoreUrl(websiteInput);
  } catch (error) {
    return res.status(400).json({ error: error.message });
  }

  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  db.prepare("INSERT INTO scrapes (id, website, query, status, created_at) VALUES (?, ?, ?, 'running', ?)")
    .run(id, website, query, createdAt);

  try {
    const result = await runScraper(website, query);
    const completedAt = new Date().toISOString();
    db.prepare(`UPDATE scrapes SET status = 'completed', product_count = ?, products_json = ?,
      report_path = ?, completed_at = ? WHERE id = ?`)
      .run(result.products.length, JSON.stringify(result.products), result.reportPath, completedAt, id);
    res.status(201).json({ id, status: "completed", productCount: result.products.length });
  } catch (error) {
    const message = String(error.message || "Scrape failed").slice(0, 1000);
    db.prepare("UPDATE scrapes SET status = 'failed', error = ?, completed_at = ? WHERE id = ?")
      .run(message, new Date().toISOString(), id);
    res.status(502).json({ id, error: message });
  }
});

const clientDist = path.join(root, "client", "dist");
if (fs.existsSync(clientDist)) {
  app.use(express.static(clientDist));
  app.get("/*splat", (_req, res) => res.sendFile(path.join(clientDist, "index.html")));
}

const port = Number(process.env.PORT || 3000);
app.listen(port, "0.0.0.0", () => console.log(`DealScope listening on http://0.0.0.0:${port}`));
