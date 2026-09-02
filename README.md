# S3 Web Browser

[![Python version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
![Last Commit](https://img.shields.io/github/last-commit/romanzdk/s3-web-browser)
[![GitHub stars](https://img.shields.io/github/stars/romanzdk/s3-web-browser.svg)](https://github.com/romanzdk/s3-web-browser/stargazers)

![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![AWS S3](https://img.shields.io/badge/AWS_S3-569A31?style=for-the-badge&logo=amazon-s3&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

S3 Web Browser is a Flask-based web application that allows users to browse AWS S3 buckets and their contents via a simple web interface. It leverages Boto3, AWS's SDK for Python, to interact with S3.

![S3 web browser page preview](docs/image.png)

![S3 web browser page preview](docs/image-1.png)

![S3 web browser page preview](docs/image-2.png)

## Features

- **Multiple Connections Manager**: Store and manage multiple S3 credentials securely in a local database.
- **List S3 Buckets**: View all S3 buckets available to a specific connection in a card-based grid layout.
- **Default Buckets**: Configure a default bucket to bypass global listing for environments with restricted permissions.
- **Browse Bucket Contents**: Navigate through folders and files with breadcrumb navigation.
- **Search Bucket Contents**: Recursively search for files and folders within any bucket or subdirectory (case-insensitive).
- **Generate Presigned URLs**: Securely download S3 objects via temporary 1-hour presigned URLs. Maximum compatibility with S3v4 signatures and path-style addressing for Ceph/MinIO support.
- **Pagination**: Browse large buckets efficiently with configurable page sizes.
- **Copy S3 Paths**: One-click copy of S3 paths (`s3://bucket/key`) to clipboard.
- **Responsive UI**: Modern interface with loading indicators and smooth navigation.

## Configuration

While AWS credentials are now primarily configured securely through the web UI and saved to a local SQLite database, application settings are configured via environment variables (or a `.env` file):

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `your_default_secret_key` | Flask session secret key |
| `DEBUG` | `False` | Flask debug mode |
| `PAGE_ITEMS` | `300` | Items per page |
| `SQLALCHEMY_DATABASE_URI` | `sqlite:///connections.db` | Database URI for storing connections (Defaults to `instance/connections.db`) |

*Note: The old `AWS_*` environment variables are deprecated as connection credentials are now managed dynamically from the UI.*

## Run

### Docker (pre-built image)

```bash
# Mount the instance directory to persist your database!
docker run -it --rm -p 8000:8000 -v ${PWD}/instance:/usr/src/app/instance romanzdk/s3-web-browser
```

### Docker (build locally)

1. `mkdir -p instance`
2. `docker build -t s3-browser .`
3. `docker run -it --rm -p 8000:8000 -v ${PWD}/instance:/usr/src/app/instance s3-browser`
4. Open http://127.0.0.1:8000/

## Development

1. Install dependencies: `poetry install`
1. Export AWS credentials:
   ```bash
   export AWS_ACCESS_KEY_ID="your_access_key_id"
   export AWS_SECRET_ACCESS_KEY="your_secret_access_key"
   ```
1. Run code quality checks: `make cq`
1. Run tests: `make test`
1. Start the app: `poetry run python run.py`
1. Open http://127.0.0.1:8000/

### Makefile targets

| Target | Description |
|---|---|
| `make install` | Install dependencies via Poetry |
| `make cq` | Run linter and formatter (Ruff) |
| `make test` | Run tests |
| `make all` | Install, lint, and test |
| `make clean` | Remove temporary files |
| `make release VERSION=x.y.z` | Build and push Docker images |

## Related

- [S3 Commander](https://github.com/romanzdk/s3-commander) — Total Commander-style dual-pane S3 file browser with server-side move/copy.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- Flask for providing the web framework.
- AWS Boto3 for interfacing with Amazon S3.
