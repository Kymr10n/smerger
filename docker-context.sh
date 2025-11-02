#!/usr/bin/env bash
set -euo pipefail

# Load environment variables
if [[ -f ".env" ]]; then
    source .env
else
    echo "Error: .env file not found"
    exit 1
fi

CONTEXT_NAME="${DOCKER_CONTEXT_NAME:-your-nas}"

case "${1:-help}" in
    "nas"|"remote")
        echo "Switching to NAS Docker context: $CONTEXT_NAME"
        docker context use "$CONTEXT_NAME"
        echo "✓ Now using Docker on NAS"
        docker version --format "Docker {{.Server.Version}} on {{.Server.Os}}/{{.Server.Arch}}"
        ;;
    "local"|"default")
        echo "Switching to local Docker context"
        docker context use default
        echo "✓ Now using local Docker"
        docker version --format "Docker {{.Server.Version}} on {{.Server.Os}}/{{.Server.Arch}}"
        ;;
    "status"|"current")
        echo "Current Docker context:"
        docker context show
        echo ""
        echo "Available contexts:"
        docker context ls
        ;;
    "test")
        echo "Testing NAS connection..."
        if docker --context "$CONTEXT_NAME" version >/dev/null 2>&1; then
            echo "✓ NAS Docker connection working"
            docker --context "$CONTEXT_NAME" version --format "NAS: Docker {{.Server.Version}} on {{.Server.Os}}/{{.Server.Arch}}"
        else
            echo "✗ NAS Docker connection failed"
            exit 1
        fi
        ;;
    "help"|*)
        echo "Docker Context Manager"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  nas, remote    Switch to NAS Docker context"
        echo "  local, default Switch to local Docker context"
        echo "  status, current Show current context and available contexts"
        echo "  test           Test NAS Docker connection"
        echo "  help           Show this help"
        echo ""
        echo "Current context: $(docker context show)"
        ;;
esac