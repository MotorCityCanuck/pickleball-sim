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
│   │   │   ├── 📄 config.py                        # Runtime settings
│   │   │   ├── 📄 configuration_profiles.py        # Versioned config repository helpers
│   │   │   └── 📄 default_configuration.py         # Default generation payload
│   │   │
│   │   ├── 📂 db/                                  # Database management
│   │   │   ├── 📄 __init__.py
│   │   │   └── 📄 session.py                       # SQLAlchemy engine/session scope
│   │   │
│   │   ├── 📂 models/                              # SQLAlchemy ORM models (33 total)
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 base.py                          # Base model + mixins
│   │   │   ├── 📄 generation_runs.py               # Generation control
│   │   │   ├── 📄 monthly_batches.py               # Batch metadata
│   │   │   ├── 📄 regions.py                       # Geographic regions
│   │   │   ├── 📄 players.py                       # Player identity
│   │   │   ├── 📄 player_rating_history.py         # Rating time-series
│   │   │   ├── 📄 player_assessment_history.py     # Assessment metrics
│   │   │   ├── 📄 player_registrations.py          # New player intake
│   │   │   ├── 📄 clubs.py                         # Club entities
│   │   │   ├── 📄 club_memberships.py              # Player-club links
│   │   │   ├── 📄 teams.py                         # Persistent teams
│   │   │   ├── 📄 team_memberships.py              # Team rosters
│   │   │   ├── 📄 matches.py                       # Match metadata
│   │   │   ├── 📄 match_games.py                   # Match games and scores
│   │   │   ├── 📄 match_teams.py                   # Match participants
│   │   │   ├── 📄 match_team_players.py            # Player participation
│   │   │   ├── 📄 tournaments.py                   # Tournament events
│   │   │   ├── 📄 first_names.py                   # Consolidated first-name frequency data
│   │   │   ├── 📄 last_names.py                    # Consolidated surname frequency data
│   │   │   ├── 📄 batch_runs.py                    # Batch execution
│   │   │   ├── 📄 uploaded_files.py                # File uploads
│   │   │   ├── 📄 export_runs.py                   # Export metadata
│   │   │   ├── 📄 validation_results.py            # Validation logs
│   │   │   ├── 📄 job_status.py                    # Job tracking
│   │   │   ├── 📄 raw_seed_load_runs.py            # Raw seed load tracking
│   │   │   ├── 📄 raw_seed_load_errors.py          # Raw seed load errors
│   │   │   ├── 📄 raw_metro_areas.py               # Raw metro-area staging
│   │   │   ├── 📄 raw_pickleball_club_names.py     # Raw club-name staging
│   │   │   ├── 📄 raw_pickleball_club_distributions.py # Raw club-count staging
│   │   │   ├── 📄 raw_first_names.py               # Raw first-name staging
│   │   │   ├── 📄 raw_last_names.py                # Raw surname staging
│   │   │   └── 📄 raw_state_prov_biases.py         # Raw surname bias staging
│   │   │
│   │   ├── 📂 generation/                          # Batch planning and orchestration
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 control_plane.py                 # Generation run/batch creation
│   │   │   └── 📄 orchestrator.py                  # Module orchestration
│   │   │
│   │   ├── 📂 generators/                          # Data generation modules
│   │   │   ├── 📄 __init__.py
│   │   │   ├── 📄 players.py                       # Player creation and initial ratings
│   │   │   ├── 📄 club_memberships.py              # Player-club memberships
│   │   │   ├── 📄 teams.py                         # Point-in-time team determination
│   │   │   ├── 📄 matches.py                       # Match scheduling and pairing
│   │   │   └── 📄 games.py                         # Game scores and expected score metrics
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
│   ├── 📂 scripts/                                 # ORM schema utilities
│   │   ├── 📄 recreate_db_from_orm.py              # [TODO] Recreate dev DB
│   │   └── 📄 export_schema_from_orm.py            # [TODO] Generate schema.sql
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
├── 📂 backend/scripts/                             # Backend command-line utilities
│   ├── 📄 recreate_db_from_orm.py                  # Rebuild local DB from ORM metadata
│   ├── 📄 export_schema_from_orm.py                # Export schema.sql from ORM metadata
│   ├── 📄 seed_configuration_profile.py            # Seed default config profile/version
│   ├── 📄 load_raw_seed_data.py                    # Load raw seed staging tables
│   ├── 📄 normalize_seed_data.py                   # Promote raw seed data to production tables
│   ├── 📄 create_generation_plan.py                # Create generation run and batch records
│   ├── 📄 generate_players.py                      # Generate players and initial ratings
│   ├── 📄 generate_club_memberships.py             # Generate club memberships
│   ├── 📄 generate_teams.py                        # Determine point-in-time teams
│   └── 📄 generate_matches.py                      # Generate matches, teams, players, and games
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
| `backend/app/core/` | Configuration and settings | 🔴 Critical | Implemented |
| `backend/app/db/` | Database session management | 🔴 Critical | Implemented |
| `backend/app/models/` | SQLAlchemy ORM models (33 tables) | 🔴 Critical | Implemented |
| `backend/app/generation/` | Generation run planning and orchestration | 🟠 High | Implemented |
| `backend/app/generators/` | Data generation modules | 🟠 High | In progress |
| `backend/app/seed_data_ingest/` | Raw seed loading | 🟠 High | Implemented |
| `backend/app/seed_data_normalize/` | Seed data normalization | 🟠 High | Implemented |
| `backend/scripts/` | ORM, seed, and generation utilities | 🔴 Critical | Implemented |
| `backend/tests/` | Test suite | 🟠 High | Implemented |
| `data/` | Data storage (git-ignored) | 🟠 High | ✅ Created |
| `scripts/` | Utility scripts | 🟡 Medium | Partial |

---

## 🎯 Implementation Phases

### Phase 1: Foundation
1. ✅ Project structure created
2. ✅ Database models (33 tables)
3. ✅ ORM schema recreation scripts
4. ✅ Session management
5. ✅ Configuration system

### Phase 2: Core Generation
6. ✅ Raw seed loading and normalization
7. ✅ Player generation
8. ✅ Initial rating history generation
9. ✅ Club membership generation
10. ✅ Point-in-time team determination

### Phase 3: Match Simulation
11. ✅ Match scheduling
12. ✅ Matchmaking
13. ✅ Game and score generation
14. ✅ Predicted winner and expected score fields
15. ⏭️ Rating calculation

### Phase 4: Batch Processing
16. ✅ Generation run and batch creation
17. ⏭️ Full monthly orchestration
18. ⏭️ Validation framework
19. ⏭️ Parquet exports
20. ✅ Integration tests for implemented modules

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
- **Backend Python Modules**: 50+ implemented across ORM, seed loading,
  generation, and tests
- **Test Files**: 30 implemented backend test modules

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

3. Recreate the development database from ORM metadata:
   ```bash
   python backend/scripts/recreate_db_from_orm.py
   ```

4. Maintain all 33 SQLAlchemy models in `backend/app/models/`

5. Generate reference SQL from ORM metadata

---

**Last Updated**: 2026-05-18  
**Current Phase**: Match simulation and rating engine buildout  
**Progress**: Core ORM, seed loading, players, clubs, teams, matches,
and games implemented; rating update engine remains next.
