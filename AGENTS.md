# Agent Guidelines & Project Memory: S3 Web Browser

This document serves as the persistent memory and operational guide for AI agents (and human developers) working on the **S3 Web Browser** project.

---

## 1. Project Overview

- **Name:** S3 Web Browser (`s3-web-browser`)
- **Type:** Flask-based web application for browsing AWS S3 and S3-compatible object storage (MinIO, Wasabi, Ceph, etc.).
- **Primary Language:** Python 3.10+ (targeted at Python 3.12).
- **Package & Dependency Manager:** Poetry (`pyproject.toml`).
- **Production Server:** Gunicorn (`0.0.0.0:8000`).
- **UI Framework:** Material Design 3 (M3) CSS tokens, Jinja2 templates, Vanilla JavaScript, SweetAlert2.

---

## 2. Architecture & Directory Map

```
s3-web-browser/
├── config.py                     # Flask Config (SECRET_KEY, DEBUG, SQLALCHEMY_DATABASE_URI, PAGE_ITEMS)
├── run.py                        # Local development entrypoint (runs app on 0.0.0.0:8000)
├── pyproject.toml                # Poetry dependencies, packaging metadata, and Ruff linter config
├── Dockerfile                    # Multi-stage production container running Gunicorn on Python 3.12 Bookworm
├── Makefile                      # Standard build automation (install, cq, test, clean, release)
├── instance/                     # Local SQLite DB location (created automatically on startup)
│   └── connections.db            # SQLite database file storing S3 connection credentials
├── s3_web_browser/               # Main application package
│   ├── __init__.py               # Flask application factory (create_app), initializes DB and routes
│   ├── models.py                 # SQLAlchemy models (Connection) & Boto3 configuration helper
│   ├── routes.py                 # HTTP routes and view controllers (CRUD connections, browse, search, upload, download, zip, size)
│   ├── s3.py                     # S3 abstraction helpers (S3Entry dataclass, list_objects, parse_responses)
│   ├── static/                   # Static assets (banner.jpg)
│   └── templates/                # Jinja2 HTML templates
│       ├── base.html             # Base layout with M3 styling, light/dark theme toggle, loading overlays
│       ├── index.html            # Connections dashboard
│       ├── connection_form.html  # Create/Edit S3 connection form
│       ├── buckets.html          # Bucket grid listing for a selected connection
│       ├── bucket_contents.html  # File/folder browser, breadcrumbs, search, upload, download, size calc
│       └── error.html            # Error display template
└── docs/                         # Documentation assets & screenshots
```

---

## 3. Core Components & Technical Details

### 3.1. Connection Management & Persistence
- **Storage:** SQLite via Flask-SQLAlchemy (`s3_web_browser/models.py`).
- **Path:** Defaults to `instance/connections.db`.
- **Auto-creation:** The application factory (`create_app` in `s3_web_browser/__init__.py`) automatically creates the `instance/` folder if it does not exist, and executes `db.create_all()`.
- **Model:** `Connection`
  - `id`: Primary key.
  - `name`: Unique connection name.
  - `endpoint_url`: Optional custom endpoint URL (for MinIO, Wasabi, LocalStack, etc.).
  - `access_key_id`: S3 access key ID.
  - `secret_access_key`: S3 secret access key.
  - `region`: AWS region (defaults to `eu-central-1`).
  - `default_bucket`: Optional default bucket name.
- **Important Note:** Legacy `.env` and `AWS_*` environment variables were deprecated and removed in v1.2.0. All connection credentials are now stored in `instance/connections.db`.

### 3.2. Boto3 Configuration & Addressing Style
- `Connection.to_boto3_kwargs()` configures:
  - `signature_version="s3v4"`
  - `s3={"addressing_style": "path"}`
  - Optional `endpoint_url`.
- This ensures compatibility with both standard AWS S3 and third-party S3-compatible storage providers (Ceph, MinIO).

### 3.3. S3 Navigation & Operations
- **Delimiter:** Trailing slash `/` is used as delimiter for folder hierarchies.
- **Pagination:** Uses S3 `list_objects_v2` with `PaginationConfig={"PageSize": items_per_page}` and continuation tokens (`NextContinuationToken`).
- **Search:** Recursively queries `list_objects_v2` across all pages (without delimiter for contents, with delimiter for prefixes), then performs case-insensitive substring matching in memory.
- **Folder Size Calculation:** Triggered on-demand via UI AJAX call (`/c/<id>/size/buckets/<bucket_name>/<path>`). Uses `ThreadPoolExecutor(max_workers=10)` to calculate prefix sizes in parallel.
- **File Upload:** Handled via multipart form POST (`request.files["file"]`) with `s3_client.upload_fileobj`. Supports drag-and-drop with sequential client uploads.
- **File Download:** Streaming chunked download (4KB chunks) via `s3_object["Body"].iter_chunks()`.
- **Folder ZIP Download:** Downloads all objects under prefix, compresses them on the fly into a `tempfile.NamedTemporaryFile`, and serves as a ZIP attachment. Sets `download_started=1` cookie for client UI polling.

---

## 4. Coding Standards & Linter Guidelines

The project enforces strict code quality via **Ruff** configured in `pyproject.toml`.

1. **Imports:**
   - **NO RELATIVE IMPORTS**: `ban-relative-imports = "all"` is enforced. Always use absolute imports:
     ```python
     # Correct:
     from s3_web_browser.models import Connection, db
     # Incorrect:
     from .models import Connection
     ```
   - Imports must be sorted according to `isort` rules (enforced by Ruff).

2. **Docstrings & Comments:**
   - Public classes and methods require docstrings.
   - Multi-line summary format: double quotes (`"""`).

3. **Function Complexity & Signatures:**
   - Max cyclomatic complexity: 10 (`mccabe`).
   - Max statements: 80, max branches: 20 (`pylint`).
   - Use explicit type annotations for parameters and return types.

4. **Formatting:**
   - Line length: 120 characters.
   - Double quotes for strings and docstrings.

---

## 5. Development & Execution Runbook

### Local Development
```bash
# Install dependencies
poetry install

# Run linters and auto-fixes
poetry run ruff format .
poetry run ruff check --unsafe-fixes --fix .

# Start development server
poetry run python run.py
# Access at http://localhost:8000
```

### Docker Usage
```bash
# Build Docker image
docker build -t s3-web-browser .

# Run container with persistent database mount (CRITICAL: instance directory must be mounted)
docker run -it --rm -p 8000:8000 -v ${PWD}/instance:/usr/src/app/instance s3-web-browser
```

---

## 6. Key Gotchas & Future Agent Instructions

1. **Docker Persistence:** Always mount `-v ${PWD}/instance:/usr/src/app/instance`. If this directory is not mounted, all saved connections will be lost upon container restart.
2. **Restricted IAM Credentials:** If an S3 credential does not have `s3:ListAllMyBuckets` permissions, users must configure `default_bucket` on the connection. The route `/c/<id>/buckets` automatically redirects straight to `view_bucket` when `default_bucket` is present.
3. **Large Bucket Search Performance:** Searching from the root of a massive S3 bucket paginates through all keys and can be slow. Keep this in mind when debugging timeouts or optimizing search.
4. **Testing Suite:** `Makefile` references `pytest`, but a dedicated `tests/` directory has not been populated yet. When adding features or refactoring, prioritize adding pytest unit tests for routes and S3 parsing.
