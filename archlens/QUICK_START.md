# ArchLens - Quick Start Guide

## Prerequisites
- Ubuntu 20.04+ or WSL2 with Ubuntu
- Internet connection
- The `archlens-backup-20260519.zip` file (includes ChromaDB)

## What's Included in the Backup

The `archlens-backup-20260519.zip` (23 MB) contains:
- ✅ **Complete source code** (frontend + backend)
- ✅ **ChromaDB vector database** with pre-populated Terraform knowledge
- ✅ **Configuration files** and documentation
- ✅ **Sample architecture diagrams**
- ❌ Excluded: node_modules, .venv (will be regenerated during setup)

## Installation Steps

### Option 1: Automatic Setup with Azure Download (Recommended)

```bash
# Download the setup script from Azure Storage
az storage blob download \
    --account-name testgroupb8e2 \
    --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
    --container-name archlens-2 \
    --name setup_archlens.sh \
    --file setup_archlens.sh

# Make it executable and run
chmod +x setup_archlens.sh
./setup_archlens.sh
```

The script will prompt you to download the application ZIP automatically.

### Option 2: Manual Download + Setup

1. **Download both files manually:**
   ```bash
   # Download application backup
   az storage blob download \
       --account-name testgroupb8e2 \
       --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
       --container-name archlens-2 \
       --name archlens-backup-20260519.zip \
       --file archlens-backup-20260519.zip

   # Download setup script
   az storage blob download \
       --account-name testgroupb8e2 \
       --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
       --container-name archlens-2 \
       --name setup_archlens.sh \
       --file setup_archlens.sh
   ```

2. **Run the setup script:**
   ```bash
   chmod +x setup_archlens.sh
   ./setup_archlens.sh
   ```

### What the Setup Script Does

The script automatically:
1. ✅ Checks OS compatibility (Ubuntu/Debian)
2. ✅ Updates system packages
3. ✅ Installs Node.js 20.x (LTS)
4. ✅ Installs Python 3.10+
5. ✅ Optionally installs Azure CLI
6. ✅ Downloads/extracts the application
7. ✅ Installs frontend dependencies (npm install)
8. ✅ Creates Python virtual environment
9. ✅ Installs backend dependencies (pip install)
10. ✅ Creates configuration templates
11. ✅ Verifies ChromaDB database
12. ✅ Creates start/stop scripts

### Post-Installation Configuration

1. **Configure Azure OpenAI credentials:**
   ```bash
   cd ~/archlens
   nano backend/.env
   ```
   
   Update these values:
   ```env
   AZURE_OPENAI_API_KEY=your_actual_key
   AZURE_OPENAI_ENDPOINT=https://your_endpoint.openai.azure.com/
   AZURE_OPENAI_DEPLOYMENT=your_deployment_name
   ```

2. **Verify ChromaDB is present:**
   ```bash
   ls -lh backend/chroma_db/
   ```
   You should see the vector database files (chroma.sqlite3, collection folders)

3. **Start the application:**
   ```bash
   ./start_archlens.sh
   ```

4. **Access ArchLens:**
   - Frontend: http://localhost:5173
   - API Docs: http://localhost:8000/docs

## About ChromaDB

### What is ChromaDB in ArchLens?

ChromaDB is a **vector database** that stores embeddings of Terraform documentation, best practices, and code examples. It enables:
- 🧠 **Intelligent Code Generation** - Context-aware Terraform code
- 🔍 **Smart Search** - Find relevant patterns and examples
- 💡 **Best Practices** - Automatically apply security and optimization patterns
- 🎯 **Accurate Suggestions** - Based on embedded knowledge

### ChromaDB Location & Structure

```
archlens/backend/chroma_db/
├── chroma.sqlite3                    # SQLite metadata database
├── 3249444f-0b1f-407a-a115-17a70c136fa5/  # Collection ID
│   ├── data_level0.bin              # Vector embeddings
│   ├── header.bin                   # Collection metadata
│   ├── length.bin                   # Document lengths
│   └── link_lists.bin               # Nearest neighbor links
└── [other collection folders]
```

### Is ChromaDB Copied Automatically?

**Yes!** The ZIP file (`archlens-backup-20260519.zip`) already includes the complete ChromaDB database:
- ✅ All vector embeddings
- ✅ Collection metadata
- ✅ Pre-populated Terraform knowledge
- ✅ Ready to use immediately

When you extract the ZIP file, ChromaDB is automatically placed in `backend/chroma_db/` and works out of the box.

### Using the Same ChromaDB on Multiple Machines

**Method 1: Use the existing ZIP backup** (Recommended)
- The ZIP already contains ChromaDB
- Just run the setup script on the new machine
- No additional steps needed

**Method 2: Copy ChromaDB manually** (if needed)
```bash
# On source machine (where ChromaDB is working)
cd ~/archlens/backend
tar -czf chroma_db_backup.tar.gz chroma_db/

# Transfer to new machine (via scp, Azure Storage, etc.)
scp chroma_db_backup.tar.gz user@newmachine:~/

# On new machine (after extracting archlens)
cd ~/archlens/backend
tar -xzf ~/chroma_db_backup.tar.gz
```

**Method 3: Share via Azure Storage** (for team distribution)
```bash
# Upload ChromaDB to Azure Storage
az storage blob upload \
    --account-name testgroupb8e2 \
    --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
    --container-name archlens-2 \
    --file backend/chroma_db_backup.tar.gz \
    --name chroma_db_backup.tar.gz

# Download on other machines
az storage blob download \
    --account-name testgroupb8e2 \
    --account-key "98+SuR78k7XodBu2mI7sicZbi5tKU99B/bAyMTmlKXQdmQ3RXEp8dU7iKPjDiPJYp989fzaXLq+3+AStc8XEpQ==" \
    --container-name archlens-2 \
    --name chroma_db_backup.tar.gz \
    --file chroma_db_backup.tar.gz
```

### Verifying ChromaDB After Setup

```bash
cd ~/archlens
python3 -c "
import os
import sys
sys.path.insert(0, 'backend')
from app.services.vector_store import check_chromadb_health
check_chromadb_health('backend/chroma_db')
"
```

Expected output:
```
✓ ChromaDB found at backend/chroma_db
✓ Collections: terraform_knowledge
✓ Documents: [number] embeddings loaded
✓ ChromaDB is healthy and ready
```

## Application Architecture

```
archlens/
├── frontend/                # React + Vite application
│   ├── src/
│   │   ├── components/     # About, Contact, Footer, etc.
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── .env
├── backend/                 # FastAPI Python application
│   ├── app/
│   │   ├── main.py
│   │   ├── services/
│   │   │   ├── vector_store.py  # ChromaDB interface
│   │   │   └── ...
│   │   └── config.py
│   ├── chroma_db/          # Vector database (included)
│   ├── requirements.txt
│   └── .env
├── docs/                    # Documentation
├── samples/                 # Sample architecture diagrams
├── start_archlens.sh       # Start script
├── stop_archlens.sh        # Stop script
└── README.md
```

## Technology Stack

- **Frontend:** React 18, Vite 5, Tailwind CSS
- **Backend:** Python 3.10+, FastAPI, Uvicorn
- **AI Engine:** Azure OpenAI (Fine-tuned LLM)
- **Vector DB:** ChromaDB (for knowledge retrieval)
- **IaC:** Terraform 1.5+

## Key Features

1. 🤖 **AI-Powered Code Generation** - Fine-tuned LLM for Terraform IaC
2. 🔒 **Security-First** - Automated security scanning
3. 💰 **Cost Optimization** - Built-in cost analysis
4. 🔧 **Auto-Fix** - Intelligent error correction
5. ☁️ **Multi-Cloud Support** - AWS, Azure, GCP
6. 📦 **Modular Architecture** - Reusable Terraform modules
7. 🧠 **Knowledge Base** - ChromaDB with embedded expertise

## Troubleshooting

### Port Already in Use

If port 5173 or 5174 is taken:
```bash
# Frontend will automatically try 5174
# Or manually specify:
cd frontend
npm run dev -- --port 5175
```

### Backend Won't Start

Check Python virtual environment:
```bash
cd backend
source .venv/bin/activate
python --version  # Should be 3.10+
pip list  # Verify dependencies installed
```

### ChromaDB Not Found

If ChromaDB is missing after extraction:
```bash
# Check if it exists
ls -la backend/chroma_db/

# If missing, extract from backup again
cd ~
unzip -q archlens-backup-20260519.zip
cd archlens/backend
ls -lh chroma_db/  # Should show database files
```

### Dependencies Installation Failed

```bash
# Clear npm cache
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install

# Clear pip cache
cd ../backend
source .venv/bin/activate
pip cache purge
pip install -r requirements.txt
```

## Stopping the Application

```bash
cd ~/archlens
./stop_archlens.sh
```

Or manually:
```bash
pkill -f "uvicorn app.main:app"
pkill -f "vite"
```

## Files in Azure Storage

All files are stored in:
- **Account:** testgroupb8e2
- **Container:** archlens-2
- **Region:** eastus

Available files:
1. `archlens-backup-20260519.zip` (23 MB) - Complete application + ChromaDB
2. `setup_archlens.sh` - Automated setup script
3. `QUICK_START.md` - This guide

## Support

For issues or questions:
- Email: support@archlens.in
- Documentation: `docs/` folder in the application

## License

© 2026 ArchLens. All rights reserved.
