# Gemini & Antigravity Agent Guidelines

This workspace uses [AGENTS.md](file:///Z:/Projects/WebsiteProjects/s3-web-browser/AGENTS.md) as the unified memory and specification document.

Please review [AGENTS.md](file:///Z:/Projects/WebsiteProjects/s3-web-browser/AGENTS.md) for full architecture details, directory layout, code quality rules, and development instructions.

### Quick Reference Rules
- **Import Style:** Strict absolute imports only (`from s3_web_browser... import ...`). Relative imports are banned by Ruff (`ban-relative-imports = "all"`).
- **Linter:** Code must pass `ruff check .` with target version Python 3.12 and line length 120.
- **Persistence:** Connections are stored in `instance/connections.db` (SQLite). Never reintroduce `.env` for AWS credentials.
- **Addressing Style:** S3 client must use `s3v4` signature and path-style addressing for S3-compatible endpoints.
