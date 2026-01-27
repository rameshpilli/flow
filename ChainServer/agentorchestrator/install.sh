#!/bin/bash
# AgentOrchestrator Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/rameshpilli/flow/main/ChainServer/agentorchestrator/install.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Symbols
CHECK="${GREEN}✓${NC}"
ARROW="${CYAN}▸${NC}"
SPARKLE="${YELLOW}✨${NC}"
ROCKET="🚀"

# Print the AO banner
print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    cat << 'EOF'
     ___    ____
    /   |  / __ \
   / /| | / / / /
  / ___ |/ /_/ /
 /_/  |_|\____/

EOF
    echo -e "${NC}"
    echo -e "${BOLD}  AgentOrchestrator${NC}"
    echo -e "  ${MAGENTA}Your Agentic AI Workflow${NC}"
    echo ""
}

# Print step with checkmark
print_success() {
    echo -e "${CHECK} $1"
}

# Print step in progress
print_progress() {
    echo -e "${ARROW} $1"
}

# Print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Print warning
print_warning() {
    echo -e "${YELLOW}! $1${NC}"
}

# Detect OS and architecture
detect_platform() {
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    case "$ARCH" in
        x86_64) ARCH="amd64" ;;
        aarch64|arm64) ARCH="arm64" ;;
        *) ARCH="unknown" ;;
    esac

    print_success "Detected ${OS}/${ARCH}"
}

# Check Python version
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            print_success "Python ${PYTHON_VERSION} found"
            return 0
        else
            print_error "Python 3.10+ required, found ${PYTHON_VERSION}"
            return 1
        fi
    else
        print_error "Python 3 not found"
        return 1
    fi
}

# Check pip
check_pip() {
    if command -v pip3 &> /dev/null; then
        print_success "pip3 found"
        return 0
    elif command -v pip &> /dev/null; then
        print_success "pip found"
        return 0
    else
        print_error "pip not found"
        return 1
    fi
}

# Install the package
install_package() {
    print_progress "Installing AgentOrchestrator..."

    # Determine pip command
    if command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    else
        PIP_CMD="pip"
    fi

    # Install with all extras for full functionality
    if $PIP_CMD install agentorchestrator[all] --quiet 2>/dev/null; then
        print_success "Package installed successfully"
    elif $PIP_CMD install agentorchestrator --quiet 2>/dev/null; then
        print_success "Package installed (base only)"
        print_warning "Install extras manually: pip install agentorchestrator[redis,langchain,observability]"
    else
        # Try from GitHub if not on PyPI
        print_progress "Installing from GitHub..."
        if $PIP_CMD install "git+https://github.com/rameshpilli/flow.git#subdirectory=ChainServer/agentorchestrator" --quiet; then
            print_success "Package installed from GitHub"
        else
            print_error "Installation failed"
            return 1
        fi
    fi
}

# Verify installation
verify_installation() {
    print_progress "Verifying installation..."

    if python3 -c "import agentorchestrator" 2>/dev/null; then
        print_success "Import verification passed"
    else
        print_error "Import verification failed"
        return 1
    fi

    if command -v ao &> /dev/null; then
        print_success "CLI command 'ao' available"
    else
        print_warning "CLI 'ao' not in PATH (may need to restart shell)"
    fi
}

# Print completion message
print_completion() {
    echo ""
    echo -e "${SPARKLE} ${BOLD}Installation Complete!${NC} ${SPARKLE}"
    echo ""
    echo -e "${BOLD}Quick Start:${NC}"
    echo ""
    echo -e "   ${CYAN}# Check installation${NC}"
    echo "   ao version"
    echo ""
    echo -e "   ${CYAN}# Create a new agent${NC}"
    echo "   ao new agent my_agent"
    echo ""
    echo -e "   ${CYAN}# Create a new chain${NC}"
    echo "   ao new chain my_workflow"
    echo ""
    echo -e "   ${CYAN}# Run health check${NC}"
    echo "   ao health --detailed"
    echo ""
    echo -e "${BOLD}Documentation:${NC}"
    echo "   https://github.com/rameshpilli/flow/tree/main/ChainServer/agentorchestrator/docs"
    echo ""
    echo -e "Happy coding! ${ROCKET}"
    echo ""
}

# Main installation flow
main() {
    print_banner

    echo -e "${BOLD}Installing AgentOrchestrator...${NC}"
    echo ""

    detect_platform

    if ! check_python; then
        echo ""
        print_error "Please install Python 3.10 or higher and try again."
        exit 1
    fi

    if ! check_pip; then
        echo ""
        print_error "Please install pip and try again."
        exit 1
    fi

    if ! install_package; then
        exit 1
    fi

    if ! verify_installation; then
        exit 1
    fi

    print_completion
}

# Run main
main "$@"
