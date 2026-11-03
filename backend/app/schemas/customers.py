"""Customer schemas and reference data for the forms."""

from pydantic import BaseModel, Field

from app.schemas.common import CustomerRef, ProductRef


class CustomerCreate(BaseModel):
    """Request to add a customer."""

    name: str = Field(min_length=1, max_length=255)
    country: str = Field(min_length=1, max_length=64)
    industry: str | None = Field(default=None, max_length=64)


class ReferenceData(BaseModel):
    """Customers the user may see and all products."""

    customers: list[CustomerRef]
    products: list[ProductRef]
