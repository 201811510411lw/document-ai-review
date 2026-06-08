# ai-service

`ai-service` is the pure Python service for `document-ai-review` V1. The first skeleton exposes the FastAPI application and a health check endpoint only.

## Scope

- FastAPI owns the HTTP API boundary.
- LangGraph, LangChain, the Python rule engine, and persistence layers are represented as module boundaries for later issues.
- This skeleton does not implement OCR review creation, field extraction, LangGraph workflow nodes, LangChain calls, rules, or database persistence.
- Java, Spring Boot, and `backend-java` are not part of V1.

## Install

From this directory:

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pip install -r requirements.txt
```

## Run

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected shape:

```json
{
  "status": "ok",
  "service": "ai-service",
  "version": "v1",
  "timestamp": "2026-06-08T14:30:00+08:00"
}
```

## Test

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pytest tests/test_health.py
```
