import yaml
import sys
import os
import pandas as pd
import io
import re
import math

import questionary
import click

from pandas.io.parsers import TextFileReader
from psycopg2 import sql
from sqlalchemy.exc import ArgumentError

from abc import ABC, abstractmethod

from pathlib import Path 
import shutil

from db import engine_creation, get_table_name
from exceptions import UserExit
from models import Settings

from logger import get_logger
logger = get_logger(__name__)

class BaseImport(ABC):
    def __init__(self, raw_data_path: Path, import_data_path: Path, schema: str, client: str):
        
        try:
            self.settings = self.init_settings('settings.yaml')
        except ValueError as e:
            raise ValueError(f"Error loading settings: {e}")
        
        repo_root = Path(__file__).resolve().parent
        self.client_name_map_filepath = repo_root / Path(self.settings.NAME_MAP_PATH_TEST)
        self.unwanted_files_dir = repo_root / Path(self.settings.UNWANTED_FILES_DIR)
        self.unwanted_files_dir.mkdir(exist_ok=True)
        

        self.client_map_df = self.load_data(self.client_name_map_filepath)
        self.client = self.verify_client(client)
        
        self.schema = schema
        try:
            self.engine = engine_creation(self.schema)
        except ArgumentError as e:
            raise ArgumentError(f"Database configuration error: {e}")
        
        self.raw_data_dir = raw_data_path

        self.import_dir = import_data_path
        Path.mkdir(self.import_dir, exist_ok=True)

        

        self.remove_empty_files()


    def init_settings(self, settings_path: str) -> Settings:
        with open(settings_path, 'r') as f:
            data = yaml.safe_load(f)
            return Settings(**data)
        
    def load_data(self, file: Path) -> pd.DataFrame:
        if file.suffix != '.csv':
            raise ValueError(f"Expected a .csv file, got {file.suffix}")
        return pd.read_csv(file, encoding='latin1', encoding_errors='ignore', low_memory=False)
         
    def load_client_name_dict(self) -> None:
        mask = self.client_map_df[self.client]
        self.name_map = self.client_map_df.loc[mask][['SF','New']].set_index('SF')['New'].to_dict()

    def verify_client(self, client: str) -> str:
        
        if client in self.client_map_df.columns:
            return client
        else:
            while True:
                print(f"{client} not found. Current clients in the mapping are:")
                for i, name in enumerate(self.client_map_df.columns[2:], start=1):
                    print(f"{i}: {name}")
                print(f"Would you like to add {client} as a new client?")
                choice = input(f"Type 1 or 2.\n1. Yes add {client} as a new client.\n2. Do not add {client} and exit.\n")
                if choice == '1':
                    self.client_map_df.loc[:,client] = True
                    self.update_client_name_map_file()
                    return client
                elif choice == '2':
                    raise UserExit("User chose to exit program")
                else:
                    print("Invalid choice, please enter 1 or 2")
    
    def remove_empty_files(self) -> None:
        self.raw_files = list(Path(self.raw_data_dir).iterdir())
        with click.progressbar(self.raw_files, label="Removing empty files") as bar:
            for file in bar:
                if file.name.startswith('.') or file.suffix != '.csv':
                    file.unlink()
                else:
                    with file.open('rb') as f:
                        try:
                            next(f)
                            second_line = f.readline()
                            if not second_line.strip():
                                file.unlink()
                            else:
                                shutil.copy2(file, self.import_dir)
                        except StopIteration:
                            file.unlink()
                      
    def update_client_name_map_file(self) -> None:
        self.client_map_df.to_csv(self.client_name_map_filepath, index=False)
    
    def safe_identifier(self, name: str) -> str:
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(f"Invalid identifier: {name}")
        return name

    def files_to_sql(self, table_name: str, chunk: pd.DataFrame, mode: str | None = None) -> None:

      
        buffer = io.StringIO()
        chunk.to_csv(buffer, index=False, header=False)
        cleaned = buffer.getvalue().replace('\x00', '')
        buffer = io.StringIO(cleaned)
        buffer.seek(0)
       

        with self.engine.raw_connection() as conn:
            cur = conn.cursor()
            try:
                if mode == 'replace':
                    cur.execute(
                        sql.SQL("truncate table {};").format(
                        sql.Identifier(self.schema, table_name)
                    ))
                cur.copy_expert(f"copy {self.safe_identifier(self.schema)}.{self.safe_identifier(table_name)} from stdin with csv null ''", buffer)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    def import_data_to_db(self) -> None:
        self.import_files = list(Path(self.import_dir).iterdir())
     
        for file in self.import_files:
            if file.name.startswith("."):
                continue
            
            chunksize = 50000
            file_size_bytes = os.path.getsize(file)
            estimated_row_size = 400  # Average bytes per row for a standard Salesforce CSV
            estimated_total_rows = file_size_bytes / estimated_row_size
            total_chunks = max(1, math.ceil(estimated_total_rows / chunksize))
            
            mode = questionary.select(
                        f'\nImport mode for {file.stem}:',
                        choices=['replace','append',f'skip importing {file.stem}']).ask()
            if mode is None:
                raise KeyboardInterrupt
            elif mode == f'skip importing {file.stem}':
                continue
            else:
                confirm = questionary.confirm(f"Are you sure you would like to {mode} the data?").ask()
                if confirm:
                    with open(file, mode='r', encoding='latin1', errors='ignore') as f:
                        chunks = pd.read_csv(f, chunksize=chunksize, encoding='latin1', engine='python')
                        with click.progressbar(chunks, length=total_chunks, label=f"Importing {file.stem}", show_percent=True) as bar:
                            for i, chunk in enumerate(bar):
                                current_chunk_mode = mode if i == 0 else None
                                self.files_to_sql(table_name=file.stem, chunk=chunk, mode=current_chunk_mode)
                                bar.update(1)
                                sys.stdout.flush()
                        click.echo(f"{file.stem} Imported")
                else:
                    continue
    
    def create_db_tables(self, files: list[Path]) -> None:
        with click.progressbar(files, label="Creating new tables") as bar:
            for file in bar:
                if file.name.startswith("."):
                    continue
                else:
                    df = pd.read_csv(file, nrows=0, encoding='latin1', engine='python')
                    df.columns = df.columns.str.strip().str.lower()
                    with self.engine.begin() as conn:
                        try:
                            df.to_sql(file.stem, con=conn, schema=self.schema, if_exists='fail', index=False)
                        except ValueError:
                            logger.warning(f"\n{file.stem} Already exists in the database. Skipping without creating a new table")
                            continue
    
    @abstractmethod
    def rename_files(self):
        pass  
    
    @abstractmethod
    def run(self):
        pass                  
        
class Import1(BaseImport):
    def __init__(self, raw_data_path: Path, import_data_path: Path, client: str, schema: str):
        super().__init__(raw_data_path, import_data_path, schema, client)
    
    def create_new_name(self, file: Path) -> None:
        while True:
            click.echo(f"{file.name} does not exist in the name map.")
            choice = questionary.select(
                "Would you like to add a new name mapping?",
                choices=['Yes', 'No', 'View Contents']).ask()

            if not choice:
                raise KeyboardInterrupt
            if choice == 'Yes':
                while True:
                    new_name = questionary.text(f"\nEnter the new name for {file.name}: \n").ask()
                    choice = questionary.select(f"Confirm this is correct.\n Old name: {file.stem}\n New name: {new_name}", choices=['Yes', 'No', 'Cancel Rename']).ask()
                    if choice == 'Yes': 
                        new_path = self.import_dir / Path(new_name).with_suffix(".csv")
                        file.rename(new_path)
                        # Adds the new name row to the dataframe
                        new_name_dict = {'SF':file.stem,'New':new_name}
                        new_row = pd.DataFrame([new_name_dict])
                        self.client_map_df = pd.concat([self.client_map_df,new_row], ignore_index=True)                        

                        # Sets the current corresponding client column to True and the others to False. 
                        # This is for test 2 when we reimport new data. So only the files from sales force that were actually used are imported to the db
                        mask = self.client_map_df['SF'] == file.stem
                        self.client_map_df.loc[mask, self.client] = True
                        self.client_map_df.loc[mask, ~self.client_map_df.columns.isin(['SF','New',self.client])] = False
                        return
                    elif choice == 'Cancel Rename':
                        break
            elif choice == 'No':
                new_path = self.unwanted_files_dir / Path(file.name)
                file.rename(new_path)
                return
            elif choice == 'View Contents':
                file_df = self.load_data(file)
                with pd.option_context('display.max_columns', None, 'display.max_colwidth', None):
                    click.echo(file_df.head(10))
            else:
                raise KeyboardInterrupt
             
    def rename_files(self) -> None:
        
        # Load fresh file name mapping data into name hashmap
        self.load_client_name_dict()
        self.import_files = list(Path(self.import_dir).iterdir())
        current_renames = self.client_map_df['New'].to_list()
        for file in self.import_files:
            if file.name.startswith('.'):
                continue
            if file.stem in current_renames:
                continue
            new_name = self.name_map.get(file.stem)

            if new_name:
                new_path = self.import_dir / Path(new_name).with_suffix(".csv")
                file.rename(new_path)

            else:
                self.create_new_name(file)
        
        # Save changes to name mapping file. Name hashmap is now stale if any updates have been made to the file
        self.update_client_name_map_file()

    def run(self):
        self.rename_files()
        self.import_files = (list(Path(self.import_dir).iterdir()))
        self.create_db_tables(self.import_files)
        choice = questionary.confirm("Files are ready to be imported. Continue to import?").ask()
        if choice:
            self.import_data_to_db()
            click.echo("All files imported to the databse!\nExiting...")
        else:
            raise UserExit("Import skipped. Exiting...")
        
class Import2(BaseImport):
    def __init__(self, raw_data_path: Path, import_data_path: Path, schema: str, client: str):
        super().__init__(raw_data_path, import_data_path, schema, client)

        self.table_names = get_table_name(self.engine)


    def update_client_file_status(self) -> None:

        mask = self.client_map_df['New'].isin(self.table_names)
        self.client_map_df.loc[mask, self.client] = True
        self.client_map_df.loc[~mask, self.client] = False

        self.update_client_name_map_file()
        
    
    def rename_files(self) -> None:

        self.load_client_name_dict()
        self.import_files = list(Path(self.import_dir).iterdir())
        for file in self.import_files:
            new_name = self.name_map.get(file.stem)
            if new_name:
                new_path = self.import_dir / Path(new_name).with_suffix('.csv')
                file.rename(new_path)
            else:
                new_path = self.unwanted_files_dir / Path(file.name)
                file.rename(new_path)
        self.table_names_check = [t for t in self.table_names if t not in [f.stem for f in self.import_files]]

        if self.table_names_check:
            logger.warning("Some tables in the schema were not found in the export")
            for i, t in enumerate(self.table_names_check, start=1):
                click.echo(f"Table {i}: {t}")

    def run(self):
        self.update_client_file_status()
        self.rename_files()
        choice = questionary.confirm("Files are ready to be imported. Continue to import?").ask()
        if choice:
            self.import_data_to_db()
        else:
            raise UserExit("Import skipped. Exiting...")
    


    
@click.command()
@click.option("--data", type=click.Path(exists=True), prompt='Path to raw data')
@click.option("--testdir", required=True, type=click.Path(file_okay=False, dir_okay=True, path_type=Path), prompt='Path to import test directory')
@click.option("--stage", type=click.Choice(['1','2']), prompt='Test 1 or 2')
@click.option("--client", type=str, prompt="Migration Client")
@click.option("--schema", type=str, prompt="DB Schema")

def main(data, testdir, stage, client,schema):

    try:
        if stage == '1':
            import1 = Import1(raw_data_path=Path(data), import_data_path=Path(testdir), client=client, schema=schema)
            import1.run()
        else:
            import2 = Import2(raw_data_path=Path(data), import_data_path=Path(testdir), client=client, schema=schema)
            import2.run()
    except ValueError as e:
        click.echo(f"Error loading data: {e}")
    except FileNotFoundError as e:
        click.echo(f"Name map file not found: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("Exiting...")
        sys.exit(0)
    except UserExit as e:
        click.echo(e)
        sys.exit(0)
    
    



if __name__ == '__main__':
    main()