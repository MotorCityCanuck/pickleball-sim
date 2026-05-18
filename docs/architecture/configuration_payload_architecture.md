# Configuration Payload Architecture

**Purpose:** Define the canonical JSON payload stored in
`configuration_profile_versions.config_payload` and copied into
`generation_runs.parameter_snapshot` for each run.

The payload is intentionally grouped by operational domain rather than by
database table. Individual configuration values live inside JSONB payloads, not
as columns on `configuration_profile_versions`. This keeps the future web UI
flexible while preserving immutable version history and run reproducibility.

## Storage Model

- `configuration_profiles` stores named profiles such as `default`,
  `student_release`, or `high_volume_test`.
- `configuration_profile_versions` stores immutable JSONB payload versions for
  a profile.
- `generation_runs.parameter_snapshot` stores the resolved effective payload
  used by a run after defaults, profile values, environment overrides, UI
  overrides, and command-line overrides are applied.
- Running generation code must read from the frozen run snapshot, not from the
  mutable latest profile version.
- The initial default profile/version is seeded with
  `python scripts/seed_configuration_profile.py` from the `backend` directory.

## Naming Rules

- Use `snake_case` for every key.
- Use explicit units in names when ambiguity is likely, for example
  `_std_dev`, `_days`, `_miles`, `_rate`, `_probability`, `_weight`, and
  `_multiplier`.
- Use `*_std_dev`, not `*_sd`.
- Use `*_noise_std_dev` for Gaussian noise and `*_noise_factor` only when the
  value is a dimensionless factor.
- Use `weekend_concentration_bias`, not `weekend_bias` or
  `weekend_bias_multiplier`.
- Use `date_allocation_noise_level`, not `date_noise_level`.
- Use `initial_confidence_score`, not `initial_confidence`.
- Use `monthly_player_growth_rate`, not `monthly_growth_rate`.
- Use `competitiveness_multiplier_default` or scoped
  `competitiveness_multiplier`, not `regional_multiplier`.

## Export Inclusion

Exports use explicit inclusion rather than an `include_instructor_only_tables`
boolean. The export engine should resolve table groups to table names, apply
any explicit `export_included_tables` override, and export only that final
allow-list.

Suggested groups:

| Group | Included Tables |
|-------|-----------------|
| `student_core` | `players`, `player_registrations`, `player_rating_history`, `player_assessment_history`, `clubs`, `club_memberships`, `teams`, `team_memberships`, `matches`, `match_games`, `match_teams`, `match_team_players`, `tournaments`, `monthly_batches` |
| `reference` | `regions`, `first_names`, `last_names` |
| `operational` | `generation_runs`, `batch_runs`, `export_runs`, `validation_results`, `job_status`, `uploaded_files` |
| `raw_seed` | `raw_seed_load_runs`, `raw_seed_load_errors`, `raw_metro_areas`, `raw_pickleball_club_names`, `raw_pickleball_club_distributions`, `raw_first_names`, `raw_last_names`, `raw_state_prov_biases` |
| `configuration` | `configuration_profiles`, `configuration_profile_versions` |
| `simulation_truth` | Future hidden truth/audit tables, for example `player_truth_state` if implemented |

## Sample Payload

```json
{
  "runtime": {
    "database_url": "postgresql://postgres:postgres@localhost:5432/pickleball",
    "database_echo": false,
    "environment_name": "local",
    "config_file_path": null,
    "ui_enabled": true,
    "max_preview_rows": 1000
  },
  "simulation": {
    "master_seed": 42,
    "simulation_name": "NAPA_Olympic_Analytics_v1",
    "simulation_version": "1.0",
    "generation_run_mode": "full",
    "target_total_players": 50000,
    "historical_batch_count": 12,
    "first_batch_month": "2024-01-01",
    "commit_strategy": "per_module",
    "batch_retry_policy": {
      "max_attempts": 1,
      "destructive_rerun_enabled": false
    }
  },
  "raw_seed_data": {
    "raw_data_root": "data/raw",
    "supported_datasets": [
      "metro_areas_us",
      "metro_areas_ca",
      "first_names_us",
      "first_names_ca",
      "last_names_us",
      "last_names_ca",
      "state_prov_biases_us",
      "state_prov_biases_ca",
      "pickleball_club_names",
      "pickleball_club_distributions"
    ],
    "replace_production": false
  },
  "player_generation": {
    "player_count": 50000,
    "initial_player_count": null,
    "monthly_player_growth_rate": 0.02,
    "age_min": 18,
    "age_max": 85,
    "age_distribution": {
      "18_29": 0.08,
      "30_44": 0.18,
      "45_59": 0.32,
      "60_74": 0.34,
      "75_plus": 0.08
    },
    "gender_weights": {
      "male": 0.5,
      "female": 0.5
    },
    "dominant_hand_weights": {
      "right": 0.88,
      "left": 0.1,
      "ambidextrous": 0.02
    },
    "player_status_weights": {
      "active": 0.94,
      "injured": 0.02,
      "retired": 0.02,
      "inactive": 0.02
    },
    "initial_skill_seed": {
      "mean": 1500,
      "std_dev": 275,
      "lower_bias": 100,
      "min": 500,
      "max": 3500
    }
  },
  "name_assignment": {
    "name_region_fallback_order": [
      "state_province",
      "country"
    ],
    "name_gender_mapping": {
      "male": "M",
      "female": "F"
    },
    "name_year_bucket_size": 1,
    "name_assignment_noise_rate": 0.03
  },
  "regional": {
    "region_population_weight": 1.0,
    "regional_allocation_strategy": "selection_probability",
    "competitiveness_multiplier_default": 1.0,
    "competitiveness_noise_std_dev": 0.05,
    "min_players_per_region": 100,
    "regional_competitiveness_multipliers": {
      "Naples, FL": 1.25,
      "Phoenix, AZ": 1.15,
      "Austin, TX": 1.1,
      "Toronto, ON": 1.05,
      "rural_cold_climates": 0.85
    }
  },
  "club_generation": {
    "clubs_per_75k_population": 1.0,
    "target_club_count": 4000,
    "monthly_club_growth_rate": 0.003,
    "club_size_distribution": {
      "tiny": 0.35,
      "small": 0.4,
      "medium": 0.2,
      "large": 0.04,
      "mega": 0.01
    },
    "capacity_ranges": {
      "tiny": [10, 30],
      "small": [31, 75],
      "medium": [76, 200],
      "large": [201, 500],
      "mega": [501, 1000]
    },
    "court_ranges": {
      "tiny": [1, 2],
      "small": [2, 4],
      "medium": [4, 8],
      "large": [8, 16],
      "mega": [16, 32]
    },
    "indoor_court_ratios": {
      "dedicated_facility": 0.75,
      "public_park": 0.0,
      "private_club": 0.45,
      "municipal_recreation": 0.35,
      "default": 0.3
    },
    "unaffiliated_player_rate": 0.12,
    "multi_club_membership_rate": 0.06,
    "min_club_memberships_per_affiliated_player": 1,
    "max_club_memberships_per_player": 3,
    "secondary_membership_same_region_rate": 0.85,
    "club_assignment_noise_std_dev": 0.1,
    "club_size_power_law_alpha": 1.4,
    "max_club_fill_ratio": 1.0,
    "cross_region_assignment_enabled": false
  },
  "club_assignment": {
    "weights": {
      "regional_proximity": 0.35,
      "club_type_compatibility": 0.2,
      "competitiveness_compatibility": 0.15,
      "capacity_factor": 0.1,
      "age_compatibility": 0.08,
      "socioeconomic_similarity": 0.05,
      "existing_social_relationships": 0.05,
      "random_noise": 0.02
    },
    "stochastic_override_rate": 0.02
  },
  "team_formation": {
    "team_persistence_probability_recreational": 0.72,
    "team_persistence_probability_competitive": 0.88,
    "team_chemistry_weight": 0.35,
    "team_skill_balance_weight": 0.25,
    "team_noise_factor": 0.15,
    "monthly_team_dissolution_rate": 0.1,
    "allow_multiple_active_teams_per_scope": false
  },
  "match_scheduling": {
    "monthly_matches_per_active_player_mean": 8.0,
    "monthly_matches_per_active_player_std_dev": 4.0,
    "matches_per_team_per_month": 4.0,
    "weekend_concentration_bias": 1.75,
    "saturday_weight": 2.25,
    "sunday_weight": 1.85,
    "friday_weight": 1.2,
    "weekday_evening_weight": 1.0,
    "league_weekday_multiplier": 1.4,
    "tournament_weekend_multiplier": 2.5,
    "date_allocation_noise_level": "medium",
    "max_daily_match_share": 0.08,
    "holiday_modifier_enabled": true,
    "capacity_rebalance_enabled": true,
    "max_daily_matches_per_team": 2,
    "travel_radius_limit_miles": 50
  },
  "match_types": {
    "weights": {
      "recreational": 0.55,
      "league": 0.2,
      "ladder": 0.1,
      "tournament": 0.1,
      "challenge": 0.04,
      "clinic": 0.01
    }
  },
  "matchmaking": {
    "rating_band_width": {
      "recreational": 400,
      "competitive": 150,
      "tournament": 100
    },
    "skill_band_tolerances": {
      "under_3_0": 0.8,
      "3_0_to_4_0": 0.5,
      "4_0_to_5_0": 0.3,
      "5_0_plus": 0.15
    },
    "matchmaking_noise_factor": 0.2,
    "rematch_penalty_window_days": 30,
    "locality_weight": 0.3,
    "quality_distribution": {
      "ideal": 0.65,
      "slight_mismatch": 0.25,
      "significant_mismatch": 0.08,
      "chaos": 0.02
    }
  },
  "games_and_scores": {
    "games_per_match": {
      "recreational": 1,
      "league": 2,
      "tournament": 3
    },
    "game_target_score": 11,
    "win_by_two_rule_enabled": true,
    "score_noise_std_dev": 1.5,
    "upset_probability_boost": 0.15
  },
  "ratings": {
    "initial_rating_mean": 1500.0,
    "initial_rating_std_dev": 200.0,
    "rating_min": 0.0,
    "rating_max": 5000.0,
    "initial_rating_elite_tail_rate": 0.003,
    "initial_rating_elite_min": 4000.0,
    "initial_rating_elite_max": 4500.0,
    "k_factor_new_player": 48.0,
    "k_factor_established": 24.0,
    "k_factor_elite": 16.0,
    "k_factor_base": 24.0,
    "rating_noise_std_dev": 75.0,
    "rating_decay": 0.0,
    "rating_movement_warning_threshold": 300.0
  },
  "confidence": {
    "initial_confidence_score": 0.1,
    "confidence_min": 0.0,
    "confidence_max": 1.0,
    "confidence_weight": 1.0,
    "confidence_recency_half_life_days": 90,
    "match_volume_weight": 0.4
  },
  "availability_and_injury": {
    "availability_noise_level": "medium",
    "base_injury_rate": 0.005,
    "minor_injury_probability": 0.7,
    "moderate_injury_probability": 0.2,
    "acute_injury_probability": 0.08,
    "recurring_injury_probability": 0.02,
    "reinjury_probability": 0.03,
    "injury_performance_penalty_min": 0.02,
    "injury_performance_penalty_max": 0.15,
    "fatigue_accumulation_rate": 0.02,
    "fatigue_recovery_rate": 0.15
  },
  "seasonality_weather_travel": {
    "seasonality_enabled": true,
    "seasonality_modifiers": {},
    "weather_impact_enabled": false,
    "court_surface_distribution": {},
    "travel_distance_penalty": 0.0
  },
  "validation": {
    "validation_strictness": "standard",
    "validation_blocker_threshold": 0,
    "validation_error_threshold": 100,
    "allowed_warning_threshold": 1000,
    "validation_sample_size_distribution": 10000,
    "weekend_concentration_min": 0.4,
    "weekend_concentration_max": 0.6,
    "distribution_tolerance": 0.01
  },
  "export": {
    "export_directory": "data/output",
    "export_format_primary": "parquet",
    "export_partition_strategy": "monthly",
    "export_compression_codec": "snappy",
    "export_included_table_groups": [
      "student_core",
      "reference"
    ],
    "export_included_tables": [],
    "export_batch_on_completion": true
  },
  "future_extensions": {
    "tournament_bracket_structures": {},
    "partnership_chemistry_evolution_rate": 0.05,
    "social_graph_decay_rate": 0.02,
    "community_hub_player_rate": 0.03,
    "data_quality_level": "standard",
    "missingness_rate": 0.0,
    "anomaly_rate": 0.0
  }
}
```

## Validation Expectations

- All probability distributions must sum to `1.0` within configured tolerance.
- Numeric values must respect documented ranges.
- Empty `export_included_tables` means resolve export tables from
  `export_included_table_groups`.
- Non-empty `export_included_tables` is an explicit table allow-list and should
  override group resolution.
- Unknown payload keys should produce validation warnings during early
  development and validation failures once the config schema is stable.
