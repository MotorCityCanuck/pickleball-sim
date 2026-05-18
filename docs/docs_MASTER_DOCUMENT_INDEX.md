# Master Document Index

**Pickleball Simulation Platform - Authoritative Design Documentation**

**Last Updated**: 2026-05-18  
**Status**: ✅ Reviewed and Consistent  
**Version**: 1.1

---

## Document Purpose

This index provides a hierarchical guide to all authoritative design documents for the Pickleball Simulation Platform. All documents have been reviewed for consistency and conflicts have been resolved.

**Development Rule**: These documents are the source of truth. Implementation must conform to these specifications.

---

## Quick Navigation

| Priority | Category | Key Documents |
|----------|----------|---------------|
| 🔴 **CRITICAL** | Foundation | architecture.md, database design, configuration spec |
| 🟠 **HIGH** | Generation Logic | Monthly batch, team formation, matchmaking |
| 🟡 **MEDIUM** | Implementation | Module interfaces, generation sequence |
| 🟢 **REFERENCE** | Context | Student assignment, RFP, dev guides |

---

## 1. Foundation Documents (READ FIRST)

### 1.1 System Architecture
**File**: `architecture/architecture.md`  
**Purpose**: Overall platform vision, technology stack, repository structure  
**Key Sections**:
- Application vision and goals
- Technology stack (FastAPI, PostgreSQL, Docker, HTMX)
- Repository structure
- Web control panel architecture
- Generation workflow overview
- AI-assisted development standards

**When to Reference**: Architecture decisions, technology choices, project structure

---

### 1.2 Database Design
**File**: `database/Pickleball_Simulation_Database_Design_v3.md`  
**Purpose**: Authoritative schema definition and data model  
**Key Sections**:
- Complete DDL for the core schema, with ORM-generated reference SQL covering
  34 live tables
- 90 explicit ORM indexes in the generated reference SQL
- 63 live check constraints verified by `backend/tests/schema_expectations.py`
- 14 unique constraints in the live ORM expectations
- Validation rules and constraints are kept aligned with the ORM consistency tests
- Parquet export strategy
- Medallion architecture (Bronze/Silver/Gold)
- Critical design prohibitions

**When to Reference**: Database implementation, migrations, queries, data modeling

**⚠️ CRITICAL RULES**:
- NO `age` column on `players` - use `birth_date`
- NO `current_rating` on `players` - use `player_rating_history`
- ALL generated data MUST include `batch_id` (NOT NULL)
- Historical records are append-only (never update in place)

---

### 1.3 Configuration Parameters
**File**: `generation_logic/configuration_parameters_specification.md`  
**Purpose**: Standardized parameter names, types, defaults, and ranges  
**Key Sections**:
- 120+ parameters with complete specifications
- Noise configuration matrix
- Parameter validation rules
- YAML/JSON examples
- Configuration precedence
- Deprecated parameter mappings

**When to Reference**: Configuration loading, parameter validation, default values

### 1.4 Configuration Payload Architecture
**File**: `architecture/configuration_payload_architecture.md`  
**Purpose**: Canonical JSONB payload grouped by domain, including export table
allow-lists and naming rules.

**When to Reference**: Configuration profile storage, web UI configuration
editing, payload validation, and run snapshot creation.

**📋 Key Parameter Categories**:
- Global simulation parameters
- Player generation parameters
- Rating and assessment parameters
- Regional distribution parameters
- Club generation parameters
- Team formation parameters
- Match scheduling parameters
- Matchmaking parameters
- Validation parameters

---

## 2. Generation Logic Specifications (IMPLEMENTATION GUIDE)

### 2.1 Monthly Batch Processing
**File**: `generation_logic/pickleball_match_game_monthly_batch_logic_v2_weekend_weighted.md`  
**Purpose**: Monthly batch workflow, match scheduling, weekend concentration  
**Key Sections**:
- Batch state machine
- Match frequency configuration
- Weekend concentration bias (Section 23)
- Day-of-month distribution
- Noise injection framework

**When to Reference**: Monthly batch implementation, match scheduling, calendar allocation

**🔑 Key Insight**: Weekend concentration should be probability-weighted, not deterministic. Target 40-60% weekend matches for recreational play.

---

### 2.2 Generation Sequence
**File**: `generation_logic/Pickleball_Simulation_Generation_Sequence_Specification.md`  
**Purpose**: Authoritative step-by-step generation workflow  
**Key Sections**:
- 21-step detailed sequence
- Module dependencies
- Retry and rerun rules
- Validation gates
- Success criteria per step

**When to Reference**: Orchestration implementation, batch processor, module ordering

**⚠️ CRITICAL**: Steps must execute in documented order. Some steps have hard dependencies.

---

### 2.3 Team Formation
**File**: `generation_logic/pickleball_team_determination_logic_v2.md`  
**Purpose**: Team persistence, partner continuity, chemistry modeling  
**Key Sections**:
- Persistent vs ad-hoc teams
- Team chemistry scoring
- Monthly continuity logic
- Partner replacement rules
- Persistence probabilities

**When to Reference**: Team generation, partnership modeling, social graph

**📊 Default Persistence Rates**:
- Recreational: 65-80%
- Competitive: 80-95%

---

### 2.4 Matchmaking Logic
**File**: `generation_logic/pickleball_matchmaking_logic.md`  
**Purpose**: Opponent selection, rating bands, controlled randomness  
**Key Sections**:
- Match context determination
- Skill banding logic
- Team compatibility scoring
- Repeat partner affinity
- Controlled randomness framework

**When to Reference**: Match pairing, opponent selection, social graph evolution

---

### 2.5 Player and Name Assignment
**File**: `generation_logic/player_region_and_name_assignment_logic.md`  
**Purpose**: Regional distribution, census-based naming, demographic modeling  
**Key Sections**:
- Regional population weighting
- Metropolitan concentration
- Birth year and gender generation
- Census frequency-based naming
- Temporal naming realism

**When to Reference**: Player generation, name generation, regional allocation

---

### 2.6 Club Generation
**File**: `generation_logic/pickleball_database_generation_club_logic_addendum.md`  
**Purpose**: Club generation, power-law distribution, capacity modeling  
**Key Sections**:
- Club count calculation (~1 club per 75k population)
- Club size distribution (power-law)
- Regional scaling
- Facility types

**When to Reference**: Club generation, capacity planning

**📊 Club Size Distribution**:
- 35% small (10-30 members)
- 40% medium (31-75 members)
- 20% large (76-200 members)
- 5% mega (200+ members)

---

### 2.7 Club Assignment
**File**: `generation_logic/player_to_club_assignment_logic_updated.md`  
**Purpose**: Player-to-club assignment post-processing  
**Key Sections**:
- Assignment occurs AFTER player creation
- Weighted probabilistic scoring
- Independent player modeling (~12% unaffiliated)

**When to Reference**: Club membership assignment

---

### 2.8 Match and Game Identification
**File**: `generation_logic/pickleball_match_game_identification_logic.md`  
**Purpose**: Match/game ID strategy, scoring, participation frequency  
**Key Sections**:
- Match ID format: `MATCH_<REGION>_<YYYYMM>_<SEQUENCE>`
- Game ID format: `GAME_<MATCH_ID>_<GAME_NUMBER>`
- Score generation logic

**When to Reference**: Match ID generation, game ID generation

---

### 2.9 Historical Simulation Design
**File**: `generation_logic/NAPA_Historical_Simulation_Design_v4_Player_Growth.md`  
**Purpose**: Rating system, confidence modeling, point-in-time assessments  
**Key Sections**:
- True skill vs observed rating
- Score-adjusted ELO rating system
- Confidence calculation
- Historical assessment storage
- Monthly player growth (2% default)

**When to Reference**: Rating calculations, confidence modeling, assessment history

**🔑 Key Architectural Principle**: Ratings stored in `player_rating_history`, NOT in `players` table

---

## 3. Implementation Specifications (DEVELOPMENT CONTRACTS)

### 3.1 Module Interface Specifications
**File**: `architecture/Pickleball_Simulation_Detailed_Module_Interface_Specifications.md`  
**Purpose**: Module contracts, data structures, return objects  
**Key Sections**:
- SimulationConfig structure
- RandomContext structure
- ModuleResult structure
- ValidationResult structure
- ExportManifest structure
- Detailed module-by-module contracts

**When to Reference**: Module implementation, interface design, testing

**📋 Key Modules**:
- configuration_loader
- database_session_manager
- reference_data_loader
- regional_distribution_engine
- club_generator
- player_core_generator
- name_assignment_engine
- club_assignment_engine
- rating_initialization_engine
- team_assignment_engine
- match_scheduler
- matchmaking_engine
- game_generation_engine
- rating_engine
- confidence_engine
- monthly_batch_processor
- validation_engine
- parquet_exporter
- web_control_service

---

## 4. Student-Facing Documents (CONTEXT)

### 4.1 Capstone Assignment
**File**: `student_assignment/NAPA_Olympic_Analytics_Capstone_Rewritten.md`  
**Purpose**: Student project requirements, deliverables, consulting engagement  
**Key Sections**:
- Business scenario
- Olympic team selection criteria
- Required analytical outcomes
- Enterprise architecture expectations
- Team roles and responsibilities

**When to Reference**: Understanding student use case, analytics requirements

---

### 4.2 RFP (Industry Style)
**File**: `student_assignment/NAPA_Olympic_Analytics_RFP_Industry_Style_v2.md`  
**Purpose**: Formal RFP document for consulting engagement  

**When to Reference**: Project context, business requirements

---

## 5. Developer Guides (ONBOARDING)

### 5.1 Comprehensive Instructor Guide
**File**: `architecture/Comprehensive_Instructor_AI_Dev_Guide_Windows_Dev_Environment_v3.md`  
**Purpose**: Instructor AI development workflow, Windows environment setup  

**When to Reference**: Development environment setup, AI-assisted workflows

---

### 5.2 Student AI Development Guide
**File**: `architecture/Fully_Expanded_Student_AI_Dev_Guide-v5-final.md`  
**Purpose**: Student-facing guide for AI-assisted development  

**When to Reference**: Student onboarding, AI tool usage

---

### 5.3 Claude vs Codex Workflow
**File**: `architecture/Claude_vs_Codex_Workflow_and_Recommendations.md`  
**Purpose**: AI tool selection and usage recommendations  

**When to Reference**: Choosing AI tools for specific tasks

---

## 6. Review and Correction Documents

### 6.1 Design Review Summary
**File**: `docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md`  
**Purpose**: Complete record of all corrections made during pre-development review  
**Key Sections**:
- 15 critical findings resolved
- Before/after comparisons
- Statistics (8 → 23 DDL statements, 3 → 48 indexes, etc.)
- Breaking changes (none)
- Validation checklist

**When to Reference**: Understanding what changed and why, audit trail

---

### 6.2 Master Document Index
**File**: `docs_MASTER_DOCUMENT_INDEX.md` (this document)  
**Purpose**: Navigation guide and document relationships  

---

## Document Dependency Graph

```
architecture.md (FOUNDATION)
    ├── database_design_v3.md (SCHEMA)
    │   ├── player_rating_history (table)
    │   ├── player_assessment_history (table)
    │   ├── monthly_batches (table)
    │   └── validation_results (table)
    │
    ├── configuration_parameters_specification.md (CONFIG)
    │   ├── monthly_player_growth_rate
    │   ├── weekend_concentration_bias
    │   └── rating_noise_std_dev
    │
    └── generation_logic/*.md (ALGORITHMS)
        ├── monthly_batch_logic (orchestration)
        ├── generation_sequence (step-by-step)
        ├── team_determination (partnerships)
        ├── matchmaking_logic (opponent selection)
        ├── player_region_name_assignment (identity)
        ├── club_generation (facilities)
        ├── club_assignment (membership)
        ├── match_game_identification (IDs)
        └── historical_simulation_design (ratings)
```

---

## Reading Order for New Developers

### Phase 1: Foundation
1. `architecture/architecture.md` - Big picture
2. `database/Pickleball_Simulation_Database_Design_v3.md` - Data model
3. `docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md` - What changed and why

### Phase 2: Configuration
4. `generation_logic/configuration_parameters_specification.md` - All parameters

### Phase 3: Generation Logic
5. `generation_logic/Pickleball_Simulation_Generation_Sequence_Specification.md` - Step-by-step workflow
6. `generation_logic/NAPA_Historical_Simulation_Design_v4_Player_Growth.md` - Rating system
7. `generation_logic/pickleball_match_game_monthly_batch_logic_v2_weekend_weighted.md` - Monthly processing

### Phase 4: Detailed Generation
8. `generation_logic/player_region_and_name_assignment_logic.md`
9. `generation_logic/pickleball_database_generation_club_logic_addendum.md`
10. `generation_logic/player_to_club_assignment_logic_updated.md`
11. `generation_logic/pickleball_team_determination_logic_v2.md`
12. `generation_logic/pickleball_matchmaking_logic.md`
13. `generation_logic/pickleball_match_game_identification_logic.md`

### Phase 5: Implementation Contracts
14. `architecture/Pickleball_Simulation_Detailed_Module_Interface_Specifications.md`

### Phase 6: Context (As Needed)
15. `student_assignment/NAPA_Olympic_Analytics_Capstone_Rewritten.md`

---

## Document Status Codes

| Status | Meaning |
|--------|---------|
| ✅ **REVIEWED** | Reviewed in pre-development audit, conflicts resolved |
| 📋 **AUTHORITATIVE** | Source of truth for this domain |
| 🔄 **SUPERSEDES** | Replaces older version |
| ⚠️ **DEPRECATED** | Contains outdated information, see corrections doc |

---

## All Documents Status

| Document | Status | Priority |
|----------|--------|----------|
| `architecture/architecture.md` | ✅ 📋 | 🔴 CRITICAL |
| `database/Pickleball_Simulation_Database_Design_v3.md` | ✅ 📋 | 🔴 CRITICAL |
| `generation_logic/configuration_parameters_specification.md` | ✅ 📋 | 🔴 CRITICAL |
| `generation_logic/Pickleball_Simulation_Generation_Sequence_Specification.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/pickleball_match_game_monthly_batch_logic_v2_weekend_weighted.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/pickleball_team_determination_logic_v2.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/pickleball_matchmaking_logic.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/player_region_and_name_assignment_logic.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/NAPA_Historical_Simulation_Design_v4_Player_Growth.md` | ✅ 📋 | 🟠 HIGH |
| `generation_logic/pickleball_database_generation_club_logic_addendum.md` | ✅ 📋 | 🟡 MEDIUM |
| `generation_logic/player_to_club_assignment_logic_updated.md` | ✅ 📋 | 🟡 MEDIUM |
| `generation_logic/pickleball_match_game_identification_logic.md` | ✅ 📋 | 🟡 MEDIUM |
| `architecture/Pickleball_Simulation_Detailed_Module_Interface_Specifications.md` | ✅ 📋 | 🟡 MEDIUM |
| `student_assignment/NAPA_Olympic_Analytics_Capstone_Rewritten.md` | ✅ | 🟢 REFERENCE |
| `student_assignment/NAPA_Olympic_Analytics_RFP_Industry_Style_v2.md` | ✅ | 🟢 REFERENCE |
| `architecture/Comprehensive_Instructor_AI_Dev_Guide_Windows_Dev_Environment_v3.md` | ✅ | 🟢 REFERENCE |
| `architecture/Fully_Expanded_Student_AI_Dev_Guide-v5-final.md` | ✅ | 🟢 REFERENCE |
| `architecture/Claude_vs_Codex_Workflow_and_Recommendations.md` | ✅ | 🟢 REFERENCE |
| `docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md` | ✅ 📋 | 🔴 CRITICAL |
| `docs_MASTER_DOCUMENT_INDEX.md` | ✅ 📋 | 🔴 CRITICAL |

---

## Quick Reference: Key Concepts

### Snake Case Convention
All parameters, tables, columns use `snake_case`:
- ✅ `monthly_player_growth_rate`
- ❌ `monthlyPlayerGrowthRate`

### Batch Association
Every generated record must trace to a batch:
- ✅ `matches.batch_id` NOT NULL
- ✅ `player_rating_history.batch_id` NOT NULL
- ✅ `player_registrations.batch_id` NOT NULL

### Historical Integrity
- ✅ Use `birth_date`, calculate age at query time
- ✅ Store ratings in `player_rating_history` with dates
- ✅ Append-only historical records
- ❌ Never update old rating records in place

### Match Types (Authoritative List)
1. `recreational`
2. `league`
3. `ladder`
4. `tournament`
5. `challenge`
6. `clinic`
7. `open_play`

### Default Configuration Values
- Monthly player growth: `0.02` (2%)
- Initial rating mean: `1500.0`
- Rating noise: `75.0` (medium)
- Weekend bias: `1.75`
- Team persistence (recreational): `0.72`
- Team persistence (competitive): `0.88`

---

## Conflict Resolution

If you find conflicting information:

1. **Check this index** for document priority
2. **Review corrections summary** for recent changes
3. **Prefer**:
   - Database design for schema questions
   - Configuration spec for parameter questions
   - Generation sequence for workflow questions
4. **Escalate** genuine conflicts to architecture team

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-05-10 | Initial post-review index |

---

## Contact

For questions about these specifications:
- **Architecture**: Refer to `architecture/architecture.md`
- **Schema**: Refer to `database/Pickleball_Simulation_Database_Design_v3.md`
- **Parameters**: Refer to `generation_logic/configuration_parameters_specification.md`
- **Changes**: Refer to `docs_DESIGN_REVIEW_CORRECTIONS_SUMMARY.md`

---

**END OF MASTER DOCUMENT INDEX**
