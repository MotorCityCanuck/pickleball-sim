"""Teams model."""
from sqlalchemy import (
    Column, BigInteger, String, Date, Numeric, ForeignKey, CheckConstraint,
    Index
)
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class Team(Base, TimestampMixin):
    """Doubles teams."""
    
    __tablename__ = 'teams'
    
    id = Column(BigInteger, primary_key=True)
    team_type = Column(
        String(30),
        nullable=False,
        default='competitive',
        server_default='competitive',
    )
    team_division = Column(
        String(50),
        nullable=False,
        default='open_doubles',
        server_default='open_doubles',
    )
    team_status = Column(String(30), default='active')
    country_code = Column(String(2))
    formation_date = Column(Date, nullable=False)
    dissolution_date = Column(Date)
    chemistry_score = Column(Numeric(8, 4))
    persistence_probability = Column(Numeric(5, 4))
    generation_run_id = Column(BigInteger, ForeignKey('generation_runs.id'))
    
    # Relationships
    generation_run = relationship("GenerationRun")
    memberships = relationship("TeamMembership", back_populates="team")
    
    __table_args__ = (
        Index('idx_teams_type', 'team_type'),
        Index('idx_teams_division', 'team_division'),
        Index('idx_teams_status', 'team_status'),
        Index('idx_teams_country', 'country_code'),
        Index('idx_teams_formation_date', 'formation_date'),
        CheckConstraint(
            "country_code IS NULL OR country_code IN ('US', 'CA')",
            name='chk_team_country',
        ),
        CheckConstraint(
            "team_type IN ('competitive', 'ad_hoc')",
            name='chk_team_type'
        ),
        CheckConstraint(
            "team_division IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles')",
            name='chk_team_division',
        ),
        CheckConstraint("team_status IN ('active', 'dormant', 'retired')", name='chk_team_status'),
        CheckConstraint('dissolution_date IS NULL OR dissolution_date >= formation_date', name='chk_team_dates'),
    )
