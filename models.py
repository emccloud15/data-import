from pydantic import BaseModel


class Settings(BaseModel):
    NAME_MAP_PATH: str
    NAME_MAP_PATH_TEST: str
    UNWANTED_FILES_DIR: str
