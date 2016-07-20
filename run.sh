#!/usr/bin/env bash
exec ./venv/bin/python example.py \
    --username asottileyelp \
    --location '140 new montgomery, san francisco, ca' \
    --step-limit 3 \
    --auto_refresh 10 \
    --ignore zubat \
    --zoom 15 \
    --host 0.0.0.0 \
    --port 5000 \
