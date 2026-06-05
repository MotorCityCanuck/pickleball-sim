"""Route registration tests for tournament API endpoints."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.web.routes import (  # noqa: E402
    _student_groups_from_payload,
    _team_submissions_from_payload,
    build_control_panel_router,
)


def test_tournament_api_routes_are_registered():
    router = build_control_panel_router()
    route_map = {
        (next(iter(route.methods)), route.path)
        for route in router.routes
        if "tournaments" in route.path
    }

    assert ("POST", "/control/tournaments/events") in route_map
    assert ("POST", "/control/tournaments/{event_id}/validate") in route_map
    assert ("POST", "/control/tournaments/{event_id}/monte-carlo/start") in route_map
    assert ("POST", "/control/tournaments/{event_id}/official/start") in route_map
    assert ("GET", "/control/tournaments/{event_id}/summary") in route_map
    assert (
        "GET",
        "/control/tournaments/official-matches/{official_match_id}",
    ) in route_map


def test_tournament_event_payload_helpers_parse_groups_and_submissions():
    payload = {
        "student_groups": [{"id": 1, "name": "Group 1"}],
        "submissions": [
            {
                "group_id": 1,
                "country_code": "US",
                "division": "mens_doubles",
                "team_id": 10,
            }
        ],
    }

    groups = _student_groups_from_payload(payload)
    submissions = _team_submissions_from_payload(payload)

    assert groups[0].id == 1
    assert groups[0].name == "Group 1"
    assert submissions[0].group_id == 1
    assert submissions[0].slot.country_code == "US"
    assert submissions[0].slot.division == "mens_doubles"
    assert submissions[0].team_id == 10
