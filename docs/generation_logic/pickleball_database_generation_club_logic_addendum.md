This addendum extends the existing pickleball simulation database
generation design with simplified but realistic club-generation logic
suitable for the initial implementation phase of the platform.

# 1. Initial Club Generation Philosophy

- The first implementation should prioritize realism while avoiding
  unnecessary complexity.

- Club naming may initially be AI-assisted using curated generated
  names.

- More advanced regional naming logic and geographic vocabulary
  generation can be added later.

- The initial focus should be realistic player clustering and social
  ecosystem behavior.

# 2. Recommended Initial Club Count

- The current default configuration uses an explicit
  `target_club_count` of 4,000 clubs for local generation, independent
  of the smaller 50,000-player default population used during active
  development.

- For larger instructional releases, an ecosystem of approximately
  250,000 simulated players may also use approximately 4,000 clubs as a
  reasonable starting point.

- This creates an average of roughly 62 players per club while still
  allowing realistic distribution variance.

- When `target_club_count` is not supplied, the club count should scale
  proportionally with regional population using the configured
  `clubs_per_75k_population` heuristic.

# 3. Recommended Club Size Distribution

- Club membership sizes should follow a power-law distribution rather
  than equal allocation.

- Recommended distribution:

- 35% of clubs: 10--30 members

- 40% of clubs: 31--75 members

- 20% of clubs: 76--200 members

- 4% of clubs: 201--500 members

- 1% of clubs: 500+ members

- This produces realistic ecosystems with many small clubs and a few
  very large regional facilities.

# 4. Geographic Club Scaling

- Club counts should scale proportionally with metropolitan population
  size.

- A reasonable initial heuristic is approximately one club per 75,000
  regional population.

- Regions with strong pickleball participation should receive regional
  multipliers.

- Retirement-heavy areas such as Naples, Florida should have
  significantly elevated club density.

- Cold-climate or rural regions may have reduced club density.

# 5. Club Membership Assignment

- Approximately 85--90% of players should be assigned to a primary club.

- Approximately 10--15% of players should remain independent or
  unaffiliated.

- Independent players simulate casual participants, open-play attendees,
  tournament visitors, and newly registered players.

# 6. Simplified Facility Model

- The initial implementation should treat clubs and facilities as the
  same entity.

- Future versions may separate physical facilities from social
  organizations.

- This simplification reduces schema complexity while still supporting
  realistic matchmaking behavior.

# 7. Monthly Club Growth

- The simulation should support gradual monthly club formation.

- Recommended initial growth rate: 0.2%--0.5% monthly club growth.

- This creates realistic ecosystem expansion and evolving social
  networks over time.

# 8. Recommended Database Tables

- club

- club_membership

- club_growth_batch

- club_region_profile

- club_match_activity_summary

# 9. Recommended club Table Attributes

- club_id

- club_name

- region_id

- club_type

- competitiveness_level

- member_count

- founding_date

- indoor_court_count

- outdoor_court_count

- socioeconomic_profile

# 10. Recommended Initial Processing Flow

- Generate regional populations

- Generate clubs by region

- Assign club sizes using power-law distribution

- Assign players to clubs

- Generate social graph relationships

- Generate sessions and matches

- Apply rating updates sequentially

- Process monthly growth and ecosystem evolution

This simplified club-generation architecture provides sufficient realism
for the initial implementation while preserving the ability to evolve
toward more advanced regional club modeling and social ecosystem
simulation later.
