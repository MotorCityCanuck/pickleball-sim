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

- Large metro regions should contain significantly more players than
  rural regions.

- Retirement-heavy regions should receive participation multipliers.

- Competitive pickleball hotspots should receive additional density
  multipliers.

# 6. Recommended Regional Assignment Formula

- regional_player_target = regional_population × participation_rate ×
  regional_multiplier

- Where:

- regional_population = census metro population

- participation_rate = estimated pickleball participation rate

- regional_multiplier = competitiveness or retirement-area adjustment

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

- First names should be generated using census or SSA frequency
  datasets.

- Generation should be conditioned on:

- Birth year

- Gender

- State/province where possible

- Frequency weighting

# 13.1 USA First-Name Source Format

USA first-name reference data will be loaded from roughly 50 state-level
`.txt` files, one file per U.S. state. Each raw row has this comma-
separated format:

```text
state,sex,birth_year,name,occurrences
```

Example:

```text
NE,F,1910,Mary,161
```

The loader maps raw fields to `first_names` as follows:

- `country_code`: constant `US`

- `state_province_code`: raw `state`

- `birth_year`: raw `birth_year`

- `gender`: raw `sex`

- `first_name`: raw `name`

- `frequency_count`: raw `occurrences`

- `source_dataset`: stable source identifier for the imported dataset

The raw `sex` value must be compatible with the current ORM constraint:
`M` or `F`.

# 14. Recommended First Name Selection Formula

- P(name_i) = frequency_i / sum(all frequencies in cohort)

- Where cohorts are segmented by birth year, gender, and optionally
  region.

# 14.1 USA First-Name Normalization Rule

For USA first names, `normalized_probability` is calculated during load
from total name occurrences in each state, birth-year, and gender cohort:

```text
normalized_probability =
  frequency_count /
  sum(frequency_count for same country_code, state_province_code, birth_year, gender)
```

This means the probabilities for all names in a given
`US + state_province_code + birth_year + gender` cohort should sum to
approximately `1.0`, subject to `NUMERIC(12,8)` rounding.

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

For the first USA implementation, the expected primary path is exact
state, birth year, and gender. Canada fallback behavior will be defined
after Canada first-name source data is finalized.

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

- Last names should be generated independently using census surname
  frequency data.

- Regional surname weighting should influence probability selection.

- Rare surnames should remain uncommon but still appear occasionally.

Canada first-name handling and last-name loading/selection rules are not
finalized in this version of the document. They will be defined after the
raw Canada first-name and last-name source files are reviewed.

# 18. Recommended Last Name Selection Model

- Use weighted probabilistic selection based on census frequency.

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

# 25. Validation Rules

- Validate regional player counts against target population
  distributions.

- Validate age distributions.

- Validate first-name popularity by birth cohort.

- Validate surname frequency distributions.

- Validate regional concentration and metro clustering.

# 26. Final Recommendation

- Player region and name assignment should be census-driven,
  probabilistic, and regionally aware.

- The strongest realism improvements come from combining population
  weighting, temporal naming realism, and controlled stochastic noise.

**Authoritative Architectural Principle:** Player identity generation
should simulate realistic demographic evolution rather than randomly
assigning disconnected attributes.
