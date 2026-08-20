#!/usr/bin/env python3
"""API endpoint tests for server.py"""

import json
import tempfile
from pathlib import Path

import pytest

# Import Flask app and setup for testing
import server


@pytest.fixture(autouse=True)
def isolated_state_files(tmp_path, monkeypatch):
    """Point the on-disk state and queue at a temp dir.

    Without this the suite posts into the real state.json and queue.json next to
    server.py, writing test fixtures such as "/path/to/video.mp4" into the
    user's actual watch history.
    """
    monkeypatch.setattr(server, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(server, "QUEUE_FILE", tmp_path / "queue.json")


@pytest.fixture(autouse=True)
def reset_catalogs():
    """Empty the catalog globals before each test and restore them after."""
    names = ("LIBRARY_CATALOG", "ROUTE_MAP", "VIDEO_INDEX")
    originals = {name: dict(getattr(server, name)) for name in names}
    for name in names:
        getattr(server, name).clear()

    yield

    for name, original in originals.items():
        container = getattr(server, name)
        container.clear()
        container.update(original)


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    server.app.config["TESTING"] = True
    with server.app.test_client() as client:
        yield client


@pytest.fixture
def app_context():
    """Provide Flask app context for tests."""
    with server.app.app_context():
        yield


SEASON_CATALOG = [
    {"title": "Test Episode 1", "source": "/path/to/video1.mp4", "grids": ["grid_01.jpg"]},
    {"title": "Test Episode 2", "source": "/path/to/video2.mp4", "grids": ["grid_01.jpg", "grid_02.jpg"]},
]
MOVIE_CATALOG = [
    {"title": "Test Movie", "source": "/path/to/movie.mp4", "grids": []},
]


@pytest.fixture
def library(tmp_path):
    """Seed a catalog with one show season and one movie, and build its routes."""
    season_dir = tmp_path / "Season 1"
    season_dir.mkdir()
    movie_dir = tmp_path / "The Movie"
    movie_dir.mkdir()

    server.LIBRARY_CATALOG["shows"] = {
        "test-show": {
            "name": "Test Show",
            "path": tmp_path,
            "seasons": {
                "season-1": {
                    "name": "Season 1",
                    "path": season_dir,
                    "catalog": SEASON_CATALOG,
                    "poster": None,
                }
            },
        }
    }
    server.LIBRARY_CATALOG["movies"] = {
        "test-series": {
            "name": "Test Series",
            "path": tmp_path,
            "movies": {
                "the-movie": {
                    "name": "The Movie",
                    "path": movie_dir,
                    "catalog": MOVIE_CATALOG,
                }
            },
        }
    }
    server.build_route_map()
    return server.LIBRARY_CATALOG


class TestSeasonVideoAPI:
    """Tests for /api/shows/<series_key>/<season_key>/videos."""

    def test_returns_cached_catalog(self, client, app_context, library):
        """The endpoint serves the in-memory catalog."""
        response = client.get("/api/shows/test-show/season-1/videos")

        assert response.status_code == 200
        assert json.loads(response.data) == SEASON_CATALOG

    def test_returns_json_content_type(self, client, app_context, library):
        """Response has the correct Content-Type."""
        response = client.get("/api/shows/test-show/season-1/videos")

        assert response.content_type == "application/json"

    def test_unknown_series_returns_404(self, client, app_context, library):
        """An unknown series key is a 404."""
        response = client.get("/api/shows/nope/season-1/videos")

        assert response.status_code == 404

    def test_unknown_season_returns_404(self, client, app_context, library):
        """An unknown season key is a 404."""
        response = client.get("/api/shows/test-show/season-99/videos")

        assert response.status_code == 404


class TestMovieVideoAPI:
    """Tests for /api/movies/<series_key>/<movie_key>/videos."""

    def test_returns_cached_catalog(self, client, app_context, library):
        """The endpoint serves the in-memory catalog."""
        response = client.get("/api/movies/test-series/the-movie/videos")

        assert response.status_code == 200
        assert json.loads(response.data) == MOVIE_CATALOG

    def test_unknown_movie_returns_404(self, client, app_context, library):
        """An unknown movie key is a 404."""
        response = client.get("/api/movies/test-series/nope/videos")

        assert response.status_code == 404


class TestStateAPI:
    """Tests for /api/state endpoints."""

    def test_api_get_state_returns_json(self, client, app_context):
        """GET /api/state returns JSON."""
        response = client.get("/api/state")

        assert response.status_code == 200
        assert response.content_type == "application/json"

    def test_api_get_state_valid_response(self, client, app_context):
        """GET /api/state returns valid JSON object."""
        response = client.get("/api/state")
        data = json.loads(response.data)

        # Should be a dict (even if empty)
        assert isinstance(data, dict)

    def test_api_post_state_requires_source(self, client, app_context):
        """POST /api/state without source returns 400."""
        response = client.post("/api/state", json={"watched": True})

        assert response.status_code == 400

    def test_api_post_state_with_watched(self, client, app_context):
        """POST /api/state with watched flag returns the updated entry."""
        response = client.post(
            "/api/state",
            json={"source": "/path/to/video.mp4", "watched": True},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert json.loads(response.data) == {"watched": True}

    def test_api_post_state_with_progress(self, client, app_context):
        """POST /api/state with progress returns the updated entry."""
        response = client.post(
            "/api/state",
            json={"source": "/path/to/video.mp4", "progress": 123.45},
            content_type="application/json",
        )

        assert response.status_code == 200
        assert json.loads(response.data) == {"progress": 123.45}

    def test_clearing_every_field_drops_the_entry(self, client, app_context):
        """An entry with nothing left in it is removed from state."""
        client.post("/api/state", json={"source": "/a.mp4", "watched": True})
        client.post("/api/state", json={"source": "/a.mp4", "watched": False})

        state = json.loads(client.get("/api/state").data)
        assert "/a.mp4" not in state


class TestPlayCount:
    """Tests for the play counter on /api/state."""

    def post(self, client, **body):
        return json.loads(
            client.post("/api/state", json=body, content_type="application/json").data
        )

    def test_first_completion_counts_once(self, client, app_context):
        """Finishing a fresh video records exactly one play, not two."""
        entry = self.post(client, source="/a.mp4", progress=None, watched=True, played=True)

        assert entry == {"watched": True, "plays": 1}

    def test_counter_increments(self, client, app_context):
        """Each completion adds one."""
        for _ in range(3):
            entry = self.post(client, source="/a.mp4", watched=True, played=True)

        assert entry["plays"] == 3

    def test_legacy_watched_entry_counts_as_one_prior_play(self, client, app_context):
        """A video watched before the counter existed is treated as seen once."""
        self.post(client, source="/a.mp4", watched=True)  # no plays field

        entry = self.post(client, source="/a.mp4", watched=True, played=True)

        assert entry["plays"] == 2

    def test_progress_updates_preserve_the_count(self, client, app_context):
        """Saving a resume point does not disturb the tally."""
        self.post(client, source="/a.mp4", watched=True, played=True)

        entry = self.post(client, source="/a.mp4", progress=42.0)

        assert entry["plays"] == 1
        assert entry["progress"] == 42.0

    def test_reset_plays_clears_the_count(self, client, app_context):
        """resetPlays drops the tally."""
        self.post(client, source="/a.mp4", watched=True, played=True)

        entry = self.post(client, source="/a.mp4", resetPlays=True)

        assert "plays" not in entry

    def test_unwatch_and_reset_together_drop_the_entry(self, client, app_context):
        """One request can clear the flag and the tally, leaving nothing behind."""
        self.post(client, source="/a.mp4", watched=True, played=True)

        entry = self.post(client, source="/a.mp4", watched=False, resetPlays=True)

        assert entry == {}


class TestQueueAPI:
    """Tests for /api/queue."""

    def put(self, client, sources):
        return client.put(
            "/api/queue", json={"sources": sources}, content_type="application/json"
        )

    def test_queue_starts_empty(self, client, app_context, library):
        """A fresh queue is an empty list."""
        response = client.get("/api/queue")

        assert response.status_code == 200
        assert json.loads(response.data) == []

    def test_put_returns_hydrated_videos(self, client, app_context, library):
        """Stored source paths come back as full video objects."""
        response = self.put(client, ["/path/to/video2.mp4"])

        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data) == 1
        assert data[0]["title"] == "Test Episode 2"
        assert data[0]["collection"] == "Test Show · Season 1"

    def test_queue_spans_shows_and_movies(self, client, app_context, library):
        """One queue can hold entries from different collections."""
        data = json.loads(
            self.put(client, ["/path/to/video1.mp4", "/path/to/movie.mp4"]).data
        )

        assert [v["collection"] for v in data] == [
            "Test Show · Season 1",
            "Test Series · The Movie",
        ]

    def test_order_is_preserved(self, client, app_context, library):
        """The queue keeps the order it was given."""
        data = json.loads(
            self.put(client, ["/path/to/video2.mp4", "/path/to/video1.mp4"]).data
        )

        assert [v["title"] for v in data] == ["Test Episode 2", "Test Episode 1"]

    def test_unknown_sources_are_rejected(self, client, app_context, library):
        """Paths outside the catalog never reach the stored queue."""
        data = json.loads(self.put(client, ["/etc/passwd", "/path/to/video1.mp4"]).data)

        assert [v["source"] for v in data] == ["/path/to/video1.mp4"]

    def test_duplicates_are_collapsed(self, client, app_context, library):
        """The same video cannot be queued twice."""
        data = json.loads(
            self.put(client, ["/path/to/video1.mp4", "/path/to/video1.mp4"]).data
        )

        assert len(data) == 1

    def test_empty_list_clears_the_queue(self, client, app_context, library):
        """Putting an empty list empties the queue."""
        self.put(client, ["/path/to/video1.mp4"])

        assert json.loads(self.put(client, []).data) == []

    def test_non_list_body_returns_400(self, client, app_context, library):
        """A malformed body is rejected."""
        response = client.put(
            "/api/queue", json={"sources": "nope"}, content_type="application/json"
        )

        assert response.status_code == 400

    def test_missing_sources_key_returns_400(self, client, app_context, library):
        """A body without sources is rejected."""
        response = client.put("/api/queue", json={}, content_type="application/json")

        assert response.status_code == 400

    def test_queue_persists_across_requests(self, client, app_context, library):
        """What was put is what comes back."""
        self.put(client, ["/path/to/video1.mp4"])

        data = json.loads(client.get("/api/queue").data)
        assert [v["source"] for v in data] == ["/path/to/video1.mp4"]

    def test_entries_missing_from_the_catalog_are_pruned(self, client, app_context, library):
        """A video that left the catalog is dropped from the queue on read."""
        self.put(client, ["/path/to/video1.mp4", "/path/to/video2.mp4"])
        del server.VIDEO_INDEX["/path/to/video1.mp4"]

        data = json.loads(client.get("/api/queue").data)

        assert [v["source"] for v in data] == ["/path/to/video2.mp4"]


class TestPosters:
    """Tests for season poster discovery."""

    def test_finds_poster_by_name(self, tmp_path):
        """Any image with 'poster' in its name is picked up."""
        (tmp_path / "paw_patrol_season_1_poster.webp").write_bytes(b"x")
        (tmp_path / "episode.mp4").write_bytes(b"x")

        assert server.find_poster(tmp_path).endswith("paw_patrol_season_1_poster.webp")

    def test_ignores_non_images(self, tmp_path):
        """A non-image named poster is not used."""
        (tmp_path / "poster.txt").write_bytes(b"x")

        assert server.find_poster(tmp_path) is None

    def test_returns_none_without_a_poster(self, tmp_path):
        """A season without artwork simply has none."""
        (tmp_path / "episode.mp4").write_bytes(b"x")

        assert server.find_poster(tmp_path) is None

    def test_seasons_page_includes_the_poster(self, client, library, tmp_path):
        """The poster path reaches the season picker."""
        season = server.LIBRARY_CATALOG["shows"]["test-show"]["seasons"]["season-1"]
        season["poster"] = "/path/to/poster.webp"

        response = client.get("/shows/test-show")

        assert response.status_code == 200
        assert b"/path/to/poster.webp" in response.data


class TestImageAPI:
    """Tests for /images/<filename> endpoint."""

    def test_images_file_requires_valid_path(self, client):
        """GET /images/<filename> with path traversal returns 403 or 404."""
        response = client.get("/images/../../../etc/passwd")

        # Path traversal attempts should not succeed (403 if caught by path check, 404 if file not found)
        assert response.status_code in (403, 404)

    def test_images_nonexistent_file_returns_404(self, client):
        """GET /images/<filename> for nonexistent file returns 404."""
        response = client.get("/images/nonexistent.jpg")

        assert response.status_code == 404


class TestMediaAPI:
    """Tests for /media path scoping."""

    def test_path_outside_the_library_is_forbidden(self, client, library):
        """Serving is scoped to the configured directories."""
        response = client.get("/media?path=/etc/passwd")

        assert response.status_code == 403

    def test_missing_file_inside_the_library_is_404(self, client, library, tmp_path):
        """A path inside the library that does not exist is a 404, not a 403."""
        missing = tmp_path / "Season 1" / "nope.jpg"

        response = client.get(f"/media?path={missing}")

        assert response.status_code == 404


class TestUIRoutes:
    """Tests for UI routes."""

    def test_home_route_status(self, client):
        """GET / returns 200 status."""
        response = client.get("/")

        assert response.status_code == 200

    def test_home_route_returns_html(self, client):
        """GET / returns HTML content."""
        response = client.get("/")

        assert b"<!DOCTYPE" in response.data or b"<html" in response.data

    def test_shows_list_route(self, client, library):
        """GET /shows lists the shows."""
        response = client.get("/shows")

        assert response.status_code == 200
        assert b"Test Show" in response.data

    def test_season_picker_route(self, client, library):
        """GET /shows/<series_key> lists the seasons."""
        response = client.get("/shows/test-show")

        assert response.status_code == 200
        assert b"Season 1" in response.data

    def test_season_videos_route(self, client, library):
        """GET /shows/<series_key>/<season_key> renders the player page."""
        response = client.get("/shows/test-show/season-1")

        assert response.status_code == 200
        assert b"<!DOCTYPE" in response.data

    def test_unknown_series_returns_404(self, client, library):
        """An unknown series is a 404."""
        response = client.get("/shows/nope")

        assert response.status_code == 404

    def test_movies_routes(self, client, library):
        """The movie picker and movie page both render."""
        assert client.get("/movies").status_code == 200
        assert client.get("/movies/test-series").status_code == 200
        assert client.get("/movies/test-series/the-movie").status_code == 200


class TestCachingIntegration:
    """Integration tests verifying caching behavior."""

    def test_api_calls_use_cached_data_not_filesystem(self, client, app_context, library, monkeypatch):
        """
        Verify that API calls return cached catalogs without accessing filesystem.

        This tests the core tech debt fix: that load_all_metadata is not called
        on every API request.
        """
        def fail(*args, **kwargs):
            raise AssertionError("load_all_metadata should not run on a request")

        monkeypatch.setattr(server, "load_all_metadata", fail)

        data1 = json.loads(client.get("/api/shows/test-show/season-1/videos").data)
        data2 = json.loads(client.get("/api/shows/test-show/season-1/videos").data)

        assert data1 == data2 == SEASON_CATALOG


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
