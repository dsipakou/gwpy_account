from datetime import datetime
from uuid import UUID

import pydantic


class UserSchema(pydantic.BaseModel):
    uuid: UUID
    currency_code: str | None = pydantic.Field(default=None)
    email: str
    first_name: str | None
    last_name: str | None
    username: str
    role: str | None = pydantic.Field(default=None)
    is_active: bool
    is_staff: bool
    date_joined: datetime
