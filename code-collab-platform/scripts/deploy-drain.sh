#!/bin/bash
# Usage: ./scripts/deploy-drain.sh <node_id>
# Marks a node as draining before docker-compose service update

set -euo pipefail

NODE_ID="${1:?Usage: ./scripts/deploy-drain.sh <node_id>}"

redis-cli SET "node:${NODE_ID}:draining" 1 EX 35
echo "Node ${NODE_ID} marked as draining. Wait 30s before updating..."
sleep 30
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps backend
