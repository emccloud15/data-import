# DATA IMPORT TOOL

Automates Salesforce data exports into a data warehouse — reducing hours of manual file sorting across 600+ files down to a single command.

Built to solve a real operational bottleneck in nonprofit CRM migrations. Salesforce exports are messy by nature: hundreds of files, inconsistent naming across clients, and a tedious manual process that had to be repeated for every migration test cycle. This tool eliminates that entirely.

---

## Key Features

- **Automated file filtering** — scans 600+ raw Salesforce export files and moves only files containing relevant data, eliminating manual sorting entirely
- **Persistent name mapping** — maintains a growing Excel-based map of every Salesforce file name seen across all migrations, translating them to a consistent internal naming convention. Gets smarter with every migration
- **Per-client file tracking** — tracks which files are actively used per client via a T/F flag, so Stage 2 re-imports only process relevant files without any manual intervention
- **Interactive new file handling** — unknown files are surfaced one at a time with options to add, preview, or discard — keeping the map up to date automatically
- **Flexible import modes** — choose between replace or append per import to support both fresh and incremental data loads

---

### Prerequisites
Install [uv](https://astral.sh/uv) before proceeding.

**MacOS & Linux**
```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

**Windows**
```bash
winget install astral-sh.uv
```

Restart your terminal after installing.

### Install

```bash
git clone https://github.com/emccloud15/data-import.git
cd data-import
uv tool install .
uv tool update-shell
```

### Configure

1. Create your `.env` file and fill in your database credentials:
```bash
cp .env.example .env
open .env
```

2. Connect to OpenVPN or your data warehouse VPN before running the tool.

3. Configure the name map path in `settings.yaml`:
```yaml
NAME_MAP_PATH: data_maps/salesforce_filename_map.csv
UNWANTED_FILES_DIR: data_maps/unwanted_files
```

The name map is a CSV that tracks every Salesforce file name seen across all migrations and maps it to a consistent internal naming convention. It grows automatically as new files are encountered and should not need to be edited manually beyond initial setup.

The tool can be run from anywhere in your terminal once installed.

---

## Usage

```bash
data-import --data <path> --testdir <path> --stage <1|2> --client <name> --schema <schema>
```

| Flag | Description |
|------|-------------|
| `--data` | Path to the raw Salesforce export directory |
| `--testdir` | Output directory for renamed files. Created automatically if it doesn't exist |
| `--stage` | `1` for first import (Test 1), `2` for re-import (Test 2) |
| `--client` | Client name — used for file name mapping. New clients will be prompted for setup |
| `--schema` | Database schema to import tables into |

---

## How It Works

Salesforce exports are notoriously messy — heavily customized file names, hundreds of irrelevant files, and no consistent naming convention across clients. The previous manual process required sifting through upwards of 600 files by hand to find relevant ones, then repeating the entire process for each test cycle. This tool eliminates that by maintaining a persistent file name mapping sheet (Excel) that grows with every migration, tracking every Salesforce file name ever seen and mapping it to a consistent Cedarstone naming convention.

### Stage 1 — First Import (Test 1)

1. Export all data from Salesforce
2. Run the tool pointing `--data` at the export directory
3. Tool scans the directory and moves only files containing data to `--testdir`
4. File name map is loaded — if the client is new, a new column is created with all values set to `T`
5. A hashmap of Salesforce → Cedarstone file names is built for all files marked `T` for the client
6. Files in `--testdir` are renamed using the hashmap
7. Any unseen files are presented one at a time with three options:
   - **Add** — add to the name map with a new Cedarstone name
   - **View** — inspect the file contents
   - **Remove** — move to the unwanted files directory (`data_maps/`)
8. Tables are created in the database for every renamed file (existing tables are skipped)
9. Choose import mode:
   - **Replace** — clears existing table data and imports fresh
   - **Append** — adds new data to existing table data

After Stage 1, drop any tables that turn out to be irrelevant and set their mapping value to `F` for the client. This speeds up Stage 2 by skipping those files entirely.

### Stage 2 — Re-import (Test 2)

Same process as Stage 1 with two differences:
- Only files marked `T` for the current client are renamed and imported
- No new file prompts

> ⚠️ **Warning:** Choose your import mode carefully in Stage 2. **Replace** deletes all Stage 1 data and replaces it. **Append** adds Stage 2 data on top of Stage 1 data. Both can cause data loss or duplication if used incorrectly.

### Future Updates

I will be adding a tracker for files that are consistently irrelavent so as to remove from the review stage entirely if a file is known to always contain data but be irrelavent to any migration. 