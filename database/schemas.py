from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ValidationError, field_validator


ALLOWED_CURRENCIES: tuple[str, ...] = (
    "AED",
    "AUD",
    "CAD",
    "CHF",
    "EUR",
    "GBP",
    "INR",
    "JPY",
    "SGD",
    "USD",
)


class RegisterSchema(BaseModel):
    name: str
    display_name: str
    email: str
    default_currency: str
    password: str
    accept_terms: bool

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if len(v) > 120:
            raise ValueError("Name must not exceed 120 characters.")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Display name must be at least 2 characters.")
        if len(v) > 60:
            raise ValueError("Display name must not exceed 60 characters.")
        return v

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        try:
            return validate_email(v.strip(), check_deliverability=False).normalized
        except EmailNotValidError:
            raise ValueError("Please enter a valid email address.")

    @field_validator("default_currency")
    @classmethod
    def validate_default_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ALLOWED_CURRENCIES:
            raise ValueError("Please choose a supported currency.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not (8 <= len(v) <= 72):
            raise ValueError("Password must be 8–72 characters.")
        return v

    @field_validator("accept_terms")
    @classmethod
    def validate_accept_terms(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must accept the Terms of Service and Privacy Policy.")
        return v


class LoginSchema(BaseModel):
    email: str
    password: str
    remember_me: bool = False

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

    @field_validator("remember_me")
    @classmethod
    def validate_remember_me(cls, v: bool) -> bool:
        if not isinstance(v, bool):
            raise ValueError("Invalid remember-me value.")
        return v


def extract_messages(exc: ValidationError) -> list[str]:
    """Return clean user-facing messages from a Pydantic v2 ValidationError."""
    return [err["msg"].removeprefix("Value error, ") for err in exc.errors()]
