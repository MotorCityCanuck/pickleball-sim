This document defines the authoritative architecture for player regional
assignment and realistic player name generation within the synthetic
pickleball ecosystem simulation. The objective is to create
statistically believable North American player populations with
realistic geographic concentration, demographic variation, and
culturally appropriate naming patterns.

This document is aligned to the ORM-first schema. SQLAlchemy models under
`backend/app/models` are the schema source of truth. Name reference data
is stored in the consolidated `first_names` and `last_names` tables. Do
not recreate legacy split tables such as `usa_first_names`,
`usa_last_names`, `canada_first_names`, or `canada_last_names`.

# 1. Design Objectives

- Generate geographically realistic player populations across North
  America.

- Make total player volume configuration driven. The player generation
  module should read the target player count from generation
  configuration rather than hardcoding population size.

- Reflect realistic regional population densities using census-based
  weighting.

- Generate culturally and temporally appropriate player names.

- Align names with state/province, birth year, and gender distributions.

- Support realistic metropolitan concentration and regional growth
  patterns.

- Prevent deterministic or repetitive naming behavior through controlled
  probabilistic selection.

# 2. Core Architectural Philosophy

- Player region assignment and name generation should occur before club
  assignment.

- Regional assignment establishes the player\'s geographic identity.

- Name generation should leverage census frequency data rather than
  random name pools.

- The ecosystem should evolve longitudinally rather than generating
  disconnected snapshots.

# 3. Recommended Generation Sequence

- Load regional population reference data.

- Load first-name reference datasets into `first_names`.

- Load last-name reference datasets into `last_names`.

- Read the configured target player count for the generation run.

- Generate regional player distribution targets.

- Assign players to regions.

- Generate birth year and gender.

- Generate first names using birth-year and gender weighting.

- Generate last names using regional surname weighting.

- Persist completed player identity records.

- Proceed to club assignment and social graph generation.

# 3.1 Current ORM Tables

The current implementation uses these schema objects for player identity
and name generation:

- `regions`

- `first_names`

- `last_names`

- `players`

- `player_registrations`

- `monthly_batches`

- `generation_runs`

Reference-name loaders must write to `first_names` and `last_names`
only. Player generation must persist final player identity values in
`players` and month-specific intake records in `player_registrations`.

# 4. Recommended Geographic Hierarchy

- Country

- State or Province

- Metropolitan Area

- Subregion or Community Cluster (optional future enhancement)

# 5. Regional Population Assignment Logic

- Players should be distributed proportionally based on metropolitan
  population.

- Production `regions.selection_probability` must represent global
  population share across all supported US and Canada regions, not a
  country-local probability. Player generation samples directly from this
  value.

- Large metro regions should contain significantly more players than
  rural regions.

- Retirement-heavy regions should receive participation multipliers.

- Competitive pickleball hotspots should receive additional density
  multipliers.

# 6. Recommended Regional Assignment Formula

- regional_player_target = regional_population × participation_rate ×
  competitiveness_multiplier

- Where:

- regional_population = census metro population

- participation_rate = estimated pickleball participation rate

- competitiveness_multiplier = competitiveness or retirement-area adjustment

# 7. Recommended Regional Multipliers

- Naples FL = 1.25

- Phoenix AZ = 1.15

- Austin TX = 1.10

- Toronto ON = 1.05

- Rural cold-climate regions = 0.80--0.95

# 8. Metropolitan Concentration Logic

- Player generation should heavily favor large metropolitan regions.

- Small rural regions should remain sparsely populated.

- The resulting ecosystem should naturally produce major regional hubs.

# 9. Recommended Population Distribution Characteristics

- A small number of metro areas should contain a disproportionately
  large percentage of players.

- The system should naturally exhibit power-law-like regional clustering
  behavior.

- Urban regions should produce denser social graphs and larger clubs.

# 10. Birth Year Generation

- Birth years should follow a weighted demographic distribution.

- Pickleball populations should skew older than the general population.

- Retirement-heavy regions should exhibit additional upward age skew.

# 11. Recommended Age Distribution

- Ages 18--29: 8%

- Ages 30--44: 18%

- Ages 45--59: 32%

- Ages 60--74: 34%

- Ages 75+: 8%

# 12. Gender Assignment Logic

- Gender assignment should use configurable weighted probabilities.

- Initial implementation may use binary gender categories for
  compatibility with historical census datasets.

- Future versions may support expanded identity modeling.

# 13. First Name Generation Logic

- First names must be generated from the normalized production
  `first_names` table.

- Player generation must not read first-name source files directly.
  Raw source files are handled only by seed ingestion and normalization.

- Generation should be conditioned on:

- Country

- State/province

- Birth year

- Gender

- `normalized_probability`

# 13.1 First-Name Production Table Grain

The production `first_names` table stores normalized first-name
probabilities at this grain:

```text
country_code,
state_province_code,
birth_year,
gender,
first_name
```

The generation module should query candidates by the player's assigned
country, state/province, birth year, and gender, then select one
`first_name` using `first_names.normalized_probability`.

The `gender` value must be compatible with the current ORM constraint:
`M` or `F`.

# 14. Recommended First Name Selection Formula

- P(first_name_i) = first_names.normalized_probability

- The probability is already normalized during seed-data normalization.

# 14.1 First-Name Normalization Rule

For both USA and Canada first names, `normalized_probability` is
calculated before player generation from total name occurrences in each
country, state/province, birth-year, and gender cohort:

```text
normalized_probability =
  frequency_count /
  sum(frequency_count for same country_code, state_province_code, birth_year, gender)
```

This means the probabilities for all names in a given
`country_code + state_province_code + birth_year + gender` cohort
should sum to approximately `1.0`, subject to `NUMERIC(12,8)`
rounding.

The current `first_names` lookup index supports this exact cohort:

```text
country_code, state_province_code, birth_year, gender
```

# 14.2 First-Name Lookup Fallback Order

When assigning a first name to a player, use the most specific cohort
available. The recommended fallback order is:

- Exact country, state/province, birth year, and gender.

- Same country, same state/province, nearest available birth year, and
  same gender.

- Same country, all available state/province cohorts for the exact birth
  year and gender.

- Same country, all available state/province cohorts for the nearest
  available birth year and same gender.

The expected primary path is exact country, state/province, birth year,
and gender for both USA and Canada.

# 15. Temporal Naming Realism

- Name popularity should vary realistically by birth year.

- Older players should disproportionately receive historically common
  names.

- Examples:

- Older male players: Robert, James, Michael

- Older female players: Susan, Linda, Patricia

- Younger players: Ethan, Liam, Ava, Chloe

# 16. Regional Name Realism

- Certain names should occur more frequently in specific regions.

- French surnames should appear more often in Quebec.

- Hispanic surnames should appear more often in Southwestern U.S.
  regions.

- Regional ethnic clustering should emerge probabilistically rather than
  deterministically.

# 17. Last Name Generation Logic

- Last names must be generated from the normalized production
  `last_names` table.

- Player generation must not read last-name source files or
  state/province bias files directly. Raw surname files and bias files
  are handled only by seed ingestion and normalization.

- Regional surname weighting should influence probability selection.

- Rare surnames should remain uncommon but still appear occasionally.

# 17.1 Last-Name Production Table Grain

The production `last_names` table stores normalized surname
probabilities at this grain:

```text
country_code,
state_province_code,
last_name
```

The generation module should query candidates by the player's assigned
country and state/province, then select one `last_name` using
`last_names.normalized_probability`.

The production row also preserves:

- `frequency_count`: original country-level surname frequency

- `bias_multiplier`: applied state/province surname bias multiplier

- `adjusted_frequency_count`: frequency after applying regional bias

# 18. Recommended Last Name Selection Model

- Use weighted probabilistic selection based on
  `last_names.normalized_probability`.

- `normalized_probability` already includes regional surname bias. It is
  calculated from:

```text
adjusted_frequency_count =
  frequency_count * bias_multiplier
```

Then, within each country/state-province surname cohort:

```text
normalized_probability =
  adjusted_frequency_count /
  sum(adjusted_frequency_count for same country_code, state_province_code)
```

- Recommended distribution should follow long-tail behavior.

- A small number of surnames should appear frequently while many remain
  rare.

# 19. Duplicate Name Handling

- Duplicate full names should be allowed.

- Real populations naturally contain repeated names.

- Artificial uniqueness constraints should be avoided.

# 20. Controlled Randomness and Noise Injection

- The system should intentionally preserve enough randomness to avoid
  deterministic naming patterns.

- Rare names should occasionally appear despite low frequency.

- Low-probability cross-regional naming should occur occasionally.

# 21. Recommended Noise Contribution

- Recommended baseline randomization: 2%--5% of name assignments.

- This creates more believable diversity and avoids rigid demographic
  partitioning.

# 22. Player Identity Persistence

- Player identity records should remain stable throughout longitudinal
  simulation.

- Names, birthdate, gender, and home region should rarely change after
  generation.

# 23. Current Database Tables

- `regions`

- `first_names`

- `last_names`

- `players`

- `player_registrations`

- `monthly_batches`

- `generation_runs`

- `clubs`

Potential future analytical/reference tables such as region
demographics or regional population targets must be introduced through
ORM models first if they become necessary.

# 24. Current `players` Identity Attributes

- `id`

- `external_player_key`

- `first_name`

- `last_name`

- `gender`

- `birth_date`

- `dominant_hand`

- `home_region_id`

- `registration_date`

- `initial_skill_seed`

- `player_status`

- `generation_run_id`

The month-specific intake link is stored in `player_registrations`:

- `player_id`

- `batch_id`

- `registration_month`

- `assigned_region_id`

# 25. Remaining Player Attribute Generation

The remaining stable player attributes should be generated during player
creation from deterministic seeded random streams. Percentages and
distribution parameters must be configurable through the generation
configuration snapshot.

## 25.1 Dominant Hand

`dominant_hand` should be assigned using configurable weighted
probabilities.

Recommended default distribution:

```text
right: 0.88
left:  0.10
ambidextrous: 0.02
```

The vast majority of players should be right-handed. Left-handed and
ambidextrous players should appear often enough to support realistic
match and partnership analysis without dominating the population.

## 25.2 Initial Skill Seed

`initial_skill_seed` should be populated for every generated player.

The value should be sampled from a bounded normal-like distribution that
is modestly biased toward lower skill ratings. This field is an immutable
starting skill seed used to initialize downstream rating and assessment
history; it is not a current rating and should not replace
`player_rating_history`.

Recommended first-pass approach:

```text
base_skill = normal(mean, standard_deviation)
lower_skill_bias = configurable downward adjustment or skew factor
initial_skill_seed = clamp(base_skill - lower_skill_bias, min_skill, max_skill)
```

Recommended configurable defaults:

```text
initial_skill_mean: 1500
initial_skill_standard_deviation: 275
initial_skill_lower_bias: 100
initial_skill_min: 500
initial_skill_max: 3500
```

The distribution should produce many beginner and lower-intermediate
players, fewer advanced players, and very few elite starting players.

## 25.3 Player Status

`player_status` should be assigned using configurable weighted
probabilities.

Recommended default distribution:

```text
ACTIVE:  0.94
INJURED: 0.02
RETIRED: 0.02
INACTIVE: 0.02
```

Most generated players should be active. Injured, retired, and inactive
players should be present in small numbers so downstream availability,
retention, and lifecycle logic has realistic non-active states to work
with.

Status percentages must be validated to sum to `1.0`. The implementation
should fail configuration validation if the status distribution is
missing, negative, or materially different from a total probability of
`1.0`.

## 25.4 Registration Date

`players.registration_date` should be randomized rather than always set
to the first day of the batch month.

During player generation, the module should choose a regional club as a
registration-date anchor. The selected date must satisfy these rules:

```text
registration_date >= associated club founding_date
registration_date <= monthly batch month start
registration_date > player birth_date
```

If a region has no eligible club, or if the selected club has no
`founding_date`, the generator may fall back to the month-specific batch
date. `player_registrations.registration_month` remains the normalized
batch month and should not be randomized.

# 26. Validation Rules

- Validate regional player counts against target population
  distributions.

- Validate age distributions.

- Validate first-name popularity by birth cohort.

- Validate surname frequency distributions.

- Validate regional concentration and metro clustering.

- Validate dominant-hand distribution against configured probabilities.

- Validate initial skill seed distribution for range, mean, and lower-skill
  skew.

- Validate player status distribution against configured probabilities.

- Validate generated registration dates are not earlier than associated
  club founding dates and are not later than the batch month.

# 27. Final Recommendation

- Player region and name assignment should be census-driven,
  probabilistic, and regionally aware.

- The strongest realism improvements come from combining population
  weighting, temporal naming realism, and controlled stochastic noise.

**Authoritative Architectural Principle:** Player identity generation
should simulate realistic demographic evolution rather than randomly
assigning disconnected attributes.
