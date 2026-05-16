# Project Structure Overview

**Pickleball Simulation Platform - Directory Layout**

---

## 📁 Complete Directory Tree

```
pickleball-sim/
│
├── 📄 README.md                                    # Project overview and quick start
├── 📄 SETUP_CHECKLIST.md                           # Step-by-step setup guide
├── 📄 PROJECT_STRUCTURE.md                         # This file
├── 📄 .gitignore                                   # Git ignore rules
├── 📄 env.example                                  # Environment template
├── 📄 docker-compose.yml                           # Docker services definition
│
├── 📂 backend/                                     # Python application root
│   ├── 📄 requirements.txt                         # Python dependencies
│   │
│   ├── 📂 app/                                     # Main application package
│   │   ├── 📄 __init__.py                          # Package marker
│   │   │
│   │   ├── 📂 core/                                # Core configuration
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 config.py                        # [TODO] Pydantic settings
│   │   │   └── 📄 logging.py                       # [TODO] Logging config
│   │   │
│   │   ├── 📂 db/                                  # Database management
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 session.py                       # [TODO] SQLAlchemy session
│   │   │   └── 📄 base.py                          # [TODO] Model registry
│   │   │
│   │   ├── 📂 models/                              # SQLAlchemy ORM models (23 total)
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 base.py                          # [TODO] Base model + mixins
│   │   │   ├── 📄 generation_runs.py               # [TODO] Generation control
│   │   │   ├── 📄 monthly_batches.py               # [TODO] Batch metadata
│   │   │   ├── 📄 regions.py                       # [TODO] Geographic regions
│   │   │   ├── 📄 players.py                       # [TODO] Player identity
│   │   │   ├── 📄 player_rating_history.py         # [TODO] Rating time-series
│   │   │   ├── 📄 player_assessment_history.py     # [TODO] Assessment metrics
│   │   │   ├── 📄 player_registrations.py          # [TODO] New player intake
│   │   │   ├── 📄 clubs.py                         # [TODO] Club entities
│   │   │   ├── 📄 club_memberships.py              # [TODO] Player-club links
│   │   │   ├── 📄 teams.py                         # [TODO] Persistent teams
│   │   │   ├── 📄 team_memberships.py              # [TODO] Team rosters
│   │   │   ├── 📄 matches.py                       # [TODO] Match metadata
│   │   │   ├── 📄 match_teams.py                   # [TODO] Match participants
│   │   │   ├── 📄 match_team_players.py            # [TODO] Player participation
│   │   │   ├── 📄 tournaments.py                   # [TODO] Tournament events
│   │   │   ├── 📄 usa_first_names.py               # [TODO] Name frequency data
│   │   │   ├── 📄 usa_last_names.py                # [TODO] Surname data
│   │   │   ├── 📄 canada_first_names.py            # [TODO] Canadian names
│   │   │   ├── 📄 canada_last_names.py             # [TODO] Canadian surnames
│   │   │   ├── 📄 batch_runs.py                    # [TODO] Batch execution
│   │   │   ├── 📄 uploaded_files.py                # [TODO] File uploads
│   │   │   ├── 📄 export_runs.py                   # [TODO] Export metadata
│   │   │   ├── 📄 validation_results.py            # [TODO] Validation logs
│   │   │   └── 📄 job_status.py                    # [TODO] Job tracking
│   │   │
│   │   ├── 📂 repositories/                        # Data access layer
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 base_repository.py               # [TODO] Base CRUD
│   │   │   ├── 📄 player_repository.py             # [TODO] Player queries
│   │   │   └── 📄 match_repository.py              # [TODO] Match queries
│   │   │
│   │   ├── 📂 services/                            # Business logic
│   │   │   ├── 📄 __init__.py
│   │   │   └── 📄 generation_orchestrator.py       # [TODO] Main orchestrator
│   │   │
│   │   ├── 📂 generators/                          # Data generation modules
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 player_generator.py              # [TODO] Player creation
│   │   │   ├── 📄 region_generator.py              # [TODO] Regional allocation
│   │   │   ├── 📄 club_generator.py                # [TODO] Club creation
│   │   │   ├── 📄 team_generator.py                # [TODO] Team formation
│   │   │   ├── 📄 match_generator.py               # [TODO] Match scheduling
│   │   │   └── 📄 rating_generator.py              # [TODO] Rating calculation
│   │   │
│   │   ├── 📂 simulations/                         # Simulation engines
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 match_simulation.py              # [TODO] Match outcomes
│   │   │   └── 📄 score_simulation.py              # [TODO] Score generation
│   │   │
│   │   ├── 📂 batch_processing/                    # Monthly batch logic
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 monthly_processor.py             # [TODO] Batch orchestration
│   │   │   └── 📄 batch_state_machine.py           # [TODO] State management
│   │   │
│   │   ├── 📂 analytics/                           # Analytics computations
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 confidence_calculator.py         # [TODO] Confidence scoring
│   │   │   └── 📄 ranking_calculator.py            # [TODO] Ranking logic
│   │   │
│   │   ├── 📂 exports/                             # Export pipelines
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 parquet_exporter.py              # [TODO] Parquet generation
│   │   │   └── 📄 export_manifest.py               # [TODO] Manifest creation
│   │   │
│   │   ├── 📂 validation/                          # Data quality validation
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 validation_engine.py             # [TODO] Rule executor
│   │   │   └── 📄 validation_rules.py              # [TODO] 35 validation rules
│   │   │
│   │   ├── 📂 web/                                 # Web interface (Phase 5)
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📂 routes/                          # FastAPI routes
│   │   │   │   └── 📄 __init__.py
│   │   │   ├── 📂 templates/                       # Jinja2 templates
│   │   │   │   └── 📂 partials/                    # HTMX partials
│   │   │   └── 📂 static/                          # Static assets
│   │   │       ├── 📂 css/
│   │   │       └── 📂 js/
│   │   │
│   │   └── 📂 utils/                               # Shared utilities
│   │       ├── 📄 __init__.py
│   │       ├── 📄 random_context.py                # [TODO] Seeded randomness
│   │       └── 📄 module_result.py                 # [TODO] Standard return objects
│   │
│   ├── 📂 alembic/                                 # Database migrations
│   │   ├── 📄 env.py                               # [TODO] Alembic environment
│   │   ├── 📄 script.py.mako                       # Migration template
│   │   └── 📂 versions/                            # Migration versions
│   │
│   └── 📂 tests/                                   # Test suite
│       ├── 📄 conftest.py                          # [TODO] Pytest fixtures
│       ├── 📂 unit/                                # Unit tests
│       ├── 📂 integration/                         # Integration tests
│       ├── 📂 generators/                          # Generator tests
│       ├── 📂 simulations/                         # Simulation tests
│       ├── 📂 batch_processing/                    # Batch tests
│       ├── 📂 exports/                             # Export tests
│       ├── 📂 web/                                 # Web tests
│       └── 📂 analytics/                           # Analytics tests
│
├── 📂 data/                                        # Data storage (git-ignored)
│   ├── 📂 input/                                   # Reference data inputs
│   │   └── 📄 .gitkeep
│   ├── 📂 output/                                  # Generated datasets
│   │   └── 📄 .gitkeep
│   ├── 📂 parquet/                                 # Exported Parquet files
│   │   ├── 📄 .gitkeep
│   │   ├── 📂 historical/                          # Initial 12 months
│   │   │   └── 📄 .gitkeep
│   │   ├── 📂 monthly/                             # Future batches
│   │   │   └── 📄 .gitkeep
│   │   ├── 📂 reference/                           # Static reference data
│   │   │   └── 📄 .gitkeep
│   │   └── 📂 metadata/                            # Export manifests
│   │       └── 📄 .gitkeep
│   └── 📂 uploads/                                 # User-uploaded files
│       └── 📄 .gitkeep
│
├── 📂 scripts/                                     # Utility scripts
│   ├── 📄 setup_dev_environment.sh                 # Automated setup
│   ├── 📄 load_reference_regions.py                # [TODO] Load regions
│   └── 📄 load_reference_names.py                  # [TODO] Load name data
│
├── 📂 docs/                                        # Additional documentation
│   └── (Created during design review)
│
├── 📂 architecture/                                # Architecture specifications
│   ├── 📄 architecture.md                          # Primary architecture doc
│   ├── 📄 Pickleball_Simulation_Detailed_Module_Interface_Specifications.md
│   └── ... (other architecture docs)
│
├── 📂 database/                                    # Database design
│   └── 📄 Pickleball_Simulation_Database_Design_v3.md
│
├── 📂 generation_logic/                            # Generation algorithm specs
│   ├── 📄 configuration_parameters_specification.md
│   ├── 📄 Pickleball_Simulation_Generation_Sequence_Specification.md
│   ├── 📄 pickleball_match_game_monthly_batch_logic_v2_weekend_weighted.md
│   ├── 📄 pickleball_team_determination_logic_v2.md
│   ├── 📄 pickleball_matchmaking_logic.md
│   ├── 📄 player_region_and_name_assignment_logic.md
│   ├── 📄 NAPA_Historical_Simulation_Design_v4_Player_Growth.md
│   └── ... (other generation logic docs)
│
├── 📂 student_assignment/                          # Student project materials
│   ├── 📄 NAPA_Olympic_Analytics_Capstone_Rewritten.md
│   └── 📄 NAPA_Olympic_Analytics_RFP_Industry_Style_v2.md
│
├── 📄 docs_QUICK_START_GUIDE.md                    # 15-minute orientation
├── 📄 docs_MASTER_DOCUMENT_INDEX.md                # Complete doc navigation
└── 📄 docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md    # Design review audit trail
```

---

## 📊 Directory Purpose Summary

| Directory | Purpose | Priority | Status |
|-----------|---------|----------|--------|
| `backend/app/core/` | Configuration and settings | 🔴 Critical | TODO |
| `backend/app/db/` | Database session management | 🔴 Critical | TODO |
| `backend/app/models/` | SQLAlchemy ORM models (23 tables) | 🔴 Critical | TODO |
| `backend/app/repositories/` | Data access layer | 🟠 High | TODO |
| `backend/app/generators/` | Data generation modules | 🟠 High | TODO |
| `backend/app/simulations/` | Match/score simulation | 🟠 High | TODO |
| `backend/app/batch_processing/` | Monthly orchestration | 🟠 High | TODO |
| `backend/app/validation/` | Data quality rules | 🟡 Medium | TODO |
| `backend/app/exports/` | Parquet export logic | 🟡 Medium | TODO |
| `backend/app/analytics/` | Derived computations | 🟡 Medium | TODO |
| `backend/app/web/` | FastAPI control panel | 🟢 Low (Phase 5) | TODO |
| `backend/alembic/` | Database migrations | 🔴 Critical | TODO |
| `backend/tests/` | Test suite | 🟠 High | TODO |
| `data/` | Data storage (git-ignored) | 🟠 High | ✅ Created |
| `scripts/` | Utility scripts | 🟡 Medium | Partial |

---

## 🎯 Implementation Phases

### Phase 1: Foundation (Current) - Days 1-2
1. ✅ Project structure created
2. ⏭️ Database models (23 files)
3. ⏭️ Alembic migrations
4. ⏭️ Session management
5. ⏭️ Configuration system

### Phase 2: Core Generation - Days 3-7
6. Regional distribution
7. Player generation
8. Club generation
9. Reference data loading
10. Basic testing

### Phase 3: Match Simulation - Days 8-12
11. Team formation
12. Match scheduling
13. Matchmaking
14. Score generation
15. Rating calculation

### Phase 4: Batch Processing - Days 13-17
16. Monthly orchestration
17. Player registration
18. Validation framework
19. Parquet exports
20. Integration tests

### Phase 5: Web Interface - Days 18-20
21. FastAPI setup
22. HTMX control panel
23. Job monitoring
24. Export management

---

## 📝 File Counts

- **Total Directories**: 40+
- **Configuration Files**: 4 (✅ Created)
- **Documentation Files**: 25+ (✅ Created)
- **Python Modules to Create**: ~60 (⏭️ Next)
- **Test Files to Create**: ~40 (⏭️ Later)

---

## 🚀 Next Steps

**Immediate Priority** (You are here):

1. Run environment setup:
   ```bash
   ./scripts/setup_dev_environment.sh
   ```

2. Verify PostgreSQL is running:
   ```bash
   docker ps
   ```

3. Initialize Alembic:
   ```bash
   cd backend
   alembic init alembic
   ```

4. Create all 23 SQLAlchemy models in `backend/app/models/`

5. Generate and apply first migration

---

**Last Updated**: 2024-05-10  
**Current Phase**: 1 - Foundation  
**Progress**: Structure Complete, Models TODO
