"""
Database tables.

Two tables:
  - Job:         one bulk request (e.g. "Python Workshop", 50 recipients)
  - Certificate: one row per recipient in that job (success or failed)
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

# Status values (plain strings keep things easy to read in the database)
JOB_PROCESSING = "processing"
JOB_COMPLETED = "completed"                        # every certificate succeeded
JOB_COMPLETED_WITH_ERRORS = "completed_with_errors"  # some succeeded, some failed
JOB_FAILED = "failed"                              # every certificate failed

CERT_SUCCESS = "success"
CERT_FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    course_name = Column(String, nullable=False)
    issue_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default=JOB_PROCESSING)
    total = Column(Integer, nullable=False, default=0)       # recipients in the request
    successful = Column(Integer, nullable=False, default=0)  # certificates generated
    failed = Column(Integer, nullable=False, default=0)      # certificates that failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # job.certificates gives the list of Certificate rows, in request order
    certificates = relationship(
        "Certificate", back_populates="job", order_by="Certificate.row_number"
    )

    # Properties are computed values; they appear in the API response automatically.
    @property
    def processed(self):
        """How many recipients have been handled so far (success + failed)."""
        return self.successful + self.failed

    @property
    def download_all_url(self):
        """URL of the ZIP with all generated certificates (only if there are any)."""
        if self.successful > 0:
            return f"/jobs/{self.id}/download"
        return None


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    row_number = Column(Integer, nullable=False)  # position in the request (1, 2, 3...)
    recipient_name = Column(String, nullable=False, default="")
    recipient_email = Column(String, nullable=False, default="")
    status = Column(String, nullable=False)       # "success" or "failed"
    error_message = Column(String, nullable=True)  # why it failed (None if success)
    file_path = Column(String, nullable=True)      # where the PDF is saved (None if failed)

    job = relationship("Job", back_populates="certificates")

    @property
    def download_url(self):
        """URL to download this PDF (only if it was generated)."""
        if self.status == CERT_SUCCESS:
            return f"/jobs/{self.job_id}/certificates/{self.id}"
        return None
