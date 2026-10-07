# ArchLens Deployment Summary

## Files in Azure Storage

**Account:** testgroupb8e2  
**Container:** archlens-2  
**Region:** eastus  

### Available Files

| File Name | Size | Description |
|-----------|------|-------------|
| `archlens-backup-20260519.zip` | 23 MB | Complete application backup including ChromaDB |
| `setup_archlens.sh` | 24 KB | Automated setup script for Ubuntu/WSL |
| `QUICK_START.md` | 9 KB | Complete installation and usage guide |

---

## Quick Deployment on New Machine

### Step 1: Download Setup Script

```bash
# Install Azure CLI (if not already installed)
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Download setup script
az storage blob download \
    --account-name testgroupb8e2 \
    --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
    --container-name archlens-2 \
    --name setup_archlens.sh \
    --file setup_archlens.sh

# Make executable
chmod +x setup_archlens.sh
```

### Step 2: Run Setup

```bash
./setup_archlens.sh
```

The script will:
- ✅ Install all dependencies (Node.js, Python, etc.)
- ✅ Download the application ZIP from Azure
- ✅ Extract application with ChromaDB database
- ✅ Install frontend dependencies
- ✅ Install backend dependencies
- ✅ Create configuration files
- ✅ Create start/stop scripts

### Step 3: Configure & Run

```bash
cd ~/archlens
nano backend/.env  # Add your Azure OpenAI credentials
./start_archlens.sh
```

---

## About ChromaDB

### What's Included

The ZIP file (`archlens-backup-20260519.zip`) **already contains** the complete ChromaDB database:

```
archlens/backend/chroma_db/
├── chroma.sqlite3                    # SQLite metadata
├── 3249444f-0b1f-407a-a115-17a70c136fa5/  # Collection
│   ├── data_level0.bin              # Vector embeddings
│   ├── header.bin                   # Metadata
│   ├── length.bin                   # Document lengths
│   └── link_lists.bin               # Index
└── [other collections...]
```

### Do You Need to Copy ChromaDB Separately?

**NO!** 🎉 

When you extract `archlens-backup-20260519.zip`, you automatically get:
- ✅ Complete ChromaDB database
- ✅ All vector embeddings
- ✅ Pre-populated Terraform knowledge
- ✅ Ready to use immediately

### Using on Multiple Machines

**Option 1: Use the Setup Script** (Recommended)
```bash
# On each new machine, just run:
./setup_archlens.sh
```
The script downloads and extracts everything including ChromaDB.

**Option 2: Manual Copy** (if needed later)
```bash
# Create backup of ChromaDB only
cd ~/archlens/backend
tar -czf chroma_db_backup.tar.gz chroma_db/

# Transfer to new machine
scp chroma_db_backup.tar.gz user@newmachine:~/

# On new machine
cd ~/archlens/backend
tar -xzf ~/chroma_db_backup.tar.gz
```

**Option 3: Update ChromaDB in Azure** (for team distribution)
```bash
# If you've updated ChromaDB and want to share
cd ~/archlens/backend
tar -czf chroma_db_backup.tar.gz chroma_db/

# Upload to Azure Storage
az storage blob upload \
    --account-name testgroupb8e2 \
    --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
    --container-name archlens-2 \
    --file chroma_db_backup.tar.gz \
    --name chroma_db_backup.tar.gz
```

---

## What the Setup Script Does

### Automatic Installation Process

1. **System Preparation**
   - Checks OS compatibility (Ubuntu/Debian)
   - Updates system packages
   - Installs essential tools (curl, wget, git, unzip)

2. **Runtime Installation**
   - Node.js 20.x (LTS) for frontend
   - Python 3.10+ for backend
   - Optionally installs Azure CLI

3. **Application Setup**
   - Downloads ZIP from Azure Storage (or uses local)
   - Extracts to `~/archlens/`
   - Verifies ChromaDB database extraction

4. **Dependency Installation**
   - Frontend: `npm install` (React, Vite, Tailwind)
   - Backend: Creates virtual env + `pip install` (FastAPI, ChromaDB, etc.)

5. **Configuration**
   - Creates `.env` templates for backend/frontend
   - Sets up Terraform cache directories
   - Creates ChromaDB configuration

6. **Helper Scripts**
   - `start_archlens.sh` - Start frontend + backend
   - `stop_archlens.sh` - Stop all services

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    ArchLens Application                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Frontend (Port 5173/5174)                                 │
│  ├─ React 18 + Vite 5                                      │
│  ├─ Tailwind CSS                                           │
│  └─ Components: About, Contact, Footer                     │
│                                                             │
│  Backend (Port 8000)                                       │
│  ├─ FastAPI + Uvicorn                                      │
│  ├─ Azure OpenAI Integration                               │
│  └─ Terraform IaC Generation                               │
│                                                             │
│  ChromaDB (Embedded)                                       │
│  ├─ Vector Database                                        │
│  ├─ Terraform Knowledge Base                               │
│  └─ Intelligent Retrieval                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Features

| Feature | Description | Enabled By |
|---------|-------------|------------|
| 🤖 AI Code Generation | Terraform IaC generation | Azure OpenAI + ChromaDB |
| 🔍 Smart Search | Context-aware code suggestions | ChromaDB embeddings |
| 🔒 Security First | Automated security scanning | Built-in validators |
| 💰 Cost Optimization | Cost analysis & recommendations | AI analysis |
| 🔧 Auto-Fix | Intelligent error correction | Pattern matching |
| ☁️ Multi-Cloud | AWS, Azure, GCP support | Universal modules |

---

## Common Use Cases

### Scenario 1: Developer Workstation
```bash
# One-time setup
./setup_archlens.sh
cd ~/archlens
nano backend/.env  # Configure Azure credentials
./start_archlens.sh

# Daily usage
cd ~/archlens && ./start_archlens.sh
# Work on http://localhost:5173
./stop_archlens.sh
```

### Scenario 2: Team Member Onboarding
```bash
# Share setup command
curl -O https://raw.githubusercontent.com/yourorg/archlens/setup.sh
chmod +x setup.sh && ./setup.sh

# Or from Azure Storage directly
az storage blob download ... # (setup script download)
chmod +x setup_archlens.sh && ./setup_archlens.sh
```

### Scenario 3: CI/CD Pipeline
```bash
# Download and extract
az storage blob download --name archlens-backup-20260519.zip ...
unzip archlens-backup-20260519.zip
cd archlens

# Install dependencies
cd frontend && npm ci && cd ..
cd backend && pip install -r requirements.txt && cd ..

# Run tests
npm test --prefix frontend
pytest backend/tests/
```

---

## Troubleshooting

### ChromaDB Not Found After Setup

```bash
# Check if ChromaDB exists
ls -lh ~/archlens/backend/chroma_db/

# If missing, re-extract
cd ~
unzip -o archlens-backup-20260519.zip
```

### Permission Issues

```bash
# Fix permissions
chmod +x ~/archlens/*.sh
chmod 755 ~/archlens/backend/chroma_db/
```

### Port Conflicts

```bash
# Check what's using ports
lsof -i :5173
lsof -i :8000

# Kill conflicting processes
pkill -f vite
pkill -f uvicorn
```

---

## Support & Documentation

- **Email:** support@archlens.in
- **Quick Start:** See `QUICK_START.md` in Azure Storage
- **Full Docs:** `~/archlens/docs/` folder after setup

---

## License

© 2026 ArchLens. All rights reserved.

---

## Summary

✅ **Everything is ready in Azure Storage!**

To deploy on any new Ubuntu/WSL machine:
1. Download `setup_archlens.sh`
2. Run it: `./setup_archlens.sh`
3. Configure Azure credentials
4. Start: `./start_archlens.sh`

**ChromaDB is included automatically** - no separate copying needed! 🎉
