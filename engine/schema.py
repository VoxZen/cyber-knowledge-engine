from pydantic import BaseModel, field_validator, model_validator


class Section(BaseModel):
    heading: str
    content: str

    @model_validator(mode="before")
    @classmethod
    def accept_title_as_heading(cls, data):
        if isinstance(data, dict):
            if "heading" not in data and "title" in data:
                data["heading"] = data["title"]
            if "content" not in data and "body" in data:
                data["content"] = data["body"]
        return data

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

    @model_validator(mode="before")
    @classmethod
    def fill_missing_summary(cls, data):
        if isinstance(data, dict):
            if not data.get("summary") and data.get("title"):
                data["summary"] = data["title"]
        return data

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
