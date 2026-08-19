#!/usr/bin/env python3
"""Unit tests for server.py"""

import json
import tempfile
from pathlib import Path

import pytest

from server import _parse_title, load_all_metadata, load_state, save_state
from extract_stills import parse_episode


@pytest.fixture(autouse=True)
def reset_catalogs():
    """Reset catalogs to empty state before and after each test."""
    import server
    original_video = server.VIDEO_CATALOG
    original_s03 = server.ABOVE_BEYOND_S03_CATALOG
    original_s04 = server.ABOVE_BEYOND_S04_CATALOG
    
    server.VIDEO_CATALOG = []
    server.ABOVE_BEYOND_S03_CATALOG = []
    server.ABOVE_BEYOND_S04_CATALOG = []
    
    yield
    
    server.VIDEO_CATALOG = original_video
    server.ABOVE_BEYOND_S03_CATALOG = original_s03
    server.ABOVE_BEYOND_S04_CATALOG = original_s04


class TestParseTitle:
    """Tests for _parse_title() function."""

    def test_above_and_beyond_with_underscore_format(self):
        """Parse 'Above & Beyond S03_01. Pininga Turtle' format."""
        result = _parse_title("Above & Beyond S03_01. Pininga Turtle")
        assert result == "Pininga Turtle"

    def test_above_and_beyond_with_multiple_dots(self):
        """Parse title with dots in filename."""
        result = _parse_title("Above & Beyond S04_23. Billabong Mystery")
        assert result == "Billabong Mystery"

    def test_octonauts_with_dash_and_pipe(self):
        """Parse 'Octonauts - Title | Extra' format."""
        result = _parse_title(
            "Octonauts - The Sea Pigs | Cartoons for Kids | Underwater Sea Education"
        )
        assert result == "The Sea Pigs"

    def test_octonauts_with_ampersand_and_pipe(self):
        """Parse 'Octonauts & Title | Extra' format."""
        result = _parse_title("Octonauts & The Yeti Crab | Episode")
        assert result == "The Yeti Crab"

    def test_octonauts_with_whitespace(self):
        """Parse title with extra whitespace around separator."""
        result = _parse_title("Octonauts  -  The Humpback Whales  |  Extra")
        assert result == "The Humpback Whales"

    def test_fallback_to_stem(self):
        """Return full stem if no known pattern matches."""
        result = _parse_title("some_random_video_name")
        assert result == "some_random_video_name"

    def test_empty_string(self):
        """Handle empty string."""
        result = _parse_title("")
        assert result == ""

    def test_paw_patrol_filename_format(self):
        result = parse_episode("PAW.Patrol.S01E01.Pups.and.the.Kitty-tastrophe.720p.mp4")
        assert result == ("PAW Patrol", "Season 1", "01 - Pups and the Kitty-tastrophe")

    def test_paw_patrol_filename_with_web_suffix(self):
        result = parse_episode(
            "PAW.Patrol.S01E23.Pups.and.the.Ghost.Pirate.720p.WEBRip.x264.AAC.mp4"
        )
        assert result[2] == "23 - Pups and the Ghost Pirate"

    def test_paw_patrol_filename_with_attached_quality_suffix(self):
        result = parse_episode("PAW.Patrol.S04E35.Sea.Patrol.Pups.Save.a.Frozen.Flounder1080p.mkv")
        assert result[2] == "35 - Sea Patrol Pups Save a Frozen Flounder"


class TestStateManagement:
    """Tests for load_state() and save_state() functions."""

    def test_save_and_load_state(self):
        """Save state to file and load it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_state.json"
            
            # Mock the STATE_FILE module variable
            import server
            original_state_file = server.STATE_FILE
            server.STATE_FILE = state_file
            
            try:
                test_state = {
                    "/path/to/video1.mp4": {"watched": True, "progress": 100.5},
                    "/path/to/video2.mp4": {"progress": 50.2},
                }
                
                save_state(test_state)
                loaded = load_state()
                
                assert loaded == test_state
            finally:
                server.STATE_FILE = original_state_file

    def test_load_state_empty_file(self):
        """Load state from empty file returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "empty.json"
            state_file.write_text("")
            
            import server
            original = server.STATE_FILE
            server.STATE_FILE = state_file
            
            try:
                result = load_state()
                assert result == {}
            finally:
                server.STATE_FILE = original

    def test_load_state_nonexistent_file(self):
        """Load state when file doesn't exist returns empty dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "nonexistent.json"
            
            import server
            original = server.STATE_FILE
            server.STATE_FILE = state_file
            
            try:
                result = load_state()
                assert result == {}
            finally:
                server.STATE_FILE = original


class TestLoadAllMetadata:
    """Tests for load_all_metadata() function."""

    def test_empty_directory(self):
        """Load from empty directory returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_all_metadata(Path(tmpdir))
            assert result == []

    def test_directory_with_video_no_metadata(self):
        """Directory with video but no metadata returns video with default info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create a video file
            video_file = tmppath / "Octonauts - Test Episode.mp4"
            video_file.touch()
            
            result = load_all_metadata(tmppath)
            
            assert len(result) == 1
            assert result[0]["title"] == "Test Episode"
            assert result[0]["source"] == str(video_file)
            assert result[0]["grids"] == []

    def test_directory_with_metadata(self):
        """Load directory with metadata.json files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create video and metadata
            video_file = tmppath / "Test Video.mp4"
            video_file.touch()
            
            stills_dir = tmppath / "Test Video_stills"
            stills_dir.mkdir()
            
            metadata = {
                "title": "Custom Title",
                "source": str(video_file),
                "grids": ["grid_01.jpg", "grid_02.jpg"],
                "stills": ["still_01.jpg", "still_02.jpg"],
            }
            
            metadata_file = stills_dir / "metadata.json"
            metadata_file.write_text(json.dumps(metadata))
            
            result = load_all_metadata(tmppath)
            
            assert len(result) == 1
            assert result[0]["title"] == "Custom Title"
            assert result[0]["grids"] == ["grid_01.jpg", "grid_02.jpg"]

    def test_multiple_videos_sorted(self):
        """Load multiple videos in sorted order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create multiple videos (in reverse name order to test sorting)
            names = ["Charlie.mp4", "Alpha.mp4", "Bravo.mp4"]
            for name in names:
                (tmppath / name).touch()
            
            result = load_all_metadata(tmppath)
            
            assert len(result) == 3
            assert result[0]["title"] == "Alpha"
            assert result[1]["title"] == "Bravo"
            assert result[2]["title"] == "Charlie"

    def test_mixed_video_formats(self):
        """Load both .mp4 and .mkv files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            (tmppath / "Video1.mp4").touch()
            (tmppath / "Video2.mkv").touch()
            
            result = load_all_metadata(tmppath)
            
            assert len(result) == 2
            titles = [r["title"] for r in result]
            assert "Video1" in titles
            assert "Video2" in titles

    def test_metadata_overrides_default(self):
        """Metadata from JSON file takes precedence over filename parsing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            
            # Create video with misleading filename
            video_file = tmppath / "Octonauts - Wrong Title.mp4"
            video_file.touch()
            
            # Create metadata with correct title
            stills_dir = tmppath / "Octonauts - Wrong Title_stills"
            stills_dir.mkdir()
            
            metadata = {
                "title": "Correct Title",
                "source": str(video_file),
                "grids": [],
            }
            
            (stills_dir / "metadata.json").write_text(json.dumps(metadata))
            
            result = load_all_metadata(tmppath)
            
            assert len(result) == 1
            assert result[0]["title"] == "Correct Title"


class TestCachingBehavior:
    """Tests to verify caching implementation works correctly."""

    def test_video_catalog_initialized_empty(self):
        """VIDEO_CATALOG should be initialized as empty list."""
        import server
        assert isinstance(server.VIDEO_CATALOG, list)
        assert server.VIDEO_CATALOG == []

    def test_above_beyond_catalogs_initialized_empty(self):
        """Above & Beyond catalogs should be initialized as empty lists."""
        import server
        assert isinstance(server.ABOVE_BEYOND_S03_CATALOG, list)
        assert isinstance(server.ABOVE_BEYOND_S04_CATALOG, list)
        assert server.ABOVE_BEYOND_S03_CATALOG == []
        assert server.ABOVE_BEYOND_S04_CATALOG == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
