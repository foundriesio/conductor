#!/bin/bash

LOGLEVEL=INFO
WORKER_CLASS="sync"
WORKERS=4

# start websocket server
conductor-ws -v 1 &

# start worker
conductor-worker --loglevel "$LOGLEVEL" -D

# start webserver
conductor-admin migrate
conductor-admin collectstatic --noinput
/usr/bin/gunicorn conductor.wsgi --log-level "$LOGLEVEL" --worker-class "$WORKER_CLASS" --workers "$WORKERS" --bind=0.0.0.0

