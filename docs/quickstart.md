# Osiris Pipeline — Quick Start

A 10‑minute happy‑path to run your first pipeline locally and (optionally) in an E2B sandbox. We'll move a small table from MySQL to a CSV file.

---

## 1) Prerequisites

- **Python 3.11+**
- **Git**
- **MySQL** database you can read from (host/user/password)
- (Optional) **E2B** account if you want to try cloud sandbox runs

> Tip: All commands below assume you work from the repo’s `testing_env/` folder.

---

## 2) Install

```bash
# Clone and set up a virtualenv
git clone https://github.com/keboola/osiris_pipeline.git
cd osiris_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3) Initialize local environment

Osiris can scaffold helpful templates.

```bash
cd testing_env
python ../osiris.py init
```

This creates (or guides you to create):

- `.env` (API keys & secrets)
- `osiris_connections.yaml` (connection aliases)

Now populate them as shown below.

### 3a) `.env`

Create `testing_env/.env` with at least:

```
OPENAI_API_KEY=sk-...
MYSQL_PASSWORD=your-mysql-password
```

### 3b) `osiris_connections.yaml`

Create `testing_env/osiris_connections.yaml` with **aliases** you’ll reference from OML. Secrets can come from environment variables.

```yaml
version: 1
connections:
  mysql:
    default:
      host: your-mysql-host
      port: 3306
      database: movies
      user: root
      password: ${MYSQL_PASSWORD}
  filesystem:
    local:
      base_dir: ./out
```

Verify everything:

```bash
python ../osiris.py connections list
python ../osiris.py connections doctor
python ../osiris.py components list
```

---

## 4) Your first pipeline (MySQL → CSV)

Save the following OML to `testing_env/pipelines/mysql_to_csv.oml.yaml`.

```yaml
oml_version: "0.1.0"
id: mysql-to-csv-demo
steps:
  - id: extract-movies
    component: mysql.extractor
    mode: read
    query: |
      SELECT id, title, release_year
      FROM movies
      ORDER BY id
    connection: "@mysql.default"

  - id: write-movies-csv
    component: filesystem.csv_writer
    mode: write
    inputs:
      df: "@extract-movies"
    path: movies.csv           # will be created under filesystem.local base_dir
    write_mode: replace        # replace file on each run
    create_if_missing: true
    connection: "@filesystem.local"
```

> Notes
> - Use `oml_version`, not `version`.
> - Reference connections with `@family.alias`.
> - `mode` is `read` for extractors and `write` for writers.

---

## 5) Compile

```bash
python ../osiris.py compile pipelines/mysql_to_csv.oml.yaml
```

Compilation produces a **deterministic manifest** under `logs/compile_*/compiled/`.

---

## 6) Run

### Local run (recommended first)
```bash
python ../osiris.py run --last-compile --verbose
```
- Artifacts (including the generated CSV) are under `logs/run_*/artifacts/` — specifically in the directory for the writer step (e.g. `artifacts/write-movies-csv/`).

### E2B sandbox run (optional)
```bash
python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose
```
- Runs in an isolated cloud sandbox with the **same** logs, metrics, and artifacts layout.

---

## 7) Inspect logs & reports

```bash
# List sessions
python ../osiris.py logs list

# Open the interactive HTML report in your browser
python ../osiris.py logs html --open
```

The HTML report shows session metadata, steps, performance, and a full event/metrics trail. E2B runs are labeled with an **E2B** badge and include bootstrap timing.

---

## 8) Troubleshooting

- **Cannot connect to MySQL** → Check `osiris_connections.yaml` host/port and that your network allows access.
- **No CSV produced** → Ensure the writer step uses `inputs: df: "@extract-movies"` and `connection: "@filesystem.local"`. The file will be under `./out/movies.csv` (relative to `testing_env`).
- **Secrets in logs** → Osiris masks sensitive fields automatically. Keep secrets in `.env`, not in OML.
- **Different local vs E2B timings** → E2B includes sandbox bootstrap; see the Performance panel.

---

## 9) Next steps

- Swap the CSV writer for `supabase.writer` to load into your warehouse.
- Explore `python ../osiris.py chat` to generate OML conversationally (approve, compile, run).
- Read the **HTML report** thoroughly — it’s designed so AI agents (and humans) can investigate runs quickly.

---

**You’re done.** You now have a deterministic, reproducible pipeline that you can version in Git and run locally or in a cloud sandbox with identical results.
