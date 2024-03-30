from datetime import datetime
from typing import Optional
from uuid import UUID
import pydantic


class UserSchema(pydantic.BaseModel):
    uuid: UUID
    currency_code: Optional[str] = pydantic.Field(default=None)
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    username: str
    role: Optional[str] = pydantic.Field(default=None)
    is_active: bool
    is_staff: bool
    date_joined: datetime
