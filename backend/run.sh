#!/usr/bin/env bash
export $(grep -v '^#' .env 2>/dev/null | xargs -I {} echo {}) >/dev/null 2>&1 || true
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
