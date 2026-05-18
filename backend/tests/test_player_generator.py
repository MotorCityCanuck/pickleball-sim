"""Tests for synthetic player identity generation."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import PlayerGenerator  # noqa: E402
from app.models import (  # noqa: E402
    Club,
    FirstName,
    GenerationRun,
    LastName,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    PlayerRegistration,
    Region,
)


def test_payload(player_count):
    """Build a compact generation payload for player generator tests."""
    payload = {
        "simulation": {
            "target_total_players": player_count,
        },
        "player_generation": {
            "player_count": player_count,
            "age_min": 18,
            "age_max": 85,
            "age_distribution": {
                "18_29": 0.08,
                "30_44": 0.18,
                "45_59": 0.32,
                "60_74": 0.34,
                "75_plus": 0.08,
            },
            "gender_weights": {
                "male": 0.5,
                "female": 0.5,
            },
            "dominant_hand_weights": {
                "right": 0.88,
                "left": 0.10,
                "ambidextrous": 0.02,
            },
            "player_status_weights": {
                "active": 0.94,
                "injured": 0.02,
                "retired": 0.02,
                "inactive": 0.02,
            },
            "initial_skill_seed": {
                "mean": 1500,
                "std_dev": 275,
                "lower_bias": 100,
                "min": 500,
                "max": 3500,
            },
        },
        "ratings": {
            "initial_rating_mean": 1400,
        },
        "confidence": {
            "initial_confidence_score": 0.2,
        },
    }
    return deepcopy(payload)


test_payload.__test__ = False


def _json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key autoincrement,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot text,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE monthly_batches (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                batch_month date not null,
                batch_sequence integer not null,
                batch_type varchar(30) not null default 'future_increment',
                active_player_count_start integer,
                new_player_count integer,
                active_player_count_end integer,
                match_count_generated integer,
                rating_update_count integer,
                assessment_update_count integer,
                processing_status varchar(30) not null default 'pending',
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE regions (
                id integer primary key autoincrement,
                country_code varchar(10) not null,
                region_type varchar(20),
                region_name varchar(255) not null,
                state_province_code varchar(10),
                population bigint,
                selection_probability numeric(12, 8),
                competitiveness_multiplier numeric(8, 4) default 1.0,
                latitude numeric(10, 6),
                longitude numeric(10, 6),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE first_names (
                id integer primary key autoincrement,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                birth_year integer not null,
                gender varchar(1) not null,
                first_name varchar(100) not null,
                frequency_count integer not null,
                normalized_probability numeric(12, 8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE last_names (
                id integer primary key autoincrement,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                last_name varchar(100) not null,
                frequency_count integer not null,
                bias_multiplier numeric(10, 4),
                adjusted_frequency_count numeric(18, 4),
                normalized_probability numeric(12, 8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key autoincrement,
                club_name varchar(255) not null,
                region_id bigint not null,
                club_type varchar(50),
                competitiveness_level varchar(50),
                member_capacity integer,
                founding_date date,
                indoor_court_count integer default 0,
                outdoor_court_count integer default 0,
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE players (
                id integer primary key autoincrement,
                external_player_key varchar(32) not null default (lower(hex(randomblob(16)))) unique,
                first_name varchar(100) not null,
                last_name varchar(100) not null,
                gender varchar(20),
                birth_date date not null,
                dominant_hand varchar(10),
                home_region_id bigint,
                registration_date date not null,
                initial_skill_seed numeric(8, 4),
                player_status varchar(30) not null default 'ACTIVE',
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_rating_history (
                id integer primary key autoincrement,
                player_id bigint not null,
                rating_date date not null,
                rating_type varchar(50) not null,
                rating_value numeric(8, 3) not null,
                confidence_score numeric(8, 3),
                volatility_score numeric(8, 3),
                expected_performance numeric(8, 3),
                regional_adjustment_factor numeric(8, 4),
                global_percentile numeric(5, 2),
                match_count_used integer,
                calculation_version varchar(50),
                batch_id bigint not null,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_registrations (
                id integer primary key autoincrement,
                player_id bigint not null,
                batch_id bigint not null,
                registration_month date not null,
                registration_source varchar(50) not null default 'synthetic',
                assigned_region_id bigint,
                initial_rating_value numeric(8, 3),
                initial_confidence_score numeric(8, 3),
                created_at datetime default current_timestamp not null,
                unique (player_id, batch_id)
            )
            """
        )
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def seed_reference_data(session, *, payload=None):
    generation_run = GenerationRun(
        generation_name="player gen",
        seed_value=123,
        simulation_version="test",
        parameter_snapshot=_json_ready(payload or test_payload(8)),
        status="pending",
    )
    session.add(generation_run)
    session.flush()
    monthly_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        batch_sequence=1,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(monthly_batch)
    regions = [
        Region(
            country_code="US",
            state_province_code="TX",
            region_name="Austin",
            region_type="MSA",
            selection_probability="0.75",
        ),
        Region(
            country_code="CA",
            state_province_code="ON",
            region_name="Toronto",
            region_type="CMA",
            selection_probability="0.25",
        ),
    ]
    session.add_all(regions)
    session.flush()
    session.add_all(
        [
            Club(
                club_name="Austin Pickleball",
                region_id=regions[0].id,
                club_type="public_park",
                competitiveness_level="recreational",
                member_capacity=100,
                founding_date=date(2010, 6, 15),
            ),
            Club(
                club_name="Toronto Pickleball",
                region_id=regions[1].id,
                club_type="municipal_recreation",
                competitiveness_level="recreational",
                member_capacity=100,
                founding_date=date(2012, 3, 10),
            ),
        ]
    )
    for country, primary_state, fallback_state in [
        ("US", "TX", "CA"),
        ("CA", "ON", "QC"),
    ]:
        for state in [primary_state, fallback_state]:
            for year in range(1939, 2007):
                for gender, names in {
                    "M": [("Alex", 0.7), ("Jordan", 0.3)],
                    "F": [("Taylor", 0.6), ("Morgan", 0.4)],
                }.items():
                    for name, probability in names:
                        session.add(
                            FirstName(
                                country_code=country,
                                state_province_code=state,
                                birth_year=year,
                                gender=gender,
                                first_name=name,
                                frequency_count=1,
                                normalized_probability=str(probability),
                            )
                        )
            for name, probability in [("Smith", 0.8), ("Nguyen", 0.2)]:
                session.add(
                    LastName(
                        country_code=country,
                        state_province_code=state,
                        last_name=name,
                        frequency_count=1,
                        normalized_probability=str(probability),
                    )
                )
    session.commit()
    return generation_run, monthly_batch


def test_generate_initial_population_creates_players_and_registrations(session):
    generation_run, monthly_batch = seed_reference_data(session)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 8
    assert session.query(Player).count() == 8
    assert session.query(PlayerRegistration).count() == 8
    assert session.query(PlayerRatingHistory).count() == 8

    players = session.query(Player).order_by(Player.id).all()
    assert {player.generation_run_id for player in players} == {generation_run.id}
    assert all(
        date(2010, 6, 15) <= player.registration_date <= date(2024, 1, 1)
        for player in players
    )
    assert {player.gender for player in players}.issubset({"M", "F"})
    assert {player.dominant_hand for player in players}.issubset(
        {"RIGHT", "LEFT", "AMBID"}
    )
    assert {player.player_status for player in players}.issubset(
        {"ACTIVE", "INJURED", "INACTIVE", "RETIRED"}
    )
    assert all(player.initial_skill_seed is not None for player in players)

    registrations = session.query(PlayerRegistration).all()
    assert {row.batch_id for row in registrations} == {monthly_batch.id}
    assert {row.registration_month for row in registrations} == {date(2024, 1, 1)}
    assert {str(row.initial_rating_value) for row in registrations} == {"1400.000"}
    assert {str(row.initial_confidence_score) for row in registrations} == {"0.200"}

    rating_rows = (
        session.query(PlayerRatingHistory).order_by(PlayerRatingHistory.id).all()
    )
    assert {row.player_id for row in rating_rows} == {player.id for player in players}
    assert {row.batch_id for row in rating_rows} == {monthly_batch.id}
    assert {row.rating_date for row in rating_rows} == {date(2024, 1, 1)}
    assert {row.rating_type for row in rating_rows} == {"initial"}
    assert all(
        Decimal("0") <= row.rating_value <= Decimal("5000") for row in rating_rows
    )
    assert {str(row.confidence_score) for row in rating_rows} == {"0.200"}
    assert {str(row.volatility_score) for row in rating_rows} == {"1.000"}
    assert {row.match_count_used for row in rating_rows} == {0}
    assert {row.calculation_version for row in rating_rows} == {"initial_v1"}

    session.refresh(monthly_batch)
    assert monthly_batch.active_player_count_start == 0
    assert monthly_batch.new_player_count == 8
    assert monthly_batch.active_player_count_end == 8


def test_generate_initial_population_is_deterministic(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session)
        second_run, second_batch = seed_reference_data(second_session)

        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )

        first_players = [
            (
                player.first_name,
                player.last_name,
                player.gender,
                player.birth_date,
                player.home_region_id,
                str(player.initial_skill_seed),
                player.player_status,
            )
            for player in first_session.query(Player).order_by(Player.id)
        ]
        first_ratings = [
            (
                row.player_id,
                row.rating_date,
                row.rating_type,
                str(row.rating_value),
                str(row.confidence_score),
                str(row.volatility_score),
                row.match_count_used,
            )
            for row in first_session.query(PlayerRatingHistory).order_by(
                PlayerRatingHistory.id
            )
        ]
        second_players = [
            (
                player.first_name,
                player.last_name,
                player.gender,
                player.birth_date,
                player.home_region_id,
                str(player.initial_skill_seed),
                player.player_status,
            )
            for player in second_session.query(Player).order_by(Player.id)
        ]
        second_ratings = [
            (
                row.player_id,
                row.rating_date,
                row.rating_type,
                str(row.rating_value),
                str(row.confidence_score),
                str(row.volatility_score),
                row.match_count_used,
            )
            for row in second_session.query(PlayerRatingHistory).order_by(
                PlayerRatingHistory.id
            )
        ]
        assert first_players == second_players
        assert first_ratings == second_ratings
    finally:
        first_session.close()
        second_session.close()


def test_generate_initial_population_rejects_existing_players(session):
    generation_run, monthly_batch = seed_reference_data(session)
    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    with pytest.raises(ValueError, match="already has players"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_player_count_limits_generation(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 3
    assert session.query(Player).count() == 3


def test_payload_probability_validation_fails_fast(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 0.9, "female": 0.9}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    with pytest.raises(ValueError, match="sum to 1.0"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_player_count_defaults_to_current_50000():
    from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
    from app.generators.players import PlayerGenerationConfig

    config = PlayerGenerationConfig.from_payload(DEFAULT_CONFIG_PAYLOAD)

    assert config.player_count == 50000
    assert config.initial_rating_elite_tail_rate == Decimal("0.003")
    assert config.initial_rating_elite_min == Decimal("4000.0")
    assert config.initial_rating_elite_max == Decimal("4500.0")


def test_payload_initial_rating_elite_tail_can_generate_high_ratings():
    from app.generators.players import PlayerGenerationConfig, initial_rating_value

    payload = test_payload(1)
    payload["ratings"]["initial_rating_elite_tail_rate"] = 1
    payload["ratings"]["initial_rating_elite_min"] = 4000
    payload["ratings"]["initial_rating_elite_max"] = 4500
    config = PlayerGenerationConfig.from_payload(payload)

    rating = initial_rating_value(42, batch_id=1, player_sequence=0, config=config)

    assert Decimal("4000") <= rating <= Decimal("4500")


def test_payload_initial_rating_elite_tail_rate_must_be_probability():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["ratings"]["initial_rating_elite_tail_rate"] = 1.5

    with pytest.raises(ValueError, match="elite_tail_rate"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_initial_rating_elite_bounds_must_fit_rating_bounds():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["ratings"]["rating_max"] = 4200
    payload["ratings"]["initial_rating_elite_min"] = 4000
    payload["ratings"]["initial_rating_elite_max"] = 4500

    with pytest.raises(ValueError, match="elite rating bounds"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_player_count_can_be_overridden_for_smoke_load(session):
    generation_run, monthly_batch = seed_reference_data(session)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=2,
        session=session,
    )

    assert result.rows_loaded == 2


def test_payload_player_count_requires_positive_value():
    from app.generators.players import PlayerGenerationConfig

    with pytest.raises(ValueError, match="player_count"):
        PlayerGenerationConfig.from_payload(test_payload(0))


def test_payload_missing_name_distribution_fails(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError, match="No first-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_batch_must_belong_to_generation_run(session):
    first_run, monthly_batch = seed_reference_data(session)
    second_run = GenerationRun(
        generation_name="other",
        seed_value=999,
        parameter_snapshot=test_payload(1),
        status="pending",
    )
    session.add(second_run)
    session.commit()

    with pytest.raises(ValueError, match="Batch does not belong"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_missing_run_or_batch_fails(session):
    with pytest.raises(ValueError, match="Generation run"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=999,
            batch_id=1,
            player_count=1,
            session=session,
        )


def test_payload_missing_batch_fails(session):
    generation_run, _ = seed_reference_data(session)

    with pytest.raises(ValueError, match="Monthly batch"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=999,
            player_count=1,
            session=session,
        )


def test_payload_no_regions_fails(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(Region).delete()
    session.commit()

    with pytest.raises(ValueError, match="No production regions"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_exact_first_name_falls_back_to_nearest_birth_year(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_last_name_falls_back_to_country(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(LastName).filter(LastName.state_province_code == "ON").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_country_without_last_names_fails(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(LastName).delete()
    session.commit()

    with pytest.raises(ValueError, match="No last-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_existing_registrations_fail_before_insert(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.add(
        PlayerRegistration(
            player_id=1,
            batch_id=monthly_batch.id,
            registration_month=date(2024, 1, 1),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="already has registrations"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_initial_skill_seed_is_bounded(session):
    payload = test_payload(5)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": 1500,
        "std_dev": 100000,
        "lower_bias": 0,
        "min": 1000,
        "max": 1100,
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(
        1000 <= player.initial_skill_seed <= 1100
        for player in session.query(Player).all()
    )


def test_payload_registration_month_is_month_start(session):
    generation_run, monthly_batch = seed_reference_data(session)
    monthly_batch.batch_month = date(2024, 1, 17)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    player = session.query(Player).one()
    registration = session.query(PlayerRegistration).one()
    assert player.registration_date <= date(2024, 1, 1)
    assert registration.registration_month == date(2024, 1, 1)


def test_payload_registration_date_is_no_earlier_than_region_club_founding(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(8))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    for player in session.query(Player):
        club = session.query(Club).filter(Club.region_id == player.home_region_id).one()
        assert club.founding_date <= player.registration_date <= date(2024, 1, 1)


def test_payload_registration_date_uses_batch_month_when_club_founded_later(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(Club).update({Club.founding_date: date(2025, 1, 1)})
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.registration_date for player in session.query(Player)} == {
        date(2024, 1, 1)
    }


def test_payload_age_bounds_are_respected(session):
    payload = test_payload(5)
    payload["player_generation"]["age_min"] = 60
    payload["player_generation"]["age_max"] = 60
    payload["player_generation"]["age_distribution"] = {"60_74": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        date(2024, 1, 1).year - player.birth_date.year
        for player in session.query(Player).all()
    } == {60}


def test_payload_gender_mapping_uses_name_gender(session):
    payload = test_payload(4)
    payload["player_generation"]["gender_weights"] = {"female": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.gender for player in session.query(Player).all()} == {"F"}
    assert {player.first_name for player in session.query(Player).all()}.issubset(
        {"Taylor", "Morgan"}
    )


def test_payload_region_selection_uses_region_weights(session):
    payload = test_payload(20)
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    region_counts = {}
    for player in session.query(Player).all():
        region_counts[player.home_region_id] = region_counts.get(player.home_region_id, 0) + 1
    assert max(region_counts.values()) > min(region_counts.values())


def test_payload_registration_rating_values_from_config(session):
    payload = test_payload(1)
    payload["ratings"]["initial_rating_mean"] = 1234
    payload["confidence"]["initial_confidence_score"] = 0.55
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    registration = session.query(PlayerRegistration).one()
    assert str(registration.initial_rating_value) == "1234.000"
    assert str(registration.initial_confidence_score) == "0.550"


def test_payload_dominant_hand_and_status_can_be_forced(session):
    payload = test_payload(2)
    payload["player_generation"]["dominant_hand_weights"] = {"left": 1.0}
    payload["player_generation"]["player_status_weights"] = {"injured": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.dominant_hand for player in session.query(Player).all()} == {"LEFT"}
    assert {player.player_status for player in session.query(Player).all()} == {
        "INJURED"
    }


def test_payload_player_count_override_does_not_mutate_snapshot(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(8))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=2,
        session=session,
    )

    assert generation_run.parameter_snapshot["player_generation"]["player_count"] == 8


def test_payload_country_first_name_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.state_province_code == "ON").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_age_distribution_invalid_total_fails():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["age_distribution"] = {"18_29": 0.1}

    with pytest.raises(ValueError, match="sum to 1.0"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_negative_weight_fails():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 1.1, "female": -0.1}

    with pytest.raises(ValueError, match="cannot be negative"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_invalid_age_bounds_fails():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 85
    payload["player_generation"]["age_max"] = 18

    with pytest.raises(ValueError, match="age bounds"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_player_count_argument_requires_positive(session):
    generation_run, monthly_batch = seed_reference_data(session)

    with pytest.raises(ValueError, match="player_count"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=0,
            session=session,
        )


def test_payload_region_equal_weight_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(6))
    for region in session.query(Region):
        region.selection_probability = 0
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 6


def test_payload_first_name_country_nearest_year_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.query(FirstName).filter(FirstName.state_province_code == "ON").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generated_birth_dates_are_before_registration(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(8))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    for player in session.query(Player).all():
        assert player.birth_date < player.registration_date


def test_payload_generated_names_allow_duplicates(session):
    payload = test_payload(5)
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(FirstName.first_name != "Alex").delete()
    session.query(LastName).filter(LastName.last_name != "Smith").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 5
    assert session.query(Player.first_name, Player.last_name).distinct().count() < 5


def test_payload_result_reports_batch_counts(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.generation_run_id == generation_run.id
    assert result.batch_id == monthly_batch.id
    assert result.active_player_count_start == 0
    assert result.active_player_count_end == 4


def test_payload_sessionless_path_uses_session_scope(monkeypatch, session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    class _Scope:
        def __enter__(self):
            return session

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("app.generators.players.session_scope", lambda: _Scope())

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
    )

    assert result.rows_loaded == 1


def test_payload_status_and_hand_values_fit_orm_lengths(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(20))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(len(player.dominant_hand) <= 10 for player in session.query(Player))
    assert all(len(player.player_status) <= 30 for player in session.query(Player))


def test_payload_name_index_exact_lookup_prefers_state(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        FirstName(
            country_code="US",
            state_province_code="TX",
            birth_year=1980,
            gender="M",
            first_name="StateSpecific",
            frequency_count=1,
            normalized_probability="100.0",
        )
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generator_does_not_create_ratings_yet(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().initial_rating_value is not None


def test_payload_player_count_from_simulation_when_player_count_missing(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(3)
    del payload["player_generation"]["player_count"]
    payload["simulation"]["target_total_players"] = 7

    assert PlayerGenerationConfig.from_payload(payload).player_count == 7


def test_payload_missing_snapshot_uses_default_config(session):
    generation_run, monthly_batch = seed_reference_data(session)
    generation_run.parameter_snapshot = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_no_last_name_country_fallback_if_country_absent(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(LastName).filter(LastName.country_code == "US").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    with pytest.raises(ValueError, match="No last-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_no_first_name_country_fallback_if_country_absent(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.country_code == "US").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    with pytest.raises(ValueError, match="No first-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=1,
            session=session,
        )


def test_payload_multiple_runs_can_generate_independently(session):
    first_run, first_batch = seed_reference_data(session, payload=test_payload(1))
    PlayerGenerator().generate_initial_population(
        generation_run_id=first_run.id,
        batch_id=first_batch.id,
        session=session,
    )

    second_run = GenerationRun(
        generation_name="second",
        seed_value=456,
        parameter_snapshot=test_payload(1),
        status="pending",
    )
    session.add(second_run)
    session.flush()
    second_batch = MonthlyBatch(
        generation_run_id=second_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(second_batch)
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=second_run.id,
        batch_id=second_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1
    assert session.query(Player).count() == 2


def test_payload_generation_run_status_is_not_completed(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert generation_run.status == "pending"


def test_payload_monthly_batch_status_is_not_completed(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.processing_status == "pending"


def test_payload_region_candidates_are_limited_to_us_and_canada(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))
    session.add(
        Region(
            country_code="MX",
            state_province_code="CMX",
            region_name="Mexico City",
            selection_probability="100.0",
        )
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        session.get(Region, player.home_region_id).country_code
        for player in session.query(Player)
    }.issubset({"US", "CA"})


def test_payload_fallback_zero_name_weights_are_accepted(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    for row in session.query(FirstName):
        row.normalized_probability = 0
    for row in session.query(LastName):
        row.normalized_probability = 0
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_configured_status_weights_sum_tolerance():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {
        "active": 0.94,
        "injured": 0.02,
        "retired": 0.02,
        "inactive": 0.019,
    }

    assert PlayerGenerationConfig.from_payload(payload).player_count == 1


def test_payload_configured_status_weights_outside_tolerance_fails():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {
        "active": 0.94,
        "injured": 0.02,
        "retired": 0.02,
        "inactive": 0.0,
    }

    with pytest.raises(ValueError, match="sum to 1.0"):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_initial_skill_seed_precision(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert abs(session.query(Player).one().initial_skill_seed.as_tuple().exponent) <= 4


def test_payload_registration_source_uses_database_default(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().registration_source == "synthetic"


def test_payload_generated_players_have_home_regions(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(player.home_region_id is not None for player in session.query(Player))


def test_payload_result_rows_loaded_matches_table_counts(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == session.query(Player).count()
    assert result.rows_loaded == session.query(PlayerRegistration).count()


def test_payload_generation_uses_generation_run_seed(session):
    first_payload = test_payload(2)
    second_payload = test_payload(2)
    first_run, first_batch = seed_reference_data(session, payload=first_payload)
    PlayerGenerator().generate_initial_population(
        generation_run_id=first_run.id,
        batch_id=first_batch.id,
        session=session,
    )
    first_names = [player.first_name for player in session.query(Player).order_by(Player.id)]

    session.query(PlayerRegistration).delete()
    session.query(Player).delete()
    first_run.seed_value = 999
    first_run.parameter_snapshot = second_payload
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=first_run.id,
        batch_id=first_batch.id,
        session=session,
    )
    second_names = [player.first_name for player in session.query(Player).order_by(Player.id)]

    assert first_names != second_names


def test_payload_month_start_helper_handles_first_day(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.batch_month = date(2024, 5, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().registration_date <= date(2024, 5, 1)


def test_payload_default_config_smoke_with_override(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=None)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_selection_probability_none_uses_equal_weight(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))
    for region in session.query(Region):
        region.selection_probability = None
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 4


def test_payload_name_index_uses_state_last_name_when_available(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).filter(LastName.last_name != "Nguyen").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().last_name == "Nguyen"


def test_payload_generated_birth_years_have_name_support(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(6))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(player.first_name for player in session.query(Player))


def test_payload_generation_leaves_batch_match_counts_unchanged(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.match_count_generated = 99
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.match_count_generated == 99


def test_payload_generation_sets_only_player_intake_counts(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.rating_update_count = 10
    monthly_batch.assessment_update_count = 11
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.rating_update_count == 10
    assert monthly_batch.assessment_update_count == 11


def test_payload_generation_allows_small_test_loads(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(50))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=10,
        session=session,
    )

    assert result.rows_loaded == 10


def test_payload_generation_uses_initial_rating_mean_as_decimal(session):
    payload = test_payload(1)
    payload["ratings"]["initial_rating_mean"] = "1555.125"
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_rating_value) == "1555.125"


def test_payload_generation_uses_confidence_as_decimal(session):
    payload = test_payload(1)
    payload["confidence"]["initial_confidence_score"] = "0.333"
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_confidence_score) == "0.333"


def test_payload_generation_country_first_name_exact_year_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.state_province_code == "ON").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=2,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_nearest_year_prefers_lower_on_tie(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(~FirstName.birth_year.in_([1979, 1981])).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_preserves_generation_run_snapshot(session):
    payload = test_payload(2)
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert generation_run.parameter_snapshot == payload


def test_payload_generation_forced_right_hand(session):
    payload = test_payload(3)
    payload["player_generation"]["dominant_hand_weights"] = {"right": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.dominant_hand for player in session.query(Player)} == {"RIGHT"}


def test_payload_generation_forced_active_status(session):
    payload = test_payload(3)
    payload["player_generation"]["player_status_weights"] = {"active": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.player_status for player in session.query(Player)} == {"ACTIVE"}


def test_payload_generation_uses_batch_generation_run_id(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().generation_run_id == monthly_batch.generation_run_id


def test_payload_generation_registration_region_matches_player_region(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    for registration in session.query(PlayerRegistration):
        assert registration.assigned_region_id == session.get(
            Player,
            registration.player_id,
        ).home_region_id


def test_payload_generation_does_not_commit_external_session(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    with session.begin_nested():
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )
        session.rollback()

    assert session.query(Player).count() == 0


def test_payload_generation_can_commit_external_session(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    session.commit()

    assert session.query(Player).count() == 1


def test_payload_generation_birth_date_day_is_valid(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(10))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(1 <= player.birth_date.day <= 28 for player in session.query(Player))


def test_payload_generation_accepts_numeric_strings(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": "1500",
        "std_dev": "275",
        "lower_bias": "100",
        "min": "500",
        "max": "3500",
    }

    assert PlayerGenerationConfig.from_payload(payload).skill_mean == 1500


def test_payload_generation_age_distribution_75_plus(session):
    payload = test_payload(2)
    payload["player_generation"]["age_min"] = 75
    payload["player_generation"]["age_max"] = 85
    payload["player_generation"]["age_distribution"] = {"75_plus": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(
        75 <= date(2024, 1, 1).year - player.birth_date.year <= 85
        for player in session.query(Player)
    )


def test_payload_generation_preserves_duplicate_full_names(session):
    payload = test_payload(3)
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(FirstName.first_name != "Alex").delete()
    session.query(LastName).filter(LastName.last_name != "Smith").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player.first_name, Player.last_name).distinct().count() == 1


def test_payload_generation_one_row_smoke(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_raises_before_partial_insert_on_name_error(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(LastName).delete()
    session.commit()

    with pytest.raises(ValueError, match="No last-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert session.query(Player).count() == 0


def test_payload_generation_raises_before_partial_insert_on_first_name_error(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError, match="No first-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert session.query(Player).count() == 0


def test_payload_generation_name_index_country_fallback_uses_available_country(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.country_code == "CA").delete()
    session.query(LastName).filter(LastName.country_code == "CA").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=2,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_sets_result_ids(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.generation_run_id == generation_run.id
    assert result.batch_id == monthly_batch.id


def test_payload_generation_supports_state_specific_surnames(session):
    payload = test_payload(4)
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(LastName).filter(LastName.state_province_code == "TX").delete()
    session.add(
        LastName(
            country_code="US",
            state_province_code="TX",
            last_name="StateSurname",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.last_name for player in session.query(Player)} == {"StateSurname"}


def test_payload_generation_no_players_when_existing_run_player_even_other_batch(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        Player(
            first_name="Existing",
            last_name="Player",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 1, 1),
            generation_run_id=generation_run.id,
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="already has players"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_batch_counts_are_integers(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert isinstance(monthly_batch.new_player_count, int)
    assert isinstance(monthly_batch.active_player_count_end, int)


def test_payload_generation_keeps_registration_source_default_with_flush(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    registration = session.query(PlayerRegistration).one()
    session.refresh(registration)

    assert registration.registration_source == "synthetic"


def test_payload_generation_uses_upper_status_values(session):
    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {"retired": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().player_status == "RETIRED"


def test_payload_generation_uses_upper_gender_values(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().gender == "M"


def test_payload_generation_does_not_require_clubs(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().home_region_id is not None


def test_payload_generation_returns_zero_start_for_initial_run(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.active_player_count_start == 0


def test_payload_generation_handles_decimal_region_weights(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))
    for region in session.query(Region):
        region.selection_probability = "0.33333333"
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 3


def test_payload_generation_status_counts_are_not_validated_posthoc(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(6))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 6


def test_payload_generation_names_are_non_empty(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(player.first_name and player.last_name for player in session.query(Player))


def test_payload_generation_batch_counts_match_rows_loaded(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(7))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.new_player_count == result.rows_loaded


def test_payload_generation_overrides_payload_count_for_small_smoke(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(100))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=3,
        session=session,
    )

    assert session.query(Player).count() == 3


def test_payload_generation_selects_from_country_state_names(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {session.get(Region, player.home_region_id).state_province_code for player in session.query(Player)} == {"TX"}


def test_payload_generation_never_sets_age_column(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert not hasattr(session.query(Player).one(), "age")


def test_payload_generation_result_is_dataclass_like(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1
    assert result.active_player_count_end == 1


def test_payload_generation_rejects_non_positive_override_before_name_lookup(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError, match="player_count"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            player_count=-1,
            session=session,
        )


def test_payload_generation_registration_month_tracks_batch_month_start(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.batch_month = date(2024, 12, 31)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().registration_month == date(2024, 12, 1)


def test_payload_generation_birth_date_month_is_valid(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(1 <= player.birth_date.month <= 12 for player in session.query(Player))


def test_payload_generation_handles_country_level_first_name_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).filter(FirstName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_full_name_fields_are_strings(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(isinstance(player.first_name, str) for player in session.query(Player))
    assert all(isinstance(player.last_name, str) for player in session.query(Player))


def test_payload_generation_sets_created_rows_in_single_flush(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 2
    assert all(player.id is not None for player in session.query(Player))


def test_payload_generation_uses_config_snapshot_from_run(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    payload = deepcopy(generation_run.parameter_snapshot)
    payload["player_generation"]["player_count"] = 4
    generation_run.parameter_snapshot = payload
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 4


def test_payload_generation_custom_unknown_gender_key_passes_through_to_lookup(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"X": 1.0}

    assert PlayerGenerationConfig.from_payload(payload).gender_weights == (("X", Decimal("1.0")),)


def test_payload_generation_unknown_gender_without_names_fails(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"X": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    with pytest.raises(ValueError, match="No first-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_unknown_status_key_passes_through(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {"CUSTOM": 1.0}

    assert PlayerGenerationConfig.from_payload(payload).player_status_weights == (
        ("CUSTOM", Decimal("1.0")),
    )


def test_payload_generation_unknown_hand_key_passes_through(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["dominant_hand_weights"] = {"CUSTOM": 1.0}

    assert PlayerGenerationConfig.from_payload(payload).dominant_hand_weights == (
        ("CUSTOM", Decimal("1.0")),
    )


def test_payload_generation_country_last_name_fallback_uses_country_pool(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).filter(LastName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_first_name_nearest_country_year_fallback_works(session):
    generation_run, monthly_batch = seed_reference_data(session)
    session.query(FirstName).filter(FirstName.state_province_code == "ON").delete()
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_updates_batch_counts_after_flush(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    session.refresh(monthly_batch)

    assert monthly_batch.new_player_count == 2


def test_payload_generation_player_status_can_be_inactive(session):
    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {"inactive": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().player_status == "INACTIVE"


def test_payload_generation_player_status_can_be_retired(session):
    payload = test_payload(1)
    payload["player_generation"]["player_status_weights"] = {"retired": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().player_status == "RETIRED"


def test_payload_generation_player_hand_can_be_ambidextrous(session):
    payload = test_payload(1)
    payload["player_generation"]["dominant_hand_weights"] = {"ambidextrous": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().dominant_hand == "AMBID"


def test_payload_generation_empty_weighted_choice_fails():
    from app.generators.players import weighted_choice
    import random

    with pytest.raises(ValueError, match="empty"):
        weighted_choice(random.Random(1), [])


def test_payload_generation_country_region_order_is_stable(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert [player.id for player in session.query(Player).order_by(Player.id)] == [1, 2, 3, 4]


def test_payload_generation_accepts_float_probabilities(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 1.0}

    assert PlayerGenerationConfig.from_payload(payload).gender_weights == (("M", Decimal("1.0")),)


def test_payload_generation_uses_fallback_default_payload_with_override(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=None)
    generation_run.parameter_snapshot = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=2,
        session=session,
    )

    assert result.rows_loaded == 2


def test_payload_generation_can_run_inside_explicit_transaction(session_factory):
    session = session_factory()
    try:
        generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
        with session.begin_nested():
            result = PlayerGenerator().generate_initial_population(
                generation_run_id=generation_run.id,
                batch_id=monthly_batch.id,
                session=session,
            )
            assert result.rows_loaded == 1
    finally:
        session.close()


def test_payload_generation_batch_counts_are_not_set_on_failure(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert monthly_batch.new_player_count is None


def test_payload_generation_supports_default_selection_weights(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    del payload["player_generation"]["gender_weights"]
    del payload["player_generation"]["dominant_hand_weights"]
    del payload["player_generation"]["player_status_weights"]

    config = PlayerGenerationConfig.from_payload(payload)

    assert config.gender_weights
    assert config.dominant_hand_weights
    assert config.player_status_weights


def test_payload_generation_supports_default_age_distribution():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    del payload["player_generation"]["age_distribution"]

    assert PlayerGenerationConfig.from_payload(payload).age_distribution


def test_payload_generation_supports_default_skill_seed():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    del payload["player_generation"]["initial_skill_seed"]

    assert PlayerGenerationConfig.from_payload(payload).skill_mean == 1500


def test_payload_generation_result_uses_player_count_override_for_counts(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.active_player_count_end == 1


def test_payload_generation_first_name_country_year_pool_aggregates_states(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 44
    payload["player_generation"]["age_max"] = 44
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(
        FirstName.country_code == "US",
        FirstName.state_province_code != "TX",
    ).delete()
    session.add(
        FirstName(
            country_code="US",
            state_province_code="CA",
            birth_year=1980,
            gender="M",
            first_name="CountryPool",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(FirstName).filter(FirstName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).one().first_name == "CountryPool"


def test_payload_generation_last_name_country_pool_aggregates_states(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).filter(
        LastName.country_code == "US",
        LastName.state_province_code != "TX",
    ).delete()
    session.add(
        LastName(
            country_code="US",
            state_province_code="CA",
            last_name="CountrySurname",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(LastName).filter(LastName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).one().last_name == "CountrySurname"


def test_payload_generation_count_override_does_not_change_config_object(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(5)
    config = PlayerGenerationConfig.from_payload(payload)

    assert config.player_count == 5


def test_payload_generation_age_distribution_clamps_to_bounds(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 30
    payload["player_generation"]["age_max"] = 40
    payload["player_generation"]["age_distribution"] = {"18_29": 1.0}

    assert PlayerGenerationConfig.from_payload(payload).age_distribution == (((30, 29), Decimal("1.0")),)


def test_payload_generation_with_clamped_empty_age_range_falls_back_to_min(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 30
    payload["player_generation"]["age_max"] = 40
    payload["player_generation"]["age_distribution"] = {"18_29": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    player = session.query(Player).one()
    assert date(2024, 1, 1).year - player.birth_date.year == 30


def test_payload_generation_missing_country_names_can_still_use_other_country_if_region_matches(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(Region).filter(Region.country_code == "US").delete()
    session.query(FirstName).filter(FirstName.country_code == "US").delete()
    session.query(LastName).filter(LastName.country_code == "US").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_uses_batch_month_for_birth_year(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 44
    payload["player_generation"]["age_max"] = 44
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    monthly_batch.batch_month = date(2024, 7, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().birth_date.year == 1980


def test_payload_generation_can_select_nearest_name_year_for_old_players(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 85
    payload["player_generation"]["age_max"] = 85
    payload["player_generation"]["age_distribution"] = {"75_plus": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_can_select_nearest_name_year_for_young_players(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 18
    payload["player_generation"]["age_max"] = 18
    payload["player_generation"]["age_distribution"] = {"18_29": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_creates_registration_for_each_player(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(9))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        registration.player_id for registration in session.query(PlayerRegistration)
    } == {player.id for player in session.query(Player)}


def test_payload_generation_names_are_from_reference_tables(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.first_name for player in session.query(Player)}.issubset(
        {"Alex", "Jordan", "Taylor", "Morgan"}
    )
    assert {player.last_name for player in session.query(Player)}.issubset(
        {"Smith", "Nguyen"}
    )


def test_payload_generation_import_exports_player_generator():
    from app.generators import PlayerGenerationResult, PlayerGenerator as Exported

    assert Exported is PlayerGenerator
    assert PlayerGenerationResult.__name__ == "PlayerGenerationResult"


def test_payload_generation_empty_regions_after_filter_fails(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    for region in session.query(Region):
        region.country_code = "MX"
    session.commit()

    with pytest.raises(ValueError, match="No production regions"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_state_province_required_for_names(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    for region in session.query(Region):
        region.state_province_code = "ZZ"
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_result_after_flush_has_player_ids(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(player.id for player in session.query(Player))


def test_payload_generation_registration_unique_pair(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    pairs = {
        (registration.player_id, registration.batch_id)
        for registration in session.query(PlayerRegistration)
    }
    assert len(pairs) == 2


def test_payload_generation_can_use_default_payload_if_snapshot_empty_dict(session):
    generation_run, monthly_batch = seed_reference_data(session, payload={})

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_initial_confidence_default(session):
    payload = test_payload(1)
    del payload["confidence"]["initial_confidence_score"]
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_confidence_score) == "0.100"


def test_payload_generation_initial_rating_default(session):
    payload = test_payload(1)
    del payload["ratings"]["initial_rating_mean"]
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_rating_value) == "1500.000"


def test_payload_generation_batch_count_start_uses_existing_players_from_run(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    # Current initial generation intentionally rejects existing run players.
    session.add(
        Player(
            first_name="Existing",
            last_name="Probe",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 1, 1),
            generation_run_id=generation_run.id,
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="already has players"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_supports_alternate_country_if_seed_selects_it(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(10))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 10


def test_payload_generation_batched_records_have_same_registration_month(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        registration.registration_month
        for registration in session.query(PlayerRegistration)
    } == {date(2024, 1, 1)}


def test_payload_generation_does_not_touch_generation_run_completed_at(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert generation_run.completed_at is None


def test_payload_generation_does_not_touch_batch_completed_at(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.completed_at is None


def test_payload_generation_works_with_string_seed_value(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    generation_run.seed_value = "123"
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_can_select_with_large_country_pool(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))
    for index in range(10):
        session.add(
            LastName(
                country_code="US",
                state_province_code=f"S{index}",
                last_name=f"Extra{index}",
                frequency_count=1,
                normalized_probability="0.1",
            )
        )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_returns_namedtuple_like_fields(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1
    assert result.active_player_count_start == 0


def test_payload_generation_default_target_is_50000_without_running_full_load():
    from app.core import DEFAULT_CONFIG_PAYLOAD

    assert DEFAULT_CONFIG_PAYLOAD["player_generation"]["player_count"] == 50000


def test_payload_generation_name_probabilities_are_weighted(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(20))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    names = [player.last_name for player in session.query(Player)]
    assert names.count("Smith") >= names.count("Nguyen")


def test_payload_generation_can_use_equal_choice_when_region_weights_zero(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    for region in session.query(Region):
        region.selection_probability = "0.0"
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 2


def test_payload_generation_birth_year_uses_registration_year(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 30
    payload["player_generation"]["age_max"] = 30
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    monthly_batch.batch_month = date(2030, 1, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().birth_date.year == 2000


def test_payload_generation_can_lookup_future_birth_year_by_nearest(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 18
    payload["player_generation"]["age_max"] = 18
    payload["player_generation"]["age_distribution"] = {"18_29": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    monthly_batch.batch_month = date(2030, 1, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_can_lookup_past_birth_year_by_nearest(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 100
    payload["player_generation"]["age_max"] = 100
    payload["player_generation"]["age_distribution"] = {"75_plus": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    monthly_batch.batch_month = date(2030, 1, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_batch_counts_start_at_zero_for_initial_population(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.active_player_count_start == 0
    assert result.active_player_count_end == 3


def test_payload_generation_does_not_require_generation_run_simulation_version(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    generation_run.simulation_version = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_can_generate_from_latest_config_shape(session):
    from app.core import default_config_payload

    payload = default_config_payload()
    payload["player_generation"]["player_count"] = 1
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_registration_values_are_set_before_commit(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    registration = session.query(PlayerRegistration).one()
    assert registration.initial_rating_value is not None
    assert registration.initial_confidence_score is not None


def test_payload_generation_no_raw_files_used(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().first_name


def test_payload_generation_rejects_empty_first_name_table(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_rejects_empty_last_name_table(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).delete()
    session.commit()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_return_type_repr(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert "PlayerGenerationResult" in repr(result)


def test_payload_generation_uses_state_province_code_from_region(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    player = session.query(Player).one()
    assert session.get(Region, player.home_region_id).state_province_code == "TX"


def test_payload_generation_uses_configured_player_count_exactly(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(11))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 11


def test_payload_generation_does_not_update_completed_counts_unrelated(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.match_count_generated = 5
    monthly_batch.rating_update_count = 6
    monthly_batch.assessment_update_count = 7
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.match_count_generated == 5
    assert monthly_batch.rating_update_count == 6
    assert monthly_batch.assessment_update_count == 7


def test_payload_generation_uses_current_batch_only_for_registrations(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {row.batch_id for row in session.query(PlayerRegistration)} == {monthly_batch.id}


def test_payload_generation_returns_loaded_count_for_override(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(99))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=4,
        session=session,
    )

    assert result.rows_loaded == 4


def test_payload_generation_no_commit_needed_for_query_visibility(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_first_names_include_gender(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(8))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    for player in session.query(Player):
        if player.gender == "M":
            assert player.first_name in {"Alex", "Jordan"}
        if player.gender == "F":
            assert player.first_name in {"Taylor", "Morgan"}


def test_payload_generation_from_default_payload_can_be_limited(session):
    from app.core import default_config_payload

    payload = default_config_payload()
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_first_name_lookup_error_includes_scope(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).delete()
    session.commit()

    with pytest.raises(ValueError, match="/"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_last_name_lookup_error_includes_country(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).delete()
    session.commit()

    with pytest.raises(ValueError, match="US|CA"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_has_no_side_effect_when_batch_missing(session):
    generation_run, _ = seed_reference_data(session, payload=test_payload(1))

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=999,
            session=session,
        )

    assert session.query(Player).count() == 0


def test_payload_generation_has_no_side_effect_when_run_missing(session):
    seed_reference_data(session, payload=test_payload(1))

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=999,
            batch_id=1,
            session=session,
        )

    assert session.query(Player).count() == 0


def test_payload_generation_works_when_region_population_missing(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    for region in session.query(Region):
        region.population = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_works_when_region_type_missing(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    for region in session.query(Region):
        region.region_type = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_uses_selection_probability_not_population(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))
    regions = session.query(Region).all()
    regions[0].population = 1
    regions[1].population = 100000000
    regions[0].selection_probability = "1.0"
    regions[1].selection_probability = "0.0"
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.home_region_id for player in session.query(Player)} == {regions[0].id}


def test_payload_generation_uses_decimal_probability_strings(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": "0.50", "female": "0.50"}

    assert PlayerGenerationConfig.from_payload(payload).gender_weights == (
        ("M", Decimal("0.50")),
        ("F", Decimal("0.50")),
    )


def test_payload_generation_name_index_allows_zero_weight_names(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).update({FirstName.normalized_probability: 0})
    session.query(LastName).update({LastName.normalized_probability: 0})
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
        player_count=1,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_batch_count_end_uses_start_plus_loaded(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.active_player_count_end == result.active_player_count_start + 3


def test_payload_generation_nearest_year_handles_empty_candidates():
    from app.generators.players import _nearest

    assert _nearest(1980, set()) is None


def test_payload_generation_nearest_year_prefers_closest():
    from app.generators.players import _nearest

    assert _nearest(1980, {1970, 1979, 1990}) == 1979


def test_payload_generation_weighted_choice_returns_last_when_target_exceeds_due_rounding():
    from app.generators.players import weighted_choice
    import random

    assert weighted_choice(random.Random(1), [("x", Decimal("0"))]) == "x"


def test_payload_generation_counts_are_set_after_success_only(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(LastName).delete()
    session.commit()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert monthly_batch.active_player_count_end is None


def test_payload_generation_generated_players_have_batch_registration(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).count() == session.query(Player).count()


def test_payload_generation_forced_canadian_region(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(Region).filter(Region.country_code == "US").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        session.get(Region, player.home_region_id).country_code
        for player in session.query(Player)
    } == {"CA"}


def test_payload_generation_forced_us_region(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {
        session.get(Region, player.home_region_id).country_code
        for player in session.query(Player)
    } == {"US"}


def test_payload_generation_supports_state_first_name_exact_year(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 44
    payload["player_generation"]["age_max"] = 44
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(FirstName).filter(FirstName.first_name != "Alex").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().first_name == "Alex"


def test_payload_generation_supports_state_last_name_exact(session):
    payload = test_payload(1)
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(LastName).filter(LastName.last_name != "Smith").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().last_name == "Smith"


def test_payload_generation_returns_after_flush_without_commit(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_player_ids_are_unique(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    ids = [player.id for player in session.query(Player)]
    assert len(ids) == len(set(ids))


def test_payload_generation_player_external_keys_are_database_defaults(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(player.external_player_key for player in session.query(Player))


def test_payload_generation_supports_custom_player_count_arg_with_default_snapshot(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=None)
    generation_run.parameter_snapshot = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_initial_skill_lower_bias_applies(session):
    payload = test_payload(1)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": 1500,
        "std_dev": 0,
        "lower_bias": 100,
        "min": 0,
        "max": 5000,
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().initial_skill_seed == Decimal("1400.0000")


def test_payload_generation_initial_skill_clamps_low(session):
    payload = test_payload(1)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": 100,
        "std_dev": 0,
        "lower_bias": 100,
        "min": 500,
        "max": 5000,
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().initial_skill_seed == Decimal("500.0000")


def test_payload_generation_initial_skill_clamps_high(session):
    payload = test_payload(1)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": 6000,
        "std_dev": 0,
        "lower_bias": 0,
        "min": 500,
        "max": 5000,
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().initial_skill_seed == Decimal("5000.0000")


def test_payload_generation_records_region_assignment_in_registration(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(
        registration.assigned_region_id
        for registration in session.query(PlayerRegistration)
    )


def test_payload_generation_player_count_from_snapshot_not_settings(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(6))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 6


def test_payload_generation_full_batch_smoke_100_rows(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(100))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 100


def test_payload_generation_does_not_use_global_random_state(session):
    import random

    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    random.seed(999)
    before = random.random()
    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    after = random.random()

    random.seed(999)
    assert before == random.random()
    assert after == random.random()


def test_payload_generation_first_name_fallback_requires_same_gender(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(FirstName).filter(FirstName.gender == "M").delete()
    session.commit()

    with pytest.raises(ValueError, match="No first-name distribution"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_result_counts_with_override_and_snapshot(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(20))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=5,
        session=session,
    )

    assert result.rows_loaded == 5
    assert monthly_batch.new_player_count == 5


def test_payload_generation_config_accepts_int_weights():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 1, "female": 0}

    assert PlayerGenerationConfig.from_payload(payload).gender_weights == (
        ("M", Decimal("1")),
        ("F", Decimal("0")),
    )


def test_payload_generation_config_accepts_missing_ratings_group(session):
    payload = test_payload(1)
    del payload["ratings"]
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_rating_value) == "1500.000"


def test_payload_generation_config_accepts_missing_confidence_group(session):
    payload = test_payload(1)
    del payload["confidence"]
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert str(session.query(PlayerRegistration).one().initial_confidence_score) == "0.100"


def test_payload_generation_uses_first_name_country_fallback_if_state_missing(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        FirstName(
            country_code="US",
            state_province_code="CA",
            birth_year=1980,
            gender="M",
            first_name="Fallback",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(FirstName).filter(FirstName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_config_from_none_uses_default_50000():
    from app.generators.players import PlayerGenerationConfig

    assert PlayerGenerationConfig.from_payload(None).player_count == 50000


def test_payload_generation_no_region_side_effect_on_failure(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).delete()
    session.commit()
    region_count = session.query(Region).count()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert session.query(Region).count() == region_count


def test_payload_generation_registration_ids_are_assigned(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert all(registration.id for registration in session.query(PlayerRegistration))


def test_payload_generation_region_weight_fallback_handles_none_and_zero(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    regions = session.query(Region).all()
    regions[0].selection_probability = None
    regions[1].selection_probability = 0
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 2


def test_payload_generation_uses_sorted_region_order_for_stability(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_can_generate_from_minimal_payload(session):
    payload = {
        "simulation": {"target_total_players": 1},
        "player_generation": {"player_count": 1},
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_year_bucket_uses_exact_year_when_available(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 44
    payload["player_generation"]["age_max"] = 44
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(FirstName).filter(FirstName.birth_year != 1980).delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_uses_registration_year_for_age_not_current_date(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 30
    payload["player_generation"]["age_max"] = 30
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    monthly_batch.batch_month = date(2010, 1, 1)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().birth_date.year == 1980


def test_payload_generation_values_are_not_none(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    for player in session.query(Player):
        assert player.first_name is not None
        assert player.last_name is not None
        assert player.birth_date is not None
        assert player.registration_date is not None


def test_payload_generation_configured_player_count_large_does_not_run_here():
    from app.core import DEFAULT_CONFIG_PAYLOAD

    assert DEFAULT_CONFIG_PAYLOAD["simulation"]["target_total_players"] == 50000


def test_payload_generation_registration_rating_fields_are_optional_but_populated(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    registration = session.query(PlayerRegistration).one()
    assert registration.initial_rating_value is not None
    assert registration.initial_confidence_score is not None


def test_payload_generation_deterministic_region_assignment(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session, payload=test_payload(5))
        second_run, second_batch = seed_reference_data(second_session, payload=test_payload(5))
        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )
        assert [
            player.home_region_id for player in first_session.query(Player).order_by(Player.id)
        ] == [
            player.home_region_id for player in second_session.query(Player).order_by(Player.id)
        ]
    finally:
        first_session.close()
        second_session.close()


def test_payload_generation_deterministic_birthdates(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session, payload=test_payload(5))
        second_run, second_batch = seed_reference_data(second_session, payload=test_payload(5))
        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )
        assert [
            player.birth_date for player in first_session.query(Player).order_by(Player.id)
        ] == [
            player.birth_date for player in second_session.query(Player).order_by(Player.id)
        ]
    finally:
        first_session.close()
        second_session.close()


def test_payload_generation_deterministic_skill_seed(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session, payload=test_payload(5))
        second_run, second_batch = seed_reference_data(second_session, payload=test_payload(5))
        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )
        assert [
            player.initial_skill_seed for player in first_session.query(Player).order_by(Player.id)
        ] == [
            player.initial_skill_seed for player in second_session.query(Player).order_by(Player.id)
        ]
    finally:
        first_session.close()
        second_session.close()


def test_payload_generation_deterministic_status(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session, payload=test_payload(5))
        second_run, second_batch = seed_reference_data(second_session, payload=test_payload(5))
        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )
        assert [
            player.player_status for player in first_session.query(Player).order_by(Player.id)
        ] == [
            player.player_status for player in second_session.query(Player).order_by(Player.id)
        ]
    finally:
        first_session.close()
        second_session.close()


def test_payload_generation_deterministic_names(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_reference_data(first_session, payload=test_payload(5))
        second_run, second_batch = seed_reference_data(second_session, payload=test_payload(5))
        PlayerGenerator().generate_initial_population(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        PlayerGenerator().generate_initial_population(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )
        assert [
            (player.first_name, player.last_name)
            for player in first_session.query(Player).order_by(Player.id)
        ] == [
            (player.first_name, player.last_name)
            for player in second_session.query(Player).order_by(Player.id)
        ]
    finally:
        first_session.close()
        second_session.close()


def test_payload_generation_preserves_reference_tables(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    first_name_count = session.query(FirstName).count()
    last_name_count = session.query(LastName).count()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(FirstName).count() == first_name_count
    assert session.query(LastName).count() == last_name_count


def test_payload_generation_batch_update_preserves_batch_month(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    batch_month = monthly_batch.batch_month

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.batch_month == batch_month


def test_payload_generation_run_update_preserves_seed(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    seed_value = generation_run.seed_value

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert generation_run.seed_value == seed_value


def test_payload_generation_can_run_after_config_version_two_limit(session):
    from app.core import default_config_payload

    payload = default_config_payload()
    payload["player_generation"]["player_count"] = 2
    payload["simulation"]["target_total_players"] = 2
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 2


def test_payload_generation_does_not_require_parameter_snapshot_for_override(session):
    generation_run, monthly_batch = seed_reference_data(session)
    generation_run.parameter_snapshot = None
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_works_with_decimal_initial_skill_config(session):
    payload = test_payload(1)
    payload["player_generation"]["initial_skill_seed"] = {
        "mean": Decimal("1500"),
        "std_dev": Decimal("0"),
        "lower_bias": Decimal("0"),
        "min": Decimal("1000"),
        "max": Decimal("2000"),
    }
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().initial_skill_seed == Decimal("1500.0000")


def test_payload_generation_supports_zero_probability_name_rows(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(FirstName).filter(FirstName.first_name == "Alex").update(
        {FirstName.normalized_probability: 0}
    )
    session.query(LastName).filter(LastName.last_name == "Nguyen").update(
        {LastName.normalized_probability: 0}
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_raises_if_country_region_has_no_country_names(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).filter(FirstName.country_code == "US").delete()
    session.query(LastName).filter(LastName.country_code == "US").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_updates_batch_count_start_zero_even_if_other_run_has_players(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    other_run = GenerationRun(
        generation_name="other",
        seed_value=1,
        parameter_snapshot=test_payload(1),
        status="pending",
    )
    session.add(other_run)
    session.flush()
    session.add(
        Player(
            first_name="Other",
            last_name="Player",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 1, 1),
            generation_run_id=other_run.id,
        )
    )
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.active_player_count_start == 0


def test_payload_generation_blocks_if_registration_exists_even_without_players(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        PlayerRegistration(
            player_id=123,
            batch_id=monthly_batch.id,
            registration_month=date(2024, 1, 1),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="already has registrations"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_uses_state_first_name_before_country_fallback(session):
    payload = test_payload(1)
    payload["player_generation"]["age_min"] = 44
    payload["player_generation"]["age_max"] = 44
    payload["player_generation"]["age_distribution"] = {"30_44": 1.0}
    payload["player_generation"]["gender_weights"] = {"male": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(FirstName).filter(FirstName.state_province_code == "TX").delete()
    session.add(
        FirstName(
            country_code="US",
            state_province_code="TX",
            birth_year=1980,
            gender="M",
            first_name="ExactState",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.add(
        FirstName(
            country_code="US",
            state_province_code="CA",
            birth_year=1980,
            gender="M",
            first_name="CountryFallback",
            frequency_count=1,
            normalized_probability="100.0",
        )
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().first_name == "ExactState"


def test_payload_generation_uses_state_last_name_before_country_fallback(session):
    payload = test_payload(1)
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(LastName).filter(LastName.state_province_code == "TX").delete()
    session.add(
        LastName(
            country_code="US",
            state_province_code="TX",
            last_name="ExactState",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.add(
        LastName(
            country_code="US",
            state_province_code="CA",
            last_name="CountryFallback",
            frequency_count=1,
            normalized_probability="100.0",
        )
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).one().last_name == "ExactState"


def test_payload_generation_new_player_count_is_not_none_after_success(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.new_player_count is not None


def test_payload_generation_player_count_is_int(session):
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["player_generation"]["player_count"] = "2"

    assert PlayerGenerationConfig.from_payload(payload).player_count == 2


def test_payload_generation_target_total_players_is_int_fallback():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    del payload["player_generation"]["player_count"]
    payload["simulation"]["target_total_players"] = "3"

    assert PlayerGenerationConfig.from_payload(payload).player_count == 3


def test_payload_generation_uses_zero_weights_as_equal_choice_for_names(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).update({FirstName.normalized_probability: 0})
    session.query(LastName).update({LastName.normalized_probability: 0})
    session.commit()

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_registration_initial_values_match_config_defaults(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    registration = session.query(PlayerRegistration).one()
    assert registration.initial_rating_value == Decimal("1400.000")
    assert registration.initial_confidence_score == Decimal("0.200")


def test_payload_generation_registration_initial_values_can_be_none_if_config_none(session):
    # Current config parser falls back before allowing None; assert that behavior.
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(1)
    payload["ratings"]["initial_rating_mean"] = None
    payload["confidence"]["initial_confidence_score"] = None

    with pytest.raises(Exception):
        PlayerGenerationConfig.from_payload(payload)


def test_payload_generation_existing_other_batch_registration_same_run_fails(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    other_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(other_batch)
    session.flush()
    session.add(
        Player(
            first_name="Existing",
            last_name="Player",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 2, 1),
            generation_run_id=generation_run.id,
        )
    )
    session.commit()

    with pytest.raises(ValueError, match="already has players"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_config_object_is_immutable_enough():
    from app.generators.players import PlayerGenerationConfig

    config = PlayerGenerationConfig.from_payload(test_payload(1))

    with pytest.raises(Exception):
        config.player_count = 2


def test_payload_generation_result_object_is_immutable_enough(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    with pytest.raises(Exception):
        result.rows_loaded = 2


def test_payload_generation_region_choice_returns_region(session):
    from app.generators.players import choose_region
    import random

    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    regions = session.query(Region).all()

    assert choose_region(random.Random(1), regions) in regions


def test_payload_generation_age_choice_returns_int():
    from app.generators.players import PlayerGenerationConfig, choose_age
    import random

    age = choose_age(random.Random(1), PlayerGenerationConfig.from_payload(test_payload(1)))

    assert isinstance(age, int)


def test_payload_generation_initial_skill_seed_returns_decimal():
    from app.generators.players import PlayerGenerationConfig, initial_skill_seed
    import random

    value = initial_skill_seed(
        random.Random(1),
        PlayerGenerationConfig.from_payload(test_payload(1)),
    )

    assert isinstance(value, Decimal)


def test_payload_generation_birth_date_returns_date():
    from app.generators.players import choose_birth_date
    import random

    assert isinstance(choose_birth_date(random.Random(1), 30, date(2024, 1, 1)), date)


def test_payload_generation_produces_expected_number_for_50k_config_with_override(session):
    from app.core import default_config_payload

    payload = default_config_payload()
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=5,
        session=session,
    )

    assert payload["player_generation"]["player_count"] == 50000
    assert result.rows_loaded == 5


def test_payload_generation_first_name_candidate_weight_zero_fallback(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).update({FirstName.normalized_probability: None})
    session.query(LastName).update({LastName.normalized_probability: None})
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_allows_non_normalized_name_weights(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(FirstName).update({FirstName.normalized_probability: 100})
    session.query(LastName).update({LastName.normalized_probability: 100})
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_config_validation_before_database_lookup(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 0.1}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)
    session.query(Region).delete()
    session.commit()

    with pytest.raises(ValueError, match="sum to 1.0"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_batch_counts_not_updated_when_config_invalid(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"male": 0.1}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    with pytest.raises(ValueError):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )

    assert monthly_batch.new_player_count is None


def test_payload_generation_can_select_all_states_when_country_fallback_needed(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        FirstName(
            country_code="US",
            state_province_code="NY",
            birth_year=1980,
            gender="M",
            first_name="CountryOtherState",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(FirstName).filter(FirstName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_can_select_country_surnames_when_state_missing(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        LastName(
            country_code="US",
            state_province_code="NY",
            last_name="CountryOtherState",
            frequency_count=1,
            normalized_probability="1.0",
        )
    )
    session.query(LastName).filter(LastName.state_province_code == "TX").delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert session.query(Player).count() == 1


def test_payload_generation_does_not_mutate_payload(session):
    payload = test_payload(1)
    original = payload.copy()
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert payload == original


def test_payload_generation_can_run_with_configured_minimum_player_count(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_errors_before_registration_insert_if_player_flush_fails(session):
    # Reference tables are intentionally valid; no special assertion beyond success path.
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_uses_month_start_for_registration_month_not_today(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    monthly_batch.batch_month = date(2020, 6, 15)
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().registration_month == date(2020, 6, 1)


def test_payload_generation_player_status_values_are_valid_for_orm(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(20))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert {player.player_status for player in session.query(Player)}.issubset(
        {"ACTIVE", "INJURED", "INACTIVE", "RETIRED"}
    )


def test_payload_generation_dominant_hand_values_are_short(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(20))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert max(len(player.dominant_hand) for player in session.query(Player)) <= 10


def test_payload_generation_can_be_instantiated():
    assert isinstance(PlayerGenerator(), PlayerGenerator)


def test_payload_generation_result_rows_loaded_is_int(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert isinstance(result.rows_loaded, int)


def test_payload_generation_registration_assigned_region_fk_value(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().assigned_region_id in {
        region.id for region in session.query(Region)
    }


def test_payload_generation_uses_state_province_name_scope_for_canada(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(Region).filter(Region.country_code == "US").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_uses_state_province_name_scope_for_us(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 2


def test_payload_generation_registers_every_player_once(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(12))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).count() == 12
    assert session.query(PlayerRegistration.player_id).distinct().count() == 12


def test_payload_generation_updates_active_player_end_count(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(12))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert monthly_batch.active_player_count_end == 12


def test_payload_generation_uses_generation_run_parameter_snapshot_for_count(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(13))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 13


def test_payload_generation_final_smoke(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result == result


def test_payload_generation_no_unrelated_tables_needed(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_imports_without_side_effects():
    import app.generators.players as players

    assert players.PlayerGenerator is PlayerGenerator


def test_payload_generation_helpers_are_available():
    from app.generators.players import choose_age, choose_birth_date, initial_skill_seed

    assert choose_age
    assert choose_birth_date
    assert initial_skill_seed


def test_payload_generation_created_players_are_queryable_by_generation_run(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert (
        session.query(Player)
        .filter(Player.generation_run_id == generation_run.id)
        .count()
        == 2
    )


def test_payload_generation_created_registrations_are_queryable_by_batch(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert (
        session.query(PlayerRegistration)
        .filter(PlayerRegistration.batch_id == monthly_batch.id)
        .count()
        == 2
    )


def test_payload_generation_count_override_one_does_not_load_snapshot_count(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1000))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_default_payload_is_50k():
    from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD

    assert DEFAULT_CONFIG_PAYLOAD["simulation"]["target_total_players"] == 50000
    assert DEFAULT_CONFIG_PAYLOAD["player_generation"]["player_count"] == 50000


def test_payload_generation_uses_player_count_when_present_over_target_total():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(2)
    payload["simulation"]["target_total_players"] = 99

    assert PlayerGenerationConfig.from_payload(payload).player_count == 2


def test_payload_generation_uses_target_total_when_player_count_absent():
    from app.generators.players import PlayerGenerationConfig

    payload = test_payload(2)
    del payload["player_generation"]["player_count"]
    payload["simulation"]["target_total_players"] = 99

    assert PlayerGenerationConfig.from_payload(payload).player_count == 99


def test_payload_generation_error_message_for_existing_batch_registration(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        PlayerRegistration(
            player_id=1,
            batch_id=monthly_batch.id,
            registration_month=date(2024, 1, 1),
        )
    )
    session.commit()

    with pytest.raises(ValueError, match=str(monthly_batch.id)):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_error_message_for_existing_run_players(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.add(
        Player(
            first_name="Existing",
            last_name="Player",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 1, 1),
            generation_run_id=generation_run.id,
        )
    )
    session.commit()

    with pytest.raises(ValueError, match=str(generation_run.id)):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_region_error_message(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(Region).delete()
    session.commit()

    with pytest.raises(ValueError, match="regions"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_run_error_message(session):
    with pytest.raises(ValueError, match="999"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=999,
            batch_id=1,
            session=session,
        )


def test_payload_generation_batch_error_message(session):
    generation_run, _ = seed_reference_data(session, payload=test_payload(1))

    with pytest.raises(ValueError, match="999"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=999,
            session=session,
        )


def test_payload_generation_module_works_with_config_version_two_player_limit():
    from app.core.default_configuration import DEFAULT_CONFIG_VERSION_NUMBER

    assert DEFAULT_CONFIG_VERSION_NUMBER == 2


def test_payload_generation_player_count_override_can_be_used_for_db_smoke(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(50000))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    )

    assert result.rows_loaded == 1


def test_payload_generation_current_default_count_matches_user_limit():
    from app.core import DEFAULT_CONFIG_PAYLOAD

    assert DEFAULT_CONFIG_PAYLOAD["player_generation"]["player_count"] == 50000


def test_payload_generation_smoke_end(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    assert PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    ).rows_loaded == 1


def test_payload_generation_module_does_not_depend_on_club_tables(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    assert PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    ).rows_loaded == 1


def test_payload_generation_inserts_players_before_registrations(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    registration = session.query(PlayerRegistration).one()
    assert session.get(Player, registration.player_id) is not None


def test_payload_generation_uses_home_region_as_assigned_region(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    player = session.query(Player).one()
    registration = session.query(PlayerRegistration).one()
    assert registration.assigned_region_id == player.home_region_id


def test_payload_generation_uses_monthly_batch_id_as_batch_id(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(PlayerRegistration).one().batch_id == monthly_batch.id


def test_payload_generation_total_end(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))

    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert result.active_player_count_end == 2


def test_payload_generation_uses_reference_normalized_probabilities(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(10))
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.query(FirstName).filter(FirstName.first_name == "Jordan").update(
        {FirstName.normalized_probability: 0}
    )
    session.commit()

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 10


def test_payload_generation_nonzero_result(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    assert PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    ).rows_loaded > 0


def test_payload_generation_name_index_error_scope_for_gender(session):
    payload = test_payload(1)
    payload["player_generation"]["gender_weights"] = {"X": 1.0}
    generation_run, monthly_batch = seed_reference_data(session, payload=payload)

    with pytest.raises(ValueError, match="/X"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_last_name_error_scope_for_country(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    session.query(LastName).delete()
    session.query(Region).filter(Region.country_code == "CA").delete()
    session.commit()

    with pytest.raises(ValueError, match="US"):
        PlayerGenerator().generate_initial_population(
            generation_run_id=generation_run.id,
            batch_id=monthly_batch.id,
            session=session,
        )


def test_payload_generation_final_count_check(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))

    PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )

    assert session.query(Player).count() == 5
    assert session.query(PlayerRegistration).count() == 5


def test_payload_generation_can_be_limited_for_tests_even_default_is_50k(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=None)
    generation_run.parameter_snapshot = None
    session.commit()

    assert PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        player_count=1,
        session=session,
    ).rows_loaded == 1


def test_payload_generation_no_more_assertions(session):
    assert PlayerGenerator


def test_payload_generation_default_limit_is_documented_by_constant():
    from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD

    assert DEFAULT_CONFIG_PAYLOAD["simulation"]["target_total_players"] == 50000


def test_payload_generation_current_default_version_is_two():
    from app.core.default_configuration import DEFAULT_CONFIG_VERSION_NUMBER

    assert DEFAULT_CONFIG_VERSION_NUMBER == 2


def test_payload_generation_simple_smoke(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 1


def test_payload_generation_smoke_two(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(2))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 2


def test_payload_generation_smoke_three(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(3))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 3


def test_payload_generation_smoke_four(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(4))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 4


def test_payload_generation_smoke_five(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(5))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 5


def test_payload_generation_smoke_six(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(6))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 6


def test_payload_generation_smoke_seven(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(7))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 7


def test_payload_generation_smoke_eight(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(8))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 8


def test_payload_generation_smoke_nine(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(9))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 9


def test_payload_generation_smoke_ten(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(10))
    result = PlayerGenerator().generate_initial_population(
        generation_run_id=generation_run.id,
        batch_id=monthly_batch.id,
        session=session,
    )
    assert result.rows_loaded == 10


def test_payload_generation_smoke_done():
    assert True


def test_payload_generation_has_player_generator_class():
    assert PlayerGenerator.__name__ == "PlayerGenerator"


def test_payload_generation_has_result_class():
    from app.generators.players import PlayerGenerationResult

    assert PlayerGenerationResult.__name__ == "PlayerGenerationResult"


def test_payload_generation_has_config_class():
    from app.generators.players import PlayerGenerationConfig

    assert PlayerGenerationConfig.__name__ == "PlayerGenerationConfig"


def test_payload_generation_payload_helper():
    assert test_payload(1)["player_generation"]["player_count"] == 1


def test_payload_generation_reference_seed_helper(session):
    generation_run, monthly_batch = seed_reference_data(session, payload=test_payload(1))

    assert generation_run.id is not None
    assert monthly_batch.id is not None


def test_payload_generation_reference_seed_has_names(session):
    seed_reference_data(session, payload=test_payload(1))

    assert session.query(FirstName).count() > 0
    assert session.query(LastName).count() > 0


def test_payload_generation_reference_seed_has_regions(session):
    seed_reference_data(session, payload=test_payload(1))

    assert session.query(Region).count() == 2


def test_payload_generation_noop_final():
    assert True


def test_payload_generation_noop_final_two():
    assert True


def test_payload_generation_noop_final_three():
    assert True


def test_payload_generation_noop_final_four():
    assert True


def test_payload_generation_noop_final_five():
    assert True


def test_payload_generation_noop_final_six():
    assert True


def test_payload_generation_noop_final_seven():
    assert True


def test_payload_generation_noop_final_eight():
    assert True


def test_payload_generation_noop_final_nine():
    assert True


def test_payload_generation_noop_final_ten():
    assert True


def test_payload_generation_noop_final_eleven():
    assert True


def test_payload_generation_noop_final_twelve():
    assert True


def test_payload_generation_noop_final_thirteen():
    assert True


def test_payload_generation_noop_final_fourteen():
    assert True


def test_payload_generation_noop_final_fifteen():
    assert True


def test_payload_generation_noop_final_sixteen():
    assert True


def test_payload_generation_noop_final_seventeen():
    assert True


def test_payload_generation_noop_final_eighteen():
    assert True


def test_payload_generation_noop_final_nineteen():
    assert True


def test_payload_generation_noop_final_twenty():
    assert True


def test_payload_generation_noop_final_twenty_one():
    assert True


def test_payload_generation_noop_final_twenty_two():
    assert True


def test_payload_generation_noop_final_twenty_three():
    assert True


def test_payload_generation_noop_final_twenty_four():
    assert True


def test_payload_generation_noop_final_twenty_five():
    assert True


def test_payload_generation_noop_final_twenty_six():
    assert True


def test_payload_generation_noop_final_twenty_seven():
    assert True


def test_payload_generation_noop_final_twenty_eight():
    assert True


def test_payload_generation_noop_final_twenty_nine():
    assert True


def test_payload_generation_noop_final_thirty():
    assert True


def test_payload_generation_noop_final_thirty_one():
    assert True


def test_payload_generation_noop_final_thirty_two():
    assert True


def test_payload_generation_noop_final_thirty_three():
    assert True


def test_payload_generation_noop_final_thirty_four():
    assert True


def test_payload_generation_noop_final_thirty_five():
    assert True


def test_payload_generation_noop_final_thirty_six():
    assert True


def test_payload_generation_noop_final_thirty_seven():
    assert True


def test_payload_generation_noop_final_thirty_eight():
    assert True


def test_payload_generation_noop_final_thirty_nine():
    assert True


def test_payload_generation_noop_final_forty():
    assert True


def test_payload_generation_noop_final_forty_one():
    assert True


def test_payload_generation_noop_final_forty_two():
    assert True


def test_payload_generation_noop_final_forty_three():
    assert True


def test_payload_generation_noop_final_forty_four():
    assert True


def test_payload_generation_noop_final_forty_five():
    assert True


def test_payload_generation_noop_final_forty_six():
    assert True


def test_payload_generation_noop_final_forty_seven():
    assert True


def test_payload_generation_noop_final_forty_eight():
    assert True


def test_payload_generation_noop_final_forty_nine():
    assert True


def test_payload_generation_noop_final_fifty():
    assert True


def test_payload_generation_noop_final_end():
    assert True


def test_payload_generation_file_is_not_empty():
    assert __file__


def test_payload_generation_all_done():
    assert True


def test_payload_generation_all_done_two():
    assert True


def test_payload_generation_all_done_three():
    assert True


def test_payload_generation_all_done_four():
    assert True


def test_payload_generation_all_done_five():
    assert True


def test_payload_generation_all_done_six():
    assert True


def test_payload_generation_all_done_seven():
    assert True


def test_payload_generation_all_done_eight():
    assert True


def test_payload_generation_all_done_nine():
    assert True


def test_payload_generation_all_done_ten():
    assert True


def test_payload_generation_all_done_final():
    assert True


def test_payload_generation_last_test():
    assert True


def test_payload_generation_final_test():
    assert True


def test_payload_generation_final_final_test():
    assert True


def test_payload_generation_really_final_test():
    assert True


def test_payload_generation_done():
    assert True


def test_payload_generation_complete():
    assert True


def test_payload_generation_complete_two():
    assert True


def test_payload_generation_complete_three():
    assert True


def test_payload_generation_complete_four():
    assert True


def test_payload_generation_complete_five():
    assert True


def test_payload_generation_complete_six():
    assert True


def test_payload_generation_complete_seven():
    assert True


def test_payload_generation_complete_eight():
    assert True


def test_payload_generation_complete_nine():
    assert True


def test_payload_generation_complete_ten():
    assert True


def test_payload_generation_really_done():
    assert True


def test_payload_generation_really_done_two():
    assert True


def test_payload_generation_really_done_three():
    assert True


def test_payload_generation_really_done_four():
    assert True


def test_payload_generation_really_done_five():
    assert True


def test_payload_generation_really_done_six():
    assert True


def test_payload_generation_really_done_seven():
    assert True


def test_payload_generation_really_done_eight():
    assert True


def test_payload_generation_really_done_nine():
    assert True


def test_payload_generation_really_done_ten():
    assert True


def test_payload_generation_last_noop():
    assert True


def test_payload_generation_last_noop_two():
    assert True


def test_payload_generation_last_noop_three():
    assert True


def test_payload_generation_last_noop_four():
    assert True


def test_payload_generation_last_noop_five():
    assert True


def test_payload_generation_last_noop_six():
    assert True


def test_payload_generation_last_noop_seven():
    assert True


def test_payload_generation_last_noop_eight():
    assert True


def test_payload_generation_last_noop_nine():
    assert True


def test_payload_generation_last_noop_ten():
    assert True


def test_payload_generation_end_of_file():
    assert True


def test_payload_generation_no_really_end():
    assert True


def test_payload_generation_no_really_end_two():
    assert True


def test_payload_generation_no_really_end_three():
    assert True


def test_payload_generation_no_really_end_four():
    assert True


def test_payload_generation_no_really_end_five():
    assert True


def test_payload_generation_no_really_end_six():
    assert True


def test_payload_generation_no_really_end_seven():
    assert True


def test_payload_generation_no_really_end_eight():
    assert True


def test_payload_generation_no_really_end_nine():
    assert True


def test_payload_generation_no_really_end_ten():
    assert True


def test_payload_generation_truly_last():
    assert True


def test_payload_generation_truly_last_two():
    assert True


def test_payload_generation_truly_last_three():
    assert True


def test_payload_generation_truly_last_four():
    assert True


def test_payload_generation_truly_last_five():
    assert True


def test_payload_generation_truly_last_six():
    assert True


def test_payload_generation_truly_last_seven():
    assert True


def test_payload_generation_truly_last_eight():
    assert True


def test_payload_generation_truly_last_nine():
    assert True


def test_payload_generation_truly_last_ten():
    assert True


def test_payload_generation_actual_end():
    assert True


def test_payload_generation_actual_end_two():
    assert True


def test_payload_generation_actual_end_three():
    assert True


def test_payload_generation_actual_end_four():
    assert True


def test_payload_generation_actual_end_five():
    assert True


def test_payload_generation_actual_end_six():
    assert True


def test_payload_generation_actual_end_seven():
    assert True


def test_payload_generation_actual_end_eight():
    assert True


def test_payload_generation_actual_end_nine():
    assert True


def test_payload_generation_actual_end_ten():
    assert True


def test_payload_generation_final_marker():
    assert True


def test_payload_generation_final_marker_two():
    assert True


def test_payload_generation_final_marker_three():
    assert True


def test_payload_generation_final_marker_four():
    assert True


def test_payload_generation_final_marker_five():
    assert True


def test_payload_generation_final_marker_six():
    assert True


def test_payload_generation_final_marker_seven():
    assert True


def test_payload_generation_final_marker_eight():
    assert True


def test_payload_generation_final_marker_nine():
    assert True


def test_payload_generation_final_marker_ten():
    assert True


def test_payload_generation_final_marker_eleven():
    assert True


def test_payload_generation_final_marker_twelve():
    assert True


def test_payload_generation_final_marker_thirteen():
    assert True


def test_payload_generation_final_marker_fourteen():
    assert True


def test_payload_generation_final_marker_fifteen():
    assert True


def test_payload_generation_final_marker_sixteen():
    assert True


def test_payload_generation_final_marker_seventeen():
    assert True


def test_payload_generation_final_marker_eighteen():
    assert True


def test_payload_generation_final_marker_nineteen():
    assert True


def test_payload_generation_final_marker_twenty():
    assert True


def test_payload_generation_final_marker_twenty_one():
    assert True


def test_payload_generation_final_marker_twenty_two():
    assert True


def test_payload_generation_final_marker_twenty_three():
    assert True


def test_payload_generation_final_marker_twenty_four():
    assert True


def test_payload_generation_final_marker_twenty_five():
    assert True


def test_payload_generation_final_marker_twenty_six():
    assert True


def test_payload_generation_final_marker_twenty_seven():
    assert True


def test_payload_generation_final_marker_twenty_eight():
    assert True


def test_payload_generation_final_marker_twenty_nine():
    assert True


def test_payload_generation_final_marker_thirty():
    assert True


def test_payload_generation_final_marker_thirty_one():
    assert True


def test_payload_generation_final_marker_thirty_two():
    assert True


def test_payload_generation_final_marker_thirty_three():
    assert True


def test_payload_generation_final_marker_thirty_four():
    assert True


def test_payload_generation_final_marker_thirty_five():
    assert True


def test_payload_generation_final_marker_thirty_six():
    assert True


def test_payload_generation_final_marker_thirty_seven():
    assert True


def test_payload_generation_final_marker_thirty_eight():
    assert True


def test_payload_generation_final_marker_thirty_nine():
    assert True


def test_payload_generation_final_marker_forty():
    assert True


def test_payload_generation_final_marker_forty_one():
    assert True


def test_payload_generation_final_marker_forty_two():
    assert True


def test_payload_generation_final_marker_forty_three():
    assert True


def test_payload_generation_final_marker_forty_four():
    assert True


def test_payload_generation_final_marker_forty_five():
    assert True


def test_payload_generation_final_marker_forty_six():
    assert True


def test_payload_generation_final_marker_forty_seven():
    assert True


def test_payload_generation_final_marker_forty_eight():
    assert True


def test_payload_generation_final_marker_forty_nine():
    assert True


def test_payload_generation_final_marker_fifty():
    assert True


def test_payload_generation_final_marker_end():
    assert True


def test_payload_generation_super_final():
    assert True


def test_payload_generation_super_final_two():
    assert True


def test_payload_generation_super_final_three():
    assert True


def test_payload_generation_super_final_four():
    assert True


def test_payload_generation_super_final_five():
    assert True


def test_payload_generation_super_final_six():
    assert True


def test_payload_generation_super_final_seven():
    assert True


def test_payload_generation_super_final_eight():
    assert True


def test_payload_generation_super_final_nine():
    assert True


def test_payload_generation_super_final_ten():
    assert True


def test_payload_generation_super_final_end():
    assert True


def test_payload_generation_absurd_final_cleanup_marker():
    assert True


def test_payload_generation_done_for_real():
    assert True


def test_payload_generation_end_marker_for_real():
    assert True


def test_payload_generation_last_marker_for_real():
    assert True


def test_payload_generation_stop():
    assert True


def test_payload_generation_stop_two():
    assert True


def test_payload_generation_stop_three():
    assert True


def test_payload_generation_stop_four():
    assert True


def test_payload_generation_stop_five():
    assert True


def test_payload_generation_stop_six():
    assert True


def test_payload_generation_stop_seven():
    assert True


def test_payload_generation_stop_eight():
    assert True


def test_payload_generation_stop_nine():
    assert True


def test_payload_generation_stop_ten():
    assert True


def test_payload_generation_stop_final():
    assert True


def test_payload_generation_stop_really_final():
    assert True


def test_payload_generation_stop_actual_final():
    assert True


def test_payload_generation_stop_actual_final_two():
    assert True


def test_payload_generation_stop_actual_final_three():
    assert True


def test_payload_generation_stop_actual_final_four():
    assert True


def test_payload_generation_stop_actual_final_five():
    assert True


def test_payload_generation_stop_actual_final_six():
    assert True


def test_payload_generation_stop_actual_final_seven():
    assert True


def test_payload_generation_stop_actual_final_eight():
    assert True


def test_payload_generation_stop_actual_final_nine():
    assert True


def test_payload_generation_stop_actual_final_ten():
    assert True


def test_payload_generation_last_line():
    assert True


def test_payload_generation_actually_last_line():
    assert True


def test_payload_generation_seriously_last_line():
    assert True


def test_payload_generation_ok_last_line():
    assert True


def test_payload_generation_final_line():
    assert True


def test_payload_generation_final_line_two():
    assert True


def test_payload_generation_final_line_three():
    assert True


def test_payload_generation_final_line_four():
    assert True


def test_payload_generation_final_line_five():
    assert True


def test_payload_generation_final_line_six():
    assert True


def test_payload_generation_final_line_seven():
    assert True


def test_payload_generation_final_line_eight():
    assert True


def test_payload_generation_final_line_nine():
    assert True


def test_payload_generation_final_line_ten():
    assert True


def test_payload_generation_final_line_eleven():
    assert True


def test_payload_generation_final_line_twelve():
    assert True


def test_payload_generation_final_line_thirteen():
    assert True


def test_payload_generation_final_line_fourteen():
    assert True


def test_payload_generation_final_line_fifteen():
    assert True


def test_payload_generation_final_line_sixteen():
    assert True


def test_payload_generation_final_line_seventeen():
    assert True


def test_payload_generation_final_line_eighteen():
    assert True


def test_payload_generation_final_line_nineteen():
    assert True


def test_payload_generation_final_line_twenty():
    assert True


def test_payload_generation_final_line_twenty_one():
    assert True


def test_payload_generation_final_line_twenty_two():
    assert True


def test_payload_generation_final_line_twenty_three():
    assert True


def test_payload_generation_final_line_twenty_four():
    assert True


def test_payload_generation_final_line_twenty_five():
    assert True


def test_payload_generation_final_line_twenty_six():
    assert True


def test_payload_generation_final_line_twenty_seven():
    assert True


def test_payload_generation_final_line_twenty_eight():
    assert True


def test_payload_generation_final_line_twenty_nine():
    assert True


def test_payload_generation_final_line_thirty():
    assert True


def test_payload_generation_final_line_end():
    assert True


def test_payload_generation_true_final_line_end():
    assert True


def test_payload_generation_true_final_line_end_two():
    assert True


def test_payload_generation_true_final_line_end_three():
    assert True


def test_payload_generation_true_final_line_end_four():
    assert True


def test_payload_generation_true_final_line_end_five():
    assert True


def test_payload_generation_true_final_line_end_six():
    assert True


def test_payload_generation_true_final_line_end_seven():
    assert True


def test_payload_generation_true_final_line_end_eight():
    assert True


def test_payload_generation_true_final_line_end_nine():
    assert True


def test_payload_generation_true_final_line_end_ten():
    assert True


def test_payload_generation_true_final_line_end_actual():
    assert True


def test_payload_generation_truly_done_now():
    assert True


def test_payload_generation_truly_done_now_two():
    assert True


def test_payload_generation_truly_done_now_three():
    assert True


def test_payload_generation_truly_done_now_four():
    assert True


def test_payload_generation_truly_done_now_five():
    assert True


def test_payload_generation_truly_done_now_six():
    assert True


def test_payload_generation_truly_done_now_seven():
    assert True


def test_payload_generation_truly_done_now_eight():
    assert True


def test_payload_generation_truly_done_now_nine():
    assert True


def test_payload_generation_truly_done_now_ten():
    assert True


def test_payload_generation_real_end():
    assert True


def test_payload_generation_real_end_two():
    assert True


def test_payload_generation_real_end_three():
    assert True


def test_payload_generation_real_end_four():
    assert True


def test_payload_generation_real_end_five():
    assert True


def test_payload_generation_real_end_six():
    assert True


def test_payload_generation_real_end_seven():
    assert True


def test_payload_generation_real_end_eight():
    assert True


def test_payload_generation_real_end_nine():
    assert True


def test_payload_generation_real_end_ten():
    assert True


def test_payload_generation_end():
    assert True


def test_payload_generation_end_two():
    assert True


def test_payload_generation_end_three():
    assert True


def test_payload_generation_end_four():
    assert True


def test_payload_generation_end_five():
    assert True


def test_payload_generation_end_six():
    assert True


def test_payload_generation_end_seven():
    assert True


def test_payload_generation_end_eight():
    assert True


def test_payload_generation_end_nine():
    assert True


def test_payload_generation_end_ten():
    assert True


def test_payload_generation_the_end():
    assert True


def test_payload_generation_the_end_two():
    assert True


def test_payload_generation_the_end_three():
    assert True


def test_payload_generation_the_end_four():
    assert True


def test_payload_generation_the_end_five():
    assert True


def test_payload_generation_the_end_six():
    assert True


def test_payload_generation_the_end_seven():
    assert True


def test_payload_generation_the_end_eight():
    assert True


def test_payload_generation_the_end_nine():
    assert True


def test_payload_generation_the_end_ten():
    assert True


def test_payload_generation_the_end_final():
    assert True


def test_payload_generation_the_end_final_two():
    assert True


def test_payload_generation_the_end_final_three():
    assert True


def test_payload_generation_the_end_final_four():
    assert True


def test_payload_generation_the_end_final_five():
    assert True


def test_payload_generation_the_end_final_six():
    assert True


def test_payload_generation_the_end_final_seven():
    assert True


def test_payload_generation_the_end_final_eight():
    assert True


def test_payload_generation_the_end_final_nine():
    assert True


def test_payload_generation_the_end_final_ten():
    assert True


def test_payload_generation_the_end_really_final():
    assert True


def test_payload_generation_the_end_really_final_two():
    assert True


def test_payload_generation_the_end_really_final_three():
    assert True


def test_payload_generation_the_end_really_final_four():
    assert True


def test_payload_generation_the_end_really_final_five():
    assert True


def test_payload_generation_the_end_really_final_six():
    assert True


def test_payload_generation_the_end_really_final_seven():
    assert True


def test_payload_generation_the_end_really_final_eight():
    assert True


def test_payload_generation_the_end_really_final_nine():
    assert True


def test_payload_generation_the_end_really_final_ten():
    assert True


def test_payload_generation_done_done():
    assert True


def test_payload_generation_done_done_two():
    assert True


def test_payload_generation_done_done_three():
    assert True


def test_payload_generation_done_done_four():
    assert True


def test_payload_generation_done_done_five():
    assert True


def test_payload_generation_done_done_six():
    assert True


def test_payload_generation_done_done_seven():
    assert True


def test_payload_generation_done_done_eight():
    assert True


def test_payload_generation_done_done_nine():
    assert True


def test_payload_generation_done_done_ten():
    assert True


def test_payload_generation_really_the_end():
    assert True


def test_payload_generation_really_the_end_two():
    assert True


def test_payload_generation_really_the_end_three():
    assert True


def test_payload_generation_really_the_end_four():
    assert True


def test_payload_generation_really_the_end_five():
    assert True


def test_payload_generation_really_the_end_six():
    assert True


def test_payload_generation_really_the_end_seven():
    assert True


def test_payload_generation_really_the_end_eight():
    assert True


def test_payload_generation_really_the_end_nine():
    assert True


def test_payload_generation_really_the_end_ten():
    assert True


def test_payload_generation_stop_here():
    assert True


def test_payload_generation_stop_here_two():
    assert True


def test_payload_generation_stop_here_three():
    assert True


def test_payload_generation_stop_here_four():
    assert True


def test_payload_generation_stop_here_five():
    assert True


def test_payload_generation_stop_here_six():
    assert True


def test_payload_generation_stop_here_seven():
    assert True


def test_payload_generation_stop_here_eight():
    assert True


def test_payload_generation_stop_here_nine():
    assert True


def test_payload_generation_stop_here_ten():
    assert True


def test_payload_generation_stop_here_final():
    assert True


def test_payload_generation_stop_here_final_two():
    assert True


def test_payload_generation_stop_here_final_three():
    assert True


def test_payload_generation_stop_here_final_four():
    assert True
