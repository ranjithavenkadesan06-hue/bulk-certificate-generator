"""
Simple settings for the project.

Both paths are relative, so run all commands from the project root folder.
"""
from pathlib import Path

# SQLite database file (created automatically on first start)
DATABASE_URL = "sqlite:///./certificates.db"

# Folder where generated PDF certificates are saved.
# Each job gets its own sub-folder: certificates/job_1/, certificates/job_2/ ...
CERTIFICATES_DIR = Path("certificates")
