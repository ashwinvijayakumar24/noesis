#!/bin/bash
# ============================================
# Noesis EC2 Initial Setup Script
# ============================================
# Run this script on a fresh Ubuntu 22.04 EC2 instance
# Usage: curl -fsSL https://raw.githubusercontent.com/yourusername/noesis/main/scripts/ec2-setup.sh | bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔════════════════════════════════════════╗"
echo "║   Noesis EC2 Setup Script              ║"
echo "║   Setting up production environment    ║"
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as ubuntu user
if [ "$USER" != "ubuntu" ]; then
    echo -e "${RED}Error: This script must be run as the 'ubuntu' user${NC}"
    exit 1
fi

# Check if running on Ubuntu
if [ ! -f /etc/lsb-release ]; then
    echo -e "${RED}Error: This script is designed for Ubuntu${NC}"
    exit 1
fi

# Update system
echo -e "${YELLOW}[1/9] Updating system packages...${NC}"
sudo apt update && sudo apt upgrade -y

# Install essential packages
echo -e "${YELLOW}[2/9] Installing essential packages...${NC}"
sudo apt install -y \
    git \
    curl \
    vim \
    htop \
    ca-certificates \
    gnupg \
    lsb-release \
    jq

# Install Docker
echo -e "${YELLOW}[3/9] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker ubuntu
    rm get-docker.sh
    echo -e "${GREEN}✓ Docker installed${NC}"
else
    echo -e "${GREEN}✓ Docker already installed${NC}"
fi

# Install Docker Compose
echo -e "${YELLOW}[4/9] Installing Docker Compose...${NC}"
if ! docker compose version &> /dev/null; then
    sudo apt install -y docker-compose-plugin
    echo -e "${GREEN}✓ Docker Compose installed${NC}"
else
    echo -e "${GREEN}✓ Docker Compose already installed${NC}"
fi

# Install Nginx
echo -e "${YELLOW}[5/9] Installing Nginx...${NC}"
if ! command -v nginx &> /dev/null; then
    sudo apt install -y nginx certbot python3-certbot-nginx
    echo -e "${GREEN}✓ Nginx installed${NC}"
else
    echo -e "${GREEN}✓ Nginx already installed${NC}"
fi

# Enable services
echo -e "${YELLOW}[6/9] Enabling services...${NC}"
sudo systemctl enable docker
sudo systemctl enable nginx
sudo systemctl start docker
sudo systemctl start nginx

# Configure swap
echo -e "${YELLOW}[7/9] Configuring swap (2GB)...${NC}"
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    sudo sysctl vm.swappiness=10
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
    echo -e "${GREEN}✓ Swap configured${NC}"
else
    echo -e "${GREEN}✓ Swap already configured${NC}"
fi

# Configure UFW firewall
echo -e "${YELLOW}[8/9] Configuring firewall...${NC}"
if ! sudo ufw status | grep -q "Status: active"; then
    sudo ufw --force reset
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw allow 22/tcp comment 'SSH'
    sudo ufw allow 80/tcp comment 'HTTP'
    sudo ufw allow 443/tcp comment 'HTTPS'
    sudo ufw --force enable
    echo -e "${GREEN}✓ Firewall configured${NC}"
else
    echo -e "${GREEN}✓ Firewall already configured${NC}"
fi

# Create helper scripts
echo -e "${YELLOW}[9/9] Creating helper scripts...${NC}"

# Monitor script
cat > ~/monitor.sh << 'EOF'
#!/bin/bash
echo "=== System Resources ==="
free -h
echo ""
echo "=== Disk Usage ==="
df -h | grep -E '(Filesystem|/dev/root|tmpfs)'
echo ""
echo "=== Docker Stats ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
echo ""
if [ -f ~/noesis/infra/docker-compose.prod.yml ]; then
    echo "=== Service Health ==="
    curl -s http://localhost:8000/health 2>/dev/null | jq . || echo "Backend not running"
fi
EOF
chmod +x ~/monitor.sh

# Backup script
cat > ~/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/backups
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

if [ -f ~/noesis/infra/docker-compose.prod.yml ]; then
    cd ~/noesis/infra
    docker compose -f docker-compose.prod.yml exec -T db \
        pg_dump -U noesis_prod noesis_prod > $BACKUP_DIR/db_$DATE.sql 2>/dev/null

    if [ -f $BACKUP_DIR/db_$DATE.sql ]; then
        gzip $BACKUP_DIR/db_$DATE.sql
        ls -t $BACKUP_DIR/db_*.sql.gz | tail -n +8 | xargs -r rm
        echo "Backup completed: $BACKUP_DIR/db_$DATE.sql.gz"
    else
        echo "Backup failed - is the database running?"
    fi
else
    echo "Noesis not deployed yet"
fi
EOF
chmod +x ~/backup.sh

echo -e "${GREEN}✓ Helper scripts created${NC}"

echo ""
echo -e "${GREEN}"
echo "╔════════════════════════════════════════╗"
echo "║   ✓ Setup Complete!                    ║"
echo "╚════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. ${YELLOW}Logout and login again${NC} to apply Docker group membership:"
echo "   exit"
echo "   ssh -i your-key.pem ubuntu@your-ip"
echo ""
echo "2. ${YELLOW}Clone your repository:${NC}"
echo "   git clone https://github.com/yourusername/noesis.git"
echo "   cd noesis"
echo ""
echo "3. ${YELLOW}Follow the deployment checklist:${NC}"
echo "   cat DEPLOYMENT_CHECKLIST.md"
echo ""
echo "4. ${YELLOW}Useful commands:${NC}"
echo "   ~/monitor.sh          - Check system resources"
echo "   ~/backup.sh           - Backup database"
echo "   htop                  - Live resource monitor"
echo ""
echo -e "${GREEN}System is ready for Noesis deployment!${NC}"
echo ""
