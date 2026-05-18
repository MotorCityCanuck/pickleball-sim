This updated document defines the recommended architecture for
player-to-club assignment within the pickleball simulation ecosystem,
including the proper sequencing of player generation and club membership
assignment.

# Recommended Architectural Sequence

- Player-to-club assignment should occur AFTER player table creation.

- The player table should first contain stable player identity and
  demographic attributes.

- Club assignment should be implemented as a separate post-processing
  generation step.

- This approach enables realistic historical club movement, independent
  players, and multi-club relationships.

# Recommended Generation Pipeline

- 1\. Generate regional demographic data

- 2\. Generate club inventory by region

- 3\. Generate player population

- 4\. Assign player archetypes and behavioral profiles

- 5\. Generate initial ratings and competitiveness profiles

- 6\. Calculate eligible clubs for each player

- 7\. Apply probabilistic club assignment logic, including configured
  unaffiliated players

- 8\. Persist primary and, for a configured minority, secondary club
  membership records

- 9\. Initialize social graph and partner affinity relationships

# Why Club Assignment Should Occur After Player Creation

- Club assignment depends on player attributes that do not yet exist
  during raw player creation.

- Important assignment drivers include home region, age,
  competitiveness, activity level, archetype, and social compatibility.

- Separating club assignment from player creation creates cleaner
  architecture and better historical tracking.

# Recommended Player Table Design

- The player table should contain relatively stable player identity
  attributes.

- Recommended columns include:

- player_id

- first_name

- last_name

- birthdate

- gender

- home_region_id

- created_batch_id

# Recommended Club Membership Table Design

- Club membership should be stored separately from the player table.

- Recommended structure:

- club_memberships

- player_id

- club_id

- membership_type

- start_date

- end_date

- is_primary

# Benefits of Separate Membership Modeling

- Supports realistic club switching behavior over time.

- Supports independent/unaffiliated players.

- Supports current multi-club membership logic for an infrequent
  configured share of affiliated players.

- Supports relocation and regional migration.

- Supports longitudinal historical analysis.

# Assignment Weighting Logic

- Assignment should use weighted probabilistic scoring.

- Recommended weighting model:

- Regional proximity = 35%

- Club type compatibility = 20%

- Competitiveness compatibility = 15%

- Club capacity factor = 10%

- Age compatibility = 8%

- Socioeconomic similarity = 5%

- Existing social relationships = 5%

- Random noise contribution = 2%

# Noise Injection and Non-Determinism

- The system should intentionally avoid deterministic assignment
  patterns.

- Recommended baseline noise contribution: 2%--8% of final score.

- Occasional stochastic overrides should occur for approximately 1%--3%
  of assignments.

# Multi-Club and Unaffiliated Controls

- `unaffiliated_player_rate` controls the baseline share of players who
  should not receive a club membership.

- Players may also remain unaffiliated naturally when their region has
  no eligible clubs.

- `multi_club_membership_rate` controls the share of affiliated players
  eligible for secondary memberships.

- `min_club_memberships_per_affiliated_player` and
  `max_club_memberships_per_player` bound active membership counts.

- `secondary_membership_same_region_rate` controls whether secondary
  memberships remain in the same region when feasible.

# Power-Law Club Distribution

- Club sizes should follow a Pareto-style power-law distribution.

- Most clubs should remain relatively small.

- A very small number of clubs should become extremely large regional
  hubs.

# Final Recommendation

- Player creation and club assignment should remain architecturally
  separate.

- The ecosystem should evolve longitudinally using historical membership
  tracking rather than static one-time assignment.
