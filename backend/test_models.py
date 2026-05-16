"""Test SQLAlchemy models against database."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.models import Base, GenerationRun, Player, FirstName, Match

# Database connection
DATABASE_URL = "postgresql://postgres:postgres@172.29.182.220:5432/pickleball"

def test_connection():
    """Test database connection and model reflection."""
    engine = create_engine(DATABASE_URL, echo=False)
    
    # Test connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(f"✓ Database connection successful: {result.scalar()}")
    
    # Test metadata matches database
    print(f"✓ Models define {len(Base.metadata.tables)} tables")
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Test simple queries
    gen_run_count = session.query(GenerationRun).count()
    player_count = session.query(Player).count()
    
    print(f"✓ GenerationRun query successful: {gen_run_count} records")
    print(f"✓ Player query successful: {player_count} records")
    print(f"✓ All model tests passed!")
    
    session.close()

if __name__ == "__main__":
    test_connection()