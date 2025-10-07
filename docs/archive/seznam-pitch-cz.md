# Osiris: LLM-First Conversational ETL Platform

## Problémy dnešních integračních nástrojů

### 1. Vysoká bariéra vstupu
- **Komplexní GUI nástroje** vyžadují týdny až měsíce školení
- **Vendor lock-in** - proprietární formáty, nemožnost migrace
- **Skryté náklady** - licence per core, per connector, per user
- **Černá skříňka** - nemožnost debugovat nebo optimalizovat

### 2. Rigidní architektura
- **Template-based přístup** - omezené možnosti customizace
- **Pomalé iterace** - změna vyžaduje překlikání GUI nebo přepis kódu
- **Chybí kontext** - nástroje nerozumí business logice
- **Manuální discovery** - analysta musí ručně procházet schémata

### 3. Provozní problémy
- **Těžký debugging** - logy jsou nečitelné pro lidi i AI
- **Performance bottlenecky** - nemožnost optimalizovat na úrovni kódu
- **Chybí transparentnost** - nevidíte, co se skutečně děje
- **Složitá správa secrets** - každý nástroj má vlastní vault

## Vize Osiris: Kam míříme

### Open Source First
- **100% OSS** - žádné skryté komponenty
- **Apache 2.0 licence** - použití i v komerčních produktech
- **Transparentní vývoj** - GitHub, veřejné ADRs
- **Community-driven** - příspěvky od uživatelů

### Total User Control
- **Plain text pipelines** (YAML) - verzovatelné v Gitu
- **Lokální i cloud execution** - váš výběr
- **Vlastní LLM provider** - OpenAI, Claude, Gemini, lokální
- **Zero vendor lock-in** - migrace kdykoliv

### Total Performance
- **DuckDB engine** - analytický výkon na lokálním stroji
- **Streaming architecture** - připraveno na TB-scale
- **Paralelní execution** - maximální využití zdrojů
- **E2B cloud sandboxes** - elastické škálování a AI vývoj

### AI-Native Design
- **Konverzační interface** - mluvte přirozeným jazykem
- **Inteligentní discovery** - AI prozkoumá vaše datové zdroje
- **Context-aware SQL** - generování s porozuměním datům
- **AIOP debugging** - AI-friendly logy pro analýzu

## Klíčové vlastnosti dnes (v0.3.1)

### 1. 🤖 LLM-First Conversational Agent
- **Multi-provider support** - GPT, Claude nebo Gemini
- **Stavový automat** - deterministické chování
- **Progressive discovery** - AI postupně poznává vaše data
- **Session management** - kontext zachován mezi konverzacemi

### 2. 📊 Component Registry System
- **Self-describing components** - JSON Schema validace
- **Pluggable drivers** - jednoduché rozšíření o nové konektory
- **MySQL, Supabase, CSV, DuckDB** - produkční konektory
- **Filesystem abstractions** - jednotné rozhraní pro I/O

### 3. 🚀 Dual Execution Modes
- **Local execution** - plná kontrola, zero latency
- **E2B cloud sandboxes** - izolace, škálovatelnost
- **Transparent proxy** - identické chování local vs cloud
- **<1% overhead** - minimální dopad na výkon

### 4. 🔍 AIOP (AI Operation Package)
- **4-layer structure** - Evidence, Semantic, Narrative, Metadata
- **Deterministic output** - reprodukovatelné výsledky
- **Automatic redaction** - žádné úniky secrets
- **LLM-optimized** - <300KB pro AI analýzu

Osiris je první ETL nástroj s AI-native observability. AI umí číst deterministické logy, chápat běh pipeline a sama radit/debugovat.

Příklady:
- AI si pamatuje, že minulý týden failoval load do Snowflake a nabídne řešení.
- Při plánování nové pipeline upozorní na duplicitu s již existující.
- Dlouhodobá optimalizace: AI ví, že tabulka orders narůstá, a navrhne partitioning.


### 5. 🎨 Rich CLI Experience
- **Beautiful tables** - strukturované výstupy
- **Progress indicators** - real-time feedback
- **Color coding** - intuitivní navigace
- **Session logs** - kompletní audit trail

### 6. 🔐 Security
- **Secrets isolation** - oddělené od pipeline definic
- **Environment substitution** - ${VAR} resolution
- **Connection aliasing** - @mysql.production reference
- **Automatic masking** - DSN redaction v logách

## Architektura systému

### Základní flow
```
┌─────────────────────────────────────────────────────────────┐
│                     OSIRIS PLATFORM                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. DESIGN           2. VALIDATE        3. COMPILE          │
│  ┌─────────┐        ┌──────────┐       ┌──────────┐         │
│  │   LLM   │───────▶│  Schema  │──────▶│ Manifest │         │
│  │  Agent  │        │ Validate │       │  Builder │         │
│  └─────────┘        └──────────┘       └──────────┘         │
│       │                                       │             │
│       ▼                                       ▼             │
│  ╔═════════╗                            ╔══════════╗        │
│  ║   OML   ║                            ║ Compiled ║        │
│  ║  (YAML) ║                            ║ Manifest ║        │
│  ╚═════════╝                            ╚══════════╝        │
│                                               │             │
│  4. EXECUTE                              5. OBSERVE         │
│  ┌─────────────────────────┐           ┌──────────┐         │
│  │   Execution Adapter     │◀─────────▶│   AIOP   │         │
│  │  ┌──────┐   ┌────────┐  │           │  Export  │         │
│  │  │Local │   │  E2B   │  │           └──────────┘         │
│  │  │Driver│   │ Sandbox│  │                │               │
│  │  └──────┘   └────────┘  │                ▼               │
│  └─────────────────────────┘           ╔══════════╗         │
│                                        ║ AI Debug ║         │
│                                        ║ Package  ║         │
│                                        ╚══════════╝         │
└─────────────────────────────────────────────────────────────┘
```

### LLM Design Phase
```
┌──────────────────────────────────────────────────┐
│              LLM CONVERSATIONAL AGENT            │
├──────────────────────────────────────────────────┤
│                                                  │
│   User ──▶ "Chci data o zákaznících do CSV"      │
│                        │                         │
│                        ▼                         │
│              ┌─────────────────┐                 │
│              │  Intent Parser  │                 │
│              └────────┬────────┘                 │
│                       ▼                          │
│              ┌─────────────────┐                 │
│              │   Discovery     │                 │
│              │   - Tables      │                 │
│              │   - Columns     │                 │
│              │   - Relations   │                 │
│              └────────┬────────┘                 │
│                       ▼                          │
│              ┌─────────────────┐                 │
│              │  SQL Generator  │                 │
│              └────────┬────────┘                 │
│                       ▼                          │
│              ┌─────────────────┐                 │
│              │  OML Synthesis  │                 │
│              └────────┬────────┘                 │
│                       ▼                          │
│                  OML v0.1.0                      │
│                    (YAML)                        │
└──────────────────────────────────────────────────┘
```

### OML Compile Phase
```
┌──────────────────────────────────────────────────┐
│                  OML COMPILER                    │
├──────────────────────────────────────────────────┤
│                                                  │
│   OML (YAML) ──▶ Parser ──▶ Validator            │
│                              │                   │
│                              ▼                   │
│                     ┌──────────────┐             │
│                     │ Component    │             │
│                     │ Registry     │             │
│                     │ Resolution   │             │
│                     └──────┬───────┘             │
│                            ▼                     │
│                     ┌──────────────┐             │
│                     │ Connection   │             │
│                     │ Resolution   │             │
│                     └──────┬───────┘             │
│                            ▼                     │
│                     ┌──────────────┐             │
│                     │   Manifest   │             │
│                     │   Builder    │             │
│                     └──────┬───────┘             │
│                            ▼                     │
│                    Compiled Manifest             │
│                  (Deterministic JSON)            │
└──────────────────────────────────────────────────┘
```

### OML Execute Phase
```
┌──────────────────────────────────────────────────┐
│              EXECUTION RUNTIME                   │
├──────────────────────────────────────────────────┤
│                                                  │
│  Manifest ──▶ ExecutionAdapter Selection         │
│                       │                          │
│         ┌─────────────┴────────────┐             │
│         ▼                          ▼             │
│   LocalAdapter              E2BTransparentProxy  │
│         │                          │             │
│         ▼                          ▼             │
│  ┌─────────────┐           ┌──────────────┐      │
│  │   Driver    │           │  E2B Sandbox │      │
│  │   Registry  │           │              │      │
│  ├─────────────┤           │ ProxyWorker  │      │
│  │ MySQL       │           │      +       │      │
│  │ Supabase    │           │   Drivers    │      │
│  │ CSV Writer  │           └──────────────┘      │
│  │ DuckDB      │                   │             │
│  └─────────────┘                   │             │
│         │                          │             │
│         └──────────┬───────────────┘             │
│                    ▼                             │
│            Session Artifacts                     │
│         (logs/, output/, .cfg)                   │
└──────────────────────────────────────────────────┘
```

### AIOP Structure
```
┌──────────────────────────────────────────────────┐
│            AIOP (AI Operation Package)           │
├──────────────────────────────────────────────────┤
│                                                  │
│  1. EVIDENCE LAYER                               │
│  ┌──────────────────────────────────────────┐    │
│  │ • Timeline (events with timestamps)      │    │
│  │ • Metrics (rows, bytes, latency)         │    │
│  │ • Errors (exceptions, warnings)          │    │
│  │ • Artifacts (files generated)            │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  2. SEMANTIC LAYER                               │
│  ┌──────────────────────────────────────────┐    │
│  │ • DAG structure (nodes, edges)           │    │
│  │ • Components (specs, capabilities)       │    │
│  │ • OML specification (v0.1.0)             │    │
│  │ • Execution context (local/E2B)          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  3. NARRATIVE LAYER                              │
│  ┌──────────────────────────────────────────┐    │
│  │ • Natural language summary               │    │
│  │ • Intent discovery (multi-source)        │    │
│  │ • Key insights with citations            │    │
│  │ • Recommendations for optimization       │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  4. METADATA LAYER                               │
│  ┌──────────────────────────────────────────┐    │
│  │ • Package version, size, format          │    │
│  │ • Session context (ID, timestamp)        │    │
│  │ • Delta analysis (vs previous runs)      │    │
│  │ • Annex policy (large artifacts)         │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

## Proč je to super?

### 1. **Rychlost vývoje**
- Z business požadavku na pipeline za **minuty**, ne hodiny či dny
- Iterace v reálném čase během konverzace
- Okamžitá validace a feedback

### 2. **Transparentnost**
- Vidíte přesně, co se děje (OML, SQL, logy)
- Debugování s AIOP - AI vám pomůže najít problém
- Verzování v Gitu - kompletní historie změn + branching v týmu

### 3. **Flexibilita**
- Spustíte lokálně i v cloudu
- Vlastní LLM provider nebo on-premise model
- Rozšiřitelné o vlastní komponenty

### 4. **Bezpečnost**
- Secrets nikdy v pipeline definicích
- Automatické maskování v logách
- Sandboxovaná execuce v E2B

### 5. **Enterprise Ready**
- Session management s audit trail
- Deterministické výstupy
- Production-grade komponenty

## Nejbližší rozvoj (Q4/2025)

### M2: Real-time Streaming
- **WebSocket streaming** pro real-time feedback během execuce
- **Incremental AIOP updates** - průběžné exporty během běhu
- **Live debugging** - AI asistent sleduje běh v reálném čase

### M3: Scale & Performance
- **Streaming I/O** - zpracování TB datasetů
- **Paralelní execution** - využití všech CPU cores
- **Distributed execution** - Spark/Ray integration
- **Observability** - Datadog, OpenTelemetry

### M4: Data Warehouse Agent
- **Apache Iceberg writer** - moderní table format
- **DWH management agent** - automatická správa schémat
- **MotherDuck/Snowflake/BigQuery** - cloud DWH integrace
- **Time travel & versioning** - historická data

### M5: Production Orchestration
- **Scheduler** - cron expressions v OML
- **Airflow/Prefect adapters** - napojení na orchestrátory
- **SLA monitoring** - automatické alerty
- **Lineage tracking** - data governance
- **Long-term memory** – perzistentní paměť pro AI asistenta → umožní AI chápat dlouhodobý kontext napříč pipeline runs, učit se z historie a nabízet prediktivní doporučení

## Závěr

Osiris představuje **paradigm shift** v integrační vrstvě:

1. **Od GUI k konverzaci** - mluvte s daty přirozeným jazykem
2. **Od black-boxu k transparentnosti** - vidíte a kontrolujete vše
3. **Od vendor lock-in k OSS** - vlastněte svůj data stack
4. **Od templates k AI** - inteligentní generování místo kopírování

**Osiris bude připraven pro produkční nasazení** od verze v0.5, která bude obsahovat všechny klíčové komponenty pro spolehlivé ETL pipelines s AI asistencí.

## Kontakt a další kroky

- **GitHub**: [github.com/padak/osiris_pipeline](https://github.com/keboola/osiris)
- **Dokumentace**: Kompletní user guide a developer guide
- **Quick Start**: 5 minut od instalace k první pipeline
- **Demo**: Live ukázka MySQL → CSV pipeline s discovery

---

*Osiris: Because data integration should be a conversation, not a configuration.*
