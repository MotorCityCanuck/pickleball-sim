# Pickleball Simulation Platform

**Large-Scale Synthetic Pickleball Analytics Data Generation Platform**

## Overview

This platform generates realistic synthetic pickleball match data for graduate-level data science education and Olympic team selection analytics.

## Solution Scale

This is a medium-to-large simulation platform rather than a single-purpose
script or prototype.

- `~53.6k` lines of backend Python across `161` Python source files
- `38` ORM models and `38` schema tables in
  [backend/schema.sql](backend/schema.sql)
- `48` test files with `1,066` individual test cases
- `53` documentation files
- `9` Jinja templates supporting the control panel UI

In practical terms, the solution spans:

- application logic
- data engineering
- monthly job orchestration
- runtime instrumentation and failure recovery
- operator-facing web control
- dataset export packaging and validation
- realism audit and analytics support

### Key Features

- 🏓 **50,000 default synthetic players** across North America, with
  smaller test runs commonly using 5,000 players
- 📊 **Monthly generated matches and games** with rating-derived expected
  scores, predicted winners, and realistic scoring
- 📅 **Monthly batch processing** for incremental data releases
- 🎯 **Rating system** with confidence and volatility tracking
- 🤝 **Team dynamics** with persistent partnerships
- 📦 **Parquet exports** for analytics-ready datasets
- ✅ **Comprehensive validation** with 35+ business rules

## Quick Start

### Prerequisites

- Docker Desktop
- Python 3.11+
- PostgreSQL 16+ (via Docker)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd pickleball-sim
   ```

2. **Set up environment**
   ```bash
   cp env.example .env
   # Edit .env with your settings
   ```

3. **Start PostgreSQL**
   ```bash
   docker compose up -d postgres
   ```

4. **Create virtual environment**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **Initialize database**
   ```bash
   python scripts/recreate_db_from_orm.py
   ```

## Project Structure

```
pickleball-sim/
├── README.md                   # This file
├── backend/                    # Python application and test suite
│   ├── app/
│   │   ├── core/               # Configuration and settings
│   │   ├── db/                 # Database session management
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── generation/         # Generation run and monthly pipeline orchestration
│   │   ├── generators/         # Data generation modules
│   │   ├── exports/            # Student dataset export and validation
│   │   ├── seed_data_ingest/   # Raw seed ingestion pipeline
│   │   ├── seed_data_normalize/ # Reference data normalization
│   │   ├── web/                # FastAPI web interface
│   ├── scripts/                # ORM, seed, and generation CLI utilities
│   ├── tests/                  # Test suite
├── data/                       # Seed data, exports, and audit snapshots
├── scripts/                    # Runtime, reporting, and environment scripts
├── docs/                       # Architecture, orchestration, and design docs
├── sql/                        # Reporting SQL
└── compose.yaml                # Docker services
```

## Backend Modules

The backend is organized into clear subsystems:

- `core` (`7` files, `~3.4k` lines): configuration defaults, config editor
  metadata, validation, app settings
- `generation` (`15` files, `~6.4k` lines): run orchestration, job lifecycle,
  destructive reset, monthly pipeline, runtime metrics
- `generators` (`8` files, `~6.4k` lines): players, club memberships, teams,
  matches, ratings, games, hidden performance bias
- `models` (`38` files, `~1.9k` lines): relational model surface for domain,
  orchestration, exports, and seed data
- `web` (`4` files, `~3.2k` lines): control panel routes, query projections,
  job recovery
- `exports` (`9` files, `~3.2k` lines): student-facing dataset projection,
  packaging, validation
- `seed_data_ingest` and `seed_data_normalize` (`13` files, `~2.8k` lines
  combined): raw ingest and normalized reference data preparation

## Documentation

Start here for development:

1. **[Quick Start Guide](docs/docs_QUICK_START_GUIDE.md)** - 15-minute orientation
2. **[Master Document Index](docs/docs_MASTER_DOCUMENT_INDEX.md)** - Complete navigation
3. **[Database Design](docs/database/Pickleball_Simulation_Database_Design_v3.md)** - Schema specification
4. **[Configuration Parameters](docs/generation_logic/configuration_parameters_specification.md)** - All parameters
5. **[Configuration Payload Architecture](docs/architecture/configuration_payload_architecture.md)** - JSONB payload shape
6. **[Database Backup and Classroom Migration](docs/database_backup_restore.md)** - Freeze, transfer, restore, and validate PostgreSQL backups
7. **[Design Review Summary](docs/docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md)** - Recent changes

## Architecture

### Technology Stack

- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy 2.0
- **Schema Management**: ORM-first development recreation
- **Web Framework**: FastAPI with server-rendered Jinja2 and HTMX control
  panel interactions
- **Data Processing**: Pandas, NumPy
- **Export Format**: Parquet (PyArrow)
- **Testing**: Pytest
- **Configuration**: Pydantic Settings

### Data Flow

```
Configuration → Monthly Batch Processor
                      ↓
    Player Generation → Team Formation → Match Scheduling
                      ↓
    Matchmaking → Game Generation → Score Simulation
                      ↓
    Rating Updates → Confidence Calculation
                      ↓
    Validation → Parquet Export → Student Analytics
```

### Operational Surface

The platform includes more than batch generation code:

- durable generation runs and monthly batches
- job and stage status tracking
- runtime instrumentation and SQL reporting
- destructive reset and stalled-job recovery
- server-rendered FastAPI/HTMX control panel
- Parquet student dataset release packaging
- release quality validation with DuckDB-based checks
- realism audit snapshots and reporting utilities

## Development Phases

### ✅ Phase 1: Foundation
- [x] Project structure
- [x] Documentation review
- [x] Database schema implementation
- [x] SQLAlchemy models
- [x] ORM-driven database recreation scripts

### ✅ Phase 2: Core Generation
- [x] Configuration system
- [x] Raw seed data loading and normalization
- [x] Player generation with initial rating history
- [x] Club membership generation, including unaffiliated and multi-club players
- [x] Team determination

### 🔄 Phase 3: Match Simulation
- [x] Team formation logic
- [x] Match scheduling (weekend-weighted)
- [x] Matchmaking engine
- [x] Game and score generation
- [x] Rating calculation engine with per-match update logs

### 🔄 Phase 4: Monthly Batch Processing and Export
- [x] Generation run and monthly batch planning
- [x] End-to-end monthly pipeline CLI for implemented stages
- [x] Job and stage status tracking
- [x] Student-facing dataset release specifications
- [ ] Multi-batch new player inflow
- [ ] Full validation and Parquet export hardening

### 🔄 Phase 5: Web Control Panel
- [x] FastAPI app shell
- [x] Server-rendered control panel structure
- [x] HTMX-driven status and workflow interactions
- [x] Job status tracking views
- [ ] Export management workflow completion

## Key Design Principles

1. **Batch Association**: All generated data MUST include `batch_id` (NOT NULL)
2. **Historical Integrity**: Ratings stored in `player_rating_history`, NOT on `players` table
3. **Age Calculation**: Store `birth_date`, calculate age at query time
4. **Append-Only History**: Never update historical records in place
5. **Snake Case**: All identifiers use `snake_case` convention

## Database Schema

38 ORM-backed tables organized into layers:

- **Bronze**: Raw ingestion and staging (`uploaded_files`, `raw_seed_load_runs`, `raw_seed_load_errors`, `raw_metro_areas`, `raw_pickleball_club_names`, `raw_pickleball_club_distributions`, `raw_first_names`, `raw_last_names`, `raw_state_prov_biases`)
- **Silver**: Validated entities (`players`, `clubs`, `teams`, `regions`)
- **Gold**: Analytics-ready (`player_rating_history`, `ratings_update_log`, `matches`, `match_games`, `monthly_batches`)
- **Operational**: Platform metadata (`generation_runs`, `batch_runs`, `validation_results`, `job_status`, `job_stage_progress`, `uploaded_files`, `export_runs`)
- **Configuration Repository**: Versioned generation settings (`configuration_profiles`, `configuration_profile_versions`)
- **Student Dataset Releases**: Export-release metadata (`student_dataset_releases`, `student_dataset_release_files`)

See [Database Design](docs/database/Pickleball_Simulation_Database_Design_v3.md) for complete DDL.

## Configuration

All parameters defined in [Configuration Parameters Specification](docs/generation_logic/configuration_parameters_specification.md)

Key defaults:
- Monthly player growth: **2%**
- Initial rating mean: **1500**
- Weekend concentration bias: **1.75x**
- Team persistence (recreational): **72%**
- Team persistence (competitive): **88%**

## Testing

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test module
pytest tests/unit/test_models.py

# Run integration tests
pytest tests/integration/
```

## Database Management

```bash
# Recreate local development database from ORM metadata
python backend/scripts/recreate_db_from_orm.py

# Export reference SQL from ORM metadata
python backend/scripts/export_schema_from_orm.py

# Run offline ORM consistency checks
python -m pytest backend/tests/test_orm_consistency.py -q

# Connect to database
docker exec -it pickleball-postgres psql -U postgres -d pickleball
```

## Contributing

This is an educational project with a meaningful operational footprint. See the
architecture and orchestration documents for design decisions before changing
generation, control-plane, or export behavior.

## License

Educational use only.

## Contact

For questions about the architecture, see the authoritative design documents in:
- `docs/architecture/`
- `docs/database/`
- `docs/generation_logic/`

---

**Status**: Operational simulation platform with active performance and
observability optimization  
**Last Updated**: 2026-06-03  
**Version**: 1.2
