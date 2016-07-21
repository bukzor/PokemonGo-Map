#!/usr/bin/env bash
set -ex
rm -rf venv
virtualenv venv
venv/bin/pip install -r requirements.txt
