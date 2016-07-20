#!/usr/bin/env bash
set -ex
SAN_MATEO_CALTRAIN='37.5678222,-122.3259203'
exec ./venv/bin/python example.py \
    --username asottilehome \
    --location $SAN_MATEO_CALTRAIN \
    --step-limit 5 \
    --auto_refresh 10 \
    --ignore zubat,rattata,pidgey,doduo,weedle,caterpie \
    --zoom 16 \
    --host 0.0.0.0 \
    --port 5000
