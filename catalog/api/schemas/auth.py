"""Bounded inputs retaining legacy aliases supported by the authentication API."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: StrictStr | None = Field(default=None, max_length=254)
    login: StrictStr | None = Field(default=None, max_length=254)
    password: StrictStr | None = Field(default=None, max_length=1024)
    token: StrictStr | None = Field(default=None, max_length=1024)


class PasswordResetInput(LoginInput):
    reset_code: StrictStr | None = Field(default=None, max_length=128)
    code: StrictStr | None = Field(default=None, max_length=128)
    new_password: StrictStr | None = Field(default=None, max_length=1024)
