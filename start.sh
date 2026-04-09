#!/usr/bin/env bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT