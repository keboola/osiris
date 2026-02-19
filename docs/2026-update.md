# Osiris 2026 - Modernizacni plan

> Stav k: 19. unora 2026
> Posledni aktivni vyvoj: prosinec 2025
> Aktualni verze: v0.5.7 (pyproject.toml) / v0.5.4 (dokumentace)

---

## 1. Executive Summary

Osiris je **konverzacni kompiler pro datove pipeline** - system, kde si povidis s AI o svem problemu, AI provede introspekci third-party systemu, navrhe reseni jako OML konfiguraci a zkompiluje ho do deterministicky spustitelneho workflow. Runtime bezi **bez AI** - spolehlivy, reprodukovatelny, auditovatelny. Nad tim vrsim AIOP - ctyrvrstvovy export, diky kteremu AI perfektne rozumi logum a nedomysli si.

Od posledniho aktivniho vyvoje (prosinec 2025) se AI ekosystem dramaticky posunul. Tento dokument analyzuje, co z architektury Osiris dava smysl, co je zbytecne slozite, a navrhuje cestu vpred.

**Klicova zjisteni:**
- Zakladni architekturalni filozofie (oddeleni design/execution, AIOP, DuckDB exchange) je **spravna a unikatni**
- Implementace je na nekterych mistech **zbytecne slozita** a da se zredukovat na ~40% kodu
- LLM integrace je zastarala (Claude 3 Sonnet, GPT-4o) - kriticka modernizace
- Dual execution (local + E2B) pridava komplexitu bez dostatecneho prinos
- Nove Claude capabilities (structured outputs, interleaved thinking) mohou nahradit slozitou validacni logiku

---

## 2. Architekturalni analyza - co dava smysl a co ne

### 2.1 Klicova filozofie Osiris

Osiris stoji na fundamentalnim oddeleni dvou fazi:

```
DESIGN (s AI)                       EXECUTION (bez AI)
──────────────────                  ──────────────────
Povidani o problemu                 Deterministicky runtime
Introspekce systemu                 Kompilace OML -> manifest
  - databaze, API, schemata         Spusteni manifestu
  - relace, typy, vzory             Perfektni logovani
Navrh reseni (OML format)           AIOP export pro AI analyzu
```

**Proc to dava smysl:**
- AI je pouzita tam, kde exceluje (porozumeni intentu, navrh reseni, introspekce)
- Runtime je deterministicky - stejny manifest = stejny vysledek, vzdy
- Logy jsou strukturovane tak, ze AI jim rozumi bez domysleni (AIOP)
- Pipeline je znovupouzitelna bez AI (staci manifest)

**Tohle je fundamentalne jiny pristup nez "nech AI vygenerovat skript":**
- "Generuj skript" = kazdy run muze dat jiny kod, zadna reprodukovatelnost
- Osiris = AI navrhe jednou, pak to bezi spolehlivy tisickrat

### 2.2 Co z architektury ZACHOVAT (klicova hodnota)

| Vrstva | Ucel | Proc zachovat |
|--------|------|---------------|
| **OML format** | Deklarativni popis workflow | To je ten "compiled artifact" - jadro celeho systemu |
| **Compiler + fingerprint** | OML -> deterministicky manifest | Reprodukovatelnost, audit trail, verzovani |
| **Component registry** | Pluggable konektory (YAML specs) | Rozsiritelnost, sebepopisujici komponenty |
| **DuckDB data exchange** | Data passing mezi stepy | Elegantni, efektivni, bez externich zavislosti |
| **AIOP 4-layer export** | AI-readable logy | **Unikatni feature** - zadny konkurent toto nema |
| **MCP server** | Integrace s Claude/Cursor | Vstupni bod pro AI, zero-secret architektura |
| **Driver system** | Izolovanej runtime pro kazdy step | Potrebny, ale da se zjednodusit |

### 2.3 Co ZJEDNODUSIT (zbytecna komplexita)

#### A) Tri-vrstvova OML validace -> schema + runtime

Aktualne: Schema -> Semanticka -> Runtime validace (3 vrstvy, stovky radku).

S Claude Sonnet 4.6 structured outputs dostavas validni OML na prvni pokus. Staci:
- **Schema validace** (JSON Schema - uz existuje) - zachovat
- **Runtime check** (existuji komponenty? maji secrets?) - zachovat
- **Semanticka vrstva** (primary_key pro upsert) - presunout do runtime checku

Vysledek: 1 validacni vrstva misto 3, Claude structured outputs jako "vrstva 0".

#### B) Dual execution (LocalAdapter + E2BAdapter + ProxyWorker) -> jeden runtime

Aktualne: Dva uplne odlisne execution paths:
- `LocalAdapter` - bezi v procesu, pouziva `RunnerV0`
- `E2BAdapter` - packuje payload, uploaduje, spousti `ProxyWorker`, RPC loop

To znamena dvojnasobnou maintenance, dvojnasobne testovani, a `ProxyWorker` je slozity RPC mechanismus (~1400 radku).

**Navrh: jeden runtime, dva prostredi:**
```
osiris run manifest.yaml              # Lokalne (Docker nebo primo)
osiris run manifest.yaml --e2b        # V E2B (nainstaluje osiris, spusti stejny prikaz)
osiris run manifest.yaml --docker     # V Docker lokalne (stejny princip)
```

Vsude bezi **stejny kod** (`osiris run`), jenom v jinem prostredi. Tim odpadne:
- Cely `ProxyWorker` a RPC mechanismus
- `e2b_full_pack.py` a `e2b_pack.py` (packing logika)
- Odlisnosti mezi LocalAdapter a E2BAdapter
- Paritni testy (Local vs E2B) - uz neni co testovat, je to stejny kod

E2B nema cistu "lokalni mode" (vzdy bezi v microVM). Ale **Docker lokalne** + **E2B v cloudu** poskytuje stejnou izolaci s jednim runtime.

#### C) Session logging (4 moduly) -> jednotny logger

Aktualne: `SessionContext`, `session_logging`, `run_export_v2`, `aiop_export` - 4 moduly pro logovani.

Navrh: Jeden strukturovany logger ktery:
- Loguje events.jsonl a metrics.jsonl (jako ted)
- Umi exportovat AIOP (jako ted, ale ze stejneho modulu)
- Nepotrebuje 4 oddelene abstrakce

#### D) LLM state machine -> nechat to na Claude

Aktualne: Explicitni state machine v `conversational_agent.py`:
```
INIT -> INTENT_CAPTURED -> DISCOVERY -> OML_SYNTHESIS -> COMPILE -> RUN
```

S interleaved thinking Claude 4.6 tenhle flow zvladne prirozene - premysli mezi kroky, rozhodne se co dal. State machine je z doby, kdy LLM nemel tuhle schopnost.

Navrh: Nahradit rigidni state machine za konverzacni agent s tool use:
- Claude dostane nastroje (discover_schema, generate_oml, compile, run)
- Sam se rozhodne v jakem poradi je pouzije
- Interleaved thinking zajisti "premysleni" mezi kroky
- Zachovat human-in-the-loop pro schvaleni pred executionem

### 2.4 Dopad zjednoduseni

```
PRED (~20K radku runtime kodu)          PO (odhad ~8K radku)
──────────────────────────              ─────────────────────
OML + 3-layer validace           ->     OML + schema validace + structured outputs
CompilerV0 + fingerprinting      ->     Zachovat beze zmeny
9 YAML component specs           ->     Zachovat (mozna zjednodusit schema)
Driver factory + registry        ->     Zachovat (zjednodusit factory)
LocalAdapter + E2BAdapter        ->     Jeden runtime (`osiris run`)
  + ProxyWorker RPC              ->     E2B/Docker pouze jako prostredi
SessionContext + 3 export mods   ->     Jednotny logger + AIOP
AIOP 4-layer                     ->     Zachovat beze zmeny (klicova hodnota)
MCP 12+ nastroju                 ->     Zachovat beze zmeny
State machine (6 stavu)          ->     Claude agent s tool use
```

---

## 3. Aktualni stav projektu

### 3.1 Co funguje dobre

| Oblast | Stav | Poznamka |
|--------|------|----------|
| DuckDB data exchange (ADR-0043) | Hotovo | Phase 2 complete, vsechny drivery migrovany |
| MCP server s CLI-first security | Produkcni | 12+ nastroju, selftest <1.3s, zero secret access |
| Deterministicka kompilace | Stabilni | SHA-256 fingerprinting, manifest reprodukovatelnost |
| AIOP system | Funkcni | **Unikatni feature** - 4-layer export, secret redaction, <=300KB |
| Component registry | 9 komponent | MySQL, Supabase, DuckDB, CSV, GraphQL, PostHog |
| Testovaci infrastruktura | 1577+ testu | 98.1% pass rate, 78.4% coverage |
| E2B integrace | Funkcni | Transparent proxy, parita s lokalnim |
| Dokumentace | Vynikajici | 43+ ADR, milestones, developer guides |

### 3.2 Co je zastarale

| Oblast | Aktualni | Stav sveta | Urgence |
|--------|----------|------------|---------|
| Claude API | anthropic 0.25+, Claude 3 Sonnet | Opus 4.6, Sonnet 4.6, Agent SDK | KRITICKA |
| OpenAI API | openai 1.3+, GPT-4o | GPT-5, structured outputs GA | VYSOKA |
| DuckDB | >=0.9.0 | 1.4.4 (MERGE, AES-256, Iceberg) | VYSOKA |
| MCP SDK | mcp 1.2.1 | Spec Nov 2025, OAuth, AAIF/Linux Foundation | STREDNI |
| Python tooling | pip + Black + isort | uv + Ruff (format+lint) | STREDNI |
| Python verze | 3.11 required | 3.12 stable (5% perf, subinterpreters) | NIZKA |

### 3.3 Metriky projektu

- **Testy:** 215 souboru, 1577+ testu, 98.1% pass rate, 78.4% coverage
- **CI/CD:** 7 GitHub Actions workflows (lint, security, coverage, E2B, MCP, guards, PyPI)
- **Zavislosti:** 14 runtime, 12 dev, 3 docs
- **Komponenty:** 9 registrovanych (mysql, supabase, duckdb, csv, graphql, posthog, filesystem)

---

## 4. Stav feature branches

### 4.1 feature/duckdb-data-exchange (AKTUALNI)

**Status: READY TO MERGE**

Hlavni architekturalni migrace z in-memory pandas DataFrames na DuckDB file-based data exchange. 56 souboru zmeneno, 7428 pridani, 963 odebrani.

- Vsechny drivery migrovany na novy kontrakt (`ctx.get_db_connection()`)
- Navratovy format zmenen: `{"df": DataFrame}` -> `{"table": step_id, "rows": count}`
- Eliminovano 1500 radku spilling logiky
- ADR-0043, design dokumenty, testy aktualizovany
- Posledni commit: 2. prosince 2025

**Doporuceni:** Zmergovat do main jako prvni krok.

### 4.2 feature/graphql-discovery

**Status: OBSOLETNI** - Ukazuje na stejny commit jako main. **Smazat.**

### 4.3 demo/e2d-dryrun

**Status: STALE** (zari 2025) - Demo skript, 5 mesicu bez aktivity. **Archivovat nebo smazat.**

### 4.4 docs/archive-seznam-pitch

**Status: NEBEZPECNA** - 435 souboru zmeneno, 93K radku smazano vcetne produkcniho MCP kodu. **Nemerovat.** Pokud je treba neco extrahovat, udelat chirurgicky.

---

## 5. Modernizace LLM integrace (KRITICKA PRIORITA)

### 5.1 Aktualni stav

Osiris pouziva vlastni `LLMAdapter` s tri providery (OpenAI default, Claude, Gemini). Modely jsou zastarale (Claude 3 Sonnet, GPT-4o).

### 5.2 Co se zmenilo od rijna 2025

**Nove Claude modely:**
| Model | Datum | Klicove vlastnosti |
|-------|-------|-------------------|
| Haiku 4.5 | ~rijen 2025 | Nejrychlejsi, agent tasks |
| Opus 4.5 | rijen 2025 | Nejsilnejsi v dobe vydani |
| Opus 4.6 | 5. unora 2026 | Agent Teams, 200K (1M beta), 128K output, fast mode 2.5x |
| Sonnet 4.6 | 17. unora 2026 | Near-Opus vykony, 1M context, novy default |

**Nove API capabilities relevantni pro Osiris:**

| Feature | Dopad na Osiris |
|---------|----------------|
| **Interleaved Thinking** | Claude premysli MEZI tool calls - transformuje schema discovery |
| **Structured Outputs (GA)** | Validovany JSON/YAML - muze nahradit velkou cast OML validace |
| **1M token context** | Cele velke schemata najednou - nepotrebujeme progressive discovery |
| **Agent Skills** | Specializovane "ETL skill" balicky instrukci pro Claude |
| **Context Compaction** | Server-side komprese - dlouhe chat sessions bez overflow |
| **Code Execution Tool** | Anthropic sandbox v API - alternativa k E2B pro jednoduche veci |
| **Fast Mode** | 2.5x rychlejsi output - lepsi UX pri generovani pipeline |
| **Files API** | Persistentni uloziste - schema cache mezi sessions |

### 5.3 Doporucena modernizace

**A) Claude jako primarni provider** s Sonnet 4.6 default:
```yaml
llm:
  provider: claude
  model: claude-sonnet-4-6-20250217
  fallback_model: claude-opus-4-6-20250205
  temperature: 0.1
  max_tokens: 4096
  features:
    interleaved_thinking: true
    structured_outputs: true
    context_compaction: true
```

**B) Interleaved Thinking pro schema discovery:**
```
Bez:  [Think] -> [Discover all] -> [Generate pipeline]
S IT: [Think] -> [Discover table_1] -> [Think o relacich] ->
      [Discover table_2] -> [Think o join strategii] -> [Generate OML]
```

**C) Structured Outputs pro OML:**
Claude vrati vzdy validni OML - eliminuje potrebu slozite parsovaci a validacni logiky.

**D) Nahradit state machine za tool-use agent:**
Misto rigidniho INIT->DISCOVERY->SYNTHESIS->COMPILE->RUN nechat Claude rozhodovat s nastroji (discover, generate_oml, compile, validate, run) a interleaved thinking.

---

## 6. Upgrade zavislosti

### 6.1 Kriticke upgrady

```
duckdb>=1.4.0           # z >=0.9.0 - MERGE, AES-256, Iceberg
anthropic>=1.0.0        # z >=0.25.0 - Opus 4.6, structured outputs, thinking
openai>=1.50.0          # z >=1.3.0 - GPT-5, structured outputs
mcp>=1.6.0              # z >=1.2.1 - Nov 2025 spec, OAuth, structured tool outputs
```

### 6.2 DuckDB 1.4.4 - klicove nove features

- **MERGE statements** - Nativni upsert (relevantni pro Supabase writer, replace/upsert)
- **AES-256 encryption** - Sifrovani `pipeline_data.duckdb` pro citliva data
- **Iceberg extension** - Full DML pro Apache Iceberg (budoucnost, roadmap M4)
- **DuckLake** - ACID lakehouse s time-travel
- **UNION ALL BY NAME** - Flexibilnejsi sjednoceni tabulek

### 6.3 Ostatni

```
pandas>=2.2.0        # nebo zvazit Polars pro performance-critical drivery
pyarrow>=17.0.0
supabase>=2.10.0
jsonschema>=4.23.0
rich>=13.9.0
```

---

## 7. Modernizace toolingu

### 7.1 UV misto pip

UV je 8-115x rychlejsi, Rust-based, plne kompatibilni s requirements.txt.

Klicovy dopad: **E2B cold-start z ~21s na ~2.6s** pro typicke zavislosti.

```bash
uv venv .venv
uv pip install -r requirements.txt
```

### 7.2 Ruff jako jediny formater + linter

Nahrazuje Black + isort + Ruff linting jednim nastrojem:
```toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.ruff.lint]
select = ["E", "F", "UP", "B", "SIM", "PL", "W", "I"]
```

### 7.3 Python 3.12 jako minimum

5% vykonnostni zlepseni, subinterpreters pro true paralelismus, stabilni ekosystem.

---

## 8. Zjednoduseni execution - jeden runtime

### 8.1 Aktualni problem

```
Aktualne: 2 odlisne cesty
──────────────────────────
LocalAdapter -> RunnerV0 -> drivers primo v procesu
E2BAdapter -> e2b_full_pack -> upload -> ProxyWorker -> RPC loop -> drivers v sandboxu
```

Tohle znamena:
- ~1400 radku ProxyWorker RPC
- Packing/unpacking logika (e2b_pack, e2b_full_pack)
- Paritni testy (overuji ze obe cesty daji stejny vysledek)
- Dvojnasobna maintenance pri zmene driveru

### 8.2 Navrzene reseni

```
Nove: 1 runtime, 3 prostredi
─────────────────────────────
osiris run manifest.yaml              # Primo (vyvoj, debug)
osiris run manifest.yaml --docker     # Docker lokalne (izolace)
osiris run manifest.yaml --e2b        # E2B cloud (produkce)
```

Implementace:
- **Primo:** `osiris run` spousti RunnerV0 v aktualnim procesu (jako ted LocalAdapter)
- **Docker:** Spusti `docker run osiris-pipeline osiris run manifest.yaml`
- **E2B:** `uv pip install osiris-pipeline && osiris run manifest.yaml` v sandboxu

Tim se eliminuje:
- ProxyWorker a cely RPC mechanismus
- e2b_full_pack, e2b_pack (packing logika)
- Dual adapter architektura
- Paritni testy (je to stejny kod)

Predpoklad: Osiris na PyPI (uz je v ADR-0041).

### 8.3 E2B nema lokalni mode

E2B vzdy bezi v Firecracker microVM (cloud nebo self-hosted na GCP). Pro lokalni izolaci pouzit Docker - stejny Python, stejne zavislosti, stejny `osiris run`.

---

## 9. MCP modernizace

### 9.1 Co se zmenilo

- MCP specifikace November 2025 - OAuth Resource Server (RFC 8707), structured tool outputs, elicitation
- MCP predano pod **Linux Foundation (AAIF)** - Anthropic, Block, OpenAI spoluzakladatele
- 97M+ mesicnich SDK stahovani, tisice serveru na MCP.so
- OpenAI, Google DeepMind, Microsoft vsichni adoptovali MCP

### 9.2 Doporucene zmeny

1. **Upgrade na MCP spec Nov 2025** - OAuth pro enterprise
2. **Structured tool outputs** - Typovane odpovedi misto stringu
3. **Registrace na MCP.so** - Zviditelneni Osiris
4. **Elicitation** - MCP server muze interaktivne ziskat info od uzivatele

---

## 10. Konkurencni prostredi

### 10.1 Prime konkurenti

| Nastroj | Pristup | Silne stranky | Slabiny vs Osiris |
|---------|---------|---------------|-------------------|
| Airflow MCP Pipeline Gen | Konverzacni -> Airflow DAGs | Enterprise ekosystem | Vazano na Airflow |
| AWS Amazon Q + MCP | Konverzacni ETL | AWS scale | Vendor lock-in |
| dlt (Data Load Tool) | Python-first, low-code | 8M dl/mesic | Neni konverzacni |
| Airbyte AI Connector | 600+ konektoru | Siroky ekosystem | Crashuje na 10M+ |
| Informatica AI | NL-to-transformation | Enterprise | Closed source, drahy |

### 10.2 Unikatni pozice Osiris

Zadny konkurent nenabizi tuto kombinaci:

1. **Oddeleni design/execution** - AI navrhe, runtime bezi deterministicky bez AI
2. **AIOP** - LLM-native logy, ktere AI interpretuje bez domysleni
3. **DuckDB-native** - Data exchange bez externich zavislosti
4. **Zero-secret MCP** - CLI-first security architektura
5. **Kompiler, ne orchestrator** - Fingerprinted manifesty, reprodukovatelnost

### 10.3 Kde Osiris zaostava

- **Konektory** - 9 vs stovky u Airbyte/dlt
- **Community** - Maly projekt
- **Streaming** - Batch-only
- **Scheduling** - Chybi orchestrace
- **UI** - Pouze CLI

---

## 11. Prioritizovany plan modernizace

### Faze 0: Stabilizace (1-2 dny)

- [ ] Zmergovat `feature/duckdb-data-exchange` do main
- [ ] Smazat `feature/graphql-discovery`
- [ ] Archivovat/smazat `demo/e2d-dryrun`
- [ ] Opravit nesoulad verze (pyproject.toml 0.5.7 vs docs 0.5.4)
- [ ] Vyresit 5 HIGH findings z FINDINGS-PENDING.md
- [ ] Opravit 26 P1 bugu z auditu rijen 2025

### Faze 1: LLM modernizace (1-2 tydny)

**Nejvetsi dopad na hodnotu Osiris.**

- [ ] Upgrade `anthropic` SDK na >=1.0, `openai` na latest
- [ ] Claude Sonnet 4.6 jako default provider/model
- [ ] Aktivovat interleaved thinking pro schema discovery
- [ ] Structured outputs pro OML generaci
- [ ] Nahradit state machine za Claude agent s tool use
- [ ] Upgrade DuckDB na >=1.4.0 (MERGE, encryption)
- [ ] Aktualizovat vsechny zavislosti

### Faze 2: Zjednoduseni runtime (2-3 tydny)

**Nejvetsi redukce komplexity.**

- [ ] Sjednotit execution na jeden runtime (`osiris run`)
- [ ] Implementovat `--docker` flag pro lokalni izolaci
- [ ] Implementovat `--e2b` jako PyPI install + `osiris run` v sandboxu (ADR-0041)
- [ ] Odstranit ProxyWorker, e2b_pack, e2b_full_pack
- [ ] Odstranit dual adapter architekturu
- [ ] Zjednodusit OML validaci (schema + runtime, bez semanticke vrstvy)
- [ ] Sjednotit session logging (4 moduly -> 1)

### Faze 3: Tooling a DX (1 tyden)

- [ ] UV jako doporuceny package manager
- [ ] Ruff jako jediny formater + linter (nahrada Black + isort)
- [ ] Python 3.12 jako minimum
- [ ] Aktualizovat CI/CD workflows
- [ ] Aktualizovat Makefile, pre-commit

### Faze 4: MCP a rozsireni (2-3 tydny)

- [ ] Upgrade MCP na spec November 2025
- [ ] Structured tool outputs
- [ ] OAuth Resource Server pro enterprise
- [ ] Registrace na MCP.so marketplace
- [ ] Nove komponenty: REST generic extractor, PostgreSQL native, S3/GCS writer

### Faze 5: Budouci vize (Q2-Q3 2026)

- [ ] Streaming I/O (DuckDB 1.4 streaming + RowStream interface)
- [ ] DAG paralelni execution
- [ ] Scheduling integrace (Airflow, Dagster, Prefect)
- [ ] Iceberg tabulky (DuckDB Iceberg extension)
- [ ] Web UI / dashboard
- [ ] Agent Teams (Claude Opus 4.6) pro paralelni discovery
- [ ] OpenTelemetry observabilita (doplneni AIOP)
- [ ] Pydantic v2 pro konfiguraci (postupna migrace)

---

## 12. P1 bugy k oprave

Z auditu rijen 2025 zustava 26 bugu:

| Kategorie | Pocet | Priklady |
|-----------|-------|----------|
| Konfigurace | 5 | `Path.home()` misto config-driven, OSIRIS_HOME hardcoded |
| Resource leaks | 7 | Session store nezavreny, connection leaky |
| Cache system | 3 | Chybi TTL validace, neomezeny rust |
| Error handling | 11 | Silent failures, parameter propagation |

Odhadovany cas: 8 hodin. Opravit v ramci Faze 0/1.

---

## 13. Rizika a mitigace

| Riziko | Dopad | Mitigace |
|--------|-------|----------|
| DuckDB 1.4 breaking changes | Vysoky | Rozsahle testy pred upgrade |
| Odstraneni dual execution | Stredni | Postupny prechod, zachovat local fallback |
| Claude API zmeny | Nizky | Abstrakce v LLMAdapter, multi-provider |
| UV nestabilita | Nizky | Fallback na pip vzdy dostupny |
| E2B pricing zmeny | Vysoky | PyPI-based execution snizuje zavislost |

---

## 14. Souhrn

### Zachovat (klicova hodnota)
- OML format + kompiler + fingerprinting
- AIOP ctyrvrstvovy export
- DuckDB data exchange
- MCP server s CLI-first security
- Component registry

### Zjednodusit (zbytecna komplexita)
- Dual execution -> jeden runtime, ruzna prostredi
- 3-vrstvova validace -> schema + runtime + structured outputs
- State machine -> Claude agent s tool use
- 4 logging moduly -> jednotny logger
- ProxyWorker RPC -> PyPI install v sandboxu

### Modernizovat (zastarale)
- LLM (Claude 3 -> Sonnet 4.6, interleaved thinking, structured outputs)
- DuckDB (0.9 -> 1.4, MERGE, encryption)
- Tooling (pip -> uv, Black+isort -> Ruff)
- MCP (1.2.1 -> Nov 2025 spec)

---

*Tento dokument byl vytvoren na zaklade analyzy celeho repozitare, vsech feature branches, 43+ ADR zaznamu, milestonu, designovych dokumentu a vyzkumu aktualniho stavu AI/ETL ekosystemu (unor 2026). Revidovan po diskusi o architekturalni filozofii projektu.*
