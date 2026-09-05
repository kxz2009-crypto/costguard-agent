"""CostGuard Core — Local AI Usage Intelligence Agent (MVP v0.1).

Privacy boundary (CG-PRIVACY-MODEL-001 / CG-LOCAL-SECURITY-HARDENING-001):
- Reads ONLY whitelisted metadata columns from local AI-tool databases.
- Never reads: prompt, response, source code, documents, API keys.
- All source databases are opened read-only (SQLite URI mode=ro).
- Local database lives at ~/.costguard/costguard.db with 0600 permissions.
"""

__version__ = "0.1.0"
