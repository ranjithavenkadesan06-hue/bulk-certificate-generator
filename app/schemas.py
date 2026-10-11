"""
Pydantic schemas: describe and validate the JSON going IN and OUT of the API.

If the request JSON does not match the "In" schemas, FastAPI automatically
returns a 422 error and our code never runs.
"""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A single request may contain at most this many recipients.
# We generate synchronously (see README), so we cap the size of one request.
MAX_RECIPIENTS = 500


# ---------- Request (input) ----------

class RecipientIn(BaseModel):
    # Remove spaces at the start/end of every text field automatically
    model_config = ConfigDict(str_strip_whitespace=True)

    # Defaults are "" on purpose: a recipient with a missing name/email does NOT
    # reject the whole request. It is validated later and marked as a failed
    # certificate, so the other recipients still get theirs.
    name: str = ""
    email: str = ""


class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    course_name: str = Field(min_length=1, max_length=200)
    issue_date: Optional[date] = None  # defaults to today if not sent
    recipients: List[RecipientIn] = Field(min_length=1, max_length=MAX_RECIPIENTS)

    @field_validator("course_name")
    @classmethod
    def course_name_must_be_printable(cls, value):
        # The built-in PDF font only supports Latin characters.
        # The course name is the same on every certificate, so reject it up front
        # instead of creating a job where every single certificate fails.
        try:
            value.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("course_name contains characters the certificate font cannot print")
        return value


# ---------- Response (output) ----------

class CertificateOut(BaseModel):
    # from_attributes lets Pydantic read values from database objects
    model_config = ConfigDict(from_attributes=True)

    id: int
    row_number: int
    recipient_name: str
    recipient_email: str
    status: str
    error_message: Optional[str] = None
    download_url: Optional[str] = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_name: str
    issue_date: date
    status: str
    total: int
    successful: int
    failed: int
    processed: int
    created_at: datetime
    download_all_url: Optional[str] = None
    certificates: List[CertificateOut]
