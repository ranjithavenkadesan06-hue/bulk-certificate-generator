"""
The core logic: validate each recipient, generate their certificate, track results.
"""
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app import config
from app.certificate import generate_certificate_pdf
from app.models import (
    CERT_FAILED,
    CERT_SUCCESS,
    JOB_COMPLETED,
    JOB_COMPLETED_WITH_ERRORS,
    JOB_FAILED,
    Certificate,
    Job,
)

# Very simple email check: something@something.something (no spaces)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_recipient(name: str, email: str) -> Optional[str]:
    """Return an error message if the recipient is invalid, otherwise None."""
    if not name:
        return "Name is required"
    if len(name) > 100:
        return "Name must be at most 100 characters"
    if not email:
        return "Email is required"
    if not EMAIL_PATTERN.match(email):
        return "Email is not valid"
    return None


def process_job(db: Session, job: Job, recipients: list):
    """
    Go through every recipient one by one.

    - Invalid recipient       -> saved as a failed certificate with the reason.
    - Error while generating  -> caught, saved as failed, and we CONTINUE
                                 with the next recipient.
    - Valid recipient         -> PDF is generated and saved.

    One bad recipient never stops the others.
    """
    job_folder = Path(config.CERTIFICATES_DIR) / f"job_{job.id}"
    job_folder.mkdir(parents=True, exist_ok=True)

    for row_number, recipient in enumerate(recipients, start=1):
        certificate = Certificate(
            job_id=job.id,
            row_number=row_number,
            recipient_name=recipient.name,
            recipient_email=recipient.email,
            status=CERT_FAILED,  # assume failed; changed to success below if all goes well
        )
        db.add(certificate)
        db.flush()  # gives the certificate an id (we use it in the file name)

        error = validate_recipient(recipient.name, recipient.email)
        if error:
            certificate.error_message = error
        else:
            try:
                file_path = job_folder / f"{certificate.id}.pdf"
                generate_certificate_pdf(file_path, recipient.name, job.course_name, job.issue_date)
                certificate.status = CERT_SUCCESS
                certificate.file_path = str(file_path)
            except Exception as exc:
                # Catch ANY error for this one certificate and keep going.
                certificate.error_message = f"Generation failed: {exc}"

        # Update the counters and save after every recipient,
        # so the job's progress is always up to date in the database.
        if certificate.status == CERT_SUCCESS:
            job.successful += 1
        else:
            job.failed += 1
        db.commit()

    # All recipients handled: set the final job status
    if job.failed == 0:
        job.status = JOB_COMPLETED
    elif job.successful == 0:
        job.status = JOB_FAILED
    else:
        job.status = JOB_COMPLETED_WITH_ERRORS
    db.commit()
