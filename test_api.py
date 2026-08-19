#!/usr/bin/env python3
"""API endpoint tests for server.py"""

import json
import tempfile
from pathlib import Path

import pytest

# Import Flask app and setup for testing
import server


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


class TestVideoAPI:
    """Tests for /api/videos endpoint."""

    def test_api_videos_returns_cached_catalog(self, client, app_context):
        """GET /api/videos returns the cached VIDEO_CATALOG."""
        # Set up mock catalog
        test_catalog = [
            {
                "title": "Test Episode 1",
                "source": "/path/to/video1.mp4",
                "grids": ["grid_01.jpg"],
            },
            {
                "title": "Test Episode 2",
                "source": "/path/to/video2.mp4",
                "grids": ["grid_01.jpg", "grid_02.jpg"],
            },
        ]
        server.VIDEO_CATALOG = test_catalog
        
        response = client.get("/api/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == test_catalog

    def test_api_videos_returns_empty_list_initially(self, client, app_context):
        """GET /api/videos returns empty list when catalog is empty."""
        server.VIDEO_CATALOG = []
        
        response = client.get("/api/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []

    def test_api_videos_returns_json(self, client, app_context):
        """GET /api/videos response has correct Content-Type."""
        server.VIDEO_CATALOG = []
        
        response = client.get("/api/videos")
        
        assert response.content_type == "application/json"


class TestAboveBeyondS03API:
    """Tests for /api/above-and-beyond/s03/videos endpoint."""

    def test_api_s03_videos_returns_cached_catalog(self, client, app_context):
        """GET /api/above-and-beyond/s03/videos returns ABOVE_BEYOND_S03_CATALOG."""
        test_catalog = [
            {
                "title": "Pininga Turtle",
                "source": "/path/to/s03_01.mkv",
                "grids": [],
            }
        ]
        server.ABOVE_BEYOND_S03_CATALOG = test_catalog
        
        response = client.get("/api/above-and-beyond/s03/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == test_catalog

    def test_api_s03_videos_returns_empty_list(self, client, app_context):
        """GET /api/above-and-beyond/s03/videos returns empty list when empty."""
        server.ABOVE_BEYOND_S03_CATALOG = []
        
        response = client.get("/api/above-and-beyond/s03/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []


class TestAboveBeyondS04API:
    """Tests for /api/above-and-beyond/s04/videos endpoint."""

    def test_api_s04_videos_returns_cached_catalog(self, client, app_context):
        """GET /api/above-and-beyond/s04/videos returns ABOVE_BEYOND_S04_CATALOG."""
        test_catalog = [
            {
                "title": "Billabong Mystery",
                "source": "/path/to/s04_23.mkv",
                "grids": [],
            }
        ]
        server.ABOVE_BEYOND_S04_CATALOG = test_catalog
        
        response = client.get("/api/above-and-beyond/s04/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == test_catalog

    def test_api_s04_videos_returns_empty_list(self, client, app_context):
        """GET /api/above-and-beyond/s04/videos returns empty list when empty."""
        server.ABOVE_BEYOND_S04_CATALOG = []
        
        response = client.get("/api/above-and-beyond/s04/videos")
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data == []


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
        """POST /api/state with watched flag succeeds."""
        response = client.post(
            "/api/state",
            json={"source": "/path/to/video.mp4", "watched": True},
            content_type="application/json",
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get("ok") is True

    def test_api_post_state_with_progress(self, client, app_context):
        """POST /api/state with progress value succeeds."""
        response = client.post(
            "/api/state",
            json={"source": "/path/to/video.mp4", "progress": 123.45},
            content_type="application/json",
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get("ok") is True


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

    def test_above_and_beyond_route_status(self, client):
        """GET /above-and-beyond returns 200 status."""
        response = client.get("/above-and-beyond")
        
        assert response.status_code == 200

    def test_above_and_beyond_s03_route_status(self, client):
        """GET /above-and-beyond/s03 returns 200 status."""
        response = client.get("/above-and-beyond/s03")
        
        assert response.status_code == 200

    def test_above_and_beyond_s04_route_status(self, client):
        """GET /above-and-beyond/s04 returns 200 status."""
        response = client.get("/above-and-beyond/s04")
        
        assert response.status_code == 200


class TestCachingIntegration:
    """Integration tests verifying caching behavior."""

    def test_api_calls_use_cached_data_not_filesystem(self, client, app_context):
        """
        Verify that API calls return cached catalogs without accessing filesystem.
        
        This tests the core tech debt fix: that load_all_metadata is not called
        on every API request.
        """
        test_catalog = [{"title": "Cached", "source": "test.mp4", "grids": []}]
        server.VIDEO_CATALOG = test_catalog
        
        # First call
        response1 = client.get("/api/videos")
        data1 = json.loads(response1.data)
        
        # Second call - should still get same data
        response2 = client.get("/api/videos")
        data2 = json.loads(response2.data)
        
        assert data1 == data2 == test_catalog


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
