"""References to related records, shared by several schemas."""

from pydantic import BaseModel, ConfigDict


class Ref(BaseModel):
    """Id and name of a related record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SupplierRef(Ref):
    """A factory or lab."""

    country: str
    city: str | None = None


class ProductRef(Ref):
    """A product."""

    cas_number: str | None = None


class CustomerRef(Ref):
    """A customer."""

    country: str
    industry: str | None
