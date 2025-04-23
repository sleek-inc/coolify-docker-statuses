#!/bin/bash
set -e
set -o pipefail

export PYTHONPATH="$(pwd)/src:$PYTHONPATH"

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac

if [ -f .env ]; then
  echo 'Loading environment variables from .env file'
  while IFS='=' read -r key value
  do
    # Remove leading and trailing whitespace from the key
    key=$(echo $key | xargs)
    # Use printf to handle multi-line and special character literals correctly
    value=$(echo "$value" | xargs)
    # Check if value starts with a double quote and ends with a double quote
    if [[ "$value" =~ ^\".*\"$ ]]; then
      # It's likely a JSON string, so preserve it
      eval export $key=$value
    else
      # Not a JSON string, so just export normally
      export $key="$value"
    fi
  done < .env
fi

# Define default values for configuration
MONITOR_INTERVAL_IN_SECONDS=${MONITOR_INTERVAL_IN_SECONDS:-5}
DOCKER_SOCKET=${DOCKER_SOCKET:-"unix://var/run/docker.sock"}
STATUS_CHANGE_WEBHOOK_URL=${STATUS_CHANGE_WEBHOOK_URL:-""}
COOLIFY_MONITOR_LABEL=${MONITOR_LABEL:-"coolify.managed"}
COOLIFY_PROJECT_NAME=${COOLIFY_PROJECT_NAME:-""}
COOLIFY_ENVIRONMENT_NAME=${COOLIFY_ENVIRONMENT_NAME:-"production"}

# Parse command-line arguments
ARGS=()
for arg in "$@"; do
  case $arg in
    --monitor-interval-in-seconds=*)
      MONITOR_INTERVAL_IN_SECONDS="${arg#*=}"
      ;;
    --docker-socket=*)
      DOCKER_SOCKET="${arg#*=}"
      ;;
    --status-change-webhook-url=*)
      STATUS_CHANGE_WEBHOOK_URL="${arg#*=}"
      ;;
    --coolify-monitor-label=*)
      COOLIFY_MONITOR_LABEL="${arg#*=}"
      ;;
    --coolify-project-name=*)
      COOLIFY_PROJECT_NAME="${arg#*=}"
      ;;
    --coolify-environment-name=*)
      COOLIFY_ENVIRONMENT_NAME="${arg#*=}"
      ;;
    *)
      # Add any other arguments to the ARGS array
      ARGS+=("$arg")
      ;;
  esac
done

# Export the variables so they're available to the Python application
export MONITOR_INTERVAL_IN_SECONDS
export DOCKER_SOCKET
export STATUS_CHANGE_WEBHOOK_URL
export MONITOR_LABEL
export COOLIFY_PROJECT_NAME
export COOLIFY_ENVIRONMENT_NAME

echo "Configuration:"
echo "  Monitor Interval: ${MONITOR_INTERVAL_IN_SECONDS} seconds"
echo "  Docker Socket: ${DOCKER_SOCKET}"
echo "  Monitor Label: ${COOLIFY_MONITOR_LABEL}"
echo "  Project Name: ${COOLIFY_PROJECT_NAME}"
echo "  Environment Name: ${COOLIFY_ENVIRONMENT_NAME}"
if [ -n "$STATUS_CHANGE_WEBHOOK_URL" ]; then
  echo "  Webhook URL: Configured"
else
  echo "  Webhook URL: Not configured"
fi

# Construct the command-line arguments for the Python application
PY_ARGS=()
PY_ARGS+=("--monitor-interval-in-seconds=${MONITOR_INTERVAL_IN_SECONDS}")
PY_ARGS+=("--docker-socket=${DOCKER_SOCKET}")
if [ -n "$STATUS_CHANGE_WEBHOOK_URL" ]; then
  PY_ARGS+=("--status-change-webhook-url=${STATUS_CHANGE_WEBHOOK_URL}")
fi
PY_ARGS+=("--coolify-monitor-label=${COOLIFY_MONITOR_LABEL}")
PY_ARGS+=("--coolify-project-name=${COOLIFY_PROJECT_NAME}")
PY_ARGS+=("--coolify-environment-name=${COOLIFY_ENVIRONMENT_NAME}")

# Add any remaining arguments
for arg in "${ARGS[@]}"; do
  PY_ARGS+=("$arg")
done

# Run the application with the constructed arguments
cs "${PY_ARGS[@]}"
