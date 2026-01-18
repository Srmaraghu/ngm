"""
SQLAlchemy models for Nepal court case database.

This module defines the database schema for storing court cases and hearings
from Nepal's court system (district, high, supreme, and special courts).
"""

import os
from datetime import datetime
from sqlalchemy import Column, String, Date, DateTime, Text, Integer, ForeignKey, create_engine, Index
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class Court(Base):
    """
    Court master table storing information about all courts in Nepal.
    
    This includes:
    - 1 Supreme Court
    - 1 Special Court
    - 18 High Courts
    - 77 District Courts
    """
    __tablename__ = "courts"
    
    # Primary identification
    identifier = Column(String(50), primary_key=True, nullable=False)
    # Examples: "kathmandudc", "rajbirajhc", "supreme", "special"
    
    # Court information
    court_type = Column(String(20), nullable=False, index=True)
    # Values: "district", "high", "supreme", "special"
    
    full_name_nepali = Column(String(200), nullable=False)
    # Example: "जिल्ला अदालत काठमाडौं"
    
    full_name_english = Column(String(200), nullable=True)
    # Example: "District Court Kathmandu"
    
    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Court(identifier={self.identifier}, type={self.court_type}, name={self.full_name_nepali})>"


class CourtCase(Base):
    """
    Main court case table storing case metadata and registration information.
    
    Each case is uniquely identified by case_number + court_identifier.
    A case can have multiple hearings over time tracked in CourtCaseHearing table.
    """
    __tablename__ = "court_cases"
    
    # Primary identification
    case_number = Column(String(50), primary_key=True, nullable=False, index=True)
    # Example: "082-OA-0503", "081-C4-3088"
    
    court_identifier = Column(
        String(50), 
        ForeignKey('courts.identifier'), 
        primary_key=True, 
        nullable=False, 
        index=True
    )
    
    # Relationship
    court = relationship("Court", backref="cases")
    
    # Registration information
    registration_date_bs = Column(String(20), nullable=True, index=True)
    # BS format: "2082-09-28"
    
    registration_date_ad = Column(Date, nullable=True, index=True)
    # AD format for queries
    
    # Case classification
    case_type = Column(String(200), nullable=True, index=True)
    # Example: "भ्रष्टाचार ( रिसवत(घुस) )", "चेक अनादर"
    
    division = Column(String(100), nullable=True)
    # Example: "निवेदन ४", "रिट १"
    
    category = Column(String(100), nullable=True)
    # Example: "फाँट क", "फाँट ख"
    
    section = Column(String(200), nullable=True)
    # Example: "मुद्दा फाटँ २७ (सरल)"
    
    # Parties
    plaintiff = Column(Text, nullable=True)
    # Can be multiple parties separated by "समेत"
    
    defendant = Column(Text, nullable=True)
    # Can be multiple parties separated by "समेत"
    
    # Related case information
    original_case_number = Column(String(100), nullable=True)
    # For appeals/related cases
    
    case_id = Column(String(50), nullable=True)
    # Internal court ID (district courts)
    
    # Priority and processing
    priority = Column(String(50), nullable=True)
    # Example: "सरल" (simple/fast-track)
    
    # Metadata - tracks first and last hearing dates
    first_hearing_date_bs = Column(String(20), nullable=True)
    first_hearing_date_ad = Column(Date, nullable=True)
    last_hearing_date_bs = Column(String(20), nullable=True)
    last_hearing_date_ad = Column(Date, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Additional data (case-specific metadata)
    extra_data = Column(JSONB, nullable=True)
    
    def __repr__(self):
        return f"<CourtCase(case_number={self.case_number}, court={self.court_identifier})>"


class CourtCaseHearing(Base):
    """
    Court case hearing records - each row represents one appearance in the daily causelist.
    
    A case can have multiple hearings over time. This table tracks the progression
    of the case through the court system.
    """
    __tablename__ = "court_case_hearings"
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to CourtCase (composite)
    case_number = Column(String(50), nullable=False, index=True)
    
    court_identifier = Column(
        String(50), 
        ForeignKey('courts.identifier'), 
        nullable=False, 
        index=True
    )
    
    # Relationship
    court = relationship("Court", backref="hearings")
    
    # Hearing date
    hearing_date_bs = Column(String(20), nullable=False, index=True)
    # BS format: "2082-09-28"
    
    hearing_date_ad = Column(Date, nullable=False, index=True)
    # AD format for queries
    
    # Bench information
    bench = Column(String(100), nullable=True)
    # Example: "इजलाश 31", "इजलास नं १"
    
    bench_type = Column(String(100), nullable=True)
    # Example: "संयुक्त इजलास", "एकल इजलास"
    
    # Judges - simple text field, can contain multiple judges separated by commas or newlines
    judge_names = Column(Text, nullable=True)
    # Example: "माननीय न्यायाधीश श्री कृतबहादुर वोहरा"
    # Or: "अध्यक्ष माननीय न्यायाधीश श्री सुदर्शनदेव भट्ट, सदस्य माननीय न्यायाधीश श्री हेमन्त रावल"
    
    # Lawyers - simple text field
    lawyer_names = Column(Text, nullable=True)
    # Can list plaintiff and defendant lawyers
    
    # Hearing details
    serial_no = Column(String(20), nullable=True)
    # Order in causelist (क, ख, 1, 2, etc.)
    
    # Status and decisions
    case_status = Column(String(100), nullable=True)
    # Example: "स्थगित", "आदेश", "फैसला"
    
    decision_type = Column(String(200), nullable=True)
    # Example: "थुनछेक आदेश (धरौटी)", "ठहर"
    
    remarks = Column(Text, nullable=True)
    # Example: "थुनछेक", "बृद्ध"
    
    # Audit fields
    scraped_at = Column(DateTime, nullable=False)
    # When this record was scraped
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Additional data (court-specific fields stored as JSON)
    # extra_data may include:
    # - bench_id: Internal bench ID (high courts)
    # - bench_no: Bench number
    # - bench_label: Judge names summary (special court)
    # - court_number: Court room number
    # - judges: Array of judge objects with roles (for structured data)
    # - lawyers: Object with plaintiff/defendant lawyers (for structured data)
    # - judges_cannot_hear: Supreme court specific field
    # - status: Multi-line status field (high courts)
    # - footer: Court officer details
    # - Any other court-specific fields
    extra_data = Column(JSONB, nullable=True)
    
    def __repr__(self):
        return f"<CourtCaseHearing(case_number={self.case_number}, hearing_date={self.hearing_date_bs})>"


# Indexes for performance
Index('idx_court_type', Court.court_type)

Index('idx_case_court_date', 
      CourtCase.court_identifier, 
      CourtCase.registration_date_ad)

Index('idx_hearing_court_date', 
      CourtCaseHearing.court_identifier, 
      CourtCaseHearing.hearing_date_ad)

Index('idx_case_type_court', 
      CourtCase.case_type, 
      CourtCase.court_identifier)

Index('idx_hearing_status', 
      CourtCaseHearing.case_status, 
      CourtCaseHearing.hearing_date_ad)

# Full-text search indexes (PostgreSQL specific)
# These enable fast text search on names
# Note: Requires pg_trgm extension: CREATE EXTENSION IF NOT EXISTS pg_trgm;
Index('idx_case_plaintiff_fts', 
      CourtCase.plaintiff, 
      postgresql_using='gin',
      postgresql_ops={'plaintiff': 'gin_trgm_ops'})

Index('idx_case_defendant_fts', 
      CourtCase.defendant, 
      postgresql_using='gin',
      postgresql_ops={'defendant': 'gin_trgm_ops'})

Index('idx_hearing_judge_fts', 
      CourtCaseHearing.judge_names, 
      postgresql_using='gin',
      postgresql_ops={'judge_names': 'gin_trgm_ops'})


# Database connection helpers

# Global engine instance (singleton pattern)
_engine = None
_engine_url = None


def get_engine(database_url=None):
    """
    Get or create database engine (singleton pattern).
    
    Returns the same engine instance across calls. Once an engine is created,
    all subsequent calls must use the same database URL.
    
    Args:
        database_url: PostgreSQL connection string. If None, reads from DATABASE_URL env var.
        
    Returns:
        SQLAlchemy engine instance
        
    Raises:
        ValueError: If database_url is not provided and DATABASE_URL env var is not set
        AssertionError: If called with a different database_url after engine is created
        
    Example:
        engine = get_engine('postgresql://user:password@localhost:5432/court_cases')
    """
    global _engine, _engine_url
    
    if database_url is None:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError(
                "DATABASE_URL not provided and not found in environment variables. "
                "Please set DATABASE_URL or pass database_url parameter."
            )
    
    # If engine already exists, assert URL is the same
    if _engine is not None:
        assert _engine_url == database_url, (
            f"Attempted to create engine with different database URL. "
            f"Existing: {_engine_url}, Requested: {database_url}. "
            f"Only one database URL is allowed per process."
        )
        return _engine
    
    # Create new engine
    _engine = create_engine(database_url, echo=False)
    _engine_url = database_url
    
    return _engine


def get_session(engine):
    """
    Create database session.
    
    Args:
        engine: SQLAlchemy engine instance
        
    Returns:
        SQLAlchemy session instance
        
    Example:
        engine = get_engine()
        session = get_session(engine)
        
        # Use session
        courts = session.query(Court).all()
        
        # Close when done
        session.close()
    """
    Session = sessionmaker(bind=engine)
    return Session()


def init_db(engine):
    """
    Initialize database tables.
    
    Creates all tables defined in the models if they don't exist.
    Safe to run multiple times (won't drop existing tables).
    
    Args:
        engine: SQLAlchemy engine instance
        
    Example:
        engine = get_engine()
        init_db(engine)
    """
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """
    Drop all tables from the database.
    
    WARNING: This will delete all data! Use with caution.
    
    Args:
        engine: SQLAlchemy engine instance
        
    Example:
        engine = get_engine()
        drop_all_tables(engine)
    """
    Base.metadata.drop_all(engine)


# Example usage
if __name__ == "__main__":
    """
    Example usage of the models.
    
    Run with:
        DATABASE_URL='postgresql://user:password@localhost:5432/court_cases' poetry run python ngm/models.py
    """
    import sys
    
    # Get database URL
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Usage: DATABASE_URL='postgresql://user:pass@host:5432/db' poetry run python ngm/models.py")
        sys.exit(1)
    
    print(f"Connecting to database...")
    engine = get_engine(database_url)
    
    print("Creating tables...")
    init_db(engine)
    
    print("Tables created successfully!")
    
    # Show table information
    session = get_session(engine)
    
    print("\nDatabase statistics:")
    print(f"  Courts: {session.query(Court).count()}")
    print(f"  Cases: {session.query(CourtCase).count()}")
    print(f"  Hearings: {session.query(CourtCaseHearing).count()}")
    
    session.close()
    engine.dispose()
    
    print("\n✓ Done!")
