# Next Steps - Post-Alembic Architecture

**Date**: 2024-05-15  
**Status**: Superseded by ORM-first schema recreation and generated reference SQL

> Historical note: this checklist documents the transition away from Alembic.
> The current workflow uses SQLAlchemy ORM metadata as the schema source of
> truth, `backend/scripts/recreate_db_from_orm.py` for destructive development
> database recreation, and `backend/scripts/export_schema_from_orm.py` to
> generate `backend/schema.sql`.
> This archived file contains stale 34-table schema references; use current ORM
> standards and setup docs for live schema guidance.

## Current State

- Alembic is not part of the active schema workflow.
- `backend/schema.sql` is generated from ORM metadata and must not be edited by
  hand.
- The live ORM currently defines 34 tables: 24 core platform tables, 8 raw
  seed-data staging tables, and 2 configuration repository tables.
- Consistency expectations live in `backend/tests/schema_expectations.py`.
- Use `../.venv/bin/python -m pytest -q` from `backend/` for the normal test
  suite.

## Current Commands

```bash
cd backend

# Recreate a local development database from ORM metadata.
../.venv/bin/python scripts/recreate_db_from_orm.py --yes

# Regenerate reference SQL from ORM metadata.
../.venv/bin/python scripts/export_schema_from_orm.py

# Run offline consistency and unit tests.
../.venv/bin/python -m pytest -q
```

---

The original checklist below is retained for historical context only.

---

## ✅ Completed

- [x] Removed all Alembic references from architecture.md
- [x] Updated database design document
- [x] Updated SETUP_CHECKLIST.md
- [x] Removed alembic from requirements.txt
- [x] Documented rationale and new approach

---

## 🎯 Immediate Next Actions

### Action 1: Clean Up Alembic Files (2 minutes)

```bash
cd ~/projects/pickleball-sim/backend

# Remove Alembic directories and config
rm -rf alembic/
rm -f alembic.ini

echo "✓ Alembic removed"
```

### Action 2: Extract DDL to schema.sql (15 minutes)

Extract all CREATE TABLE and CREATE INDEX statements from:
- `database/Pickleball_Simulation_Database_Design_v3.md` Section 11 (tables)
- `database/Pickleball_Simulation_Database_Design_v3.md` Section 12 (indexes)

Save as: `backend/schema.sql`

**Content structure**:
```sql
-- ============================================
-- Pickleball Simulation Platform - Database Schema
-- Generated from: database/Pickleball_Simulation_Database_Design_v3.md
-- ============================================

-- Foundation Tables
CREATE TABLE generation_runs (...);
CREATE TABLE regions (...);
CREATE TABLE monthly_batches (...);

-- Player Tables
CREATE TABLE players (...);
CREATE TABLE player_rating_history (...);
CREATE TABLE player_assessment_history (...);
CREATE TABLE player_registrations (...);

-- [... historical example originally continued for the then-current core tables ...]

-- ============================================
-- Indexes (Section 12)
-- ============================================

CREATE INDEX idx_players_region ON players(home_region_id);
-- [... all indexes ...]
```

### Action 3: Reset Database and Apply Schema (5 minutes)

```bash
# Drop and recreate database
docker exec -it pickleball-postgres psql -U postgres -c "DROP DATABASE IF EXISTS pickleball;"
docker exec -it pickleball-postgres psql -U postgres -c "CREATE DATABASE pickleball;"

# Apply schema
docker exec -i pickleball-postgres psql -U postgres -d pickleball < backend/schema.sql

# Verify
docker exec -it pickleball-postgres psql -U postgres -d pickleball -c "\dt"
docker exec -it pickleball-postgres psql -U postgres -d pickleball -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';"
```

**Historical expected output**: 22 tables at the time of this checklist.
Current ORM-backed schema expectation: 34 tables.

### Action 4: Fix Priority 2 Models (10 minutes)

Models exist but had import issues. Verify they work:

```bash
cd ~/projects/pickleball-sim/backend
source venv/bin/activate

# Test individual imports
python -c "from app.models import Base; print('Base OK')"
python -c "from app.models import Player; print('Player OK')"
python -c "from app.models import PlayerRatingHistory; print('PlayerRatingHistory OK')"
python -c "from app.models import PlayerAssessmentHistory; print('PlayerAssessmentHistory OK')"
python -c "from app.models import PlayerRegistration; print('PlayerRegistration OK')"

# Test all Priority 1 + 2 models
python -c "from app.models import GenerationRun, MonthlyBatch, Region, Player, PlayerRatingHistory, PlayerAssessmentHistory, PlayerRegistration; print('✓ All Priority 1+2 models imported')"
```

If any fail, the model files need fixing (they exist in `backend/app/models/`).

### Action 5: Create Database Session Handler (15 minutes)

**File**: `backend/app/db/session.py`

```python
"""Database session management."""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DATABASE_ECHO,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db() -> Session:
    """Context manager for database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**File**: `backend/app/db/__init__.py`

```python
"""Database package."""
from .session import engine, SessionLocal, get_db

__all__ = ['engine', 'SessionLocal', 'get_db']
```

### Action 6: Test End-to-End (5 minutes)

**File**: `backend/tests/test_database_setup.py`

```python
"""Test database setup and connectivity."""
import pytest
from sqlalchemy import inspect, text
from app.db import engine, get_db
from app.models import Player, Region, MonthlyBatch, GenerationRun


def test_database_connection():
    """Test basic database connectivity."""
    with get_db() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_all_tables_exist():
    """Verify all ORM-backed tables were created."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    assert len(tables) == 34, f"Expected 34 tables, found {len(tables)}: {tables}"
    
    # Check key tables
    expected_tables = [
        'generation_runs', 'regions', 'monthly_batches',
        'players', 'player_rating_history', 'ratings_update_log',
        'player_assessment_history', 'player_registrations',
        'clubs', 'club_memberships', 'teams', 'team_memberships',
        'matches', 'match_teams', 'match_team_players', 'tournaments',
        'first_names', 'last_names',
        'batch_runs', 'uploaded_files', 'export_runs', 'validation_results', 'job_status'
    ]
    
    for table in expected_tables:
        assert table in tables, f"Table '{table}' not found"


def test_model_to_table_mapping():
    """Test that SQLAlchemy models map to existing tables."""
    inspector = inspect(engine)
    
    # Test Priority 1 models
    assert 'generation_runs' in inspector.get_table_names()
    assert 'regions' in inspector.get_table_names()
    assert 'monthly_batches' in inspector.get_table_names()
    
    # Test Priority 2 models
    assert 'players' in inspector.get_table_names()
    assert 'player_rating_history' in inspector.get_table_names()
    assert 'player_assessment_history' in inspector.get_table_names()
    assert 'player_registrations' in inspector.get_table_names()


def test_can_query_tables():
    """Test that we can query tables via SQLAlchemy."""
    with get_db() as session:
        # Should not raise errors (tables are empty)
        regions_count = session.query(Region).count()
        players_count = session.query(Player).count()
        
        assert regions_count == 0  # No data yet
        assert players_count == 0  # No data yet


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

Run tests:

```bash
cd ~/projects/pickleball-sim/backend
source venv/bin/activate
pytest tests/test_database_setup.py -v
```

---

## 📋 Checklist Summary

- [ ] Remove alembic directories (`rm -rf alembic/`)
- [ ] Create `backend/schema.sql` from database design doc
- [ ] Drop and recreate database
- [ ] Apply schema (`psql -f schema.sql`)
- [ ] Verify 34 tables exist
- [ ] Test Priority 1+2 model imports
- [ ] Create `backend/app/db/session.py`
- [ ] Create `backend/app/db/__init__.py`
- [ ] Create `backend/tests/test_database_setup.py`
- [ ] Run tests (`pytest tests/test_database_setup.py -v`)

**Estimated time**: 45-60 minutes total

---

## 🎉 Success Criteria

When complete, you should have:

✅ Clean architecture (no Alembic)  
✅ 34 database tables created via ORM metadata
✅ SQLAlchemy models that work with existing schema  
✅ Database session management  
✅ Passing tests  
✅ Core, reference, and raw seed-data models implemented  
✅ Foundation for data generation logic  

---

## 🚀 After This (Priority 3)

Once database foundation is solid:

1. **Create Configuration System** (`app/core/config.py`)
2. **Build Club Models** (clubs, club_memberships)
3. **Build Team Models** (teams, team_memberships)
4. **Build Match Models** (matches, match_teams, match_team_players, tournaments)
5. **Build Reference Data Models** (USA/Canada names)
6. **Build Operational Models** (batch_runs, exports, validation, etc.)

Then move to:

7. **Data Generation Logic** (generators/)
8. **Simulation Engine** (simulations/)
9. **Batch Processing** (batch_processing/)
10. **Web Control Panel** (web/)

---

**Ready to proceed with Action 1?** Let me know when you want to start extracting the DDL!
