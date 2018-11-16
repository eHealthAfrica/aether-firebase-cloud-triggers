#!/bin/bash

# args [
    # 1     cloud function name in GCP [RTDB_update_s1]
    # 2     aether_functions import name being referenced [handle_update_RTDB]
    # 3     type of changes even to attach [create / update, etc]
    # 4     instance name of project [aether-kernel-gcp, etc]
    # 5     path being monitored [refs/entities/{entityName}/{entityID}]
    # ]

pushd triggers
echo "from aether_functions import $2 as $1" > main.py
gcloud functions deploy $1 \
  --trigger-event providers/google.firebase.database/eventTypes/ref.$3 \
  --trigger-resource projects/_/instances/$4/$5 \
  --runtime python37
popd