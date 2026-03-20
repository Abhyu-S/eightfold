#!/bin/bash
export PYTHONPATH=$(pwd)
python backend/test_pipeline.py "$@"
