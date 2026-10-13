const express = require("express");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const sqlite3 = require("sqlite3");
const { open } = require("sqlite");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const dns = require("node:dns").promises;
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const app = express();
const root = path.resolve(__dirname, "..");
const dbPath = process.env.DATABASE_PATH || path.join(__dirname, "database.db");
const reportDir = process.env.REPORT_DIR || path.join(root, "data", "reports");
const jwtSecret = process.env.JWT_SECRET || "dealsense-local-development-secret-change-in-production";
let db;

fs.mkdirSync(reportDir, { recursive: true });
app.use(express.json({ limit: "32kb" }));
const allowedOrigins = new Set([
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  ...String(process.env.FRONTEND_URL || "").split(",").map((value) => value.trim()).filter(Boolean),
]);
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && allowedOrigins.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS");
  }
  if (req.method === "OPTIONS") return res.status(204).end();
  next();
});

function normalizeSite(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) throw new Error("Website name is required");
  const url = new URL(/^https?:\/\//.test(raw) ? raw : `https://${raw}`);
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".")) throw new Error("Enter a valid public website such as example.com");
  url.pathname = "/"; url.search = ""; url.hash = "";
  return url.toString();
}

function isPrivateIp(ip) {
  return ip === "::1" || ip.startsWith("127.") || ip.startsWith("10.") || ip.startsWith("192.168.") || /^172\.(1[6-9]|2\d|3[01])\./.test(ip) || ip.startsWith("169.254.") || ip.startsWith("fc") || ip.startsWith("fd");
}

async function assertPublicSite(value) {
  const normalized = normalizeSite(value);
  const url = new URL(normalized);
  if (url.hostname === "localhost" || (net.isIP(url.hostname) && isPrivateIp(url.hostname))) throw new Error("Private websites are not allowed");
  const records = await dns.lookup(url.hostname, { all: true });
  if (!records.length || records.some((record) => isPrivateIp(record.address))) throw new Error("Website must resolve to a public address");
  return normalized;
}

function tokenFor(user) { return jwt.sign({ id: user.id, email: user.email, role: user.role, username: user.username }, jwtSecret, { expiresIn: "7d" }); }
function auth(requiredRole) {
  return (req, res, next) => {
    try {
      req.user = jwt.verify(String(req.headers.authorization || "").replace(/^Bearer\s+/i, ""), jwtSecret);
      if (requiredRole && req.user.role !== requiredRole) return res.status(403).json({ error: "Administrator access required" });
      next();
    } catch { res.status(401).json({ error: "Please sign in to continue" }); }
  };
}

function runScraper(website, query) {
  const venvPython = process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
  const executable = process.env.PYTHON_BIN || (fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "py" : "python3"));
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [path.join(root, "api_scrape.py"), website, query], { cwd: root, env: { ...process.env, HEADLESS: "true", REPORT_DIR: reportDir, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }, windowsHide: true });
    let stdout = "", stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", reject);
    child.on("close", () => {
      try {
        const payload = JSON.parse(stdout.trim().split(/\r?\n/).filter(Boolean).at(-1) || "{}");
        if (!payload.ok) return reject(new Error(payload.error || stderr || "Scrape failed"));
        resolve(payload.data);
      } catch (error) { reject(new Error(stderr || error.message)); }
    });
  });
}

function publicUser(row) { return { id: row.id, username: row.username, email: row.email, role: row.role }; }
function host(value) { try { return new URL(value).hostname.replace(/^www\./, ""); } catch { return value; } }
function priceNumber(value) { const match = String(value || "").replace(/,/g, "").match(/\d+(?:\.\d+)?/); return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER; }
function productKey(product) {
  const identity = String(product.product_url || `${product.brand || ""}:${product.name || ""}`).toLowerCase().replace(/[?#].*$/, "");
  return crypto.createHash("sha256").update(identity).digest("hex");
}

async function storeProducts(site, searchId, products) {
  for (const product of products) {
    const key = productKey(product);
    await db.run(`INSERT INTO products
      (website_id, product_key, name, product_url, image_url, brand, description, specifications_json, availability, source_data_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(website_id, product_key) DO UPDATE SET
        name=excluded.name, product_url=excluded.product_url, image_url=excluded.image_url,
        brand=excluded.brand, description=excluded.description, specifications_json=excluded.specifications_json,
        availability=excluded.availability, source_data_json=excluded.source_data_json, last_seen=CURRENT_TIMESTAMP`,
      site.id, key, product.name, product.product_url, product.image_url, product.brand, product.description,
      JSON.stringify(product.specifications || []), product.availability, JSON.stringify(product));
    const saved = await db.get("SELECT id FROM products WHERE website_id = ? AND product_key = ?", site.id, key);
    await db.run(`INSERT INTO price_history
      (product_id, search_id, price, price_value, original_price, discount, currency, rating)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`, saved.id, searchId, product.price, priceNumber(product.price) === Number.MAX_SAFE_INTEGER ? null : priceNumber(product.price), product.original_price, product.discount, product.currency, product.rating);
  }
}

async function initializeDBAndServer() {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  db = await open({ filename: dbPath, driver: sqlite3.Database });
  await db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
  await db.exec(`CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS websites (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, url TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS searches (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, query TEXT NOT NULL, status TEXT NOT NULL, results_json TEXT NOT NULL DEFAULT '[]', errors_json TEXT NOT NULL DEFAULT '[]', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME, FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, website_id INTEGER NOT NULL, product_key TEXT NOT NULL, name TEXT NOT NULL, product_url TEXT, image_url TEXT, brand TEXT, description TEXT, specifications_json TEXT NOT NULL DEFAULT '[]', availability TEXT, source_data_json TEXT NOT NULL DEFAULT '{}', first_seen DATETIME DEFAULT CURRENT_TIMESTAMP, last_seen DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(website_id, product_key), FOREIGN KEY(website_id) REFERENCES websites(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, search_id TEXT NOT NULL, price TEXT, price_value REAL, original_price TEXT, discount TEXT, currency TEXT, rating TEXT, observed_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE, FOREIGN KEY(search_id) REFERENCES searches(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS search_errors (id INTEGER PRIMARY KEY AUTOINCREMENT, search_id TEXT NOT NULL, user_id INTEGER NOT NULL, website_id INTEGER, website_name TEXT NOT NULL, query TEXT NOT NULL, error TEXT NOT NULL, occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(search_id) REFERENCES searches(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES Users(id) ON DELETE CASCADE, FOREIGN KEY(website_id) REFERENCES websites(id) ON DELETE SET NULL);
    CREATE INDEX IF NOT EXISTS idx_prices_product_time ON price_history(product_id, observed_at DESC);
    CREATE INDEX IF NOT EXISTS idx_errors_time ON search_errors(occurred_at DESC);`);
  const columns = await db.all("PRAGMA table_info(Users)");
  if (!columns.some((column) => column.name === "role")) await db.exec("ALTER TABLE Users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'");
  const adminHash = await bcrypt.hash("Password123", 12);
  await db.run(`INSERT INTO Users (username, email, password, role) VALUES (?, ?, ?, 'admin') ON CONFLICT(email) DO UPDATE SET username = excluded.username, password = excluded.password, role = 'admin'`, "Administrator", "admin@gmail.com", adminHash);
  const port = Number(process.env.PORT || 3000);
  app.listen(port, "0.0.0.0", () => console.log(`DealSense running at http://localhost:${port}`));
}

app.get("/api/health", (_req, res) => res.json({ ok: true }));
app.post("/api/auth/signup", async (req, res) => {
  try {
    const username = String(req.body.username || "").trim(), email = String(req.body.email || "").trim().toLowerCase(), password = String(req.body.password || "");
    if (username.length < 2 || !/^\S+@\S+\.\S+$/.test(email) || password.length < 8) return res.status(400).json({ error: "Enter a name, valid email, and password of at least 8 characters" });
    const hash = await bcrypt.hash(password, 12);
    const result = await db.run("INSERT INTO Users (username, email, password, role) VALUES (?, ?, ?, 'user')", username, email, hash);
    const user = { id: result.lastID, username, email, role: "user" };
    res.status(201).json({ token: tokenFor(user), user });
  } catch (error) {
    if (String(error.message).includes("UNIQUE")) return res.status(409).json({ error: "An account with this email already exists" });
    res.status(500).json({ error: "Could not create your account" });
  }
});

app.post("/api/auth/login", async (req, res) => {
  const row = await db.get("SELECT * FROM Users WHERE email = ?", String(req.body.email || "").trim().toLowerCase());
  if (!row || !(await bcrypt.compare(String(req.body.password || ""), row.password))) return res.status(401).json({ error: "Incorrect email or password" });
  const user = publicUser(row);
  res.json({ token: tokenFor(user), user });
});

app.get("/api/auth/me", auth(), async (req, res) => {
  const row = await db.get("SELECT id, username, email, role FROM Users WHERE id = ?", req.user.id);
  if (!row) return res.status(401).json({ error: "Account not found" });
  res.json({ user: row });
});

app.get("/api/websites", auth(), async (_req, res) => res.json(await db.all("SELECT * FROM websites ORDER BY created_at DESC")));
app.post("/api/websites", auth("admin"), async (req, res) => {
  try {
    const url = await assertPublicSite(req.body.url || req.body.name), name = host(url);
    const result = await db.run("INSERT INTO websites (name, url) VALUES (?, ?)", name, url);
    res.status(201).json(await db.get("SELECT * FROM websites WHERE id = ?", result.lastID));
  } catch (error) {
    const duplicate = String(error.message).includes("UNIQUE");
    res.status(duplicate ? 409 : 400).json({ error: duplicate ? "That website is already listed" : error.message });
  }
});
app.patch("/api/websites/:id", auth("admin"), async (req, res) => { await db.run("UPDATE websites SET active = ? WHERE id = ?", req.body.active ? 1 : 0, req.params.id); res.json(await db.get("SELECT * FROM websites WHERE id = ?", req.params.id)); });
app.delete("/api/websites/:id", auth("admin"), async (req, res) => { await db.run("DELETE FROM websites WHERE id = ?", req.params.id); res.status(204).end(); });

app.get("/api/searches", auth(), async (req, res) => {
  const rows = await db.all("SELECT id, query, status, results_json, errors_json, created_at, completed_at FROM searches WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", req.user.id);
  res.json(rows.map((row) => ({ id: row.id, query: row.query, status: row.status, resultCount: JSON.parse(row.results_json).length, createdAt: row.created_at, completedAt: row.completed_at })));
});
app.get("/api/searches/:id", auth(), async (req, res) => {
  const row = await db.get("SELECT * FROM searches WHERE id = ? AND user_id = ?", req.params.id, req.user.id);
  if (!row) return res.status(404).json({ error: "Search not found" });
  res.json({ id: row.id, query: row.query, status: row.status, results: JSON.parse(row.results_json), createdAt: row.created_at, completedAt: row.completed_at });
});
app.post("/api/searches", auth(), async (req, res) => {
  const query = String(req.body.query || "").trim();
  if (query.length < 2 || query.length > 120) return res.status(400).json({ error: "Enter a product name between 2 and 120 characters" });
  const sites = await db.all("SELECT id, name, url FROM websites WHERE active = 1 ORDER BY name");
  if (!sites.length) return res.status(400).json({ error: "No active shopping websites are configured. Ask the administrator to add one." });
  const id = crypto.randomUUID();
  await db.run("INSERT INTO searches (id, user_id, query, status) VALUES (?, ?, ?, 'running')", id, req.user.id, query);
  const results = [], errors = [];
  for (const site of sites) {
    try {
      const scraped = await runScraper(site.url, query);
      await storeProducts(site, id, scraped.products);
      results.push(...scraped.products.map((product) => ({ ...product, website: site.name, websiteUrl: site.url })));
    } catch (error) {
      const message = String(error.message || "Search failed").slice(0, 1000);
      errors.push({ website: site.name, error: message });
      await db.run("INSERT INTO search_errors (search_id, user_id, website_id, website_name, query, error) VALUES (?, ?, ?, ?, ?, ?)", id, req.user.id, site.id, site.name, query, message);
    }
  }
  results.sort((a, b) => priceNumber(a.price) - priceNumber(b.price));
  const status = results.length ? "completed" : "failed";
  await db.run("UPDATE searches SET status = ?, results_json = ?, errors_json = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?", status, JSON.stringify(results), JSON.stringify(errors), id);
  res.status(201).json({ id, query, status, results });
});

app.get("/api/admin/stats", auth("admin"), async (_req, res) => {
  const users = await db.get("SELECT COUNT(*) count FROM Users WHERE role = 'user'"), websites = await db.get("SELECT COUNT(*) count, SUM(active) active FROM websites"), searches = await db.get("SELECT COUNT(*) count FROM searches"), products = await db.get("SELECT COUNT(*) count FROM products");
  res.json({ users: users.count, websites: websites.count, activeWebsites: websites.active || 0, searches: searches.count, products: products.count });
});

app.get("/api/admin/errors", auth("admin"), async (_req, res) => {
  res.json(await db.all(`SELECT e.id, e.query, e.website_name AS website, e.error, e.occurred_at AS occurredAt,
    u.username, u.email FROM search_errors e JOIN Users u ON u.id = e.user_id ORDER BY e.occurred_at DESC LIMIT 200`));
});

app.get("/api/admin/products", auth("admin"), async (_req, res) => {
  res.json(await db.all(`SELECT p.id, p.name, p.product_url AS productUrl, p.image_url AS imageUrl,
    p.brand, p.availability, p.specifications_json AS specifications, p.first_seen AS firstSeen,
    p.last_seen AS lastSeen, w.name AS website,
    (SELECT price FROM price_history WHERE product_id = p.id ORDER BY observed_at DESC, id DESC LIMIT 1) AS latestPrice,
    (SELECT observed_at FROM price_history WHERE product_id = p.id ORDER BY observed_at DESC, id DESC LIMIT 1) AS latestPriceAt,
    (SELECT COUNT(*) FROM price_history WHERE product_id = p.id) AS observationCount
    FROM products p JOIN websites w ON w.id = p.website_id ORDER BY p.last_seen DESC LIMIT 500`));
});

app.get("/api/admin/products/:id/prices", auth("admin"), async (req, res) => {
  res.json(await db.all(`SELECT ph.price, ph.price_value AS priceValue, ph.original_price AS originalPrice,
    ph.discount, ph.currency, ph.rating, ph.observed_at AS observedAt, w.name AS website
    FROM price_history ph JOIN products p ON p.id = ph.product_id JOIN websites w ON w.id = p.website_id
    WHERE p.id = ? ORDER BY ph.observed_at DESC`, req.params.id));
});

const clientDist = path.join(root, "client", "dist");
if (fs.existsSync(clientDist)) { app.use(express.static(clientDist)); app.get("/*splat", (_req, res) => res.sendFile(path.join(clientDist, "index.html"))); }
initializeDBAndServer().catch((error) => { console.error(`DB Error: ${error.message}`); process.exit(1); });
