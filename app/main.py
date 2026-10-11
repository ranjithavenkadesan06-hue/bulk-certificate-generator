"""
The FastAPI application: all API endpoints live here.

Endpoints:
  POST /jobs                                  create a bulk certificate job
  GET  /jobs/{job_id}                         job status, progress and per-certificate results
  GET  /jobs/{job_id}/certificates/{cert_id}  download ONE certificate (PDF)
  GET  /jobs/{job_id}/download                download ALL generated certificates (ZIP)
"""
import io
import zipfile
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.certificate import safe_filename
from app.database import Base, engine, get_db
from app.models import CERT_SUCCESS, JOB_PROCESSING, Certificate, Job
from app.schemas import JobCreate, JobOut
from app.services import process_job


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: create the database tables if missing.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Bulk Certificate Generator", lifespan=lifespan)


def get_job_or_404(db: Session, job_id: int) -> Job:
    """Load a job or return a 404 error if it does not exist."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/jobs", response_model=JobOut, status_code=201)
def create_job(request: JobCreate, db: Session = Depends(get_db)):
    """
    Submit many recipients in ONE request.
    Certificates are generated synchronously, so the response already contains
    the final result (see README for why).
    """
    # 1. Save the job first so it gets an id
    job = Job(
        course_name=request.course_name,
        issue_date=request.issue_date or date.today(),
        status=JOB_PROCESSING,
        total=len(request.recipients),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # 2. Generate all the certificates
    process_job(db, job, request.recipients)

    # 3. Reload from the database and return the finished job
    db.refresh(job)
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Status, progress (successful / failed / processed) and the result of every certificate."""
    return get_job_or_404(db, job_id)


@app.get("/jobs/{job_id}/certificates/{certificate_id}")
def download_certificate(job_id: int, certificate_id: int, db: Session = Depends(get_db)):
    """Download one generated certificate as a PDF."""
    get_job_or_404(db, job_id)

    # Filter by job_id too, so a certificate cannot be fetched through the wrong job
    certificate = (
        db.query(Certificate)
        .filter(Certificate.id == certificate_id, Certificate.job_id == job_id)
        .first()
    )
    if certificate is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if certificate.status != CERT_SUCCESS:
        raise HTTPException(
            status_code=404,
            detail=f"This certificate was not generated: {certificate.error_message}",
        )
    if not Path(certificate.file_path).exists():
        raise HTTPException(status_code=404, detail="Certificate file is missing on the server")

    filename = f"{safe_filename(certificate.recipient_name)}_certificate.pdf"
    return FileResponse(certificate.file_path, media_type="application/pdf", filename=filename)


@app.get("/jobs/{job_id}/download")
def download_all_certificates(job_id: int, db: Session = Depends(get_db)):
    """Download every successfully generated certificate of the job in one ZIP file."""
    job = get_job_or_404(db, job_id)

    successful = [c for c in job.certificates if c.status == CERT_SUCCESS]
    if not successful:
        raise HTTPException(status_code=404, detail="No certificates were generated for this job")

    # Build the ZIP in memory (no temporary file needed)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for certificate in successful:
            if Path(certificate.file_path).exists():
                # Row number in the name keeps entries unique even if two people share a name
                entry_name = f"{certificate.row_number}_{safe_filename(certificate.recipient_name)}.pdf"
                zip_file.write(certificate.file_path, arcname=entry_name)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=job_{job.id}_certificates.zip"},
    )
