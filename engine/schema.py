from pydantic import BaseModel, field_validator


class Section(BaseModel):
    heading: str
    content: str

    @field_validator("heading")
    @classmethod
    def heading_not_empty(cls, v):
        if not v.strip():
            raise ValueError("heading cannot be empty")
        return v.strip()

    @field_validator("content", mode="before")
    @classmethod
    def content_to_string(cls, v):
        if isinstance(v, list):
            return "\n".join(f"- {item}" for item in v)
        return str(v)

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v):
        if not v.strip():
            raise ValueError("content cannot be empty")
        return v.strip()


class Note(BaseModel):
    title: str
    summary: str
    sections: list[Section]

    @field_validator("title", "summary")
    @classmethod
    def not_empty(cls, v):
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v.strip()

    @field_validator("sections")
    @classmethod
    def at_least_one_section(cls, v):
        if not v:
            raise ValueError("at least one section is required")
        return v
