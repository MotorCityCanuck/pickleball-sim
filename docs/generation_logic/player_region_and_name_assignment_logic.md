This document defines the authoritative architecture for player regional
assignment and realistic player name generation within the synthetic
pickleball ecosystem simulation. The objective is to create
statistically believable North American player populations with
realistic geographic concentration, demographic variation, and
culturally appropriate naming patterns.

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

- Load census first-name datasets.

- Load census last-name datasets.

- Generate regional player distribution targets.

- Assign players to regions.

- Generate birth year and gender.

- Generate first names using birth-year and gender weighting.

- Generate last names using regional surname weighting.

- Persist completed player identity records.

- Proceed to club assignment and social graph generation.

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

# 14. Recommended First Name Selection Formula

- P(name_i) = frequency_i / sum(all frequencies in cohort)

- Where cohorts are segmented by birth year, gender, and optionally
  region.

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

# 23. Recommended Database Tables

- region

- region_demographics

- census_first_name

- census_last_name

- player

- player_identity_generation_batch

- regional_population_target

# 24. Recommended player Table Attributes

- player_id

- first_name

- last_name

- birthdate

- gender

- home_region_id

- country_code

- created_batch_id

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
