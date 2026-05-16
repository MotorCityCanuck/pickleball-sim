# Development Setup Checklist

**Pickleball Simulation Platform - Phase 1 Foundation Setup**

---

## ✅ STEP 1: PROJECT STRUCTURE (COMPLETE)

- [x] Created `backend/` directory structure
- [x] Created `backend/app/` with all submodules
  - [x] `core/` - Configuration and settings
  - [x] `db/` - Database session management
  - [x] `models/` - SQLAlchemy ORM models
  - [x] `repositories/` - Data access layer
  - [x] `services/` - Business logic services
  - [x] `generators/` - Data generation modules
  - [x] `simulations/` - Simulation engines
  - [x] `batch_processing/` - Monthly batch orchestration
  - [x] `analytics/` - Analytics computations
  - [x] `exports/` - Parquet export logic
  - [x] `validation/` - Data quality validation
  - [x] `web/` - FastAPI web interface (later)
  - [x] `utils/` - Shared utilities
- [x] Created `backend/schema.sql` for database schema
- [x] Created `backend/tests/` structure
- [x] Created `data/` directories
  - [x] `input/` - Reference data
  - [x] `output/` - Generated datasets
  - [x] `parquet/` - Parquet exports (with subdirectories)
  - [x] `uploads/` - User uploads
- [x] Created `scripts/` for utility scripts
- [x] Created `.gitignore`
- [x] Created `env.example`
- [x] Created `README.md`
- [x] Created `docker-compose.yml`
- [x] Created `requirements.txt`
- [x] Created setup script

---

## 🔄 STEP 2: ENVIRONMENT SETUP (IN PROGRESS)

### Prerequisites

- [ ] Docker Desktop installed and running
- [ ] Python 3.11+ installed
- [ ] Git installed
- [ ] Code editor (VS Code recommended)

### Environment Configuration

- [ ] Copy `env.example` to `.env`
  ```bash
  cp env.example .env
  ```
- [ ] Review `.env` and update if needed
- [ ] Ensure Docker is running

### Quick Setup Option

Run the automated setup script:
```bash
./scripts/setup_dev_environment.sh
```

### Manual Setup Steps

1. **Start PostgreSQL**
   ```bash
   docker-compose up -d postgres
   ```
   - [ ] PostgreSQL container running
   - [ ] Can connect to database

2. **Create Python Virtual Environment**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
   - [ ] Virtual environment created
   - [ ] Virtual environment activated

3. **Install Dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   - [ ] All packages installed successfully
   - [ ] No dependency conflicts

4. **Verify Installation**
   ```bash
   python -c "import sqlalchemy; print(f'SQLAlchemy: {sqlalchemy.__version__}')"
   python -c "import pandas; print(f'Pandas: {pandas.__version__}')"
   ```
   - [ ] SQLAlchemy 2.0.23+
   - [ ] Pandas 2.1.3+

---

## ⏭️ STEP 3: DATABASE SCHEMA CREATION (NEXT)

### Recreate Database from ORM Metadata

The executable schema is defined by SQLAlchemy models in `backend/app/models`.

- [ ] Create `backend/scripts/recreate_db_from_orm.py`
- [ ] Create `backend/scripts/export_schema_from_orm.py`
- [ ] Ensure all indexes and constraints are declared in ORM models

### Apply Schema to Database

```bash
# Recreate local development database
python backend/scripts/recreate_db_from_orm.py

# Regenerate SQL reference file
python backend/scripts/export_schema_from_orm.py
```

- [ ] Schema applied successfully
- [ ] `backend/schema.sql` regenerated successfully

### Verify Database Schema

```bash
docker exec -it pickleball-postgres psql -U postgres -d pickleball_sim
```
```sql
\dt                    -- List all tables (should see 22)
\d players             -- Describe players table
\d+ players            -- Detailed view with constraints
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';
\q
```
- [ ] All 22 tables created
- [ ] Constraints applied correctly
- [ ] Indexes created
- [ ] Foreign keys established

---

## ⏭️ STEP 4: CREATE SQLALCHEMY MODELS (NEXT)

Based on `database/Pickleball_Simulation_Database_Design_v3.md` Section 11.

### Core Foundation Models (Priority 1)

- [ ] `backend/app/models/base.py` - Base class and mixins
- [ ] `backend/app/models/generation_runs.py`
- [ ] `backend/app/models/monthly_batches.py`
- [ ] `backend/app/models/regions.py`

### Player and Identity Models (Priority 2)

- [ ] `backend/app/models/players.py`
- [ ] `backend/app/models/player_rating_history.py`
- [ ] `backend/app/models/player_assessment_history.py`
- [ ] `backend/app/models/player_registrations.py`

### Club and Team Models (Priority 3)

- [ ] `backend/app/models/clubs.py`
- [ ] `backend/app/models/club_memberships.py`
- [ ] `backend/app/models/teams.py`
- [ ] `backend/app/models/team_memberships.py`

### Match Models (Priority 4)

- [ ] `backend/app/models/matches.py`
- [ ] `backend/app/models/match_teams.py`
- [ ] `backend/app/models/match_team_players.py`
- [ ] `backend/app/models/tournaments.py`

### Reference Data Models (Priority 5)

- [ ] `backend/app/models/first_names.py`
- [ ] `backend/app/models/last_names.py`

### Operational Models (Priority 6)

- [ ] `backend/app/models/batch_runs.py`
- [ ] `backend/app/models/uploaded_files.py`
- [ ] `backend/app/models/export_runs.py`
- [ ] `backend/app/models/validation_results.py`
- [ ] `backend/app/models/job_status.py`

### Model Package

- [ ] Update `backend/app/models/__init__.py` with all imports

---


## ⏭️ STEP 5: VERIFY SQLALCHEMY MODELS (NEXT)


### Test Model Imports

```bash
cd backend

source venv/bin/activate
python -c "from app.models import Player, Region, MonthlyBatch; print('Models imported successfully')"
```




- [ ] All models import without errors
- [ ] No circular dependency issues


### Test Database Connection via SQLAlchemy









```bash

python -c "from app.db.session import get_db; from app.models import Player; print('Connection works')"
```


- [ ] SQLAlchemy can connect to database
- [ ] Models can query existing tables


**Note**: SQLAlchemy models are the schema source of truth. `schema.sql` is a generated/reference artifact.
















---

## ⏭️ STEP 6: DATABASE SESSION MANAGEMENT (NEXT)

### Create Database Session Handler

- [ ] `backend/app/db/session.py` - SQLAlchemy session management
- [ ] `backend/app/db/base.py` - Import all models for ORM metadata setup

### Test Database Connection

Create `backend/tests/test_db_connection.py`:
```python
def test_database_connection():
    from app.db.session import get_db_session
    with get_db_session() as session:
        result = session.execute("SELECT 1")
        assert result.scalar() == 1
```

```bash
pytest backend/tests/test_db_connection.py
```
- [ ] Test passes
- [ ] Can create session
- [ ] Can execute queries

---

## ⏭️ STEP 7: CONFIGURATION SYSTEM (NEXT)

### Create Configuration Classes

- [ ] `backend/app/core/config.py` - Pydantic settings
- [ ] Load from environment variables
- [ ] Based on `generation_logic/configuration_parameters_specification.md`

### Test Configuration

- [ ] Configuration loads from `.env`
- [ ] Defaults applied correctly
- [ ] Validation works

---

## ⏭️ STEP 8: BASIC TESTING INFRASTRUCTURE (NEXT)

### Test Configuration

- [ ] `backend/pytest.ini` - Pytest configuration
- [ ] `backend/conftest.py` - Shared fixtures

### First Tests

- [ ] Database connection test
- [ ] Model instantiation tests
- [ ] Configuration loading test

---

## 📊 PROGRESS TRACKING

| Phase | Status | Completion |
|-------|--------|------------|
| **1. Project Structure** | ✅ Complete | 100% |
| **2. Environment Setup** | 🔄 In Progress | 50% |
| **3. Database Init** | ⏭️ Next | 0% |
| **4. SQLAlchemy Models** | ⏭️ Next | 0% |
| **5. Migrations** | ⏭️ Next | 0% |
| **6. Session Management** | ⏭️ Next | 0% |
| **7. Configuration** | ⏭️ Next | 0% |
| **8. Testing** | ⏭️ Next | 0% |

---

## 🎯 CURRENT FOCUS

**YOU ARE HERE** → Step 2: Environment Setup

**NEXT STEP** → Step 3: Database Initialization (ORM recreation setup)

---

## 📚 REFERENCE DOCUMENTATION

- [Quick Start Guide](docs_QUICK_START_GUIDE.md)
- [Master Document Index](docs_MASTER_DOCUMENT_INDEX.md)
- [Database Design](database/Pickleball_Simulation_Database_Design_v3.md)
- [Configuration Spec](generation_logic/configuration_parameters_specification.md)
- [Design Review](docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md)

---

## 🆘 TROUBLESHOOTING

### Docker Issues

**PostgreSQL won't start:**
```bash
docker-compose down
docker-compose up -d postgres
docker-compose logs -f postgres
```

**Can't connect to PostgreSQL:**
- Check container is running: `docker ps`
- Check logs: `docker-compose logs postgres`
- Verify port 5432 not in use: `netstat -an | grep 5432`

### Python Issues

**Virtual environment not activating:**
- Windows: Use `venv\Scripts\activate`
- Linux/Mac: Use `source venv/bin/activate`

**Package installation fails:**
```bash
pip install --upgrade pip
pip cache purge
pip install -r requirements.txt
```

**Import errors:**
- Ensure virtual environment is activated
- Ensure you're in `backend/` directory
- Check Python path: `echo $PYTHONPATH`

---

## ✅ COMPLETION CRITERIA

Phase 1 is complete when:

- [x] All directories created
- [ ] PostgreSQL running via Docker
- [ ] Python virtual environment created
- [ ] All dependencies installed
- [ ] `backend/schema.sql` generated from ORM metadata
- [ ] All 22 SQLAlchemy models created
- [ ] Schema applied to database (all 22 tables exist)
- [ ] Database session management working
- [ ] Configuration system working
- [ ] Basic tests passing

**Estimated Time**: 1-2 days focused work

---

**Last Updated**: 2024-05-10  
**Current Phase**: 1 - Foundation Setup  
**Status**: 50% Complete
