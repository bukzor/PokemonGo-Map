#!/usr/bin/env bash
set -ex
rm -rf venv
virtualenv venv -ppython2.7
venv/bin/pip install -r requirements.txt
