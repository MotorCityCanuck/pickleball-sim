"""SQLAlchemy models for the Pickleball Simulation Platform.

This module exports database models for ORM metadata and the application.
"""
from .base import Base, TimestampMixin
from .generation_runs import GenerationRun
from .monthly_batches import MonthlyBatch
from .regions import Region
from .players import Player
from .player_rating_history import PlayerRatingHistory
from .player_assessment_history import PlayerAssessmentHistory
from .player_registrations import PlayerRegistration

# Priority 1 models (Generation Control)
# Priority 2 models (Player Core)
__all__ = [
    'Base',
    'TimestampMixin',
    # Priority 1
    'GenerationRun',
    'MonthlyBatch',
    'Region',
    # Priority 2
    'Player',
    'PlayerRatingHistory',
    'PlayerAssessmentHistory',
    'PlayerRegistration',
]

# Priority 3+ models (to be added):
# - Club
# - ClubMembership
# - Team
# - TeamMembership
# - Match
# - MatchTeam
# - MatchTeamPlayer
# - Tournament
# - USAFirstName
# - USALastName
# - CanadaFirstName
# - CanadaLastName
# - BatchRun
# - UploadedFile
# - ExportRun
# - ValidationResult
# - JobStatus

if __name__ == '__main__':
    print(f"Models module loaded successfully")
    print(f"Available models: {__all__}")
