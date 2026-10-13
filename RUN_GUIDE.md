# DealScope Run Guide

This guide explains how to run the React frontend, Node.js backend, and Python Selenium scraper on Windows.

## Prerequisites

Install the following software:

- Node.js 22 or later
- Python 3.10 or later
- Google Chrome
- Git

Open PowerShell in the project directory:

```powershell
cd C:\Users\mi423\Downloads\ecommerce_scraper_project
```

## One-time setup

Create and activate a Python virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the Python and Node.js dependencies:

```powershell
python -m pip install -r requirements.txt
npm install
```

If PowerShell blocks virtual-environment activation, run Python through the launcher instead:

```powershell
py -m pip install -r requirements.txt
```

## Run each part separately

Use a separate PowerShell terminal for each part.

### Terminal 1: Node.js backend

```powershell
cd C:\Users\mi423\Downloads\ecommerce_scraper_project\server
npm run dev
```

The backend runs at:

```text
http://localhost:3000
```

Test its health endpoint:

```text
http://localhost:3000/api/health
```

### Terminal 2: React frontend

```powershell
cd C:\Users\mi423\Downloads\ecommerce_scraper_project\client
npm run dev
```

Open the Vite URL printed in the terminal, normally:

```text
http://localhost:5173
```

Vite forwards `/api` requests to the Node.js backend on port `3000`.

### Terminal 3: Standalone Python scraper (optional)

`main.py` is an interactive standalone scraper, not a web server. It is optional and is not required while using the dashboard.

```powershell
cd C:\Users\mi423\Downloads\ecommerce_scraper_project
.\.venv\Scripts\Activate.ps1
python main.py
```

The web backend starts `api_scrape.py` itself whenever a dashboard user searches for a product.

## Production mode

Build the React application:

```powershell
npm run build
```

Start the Node.js server:

```powershell
npm start
```

Open:

```text
http://localhost:3000
```

## Deploy frontend on Vercel and backend on Render

### Render backend and Python

Create the Render service from the repository root using `render.yaml`. The Docker service contains Node.js, Python, Chromium, ChromeDriver, Selenium, and the persistent SQLite disk.

Set this Render environment variable after the Vercel project has a URL:

```text
FRONTEND_URL=https://your-project.vercel.app
```

Render automatically configures `DATABASE_PATH`, `REPORT_DIR`, `PYTHON_BIN`, `CHROME_BIN`, `HEADLESS`, and a generated `JWT_SECRET` from `render.yaml`.

### Vercel frontend

Import the same GitHub repository into Vercel and set the project Root Directory to:

```text
client
```

Add this Vercel environment variable for Production, Preview, and Development as needed:

```text
VITE_API_URL=https://your-render-service.onrender.com
```

Do not include `/api` at the end. Redeploy Vercel after changing `VITE_API_URL`, because Vite embeds it during the build.

In production mode, Express serves the compiled React files from `client/dist` and handles all `/api` requests.

## Run only the Python command-line scraper

The original interactive Python program can run independently of the web application:

```powershell
cd C:\Users\mi423\Downloads\ecommerce_scraper_project
.\.venv\Scripts\Activate.ps1
python main.py
```

If the virtual-environment Python is blocked by Windows application-control policy, use:

```powershell
py main.py
```

The program asks for:

1. An e-commerce website, such as `amazon.in`.
2. A product search term, such as `wireless headphones`.

It opens Chrome, extracts available product information, and saves a PDF report in the user's Downloads directory.

## How the web application runs Python

You do not need to start `main.py` while using the web application. The Node.js API automatically starts `api_scrape.py` for every web search:

```text
React → Node.js API → api_scrape.py → Selenium/Chrome
                    ↓
                  SQLite
```

`main.py` is only for the standalone interactive terminal experience. `api_scrape.py` provides the non-interactive JSON interface used by Node.js.

## Data and reports

The web application stores runtime files under:

```text
data/
├── dealscope.db
└── reports/
```

These files are ignored by Git. You can override their locations with environment variables:

```powershell
$env:DATA_DIR = "C:\dealscope-data"
$env:REPORT_DIR = "C:\dealscope-data\reports"
npm start
```

## Run tests

Run the Node.js and Python tests together:

```powershell
npm test
```

Run them separately:

```powershell
npm run test -w server
py -m pytest -q
```

## Stop the application

Press `Ctrl+C` in each PowerShell terminal that is running a development or production server.

## Common problems

### Port 3000 is already in use

The application may already be running in another terminal. Stop that process with `Ctrl+C`, or select another port:

```powershell
$env:PORT = "4000"
npm start
```

### Chrome does not start

Confirm that Google Chrome is installed and update Selenium:

```powershell
py -m pip install --upgrade selenium
```

### Rupee symbol encoding error

The web application already forces UTF-8 for its Python subprocess. For a manual Python run, set:

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
py main.py
```

### A store returns no products

The store may have changed its page structure, may require authentication, or may be showing a CAPTCHA. DealScope does not bypass CAPTCHAs or access controls. A site-specific selector might need to be updated in `site_adapters.py`.
