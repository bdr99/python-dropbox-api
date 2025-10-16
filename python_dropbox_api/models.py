from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, kw_only=True)
class UploadSessionStartResponse:
    """Response from upload session start."""

    session_id: str


@dataclass(frozen=True, kw_only=True)
class PropertyField:
    """A field in a property template."""

    name: str
    description: str
    type: Literal["string", "number", "boolean", "date", "list", "multi_select"]


@dataclass(frozen=True, kw_only=True)
class PropertyTemplate:
    """A property template for files and folders."""

    name: str
    description: str
    fields: list[PropertyField]


@dataclass(frozen=True, kw_only=True)
class PropertyTemplateResponse:
    """Response from creating a property template."""

    template_id: str


@dataclass(frozen=True, kw_only=True)
class PropertyTemplateGetResponse:
    """Response from getting a property template."""

    name: str
    description: str
    fields: list[PropertyField]


@dataclass(frozen=True, kw_only=True)
class PropertyFieldValue:
    """A field value in a property group."""

    name: str
    value: str


@dataclass(frozen=True, kw_only=True)
class PropertyGroup:
    """A property group containing fields."""

    fields: list[PropertyFieldValue]
    template_id: str


@dataclass(frozen=True, kw_only=True)
class FileOrFolderInfo:
    """File information."""

    is_folder: bool
    name: str
    size: int | None
    property_groups: list[PropertyGroup] | None


@dataclass(frozen=True, kw_only=True)
class AccountInfo:
    """Info about an account."""

    account_id: str
    email: str
    display_name: str
