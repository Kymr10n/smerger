#!/usr/bin/env bash
set -euo pipefail

# Load environment variables
if [[ -f ".env" ]]; then
    source .env
else
    echo "Error: .env file not found. Please copy .env.example to .env and configure it first."
    exit 1
fi

# Check required variables
if [[ -z "${NAS_HOST:-}" || -z "${NAS_USER:-}" ]]; then
    echo "Error: NAS_HOST and NAS_USER must be set in .env file"
    exit 1
fi

echo "Setting up NAS connection for ${NAS_USER}@${NAS_HOST}"

# Function to check if SSH key exists
check_ssh_key() {
    local key_path="${NAS_SSH_KEY/#\~/$HOME}"
    if [[ ! -f "$key_path" ]]; then
        echo "SSH key not found at $key_path"
        read -p "Would you like to generate a new SSH key? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            generate_ssh_key "$key_path"
        else
            echo "Please generate an SSH key manually or update NAS_SSH_KEY in .env"
            exit 1
        fi
    else
        echo "✓ SSH key found at $key_path"
    fi
}

# Function to generate SSH key
generate_ssh_key() {
    local key_path="$1"
    echo "Generating SSH key at $key_path"
    ssh-keygen -t rsa -b 4096 -f "$key_path" -N ""
    echo "✓ SSH key generated"
}

# Function to copy SSH key to NAS
setup_ssh_key() {
    local key_path="${NAS_SSH_KEY/#\~/$HOME}"
    echo "Copying SSH public key to NAS..."
    
    if command -v ssh-copy-id >/dev/null 2>&1; then
        ssh-copy-id -i "$key_path" "${NAS_USER}@${NAS_HOST}"
    else
        echo "ssh-copy-id not found. Manually copying key..."
        cat "${key_path}.pub" | ssh "${NAS_USER}@${NAS_HOST}" "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
    fi
    
    echo "✓ SSH key copied to NAS"
}

# Function to test SSH connection
test_ssh_connection() {
    echo "Testing SSH connection..."
    if ssh -o ConnectTimeout=10 -o BatchMode=yes "${NAS_USER}@${NAS_HOST}" "echo 'SSH connection successful'"; then
        echo "✓ SSH connection test passed"
        return 0
    else
        echo "✗ SSH connection test failed"
        return 1
    fi
}

# Function to setup Docker context
setup_docker_context() {
    echo "Setting up Docker context '${DOCKER_CONTEXT_NAME}'..."
    
    # Remove existing context if it exists
    if docker context ls --format "{{.Name}}" | grep -q "^${DOCKER_CONTEXT_NAME}$"; then
        echo "Removing existing Docker context '${DOCKER_CONTEXT_NAME}'"
        docker context rm "${DOCKER_CONTEXT_NAME}"
    fi
    
    # Create new Docker context
    docker context create "${DOCKER_CONTEXT_NAME}" --docker "host=ssh://${NAS_USER}@${NAS_HOST}"
    echo "✓ Docker context '${DOCKER_CONTEXT_NAME}' created"
}

# Function to test Docker context
test_docker_context() {
    echo "Testing Docker context..."
    if docker --context "${DOCKER_CONTEXT_NAME}" version >/dev/null 2>&1; then
        echo "✓ Docker context test passed"
        
        # Show Docker info from NAS
        echo ""
        echo "Docker info from NAS:"
        docker --context "${DOCKER_CONTEXT_NAME}" version --format "Docker {{.Server.Version}} on {{.Server.Os}}/{{.Server.Arch}}"
        return 0
    else
        echo "✗ Docker context test failed"
        return 1
    fi
}

# Function to configure SSH client
configure_ssh_client() {
    local ssh_config="$HOME/.ssh/config"
    local host_entry="Host ${NAS_HOST%.*}
    HostName ${NAS_HOST}
    User ${NAS_USER}
    IdentityFile ${NAS_SSH_KEY}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR"

    if [[ -f "$ssh_config" ]] && grep -q "Host ${NAS_HOST%.*}" "$ssh_config"; then
        echo "SSH config entry already exists for ${NAS_HOST%.*}"
    else
        echo "Adding SSH config entry..."
        mkdir -p "$(dirname "$ssh_config")"
        echo "" >> "$ssh_config"
        echo "$host_entry" >> "$ssh_config"
        echo "✓ SSH config updated"
    fi
}

# Main execution
main() {
    echo "=== NAS Connection Setup ==="
    echo "NAS: ${NAS_HOST}"
    echo "User: ${NAS_USER}"
    echo "SSH Key: ${NAS_SSH_KEY}"
    echo "Docker Context: ${DOCKER_CONTEXT_NAME}"
    echo ""

    # Step 1: Check/generate SSH key
    check_ssh_key
    
    # Step 2: Configure SSH client
    configure_ssh_client
    
    # Step 3: Test SSH or setup key
    if ! test_ssh_connection; then
        echo ""
        echo "SSH connection failed. Setting up SSH key authentication..."
        setup_ssh_key
        
        # Test again
        if ! test_ssh_connection; then
            echo "Failed to establish SSH connection. Please check:"
            echo "1. NAS is accessible at ${NAS_HOST}"
            echo "2. SSH is enabled on the NAS"
            echo "3. User ${NAS_USER} exists and has SSH access"
            exit 1
        fi
    fi
    
    # Step 4: Setup Docker context
    setup_docker_context
    
    # Step 5: Test Docker context
    if ! test_docker_context; then
        echo "Docker context test failed. Please check:"
        echo "1. Docker is installed and running on the NAS"
        echo "2. User ${NAS_USER} has Docker permissions"
        echo "   Try: ssh ${NAS_USER}@${NAS_HOST} 'sudo usermod -aG docker ${NAS_USER}'"
        exit 1
    fi
    
    echo ""
    echo "=== Setup Complete! ==="
    echo ""
    echo "To use the remote Docker context:"
    echo "  docker context use ${DOCKER_CONTEXT_NAME}"
    echo ""
    echo "To switch back to local Docker:"
    echo "  docker context use default"
    echo ""
    echo "To build and run on NAS:"
    echo "  docker context use ${DOCKER_CONTEXT_NAME}"
    echo "  docker compose up --build"
}

# Run main function
main "$@"