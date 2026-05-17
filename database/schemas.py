import re

from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, ValidationError, field_validator

_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,72}$'
)


class RegisterSchema(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if len(v) > 120:
            raise ValueError("Name must not exceed 120 characters.")
        return v

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        try:
            return validate_email(v.strip(), check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Please enter a valid email address.")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be 8–72 characters and include an uppercase letter, "
                "a lowercase letter, a digit, and a special character (@$!%*#?&)."
            )
        return v


class LoginSchema(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        try:
            return validate_email(v.strip(), check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Invalid email format.")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password is required.")
        return v


def extract_messages(exc: ValidationError) -> list[str]:
    """Return clean user-facing messages from a Pydantic v2 ValidationError."""
    return [
        err["msg"].removeprefix("Value error, ")
        for err in exc.errors()
    ]
