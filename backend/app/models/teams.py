"""Teams model."""
from sqlalchemy import Column, BigInteger, String, Date, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class Team(Base, TimestampMixin):
    """Doubles teams."""
    
    __tablename__ = 'teams'
    
    id = Column(BigInteger, primary_key=True)
    team_type = Column(String(50), nullable=False)
    team_status = Column(String(30), default='active')
    formation_date = Column(Date, nullable=False)
    dissolution_date = Column(Date)
    chemistry_score = Column(Numeric(8, 4))
    persistence_probability = Column(Numeric(5, 4))
    generation_run_id = Column(BigInteger, ForeignKey('generation_runs.id'))
    
    # Relationships
    generation_run = relationship("GenerationRun")
    memberships = relationship("TeamMembership", back_populates="team")
    
    __table_args__ = (
        CheckConstraint(
            "team_type IN ('mens_doubles', 'womens_doubles', 'mixed_doubles', 'open_doubles')",
            name='chk_team_type'
        ),
        CheckConstraint("team_status IN ('active', 'dormant', 'retired')", name='chk_team_status'),
        CheckConstraint('dissolution_date IS NULL OR dissolution_date >= formation_date', name='chk_team_dates'),
    )
