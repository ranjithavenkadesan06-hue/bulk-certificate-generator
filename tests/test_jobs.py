"""
Tests for the Bulk Certificate Generator.

Sections match the assignment's list:
  1. Creating a generation job
  2. Input validation
  3. Certificate generation
  4. Job status / progress
  5. Handling an individual certificate failure
  6. Retrieving generated certificates
"""
import io
import zipfile
from datetime import date
from pathlib import Path

from app import services
from app.certificate import generate_certificate_pdf
from tests.conftest import make_payload


# ---------------------------------------------------------------
# 1. Creating a generation job
# ---------------------------------------------------------------

def test_create_job_returns_completed_job(client):
    response = client.post("/jobs", json=make_payload())

    assert response.status_code == 201
    job = response.json()
    assert job["id"] == 1
    assert job["course_name"] == "Python Workshop 2026"
    assert job["status"] == "completed"
    assert job["total"] == 2
    assert job["successful"] == 2
    assert job["failed"] == 0
    assert len(job["certificates"]) == 2


def test_create_job_uses_given_issue_date(client):
    response = client.post("/jobs", json=make_payload(issue_date="2026-01-15"))

    assert response.status_code == 201
    assert response.json()["issue_date"] == "2026-01-15"


def test_create_job_defaults_issue_date_to_today(client):
    response = client.post("/jobs", json=make_payload())

    assert response.json()["issue_date"] == date.today().isoformat()


# ---------------------------------------------------------------
# 2. Input validation
# ---------------------------------------------------------------

def test_missing_course_name_is_rejected(client):
    payload = make_payload()
    del payload["course_name"]

    assert client.post("/jobs", json=payload).status_code == 422


def test_blank_course_name_is_rejected(client):
    assert client.post("/jobs", json=make_payload(course_name="   ")).status_code == 422


def test_empty_recipient_list_is_rejected(client):
    assert client.post("/jobs", json=make_payload(recipients=[])).status_code == 422


def test_too_many_recipients_is_rejected(client):
    too_many = [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(501)]

    assert client.post("/jobs", json=make_payload(recipients=too_many)).status_code == 422


def test_invalid_issue_date_is_rejected(client):
    assert client.post("/jobs", json=make_payload(issue_date="not-a-date")).status_code == 422


def test_course_name_with_unsupported_characters_is_rejected(client):
    assert client.post("/jobs", json=make_payload(course_name="தமிழ்")).status_code == 422


def test_invalid_recipients_are_marked_failed_but_valid_ones_succeed(client):
    recipients = [
        {"name": "Asha Raman", "email": "asha@example.com"},  # valid
        {"name": "", "email": "noname@example.com"},          # missing name
        {"name": "No Email", "email": ""},                    # missing email
        {"name": "Bad Email", "email": "not-an-email"},       # invalid email
        {"name": "Ravi Kumar", "email": "ravi@example.com"},  # valid
    ]
    response = client.post("/jobs", json=make_payload(recipients=recipients))

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "completed_with_errors"
    assert job["successful"] == 2
    assert job["failed"] == 3

    certificates = job["certificates"]
    assert [c["status"] for c in certificates] == ["success", "failed", "failed", "failed", "success"]
    assert certificates[1]["error_message"] == "Name is required"
    assert certificates[2]["error_message"] == "Email is required"
    assert certificates[3]["error_message"] == "Email is not valid"


def test_job_with_only_invalid_recipients_has_status_failed(client):
    recipients = [{"name": "", "email": ""}, {"name": "X", "email": "bad"}]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()

    assert job["status"] == "failed"
    assert job["successful"] == 0
    assert job["failed"] == 2
    assert job["download_all_url"] is None


def test_name_longer_than_100_characters_fails(client):
    recipients = [{"name": "A" * 101, "email": "long@example.com"}]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()

    assert job["certificates"][0]["status"] == "failed"
    assert "100 characters" in job["certificates"][0]["error_message"]


# ---------------------------------------------------------------
# 3. Certificate generation
# ---------------------------------------------------------------

def test_generate_certificate_pdf_creates_a_valid_pdf_with_recipient_details(tmp_path):
    pdf_path = tmp_path / "test.pdf"

    generate_certificate_pdf(pdf_path, "Asha Raman", "Python Workshop 2026", date(2026, 1, 15))

    content = pdf_path.read_bytes()
    assert content.startswith(b"%PDF")             # it is a real PDF
    assert b"Asha Raman" in content                # recipient-specific info
    assert b"Python Workshop 2026" in content      # course name
    assert b"2026-01-15" in content                # date


def test_generate_certificate_pdf_rejects_unsupported_characters(tmp_path):
    try:
        generate_certificate_pdf(tmp_path / "x.pdf", "தமிழ்", "Course", date.today())
        assert False, "expected a ValueError"
    except ValueError:
        pass


def test_job_creates_one_pdf_file_per_valid_recipient(client):
    job = client.post("/jobs", json=make_payload()).json()

    for certificate in job["certificates"]:
        # Download it and check it is a PDF containing that person's name
        pdf = client.get(certificate["download_url"]).content
        assert pdf.startswith(b"%PDF")
        assert certificate["recipient_name"].encode() in pdf


# ---------------------------------------------------------------
# 4. Job status / progress
# ---------------------------------------------------------------

def test_get_job_status_shows_progress_counts(client):
    recipients = [
        {"name": "Asha Raman", "email": "asha@example.com"},
        {"name": "Bad", "email": "bad"},
        {"name": "Ravi Kumar", "email": "ravi@example.com"},
    ]
    job_id = client.post("/jobs", json=make_payload(recipients=recipients)).json()["id"]

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "completed_with_errors"
    assert job["total"] == 3
    assert job["successful"] == 2
    assert job["failed"] == 1
    assert job["processed"] == 3  # processed = successful + failed
    assert len(job["certificates"]) == 3


def test_get_job_lists_each_certificate_in_request_order(client):
    job_id = client.post("/jobs", json=make_payload()).json()["id"]

    certificates = client.get(f"/jobs/{job_id}").json()["certificates"]

    assert [c["row_number"] for c in certificates] == [1, 2]
    assert [c["recipient_name"] for c in certificates] == ["Asha Raman", "Ravi Kumar"]


def test_get_unknown_job_returns_404(client):
    response = client.get("/jobs/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_jobs_are_independent(client):
    first = client.post("/jobs", json=make_payload()).json()
    second = client.post("/jobs", json=make_payload()).json()

    assert first["id"] != second["id"]
    assert len(client.get(f"/jobs/{first['id']}").json()["certificates"]) == 2
    assert len(client.get(f"/jobs/{second['id']}").json()["certificates"]) == 2


# ---------------------------------------------------------------
# 5. Handling an individual certificate failure
# ---------------------------------------------------------------

def test_one_generation_error_does_not_stop_other_certificates(client, monkeypatch):
    # Replace the PDF generator with a fake one that crashes for ONE person only
    real_generate = services.generate_certificate_pdf

    def flaky_generate(file_path, recipient_name, course_name, issue_date):
        if recipient_name == "Crash Me":
            raise RuntimeError("something went wrong")
        real_generate(file_path, recipient_name, course_name, issue_date)

    monkeypatch.setattr(services, "generate_certificate_pdf", flaky_generate)

    recipients = [
        {"name": "Asha Raman", "email": "asha@example.com"},
        {"name": "Crash Me", "email": "crash@example.com"},
        {"name": "Ravi Kumar", "email": "ravi@example.com"},
    ]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()

    assert job["status"] == "completed_with_errors"
    assert job["successful"] == 2
    assert job["failed"] == 1

    asha, crash, ravi = job["certificates"]
    assert asha["status"] == "success"      # before the failure
    assert crash["status"] == "failed"
    assert "something went wrong" in crash["error_message"]
    assert crash["download_url"] is None
    assert ravi["status"] == "success"      # AFTER the failure: still generated


def test_name_with_unsupported_characters_fails_only_that_certificate(client):
    # A real generation failure: the PDF font cannot print Tamil characters
    recipients = [
        {"name": "தமிழ்", "email": "tamil@example.com"},
        {"name": "Ravi Kumar", "email": "ravi@example.com"},
    ]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()

    assert job["status"] == "completed_with_errors"
    assert job["certificates"][0]["status"] == "failed"
    assert "not supported" in job["certificates"][0]["error_message"]
    assert job["certificates"][1]["status"] == "success"


# ---------------------------------------------------------------
# 6. Retrieving generated certificates
# ---------------------------------------------------------------

def test_download_single_certificate_as_pdf(client):
    job = client.post("/jobs", json=make_payload()).json()
    certificate = job["certificates"][0]

    response = client.get(certificate["download_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert b"Asha Raman" in response.content


def test_download_failed_certificate_returns_404_with_reason(client):
    recipients = [{"name": "", "email": "x@example.com"}]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()
    certificate_id = job["certificates"][0]["id"]

    response = client.get(f"/jobs/{job['id']}/certificates/{certificate_id}")

    assert response.status_code == 404
    assert "Name is required" in response.json()["detail"]


def test_download_unknown_certificate_returns_404(client):
    job_id = client.post("/jobs", json=make_payload()).json()["id"]

    assert client.get(f"/jobs/{job_id}/certificates/999").status_code == 404


def test_certificate_cannot_be_downloaded_through_another_job(client):
    first = client.post("/jobs", json=make_payload()).json()
    second = client.post("/jobs", json=make_payload()).json()
    certificate_id = first["certificates"][0]["id"]

    response = client.get(f"/jobs/{second['id']}/certificates/{certificate_id}")

    assert response.status_code == 404


def test_download_all_certificates_as_zip(client):
    recipients = [
        {"name": "Asha Raman", "email": "asha@example.com"},
        {"name": "Bad", "email": "bad"},  # failed: must NOT be in the ZIP
        {"name": "Ravi Kumar", "email": "ravi@example.com"},
    ]
    job = client.post("/jobs", json=make_payload(recipients=recipients)).json()

    response = client.get(job["download_all_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        assert sorted(zip_file.namelist()) == ["1_Asha_Raman.pdf", "3_Ravi_Kumar.pdf"]
        for name in zip_file.namelist():
            assert zip_file.read(name).startswith(b"%PDF")


def test_download_zip_with_no_certificates_returns_404(client):
    job = client.post("/jobs", json=make_payload(recipients=[{"name": "", "email": ""}])).json()

    assert client.get(f"/jobs/{job['id']}/download").status_code == 404


def test_download_zip_for_unknown_job_returns_404(client):
    assert client.get("/jobs/999/download").status_code == 404
