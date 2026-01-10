#!/bin/bash

if [ $UID -ne 0 ]; then
  echo "Not root. Using sudo."
  exec sudo $0
fi

#sets the username of the system, supervisord does not have a login
#so we need to use the who command. 
HOMENAME=`who | head -n1 | cut -d " " -f1`

export HOME="/root"
export PYTHONPATH="/home/$HOMENAME/psmoveapi/build/"

echo "Starting OTel Collector..."
docker stop otel-collector 2>/dev/null || true
docker rm otel-collector 2>/dev/null || true

docker run -d --name otel-collector \
    -p 4317:4317 \
    -p 4318:4318 \
    -v "$(pwd)/otel-collector-config.yaml":/etc/otel-collector-config.yaml \
    ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.142.0 \
    --config=/etc/otel-collector-config.yaml

echo "Starting JoustMania..."
exec /home/$HOMENAME/JoustMania/venv/bin/opentelemetry-instrument \
    --logs_exporter otlp \
    --service_name joustmania \
    /home/$HOMENAME/JoustMania/venv/bin/python3 \
    /home/$HOMENAME/JoustMania/piparty.py
