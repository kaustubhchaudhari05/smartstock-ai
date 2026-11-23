from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

# Simple structural check; avoids an extra dependency (email-validator) for now.
Email = Annotated[
    str,
    Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    AfterValidator(str.lower),
]
Name = Annotated[str, Field(min_length=1, max_length=255)]
Phone = Annotated[str, Field(max_length=50)]
LeadTime = Annotated[int, Field(ge=0, le=365)]


class SupplierCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Name
    email: Email
    phone: Phone | None = None
    address: str | None = None
    lead_time_days: LeadTime


class SupplierUpdate(BaseModel):
    """Partial update. Set is_active=false to deactivate (suppliers are never deleted)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Name | None = None
    email: Email | None = None
    phone: Phone | None = None
    address: str | None = None
    lead_time_days: LeadTime | None = None
    is_active: bool | None = None

    @field_validator("name", "email", "lead_time_days", "is_active")
    @classmethod
    def not_null(cls, value):
        # Only phone and address may be cleared with an explicit null.
        if value is None:
            raise ValueError("may not be null")
        return value


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    address: str | None
    lead_time_days: int
    is_active: bool
