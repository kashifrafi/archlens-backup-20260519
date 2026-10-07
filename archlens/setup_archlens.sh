#!/bin/bash

################################################################################
# ArchLens Application Setup Script
# Purpose: Complete setup for ArchLens on Ubuntu/WSL
# Usage: ./setup_archlens.sh
################################################################################

set -e  # Exit on any error

echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║              ArchLens Application Setup Script                        ║"
echo "║              Setting up on Ubuntu/WSL                                  ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

################################################################################
# Step 1: Check if running on Ubuntu/Debian
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Checking Operating System"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    print_success "Running on: $NAME $VERSION"
else
    print_error "Cannot determine OS. This script is designed for Ubuntu/Debian."
    exit 1
fi

################################################################################
# Step 2: Update System Packages
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Updating System Packages"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "Updating package list..."
sudo apt-get update -qq
print_success "Package list updated"

################################################################################
# Step 3: Install System Dependencies
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Installing System Dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
print_info "Installing essential tools (curl, wget, git, unzip)..."
sudo apt-get install -y curl wget git unzip build-essential -qq
print_success "Essential tools installed"

################################################################################
# Step 4: Install Node.js and npm
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Installing Node.js and npm"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node -v)
    print_warning "Node.js already installed: $NODE_VERSION"
else
    print_info "Installing Node.js 20.x (LTS)..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs -qq
    print_success "Node.js installed: $(node -v)"
fi
print_info "npm version: $(npm -v)"

################################################################################
# Step 5: Install Python 3.10+
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Installing Python 3.10+"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    print_warning "Python already installed: $PYTHON_VERSION"
else
    print_info "Installing Python 3.10..."
    sudo apt-get install -y python3.10 python3.10-venv python3-pip -qq
    print_success "Python installed: $(python3 --version)"
fi

################################################################################
# Step 6: Install Azure CLI (Optional for downloading from Azure Storage)
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Installing Azure CLI (Optional)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Do you want to install Azure CLI to download from Azure Storage? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v az &> /dev/null; then
        print_warning "Azure CLI already installed: $(az version --query '\"azure-cli\"' -o tsv)"
    else
        print_info "Installing Azure CLI..."
        curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
        print_success "Azure CLI installed"
    fi
else
    print_info "Skipping Azure CLI installation"
fi

################################################################################
# Step 7: Download or Locate ZIP File
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7: Download ArchLens Application"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ARCHLENS_ZIP="archlens-backup-20260519.zip"
INSTALL_DIR="$HOME/archlens"

if [ -f "$ARCHLENS_ZIP" ]; then
    print_success "Found $ARCHLENS_ZIP in current directory"
else
    read -p "Do you want to download from Azure Storage? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if ! command -v az &> /dev/null; then
            print_error "Azure CLI not installed. Cannot download from Azure Storage."
            print_info "Please manually download the ZIP file or install Azure CLI."
            exit 1
        fi
        
        print_info "Downloading from Azure Storage..."
        az storage blob download \
            --account-name testgroupb8e2 \
            --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
            --container-name archlens-2 \
            --name archlens-backup-20260519.zip \
            --file "$ARCHLENS_ZIP"
        print_success "Downloaded $ARCHLENS_ZIP"
    else
        print_error "ZIP file not found. Please place $ARCHLENS_ZIP in the current directory."
        exit 1
    fi
fi

################################################################################
# Step 8: Extract ZIP File
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 8: Extracting Application Files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "$INSTALL_DIR" ]; then
    print_warning "Directory $INSTALL_DIR already exists"
    read -p "Do you want to remove it and reinstall? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$INSTALL_DIR"
        print_info "Removed existing directory"
    else
        print_error "Installation cancelled"
        exit 1
    fi
fi

print_info "Extracting to $INSTALL_DIR..."
unzip -q "$ARCHLENS_ZIP" -d "$HOME/"
print_success "Files extracted to $INSTALL_DIR"

# Verify ChromaDB database was extracted
if [ -d "$INSTALL_DIR/backend/chroma_db" ]; then
    print_success "ChromaDB vector database found (pre-populated with knowledge)"
else
    print_warning "ChromaDB directory not found - will be created on first run"
fi

cd "$INSTALL_DIR"

################################################################################
# Step 9: Setup Frontend (React + Vite)
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 9: Setting up Frontend (React + Vite)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "frontend" ]; then
    cd frontend
    print_info "Installing frontend dependencies (this may take a few minutes)..."
    npm install
    print_success "Frontend dependencies installed"
    cd ..
else
    print_error "Frontend directory not found!"
fi

################################################################################
# Step 10: Setup Backend (Python FastAPI)
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 10: Setting up Backend (Python FastAPI)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "backend" ]; then
    cd backend
    
    # Create virtual environment
    print_info "Creating Python virtual environment..."
    python3 -m venv .venv
    print_success "Virtual environment created"
    
    # Activate virtual environment
    print_info "Activating virtual environment..."
    source .venv/bin/activate
    
    # Upgrade pip
    print_info "Upgrading pip..."
    pip install --upgrade pip -q
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        print_info "Installing backend dependencies (this may take a few minutes)..."
        pip install -r requirements.txt -q
        print_success "Backend dependencies installed"
    else
        print_warning "requirements.txt not found in backend directory"
    fi
    
    deactivate
    cd ..
else
    print_error "Backend directory not found!"
fi

################################################################################
# Step 11: Setup Environment Variables
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 11: Configuring Environment Variables"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create .env file for backend if it doesn't exist
if [ ! -f "backend/.env" ]; then
    print_info "Creating backend .env file template..."
    cat > backend/.env << 'EOF'
# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY=your_api_key_here
AZURE_OPENAI_ENDPOINT=your_endpoint_here
AZURE_OPENAI_DEPLOYMENT=your_deployment_name
AZURE_OPENAI_API_VERSION=2023-07-01-preview

# Application Configuration
PORT=8000
HOST=0.0.0.0
CORS_ORIGINS=http://localhost:5173,http://localhost:5174

# ChromaDB Configuration (vector database for knowledge retrieval)
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION_NAME=terraform_knowledge

# Optional: Terraform Plugin Cache
TERRAFORM_PLUGIN_CACHE_DIR=$HOME/.archlens/tf-plugin-cache
EOF
    print_success "Backend .env template created"
    print_warning "⚠ IMPORTANT: Edit backend/.env with your actual Azure credentials!"
else
    print_success "Backend .env file already exists"
fi

# Create .env file for frontend if needed
if [ ! -f "frontend/.env" ]; then
    print_info "Creating frontend .env file..."
    cat > frontend/.env << 'EOF'
# Backend API URL
VITE_API_URL=http://localhost:8000
EOF
    print_success "Frontend .env file created"
else
    print_success "Frontend .env file already exists"
fi

################################################################################
# Step 12: Create Terraform Plugin Cache Directory
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 12: Setting up Terraform Cache"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p "$HOME/.archlens/tf-plugin-cache"
mkdir -p "$HOME/.archlens/module-archive"
print_success "Terraform cache directories created"

################################################################################
# Step 13: Verify ChromaDB Setup
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 13: Verifying ChromaDB Vector Database"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ -d "backend/chroma_db" ]; then
    CHROMA_SIZE=$(du -sh backend/chroma_db | cut -f1)
    print_success "ChromaDB ready: $CHROMA_SIZE (pre-populated with Terraform knowledge)"
    print_info "Location: $INSTALL_DIR/backend/chroma_db"
    print_info "This database contains embedded knowledge for intelligent code generation"
else
    print_warning "ChromaDB will be initialized on first application run"
fi

################################################################################
# Step 14: Create Run Scripts
################################################################################
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 14: Creating Run Scripts"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create start script
cat > start_archlens.sh << 'EOF'
#!/bin/bash

echo "Starting ArchLens Application..."
echo ""

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if backend .env is configured
if grep -q "your_api_key_here" backend/.env 2>/dev/null; then
    echo "⚠ WARNING: Backend .env file not configured with Azure credentials!"
    echo "Please edit backend/.env with your actual Azure OpenAI credentials"
    echo ""
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start backend in background
echo "Starting Backend (FastAPI)..."
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"
cd ..

# Wait for backend to be ready
sleep 3

# Start frontend
echo "Starting Frontend (Vite)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"
cd ..

echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                    ArchLens is now running!                            ║"
echo "╠════════════════════════════════════════════════════════════════════════╣"
echo "║  Frontend: http://localhost:5173 or http://localhost:5174             ║"
echo "║  Backend:  http://localhost:8000                                       ║"
echo "║  API Docs: http://localhost:8000/docs                                  ║"
echo "╠════════════════════════════════════════════════════════════════════════╣"
echo "║  ChromaDB: Vector database active with Terraform knowledge            ║"
echo "║  To stop: Press Ctrl+C or run ./stop_archlens.sh                      ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

# Save PIDs for stop script
echo "$BACKEND_PID" > .backend.pid
echo "$FRONTEND_PID" > .frontend.pid

# Wait for Ctrl+C
wait
EOF

# Create stop script
cat > stop_archlens.sh << 'EOF'
#!/bin/bash

echo "Stopping ArchLens Application..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Stop backend
if [ -f .backend.pid ]; then
    BACKEND_PID=$(cat .backend.pid)
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        kill $BACKEND_PID
        echo "✓ Backend stopped"
    fi
    rm .backend.pid
fi

# Stop frontend
if [ -f .frontend.pid ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        kill $FRONTEND_PID
        echo "✓ Frontend stopped"
    fi
    rm .frontend.pid
fi

# Cleanup any remaining processes
pkill -f "uvicorn app.main:app"
pkill -f "vite"

echo "✓ ArchLens stopped"
EOF

chmod +x start_archlens.sh
chmod +x stop_archlens.sh
print_success "Run scripts created"

################################################################################
# Final Summary
################################################################################
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete! 🎉                                  ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""
print_success "ArchLens has been successfully installed to: $INSTALL_DIR"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Configure Azure credentials:"
echo "   cd $INSTALL_DIR"
echo "   nano backend/.env"
echo "   (Update AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT)"
echo ""
echo "2. Start the application:"
echo "   cd $INSTALL_DIR"
echo "   ./start_archlens.sh"
echo ""
echo "3. Access the application:"
echo "   Frontend: http://localhost:5173"
echo "   Backend API: http://localhost:8000/docs"
echo ""
echo "4. To stop the application:"
echo "   ./stop_archlens.sh"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ChromaDB Information:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -d "$INSTALL_DIR/backend/chroma_db" ]; then
    echo "  ✓ Vector database included with pre-populated Terraform knowledge"
    echo "  ✓ Location: backend/chroma_db/"
    echo "  ✓ This enables intelligent code generation and context-aware suggestions"
else
    echo "  ⚠ ChromaDB will be initialized on first run"
fi
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Documentation:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  - docs/HLD.md          - High-level design"
echo "  - docs/LLD.md          - Low-level design"
echo "  - docs/README.md       - Project overview"
echo ""
print_success "Setup completed successfully!"
