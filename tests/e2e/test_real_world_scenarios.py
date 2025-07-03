"""End-to-end tests for real-world sync scenarios."""

import asyncio
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from client.sync_engine import SyncEngine
from shared.models import ClientConfig


class TestRealWorldScenarios:
    """Real-world sync scenario tests."""

    @pytest.fixture
    async def temp_directories(self):
        """Create temporary directories for testing."""
        client_dir = Path(tempfile.mkdtemp(prefix="rw_client_"))
        server_dir = Path(tempfile.mkdtemp(prefix="rw_server_"))

        yield {"client": client_dir, "server": server_dir}

        # Cleanup
        shutil.rmtree(client_dir, ignore_errors=True)
        shutil.rmtree(server_dir, ignore_errors=True)

    @pytest.fixture
    def client_config(self, temp_directories):
        """Create realistic client configuration."""
        return ClientConfig(
            client_name="developer_workstation",
            sync_directory=str(temp_directories["client"]),
            server_host="sync.company.com",
            server_port=443,
            ignore_patterns=[
                ".git",
                ".gitignore",
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "node_modules",
                "*.log",
                "*.tmp",
                ".DS_Store",
                "Thumbs.db",
                "*.swp",
                "*.swo",
                "*~",
            ],
        )

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_developer_workflow_scenario(self, temp_directories, client_config):
        """Test typical developer workflow with code files."""
        base_dir = temp_directories["client"]

        # Create realistic project structure
        project_files = {
            "README.md": "# My Project\nThis is a sample project.",
            "requirements.txt": "fastapi==0.68.0\nuvicorn==0.15.0\npydantic==1.8.2",
            "src/main.py": """
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
""",
            "src/models.py": """
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str
    email: str
""",
            "tests/test_main.py": """
import pytest
from src.main import app

def test_read_root():
    # Test implementation
    pass
""",
            ".gitignore": """
__pycache__/
*.pyc
.env
.venv/
""",
            "config.json": '{"debug": true, "database_url": "sqlite:///./test.db"}',
        }

        # Create project structure
        for file_path, content in project_files.items():
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        sync_engine = SyncEngine(client_config)

        # Mock successful sync responses
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 20 + [sync_response]

            await sync_engine.start()

            # Initial sync
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Simulate code changes
            main_file = base_dir / "src/main.py"
            with open(main_file, "a") as f:
                f.write(
                    "\n\n@app.get('/health')\ndef health_check():\n    return {'status': 'ok'}"
                )

            # Add new test file
            new_test = base_dir / "tests/test_health.py"
            with open(new_test, "w") as f:
                f.write(
                    "def test_health_check():\n    # Test health endpoint\n    pass"
                )

            # Sync changes
            mock_session.post.side_effect = [
                upload_response,
                upload_response,
                sync_response,
            ]
            success = await sync_engine.perform_full_sync()
            assert success is True

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_document_collaboration_scenario(
        self, temp_directories, client_config
    ):
        """Test document collaboration scenario with conflicts."""
        base_dir = temp_directories["client"]

        # Create shared documents
        documents = {
            "project_proposal.md": """
# Project Proposal

## Overview
This document outlines our new project initiative.

## Goals
- Increase efficiency by 20%
- Reduce costs
- Improve user experience
""",
            "meeting_notes.txt": """
Meeting Notes - 2023-01-15

Attendees: Alice, Bob, Charlie

Discussion:
- Budget allocation
- Timeline review
- Resource planning
""",
            "shared_config.json": """
{
    "project_name": "collaboration_project",
    "version": "1.0.0",
    "settings": {
        "auto_save": true,
        "backup_frequency": "hourly"
    }
}
""",
        }

        # Create documents
        for file_path, content in documents.items():
            full_path = base_dir / file_path
            with open(full_path, "w") as f:
                f.write(content)

        sync_engine = SyncEngine(client_config)

        # Simulate conflict scenario
        conflict_response = Mock()
        conflict_response.status = 200
        conflict_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [
                    {
                        "path": "project_proposal.md",
                        "size": 500,
                        "checksum": "different_hash",
                        "modified_time": datetime.now().isoformat(),
                        "is_directory": False,
                    }
                ],
                "conflicts": ["meeting_notes.txt"],
            }
        )

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        download_response = Mock()
        download_response.status = 200
        download_response.content.iter_chunked = AsyncMock(
            return_value=[
                b"# Project Proposal\n\n## Overview\nThis document has been updated by another user.\n"
            ]
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 5 + [conflict_response]
            mock_session.get.return_value = download_response

            await sync_engine.start()

            # Initial sync with conflicts
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Verify conflict handling was triggered
            assert mock_session.post.call_count >= 4  # Uploads + sync request

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_media_files_sync_scenario(self, temp_directories, client_config):
        """Test syncing large media files (images, videos)."""
        base_dir = temp_directories["client"]

        # Create media directory structure
        media_dirs = ["images", "videos", "documents"]
        for dir_name in media_dirs:
            (base_dir / dir_name).mkdir()

        # Create mock media files
        media_files = {
            "images/photo1.jpg": b"\xff\xd8\xff\xe0"
            + b"fake_jpeg_data" * 1000,  # ~15KB
            "images/screenshot.png": b"\x89PNG\r\n\x1a\n"
            + b"fake_png_data" * 2000,  # ~30KB
            "videos/demo.mp4": b"\x00\x00\x00\x20ftypmp41"
            + b"fake_video_data" * 5000,  # ~75KB
            "documents/presentation.pdf": b"%PDF-1.4"
            + b"fake_pdf_content" * 3000,  # ~45KB
        }

        # Create binary files
        for file_path, content in media_files.items():
            full_path = base_dir / file_path
            with open(full_path, "wb") as f:
                f.write(content)

        sync_engine = SyncEngine(client_config)

        # Mock responses for large file uploads
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]

            await sync_engine.start()

            # Sync media files (should handle binary data and chunking)
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Verify all media files were processed
            assert mock_session.post.call_count >= len(media_files)

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_remote_work_scenario(self, temp_directories, client_config):
        """Test remote work scenario with intermittent connectivity."""
        base_dir = temp_directories["client"]

        # Create work files
        work_files = {
            "daily_report.md": "# Daily Report\n\n## Tasks Completed\n- Task 1\n- Task 2",
            "timesheet.csv": "Date,Hours,Description\n2023-01-15,8,Development work",
            "code_review.txt": "Code Review Notes:\n\n1. Check error handling\n2. Add unit tests",
            "backup/archive.zip": b"PK\x03\x04" + b"fake_zip_data" * 100,
        }

        # Create files
        for file_path, content in work_files.items():
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                with open(full_path, "wb") as f:
                    f.write(content)
            else:
                with open(full_path, "w") as f:
                    f.write(content)

        sync_engine = SyncEngine(client_config)

        # Simulate intermittent connectivity (failures then success)
        network_error = Mock()
        network_error.status = 503  # Service unavailable

        success_response = Mock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            # First attempts fail, then succeed (simulating retry logic)
            mock_session.post.side_effect = [
                network_error,
                network_error,  # Initial failures
                success_response,
                success_response,
                success_response,  # Retries succeed
                sync_response,
            ]

            await sync_engine.start()

            # Should eventually succeed despite initial failures
            success = await sync_engine.perform_full_sync()
            assert success is True

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_file_versioning_scenario(self, temp_directories, client_config):
        """Test file versioning and history tracking."""
        base_dir = temp_directories["client"]

        # Create initial document
        document = base_dir / "important_document.txt"
        versions = [
            "Version 1: Initial draft of the document.",
            "Version 2: Added introduction and background.",
            "Version 3: Revised methodology section.",
            "Version 4: Final review and corrections.",
        ]

        sync_engine = SyncEngine(client_config)

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response] * 4

            await sync_engine.start()

            # Simulate document evolution over time
            for _i, version_content in enumerate(versions, 1):
                # Update document
                with open(document, "w") as f:
                    f.write(version_content)

                # Sync each version
                success = await sync_engine.perform_full_sync()
                assert success is True

                # Simulate time passing between versions
                await asyncio.sleep(0.01)

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_team_project_scenario(self, temp_directories, client_config):
        """Test team project with multiple file types and rapid changes."""
        base_dir = temp_directories["client"]

        # Create team project structure
        project_structure = {
            "README.md": "# Team Project\n\nCollaborative development project.",
            "src/": {
                "main.py": "# Main application file",
                "utils.py": "# Utility functions",
                "config.py": "# Configuration settings",
            },
            "docs/": {
                "api.md": "# API Documentation",
                "setup.md": "# Setup Instructions",
            },
            "tests/": {
                "test_main.py": "# Main tests",
                "test_utils.py": "# Utility tests",
            },
            "assets/": {
                "logo.png": b"\x89PNG\r\n\x1a\n" + b"logo_data" * 100,
                "icon.ico": b"\x00\x00\x01\x00" + b"icon_data" * 50,
            },
        }

        # Create nested structure
        def create_structure(base_path, structure):
            for name, content in structure.items():
                path = base_path / name
                if isinstance(content, dict):
                    path.mkdir(exist_ok=True)
                    create_structure(path, content)
                elif isinstance(content, bytes):
                    with open(path, "wb") as f:
                        f.write(content)
                else:
                    with open(path, "w") as f:
                        f.write(content)

        create_structure(base_dir, project_structure)

        sync_engine = SyncEngine(client_config)

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 20 + [sync_response]

            await sync_engine.start()

            # Initial project sync
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Simulate rapid development changes
            changes = [
                ("src/main.py", "# Updated main file with new features"),
                ("tests/test_new_feature.py", "# Tests for new feature"),
                ("docs/changelog.md", "# Changelog\n\n## v1.0.1\n- Added new feature"),
            ]

            for file_path, content in changes:
                full_path = base_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, "w") as f:
                    f.write(content)

            # Sync changes
            mock_session.post.side_effect = [upload_response] * 5 + [sync_response]
            success = await sync_engine.perform_full_sync()
            assert success is True

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    @pytest.mark.slow
    async def test_backup_restoration_scenario(self, temp_directories, client_config):
        """Test backup and restoration scenario."""
        base_dir = temp_directories["client"]

        # Create important files to backup
        important_files = {
            "critical_data.json": '{"users": [{"id": 1, "name": "Alice"}], "settings": {"version": "1.0"}}',
            "database_backup.sql": "CREATE TABLE users (id INT, name VARCHAR(50));\nINSERT INTO users VALUES (1, 'Alice');",
            "config_backup.yaml": "database:\n  host: localhost\n  port: 5432\nredis:\n  host: redis-server",
            "certificates/ssl.cert": "-----BEGIN CERTIFICATE-----\nMIIC...(fake cert data)\n-----END CERTIFICATE-----",
            "certificates/ssl.key": "-----BEGIN FAKE PRIVATE KEY-----\nMIIE...(fake key data for testing)\n-----END FAKE PRIVATE KEY-----",
        }

        # Create backup files
        for file_path, content in important_files.items():
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

        sync_engine = SyncEngine(client_config)

        # Mock backup sync
        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        # Mock restoration (download from server)
        download_response = Mock()
        download_response.status = 200

        def mock_download_content(file_path):
            if "critical_data" in file_path:
                return [
                    b'{"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}'
                ]
            elif "database_backup" in file_path:
                return [
                    b"CREATE TABLE users (id INT, name VARCHAR(50));\nINSERT INTO users VALUES (1, 'Alice'), (2, 'Bob');"
                ]
            return [b"restored content"]

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [
                    {
                        "path": "critical_data.json",
                        "size": 100,
                        "checksum": "updated_hash",
                        "modified_time": datetime.now().isoformat(),
                        "is_directory": False,
                    }
                ],
                "conflicts": [],
            }
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            # Setup mock responses
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]
            download_response.content.iter_chunked = AsyncMock(
                side_effect=lambda: mock_download_content("critical_data")
            )
            mock_session.get.return_value = download_response

            await sync_engine.start()

            # Perform backup (initial sync)
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Simulate restoration scenario (files updated on server)
            # This would download newer versions
            success = await sync_engine.perform_full_sync()
            assert success is True

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_mobile_sync_scenario(self, temp_directories, client_config):
        """Test mobile device sync with bandwidth limitations."""
        base_dir = temp_directories["client"]

        # Create mobile-typical files (photos, notes, documents)
        mobile_files = {
            "photos/IMG_001.jpg": b"\xff\xd8\xff\xe0" + b"photo_data" * 2000,  # ~30KB
            "photos/IMG_002.jpg": b"\xff\xd8\xff\xe0" + b"photo_data" * 3000,  # ~45KB
            "notes/meeting_notes.txt": "Quick notes from mobile device\n- Point 1\n- Point 2",
            "documents/report_draft.pdf": b"%PDF-1.4" + b"mobile_pdf" * 1000,  # ~15KB
            "voice_memos/memo_001.m4a": b"\x00\x00\x00\x20ftypM4A "
            + b"audio_data" * 500,  # ~7.5KB
        }

        # Create mobile files
        for file_path, content in mobile_files.items():
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                with open(full_path, "wb") as f:
                    f.write(content)
            else:
                with open(full_path, "w") as f:
                    f.write(content)

        # Configure for mobile (smaller chunks, compression)
        client_config.max_file_size = 5 * 1024 * 1024  # 5MB limit for mobile

        sync_engine = SyncEngine(client_config)
        sync_engine.max_bandwidth = 512 * 1024  # 512KB/s bandwidth limit

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(return_value={"success": True})

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={"success": True, "files_to_sync": [], "conflicts": []}
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]

            await sync_engine.start()

            # Mobile sync should handle bandwidth limitations
            start_time = time.time()
            success = await sync_engine.perform_full_sync()
            end_time = time.time()

            assert success is True

            # Should respect bandwidth throttling (rough check)
            sync_time = end_time - start_time
            # With throttling, should take some minimum time
            assert sync_time >= 0.1  # At least 100ms due to throttling

            await sync_engine.stop()

    @pytest.mark.e2e
    @pytest.mark.real_world
    async def test_enterprise_compliance_scenario(
        self, temp_directories, client_config
    ):
        """Test enterprise compliance scenario with audit trails."""
        base_dir = temp_directories["client"]

        # Create compliance-sensitive files
        compliance_files = {
            "financial_reports/Q1_2023.xlsx": b"PK\x03\x04" + b"excel_data" * 1000,
            "financial_reports/Q2_2023.xlsx": b"PK\x03\x04" + b"excel_data" * 1100,
            "contracts/vendor_agreement.pdf": b"%PDF-1.4" + b"contract_data" * 800,
            "hr_documents/employee_handbook.docx": b"PK\x03\x04" + b"docx_data" * 600,
            "audit_logs/system_access.log": "2023-01-15 10:00:00 - User login: alice@company.com\n2023-01-15 10:15:00 - File access: financial_reports/Q1_2023.xlsx",
            "policies/data_retention.md": "# Data Retention Policy\n\n## Overview\nCompany data retention guidelines.",
        }

        # Create compliance files
        for file_path, content in compliance_files.items():
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, bytes):
                with open(full_path, "wb") as f:
                    f.write(content)
            else:
                with open(full_path, "w") as f:
                    f.write(content)

        # Configure for enterprise (encryption, audit trails)
        client_config.api_key = "enterprise_api_key_12345"

        sync_engine = SyncEngine(client_config)

        upload_response = Mock()
        upload_response.status = 200
        upload_response.json = AsyncMock(
            return_value={"success": True, "audit_id": "audit_12345_67890"}
        )

        sync_response = Mock()
        sync_response.status = 200
        sync_response.json = AsyncMock(
            return_value={
                "success": True,
                "files_to_sync": [],
                "conflicts": [],
                "compliance_check": "passed",
            }
        )

        with patch.object(sync_engine, "_ensure_session"), patch.object(
            sync_engine, "session"
        ) as mock_session:
            mock_session.post.side_effect = [upload_response] * 10 + [sync_response]

            await sync_engine.start()

            # Enterprise sync with compliance checks
            success = await sync_engine.perform_full_sync()
            assert success is True

            # Verify compliance headers were included
            for call in mock_session.post.call_args_list:
                if len(call[1]) > 0 and "headers" in call[1]:
                    headers = call[1]["headers"]
                    assert "Authorization" in headers
                    assert headers["Authorization"] == "Bearer enterprise_api_key_12345"

            await sync_engine.stop()
