# Pickleball Simulation Platform

**Large-Scale Synthetic Pickleball Analytics Data Generation Platform**

## Overview

This platform generates realistic synthetic pickleball match data for graduate-level data science education and Olympic team selection analytics.

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
├── backend/                    # Python application
│   ├── app/
│   │   ├── core/              # Configuration and settings
│   │   ├── db/                # Database session management
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── generation/        # Generation run and monthly pipeline orchestration
│   │   ├── generators/        # Data generation modules
│   │   ├── web/               # FastAPI web interface
│   │   └── utils/             # Shared utilities
│   ├── scripts/               # ORM, seed, and generation CLI utilities
│   ├── tests/                 # Test suite
│   └── requirements.txt       # Python dependencies
├── data/                      # Data storage
│   ├── input/                 # Reference data inputs
│   ├── output/                # Generated datasets
│   ├── parquet/               # Exported Parquet files
│   └── uploads/               # User-uploaded files
├── scripts/                   # Utility scripts
├── docs/                      # Additional documentation
├── architecture/              # Architecture specifications
├── database/                  # Database design documents
├── generation_logic/          # Generation algorithm specs
├── student_assignment/        # Student project materials
├── compose.yaml               # Docker services
└── README.md                  # This file
```

## Documentation

📚 **Start here for development:**

1. **[Quick Start Guide](docs_QUICK_START_GUIDE.md)** - 15-minute orientation
2. **[Master Document Index](docs_MASTER_DOCUMENT_INDEX.md)** - Complete navigation
3. **[Database Design](database/Pickleball_Simulation_Database_Design_v3.md)** - Schema specification
4. **[Configuration Parameters](generation_logic/configuration_parameters_specification.md)** - All parameters
5. **[Configuration Payload Architecture](architecture/configuration_payload_architecture.md)** - JSONB payload shape
6. **[Design Review Summary](docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md)** - Recent changes

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

⚠️ **CRITICAL RULES**

1. **Batch Association**: All generated data MUST include `batch_id` (NOT NULL)
2. **Historical Integrity**: Ratings stored in `player_rating_history`, NOT on `players` table
3. **Age Calculation**: Store `birth_date`, calculate age at query time
4. **Append-Only History**: Never update historical records in place
5. **Snake Case**: All identifiers use `snake_case` convention

## Database Schema

37 ORM-backed tables organized into layers:

- **Bronze**: Raw ingestion and staging (`uploaded_files`, `raw_seed_load_runs`, `raw_seed_load_errors`, `raw_metro_areas`, `raw_pickleball_club_names`, `raw_pickleball_club_distributions`, `raw_first_names`, `raw_last_names`, `raw_state_prov_biases`)
- **Silver**: Validated entities (`players`, `clubs`, `teams`, `regions`)
- **Gold**: Analytics-ready (`player_rating_history`, `ratings_update_log`, `matches`, `match_games`, `monthly_batches`)
- **Operational**: Platform metadata (`generation_runs`, `batch_runs`, `validation_results`, `job_status`, `job_stage_progress`, `uploaded_files`, `export_runs`)
- **Configuration Repository**: Versioned generation settings (`configuration_profiles`, `configuration_profile_versions`)
- **Student Dataset Releases**: Export-release metadata (`student_dataset_releases`, `student_dataset_release_files`)

See [Database Design](database/Pickleball_Simulation_Database_Design_v3.md) for complete DDL.

## Configuration

All parameters defined in [Configuration Parameters Specification](generation_logic/configuration_parameters_specification.md)

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

This is an educational project. See architecture documents for design decisions.

## License

Educational use only.

## Contact

For questions about the architecture, see the authoritative design documents in:
- `architecture/`
- `database/`
- `generation_logic/`

---

**Status**: Core generation and match/game generation in progress  
**Last Updated**: 2026-05-18  
**Version**: 1.1
