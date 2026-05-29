from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceBase(StrictBaseModel):
    name: str = Field(min_length=1, max_length=255)
    rack_id: int
    device_type: str = Field(min_length=1, max_length=50)
    u_position_start: int | None = None
    u_position_end: int | None = None
    has_ilo: bool = False
    ilo_host: str | None = None
    ilo_profile: str | None = None
    active: bool = True

    @model_validator(mode="after")
    def validate_positions_and_ilo(self) -> "DeviceBase":
        if (
            self.u_position_start is not None
            and self.u_position_end is not None
            and self.u_position_start > self.u_position_end
        ):
            raise ValueError("u_position_start must be less than or equal to u_position_end")
        if self.has_ilo and (not self.ilo_host or not self.ilo_profile):
            raise ValueError("ilo_host and ilo_profile are required when has_ilo is true")
        return self


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(StrictBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    rack_id: int | None = None
    device_type: str | None = Field(default=None, min_length=1, max_length=50)
    u_position_start: int | None = None
    u_position_end: int | None = None
    has_ilo: bool | None = None
    ilo_host: str | None = None
    ilo_profile: str | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def validate_positions_and_ilo(self) -> "DeviceUpdate":
        if (
            self.u_position_start is not None
            and self.u_position_end is not None
            and self.u_position_start > self.u_position_end
        ):
            raise ValueError("u_position_start must be less than or equal to u_position_end")
        if self.has_ilo is True and (not self.ilo_host or not self.ilo_profile):
            raise ValueError("ilo_host and ilo_profile are required when has_ilo is true")
        return self


class DeviceRead(DeviceBase):
    id: int
