from dotenv import load_dotenv
import os

from sqlalchemy import create_engine, Inspector

load_dotenv()

def engine_creation(default_schema: str | None):
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", '5432')
    database = os.getenv("DB_NAME")
    schema = default_schema
    
    return create_engine(
        f'postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}',
        connect_args={'options': f'-c search_path={schema}'}
    )
def get_table_name(engine):
    inspector = Inspector(engine)
    return inspector.get_table_names()
    

