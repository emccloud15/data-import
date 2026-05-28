from pydantic import BaseModel


class Settings(BaseModel):
    NAME_MAP_PATH: str
    UNWANTED_FILES_DIR: str
