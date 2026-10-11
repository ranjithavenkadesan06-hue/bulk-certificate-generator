# Bulk Certificate Generator

A small backend API (Python + FastAPI + SQLite) that accepts **one request with many
recipients**, generates a PDF certificate for each valid recipient from a single
predefined template, tracks the result, and lets you download the certificates.

## Project structure

```
bulk-certificate-generator/
├── app/
│   ├── main.py          # FastAPI app + the 4 API endpoints
│   ├── schemas.py       # Request/response shapes + request validation (Pydantic)
│   ├── models.py        # Database tables: Job and Certificate (SQLAlchemy)
│   ├── database.py      # SQLite connection + session
│   ├── services.py      # Core logic: validate each recipient, generate, track results
│   ├── certificate.py   # The certificate template (draws the PDF with ReportLab)
│   └── config.py        # Database URL and output folder
├── tests/
│   ├── conftest.py      # Test setup (temporary database + temporary PDF folder)
│   └── test_jobs.py     # All tests (28)
├── requirements.txt
├── pytest.ini
└── README.md
```

## 1. Setup (Windows PowerShell)

Run all commands from the project root folder (the one containing `app/`).

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script ("running scripts is disabled"), run this once
in the same window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 2. Run the application

```powershell
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- **Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs**

The database file `certificates.db` and the `certificates/` folder (generated PDFs)
are created automatically in the project folder.

## 3. Run the tests

```powershell
python -m pytest -v
```

Tests use a temporary in-memory database and a temporary folder, so they never
touch your real data.

## 4. Submit a certificate generation request

`POST /jobs` with ONE request containing all recipients.

| Field | Required | Notes |
|---|---|---|
| `course_name` | yes | 1-200 characters |
| `issue_date` | no | `YYYY-MM-DD`, defaults to today |
| `recipients` | yes | 1-500 items, each with `name` and `email` |

You can try it in the browser at `/docs` (click **POST /jobs** -> **Try it out**), or with PowerShell:

```powershell
$body = @'
{
  "course_name": "Python Workshop 2026",
  "issue_date": "2026-10-11",
  "recipients": [
    {"name": "Asha Raman", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com"},
    {"name": "", "email": "missing.name@example.com"}
  ]
}
'@

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/jobs -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 5
```

The third recipient has no name, so it is reported as **failed** while the other two
are still generated. Example response (shortened):

```json
{
  "id": 1,
  "course_name": "Python Workshop 2026",
  "status": "completed_with_errors",
  "total": 3, "successful": 2, "failed": 1, "processed": 3,
  "download_all_url": "/jobs/1/download",
  "certificates": [
    {"id": 1, "row_number": 1, "recipient_name": "Asha Raman", "status": "success",
     "error_message": null, "download_url": "/jobs/1/certificates/1"},
    {"id": 3, "row_number": 3, "recipient_name": "", "status": "failed",
     "error_message": "Name is required", "download_url": null}
  ]
}
```

### Check job status / progress

```powershell
Invoke-RestMethod http://127.0.0.1:8000/jobs/1 | ConvertTo-Json -Depth 5
```

| Job status | Meaning |
|---|---|
| `processing` | Certificates are still being generated |
| `completed` | Every certificate was generated |
| `completed_with_errors` | Some succeeded, some failed (see each certificate's `error_message`) |
| `failed` | Every certificate failed |

## 5. Retrieve generated certificates

```powershell
# One certificate (PDF) - use the download_url from the job response
Invoke-WebRequest -Uri http://127.0.0.1:8000/jobs/1/certificates/1 -OutFile asha.pdf

# All successfully generated certificates of the job (ZIP)
Invoke-WebRequest -Uri http://127.0.0.1:8000/jobs/1/download -OutFile job1.zip
```

(Or just open those URLs in a browser.)

## API summary

| Method | URL | Purpose | Errors |
|---|---|---|---|
| POST | `/jobs` | Create a job with many recipients | 422 invalid request |
| GET | `/jobs/{job_id}` | Status, progress, result of every certificate | 404 unknown job |
| GET | `/jobs/{job_id}/certificates/{certificate_id}` | Download one PDF | 404 unknown / failed certificate |
| GET | `/jobs/{job_id}/download` | Download all generated PDFs as a ZIP | 404 unknown job / nothing generated |

## Important design decisions

**1. Synchronous processing (no background workers).**
`POST /jobs` generates all certificates before it responds, so the response already
contains the final result. Reasons: a certificate PDF takes only a few milliseconds
to draw, the request size is capped at 500 recipients, and it keeps the code simple
and easy to reason about (no queue, no worker, no race conditions).
*Trade-off:* a very large request would make the client wait. If needed later, the
change is small: `create_job` would return immediately with status `processing` and
call `process_job` through FastAPI `BackgroundTasks` (or a task queue such as Celery);
`GET /jobs/{id}` already reports progress because `process_job` saves the counters
after every recipient.

**2. Two levels of validation.**
- *Whole-request problems* (missing `course_name`, empty or >500 recipients, bad date)
  are rejected immediately with **422** and no job is created. FastAPI/Pydantic does this.
- *Per-recipient problems* (missing name, missing/invalid email, name over 100 characters)
  do **not** reject the request. That recipient is saved as a failed certificate with an
  `error_message`, and everyone else is still processed. `row_number` tells the client
  which recipient in their list it was.

**3. One failure never stops the others.**
Each certificate is generated inside its own `try/except` in `process_job`. Any error is
stored on that certificate and the loop continues.

**4. Status tracking in the database.**
`Job` stores `total`, `successful`, `failed` (and `processed = successful + failed`).
`Certificate` stores one row per recipient with `status`, `error_message` and the PDF path.
The counters are saved after every recipient, so progress is always current.

**5. Single template, PDF output.**
The template is the fixed layout in `app/certificate.py` (ReportLab). Only the recipient
name, course name and date change. Long names are shrunk to fit the page.

**6. Database and storage.** SQLite (a relational database, no setup needed) via SQLAlchemy.
PDFs are stored on disk in `certificates/job_<id>/<certificate_id>.pdf`; the database stores the path.

## Known limitations

- The built-in PDF font supports **Latin characters only**. A recipient name with other
  scripts (e.g. Tamil, Chinese) fails with a clear message instead of printing garbage;
  `course_name` with such characters is rejected with 422. Supporting more scripts would
  need a Unicode `.ttf` font registered in ReportLab.
- The email check is a simple format check (`something@something.something`); no email is sent.
- No authentication (not part of the assignment).
