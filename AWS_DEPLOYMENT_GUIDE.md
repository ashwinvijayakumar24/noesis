# AWS Deployment Guide - Noesis (Budget: $10-20/month)

> **Production-ready deployment for early-stage users and pilot programs**

---

## 1. Architecture Overview

### Final Production Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ VERCEL (Free Tier)                                          │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Frontend (React/Vite)                                   │ │
│ │ - Static hosting                                        │ │
│ │ - Auto SSL                                              │ │
│ │ - CDN                                                   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ AWS EC2 t4g.micro (ARM64) - $3.07/month                     │
│ Ubuntu 22.04 LTS + Docker Compose                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ NGINX (Reverse Proxy + SSL Termination)               │ │
│  │ - Port 80/443                                          │ │
│  │ - Let's Encrypt SSL                                    │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Docker Compose Services                                │ │
│  │                                                          │ │
│  │  [FastAPI]     [PostgreSQL+pgvector]                   │ │
│  │   :8000           :5432                                 │ │
│  │   250MB RAM       512MB RAM                             │ │
│  │                                                          │ │
│  │  [Redis]       [GROBID]                                │ │
│  │   :6379           :8070                                 │ │
│  │   128MB RAM       128MB RAM (on-demand)                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  Storage: 30GB EBS (gp3)                                    │
└─────────────────────────────────────────────────────────────┘
```

### Why This Fits $10-20 Budget

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| **EC2 t4g.micro** | **$3.07** | ARM-based, 1 vCPU, 1GB RAM, cheapest option |
| **30GB EBS (gp3)** | **$2.40** | Storage for OS + Docker volumes + PostgreSQL data |
| **Data Transfer** | **~$1-3** | First 100GB out is free, typical usage stays under |
| **Elastic IP** | **$3.60** | Required for static IP (free when attached) |
| **Vercel Frontend** | **$0** | Free tier (100GB bandwidth/month) |
| **Total** | **~$9-12** | Well under budget with room for growth |

**Key Cost Savers:**
- ✅ Single EC2 instance (no load balancer = save $16/month)
- ✅ No NAT Gateway (save $32/month)
- ✅ No RDS (save $15/month minimum)
- ✅ No ElastiCache (save $13/month minimum)
- ✅ ARM-based t4g.micro (20% cheaper than t3.micro)
- ✅ Frontend on Vercel (save $10-20/month on S3+CloudFront)

---

## 2. Docker Compose (Production)

Create `infra/docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  # ============================================
  # PostgreSQL with pgvector (Primary Data Store)
  # ============================================
  db:
    image: pgvector/pgvector:pg15
    container_name: noesis-db-prod
    restart: unless-stopped

    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: noesis_prod
      # Performance tuning for 1GB RAM instance
      POSTGRES_SHARED_BUFFERS: 128MB
      POSTGRES_EFFECTIVE_CACHE_SIZE: 256MB
      POSTGRES_WORK_MEM: 4MB

    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db-init:/docker-entrypoint-initdb.d:ro

    # CRITICAL: Memory limits for micro instance
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    # No port exposure - only accessible within Docker network
    networks:
      - noesis-network

  # ============================================
  # Redis (Caching Layer)
  # ============================================
  redis:
    image: redis:7-alpine
    container_name: noesis-redis-prod
    restart: unless-stopped

    command: >
      redis-server
      --maxmemory 100mb
      --maxmemory-policy allkeys-lru
      --save 60 1
      --appendonly yes

    volumes:
      - redis_data:/data

    deploy:
      resources:
        limits:
          memory: 128M
        reservations:
          memory: 64M

    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

    networks:
      - noesis-network

  # ============================================
  # GROBID (PDF Processing - On Demand)
  # ============================================
  grobid:
    image: lfoppiano/grobid:0.7.0
    container_name: noesis-grobid-prod
    restart: unless-stopped

    # CRITICAL: Run with minimal resources
    # GROBID is memory-hungry but used infrequently
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8070/api/isalive"]
      interval: 60s
      timeout: 15s
      retries: 3
      start_period: 90s

    networks:
      - noesis-network

  # ============================================
  # FastAPI Backend
  # ============================================
  backend:
    build:
      context: ../services/backend
      dockerfile: Dockerfile.prod
    container_name: noesis-backend-prod
    restart: unless-stopped

    env_file:
      - ../services/backend/.env.production

    environment:
      # Docker internal networking
      DATABASE_URL: postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@db:5432/noesis_prod
      REDIS_URL: redis://redis:6379
      GROBID_URL: http://grobid:8070
      ENVIRONMENT: production
      LOG_LEVEL: INFO

    volumes:
      # Persistent storage for uploaded PDFs
      - pdf_storage:/app/pdfs
      # Logs for debugging
      - backend_logs:/app/logs

    deploy:
      resources:
        limits:
          memory: 384M
          cpus: '0.5'
        reservations:
          memory: 256M

    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      grobid:
        condition: service_healthy

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

    # Expose to Nginx reverse proxy
    ports:
      - "127.0.0.1:8000:8000"

    networks:
      - noesis-network

networks:
  noesis-network:
    driver: bridge

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  pdf_storage:
    driver: local
  backend_logs:
    driver: local
```

### Key Production Optimizations

**Memory Management:**
- Total allocated: ~1.4GB (leaves ~400MB for OS on 1GB instance with swap)
- Strict limits prevent OOM killer
- Services will gracefully handle memory pressure

**Resource Priorities:**
1. PostgreSQL: 512MB (most critical)
2. FastAPI: 384MB (handles requests)
3. Redis: 128MB (optional cache)
4. GROBID: 512MB (on-demand, rarely used simultaneously)

**Storage Strategy:**
- Named volumes for data persistence
- Automatic backups via Docker volume snapshots
- Logs stored separately for debugging

---

## 3. Production Dockerfiles

### Backend: `services/backend/Dockerfile.prod`

```dockerfile
# Multi-stage build for minimal image size
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================
# Final production image
# ============================================
FROM python:3.11-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 noesis && \
    mkdir -p /app/pdfs /app/logs && \
    chown -R noesis:noesis /app

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=noesis:noesis /root/.local /home/noesis/.local

# Copy application code
COPY --chown=noesis:noesis . .

# Update PATH
ENV PATH=/home/noesis/.local/bin:$PATH

# Switch to non-root user
USER noesis

# Expose port
EXPOSE 8000

# Production server with optimized settings for micro instance
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
```

**Key Optimizations:**
- ✅ Multi-stage build (saves ~200MB)
- ✅ Non-root user (security best practice)
- ✅ Single worker (memory constraint)
- ✅ uvloop for async performance
- ✅ No dev dependencies

### ARM64 Compatibility Note

All images used are ARM64-compatible:
- ✅ `python:3.11-slim` - multi-arch
- ✅ `pgvector/pgvector:pg15` - multi-arch
- ✅ `redis:7-alpine` - multi-arch
- ✅ `lfoppiano/grobid:0.7.0` - multi-arch

---

## 4. Environment Configuration

### `.env.production.example` (Backend)

Create `services/backend/.env.production.example`:

```bash
# ================================
# Production Environment Variables
# ================================
# Copy to .env.production and fill in actual values
# NEVER commit .env.production to git!

# ================================
# Database (PostgreSQL + pgvector)
# ================================
# MANUAL: Set strong password
DB_USER=noesis_prod
DB_PASSWORD=CHANGE_ME_STRONG_PASSWORD_HERE

# Set by docker-compose - do not change
DATABASE_URL=postgresql+asyncpg://noesis_prod:CHANGE_ME@db:5432/noesis_prod

# ================================
# Redis Cache
# ================================
# Set by docker-compose - do not change
REDIS_URL=redis://redis:6379

# ================================
# GROBID PDF Processing
# ================================
# Set by docker-compose - do not change
GROBID_URL=http://grobid:8070

# ================================
# Supabase Authentication
# ================================
# MANUAL: Get from Supabase dashboard (https://app.supabase.com)
# Settings > API > Project URL and API Keys
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key-here

# ================================
# OpenAI API
# ================================
# MANUAL: Get from OpenAI platform (https://platform.openai.com/api-keys)
OPENAI_API_KEY=sk-proj-your-openai-api-key-here

# ================================
# Application Settings
# ================================
ENVIRONMENT=production
LOG_LEVEL=INFO

# MANUAL: Set to your Vercel frontend URL
# Example: https://noesis.vercel.app,https://www.yourapp.com
CORS_ORIGINS=https://your-vercel-app.vercel.app

# ================================
# File Upload
# ================================
MAX_UPLOAD_SIZE_MB=50
ALLOWED_EXTENSIONS=.pdf

# ================================
# Rate Limiting (for micro instance)
# ================================
# Lower than dev to prevent resource exhaustion
RATE_LIMIT_PER_MINUTE=50
```

### What You Must Set Manually

| Variable | Where to Get It | Notes |
|----------|----------------|-------|
| `DB_PASSWORD` | **Generate yourself** | Use `openssl rand -base64 32` |
| `SUPABASE_URL` | Supabase Dashboard → Settings → API | Starts with `https://` |
| `SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API | Public key (safe for frontend) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase Dashboard → Settings → API | **Secret key** - never expose |
| `OPENAI_API_KEY` | OpenAI Platform → API Keys | Starts with `sk-proj-` |
| `CORS_ORIGINS` | Your Vercel deployment URL | Get after deploying frontend |

### What's Auto-Configured

| Variable | Set By | Notes |
|----------|--------|-------|
| `DATABASE_URL` | docker-compose.prod.yml | Internal Docker networking |
| `REDIS_URL` | docker-compose.prod.yml | Internal Docker networking |
| `GROBID_URL` | docker-compose.prod.yml | Internal Docker networking |

---

## 5. Nginx & SSL Configuration

### Install Nginx on EC2

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Nginx Configuration: `/etc/nginx/sites-available/noesis`

```nginx
# Rate limiting zone (protect against abuse on micro instance)
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# Upstream backend
upstream noesis_backend {
    server 127.0.0.1:8000;
    keepalive 16;
}

# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name api.yourdomain.com;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.yourdomain.com;

    # SSL certificates (Certbot will populate these)
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    ssl_trusted_certificate /etc/letsencrypt/live/api.yourdomain.com/chain.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/noesis_access.log;
    error_log /var/log/nginx/noesis_error.log;

    # Client upload size (match backend setting)
    client_max_body_size 50M;

    # Timeouts for micro instance (be conservative)
    client_body_timeout 60s;
    client_header_timeout 60s;
    keepalive_timeout 65s;
    send_timeout 60s;

    # Proxy to FastAPI backend
    location / {
        # Rate limiting
        limit_req zone=api_limit burst=20 nodelay;
        limit_conn conn_limit 10;

        proxy_pass http://noesis_backend;
        proxy_http_version 1.1;

        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;  # Long timeout for AI operations

        # Buffering (disable for SSE/streaming if needed)
        proxy_buffering off;
    }

    # Health check endpoint (no rate limiting)
    location /health {
        proxy_pass http://noesis_backend;
        access_log off;
    }
}
```

### Enable the Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/noesis /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## 6. AWS Setup Instructions (Manual Steps)

### Step 1: Launch EC2 Instance

**⚙️ Manual Action Required**

1. **Go to AWS Console** → EC2 → Launch Instance

2. **Name and tags:**
   - Name: `noesis-production`

3. **AMI Selection:**
   - **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type**
   - Architecture: **64-bit (Arm)** ← Important for t4g

4. **Instance type:**
   - **t4g.micro** (1 vCPU, 1 GiB RAM, ARM-based)
   - Cost: ~$3.07/month ($0.0042/hour)

5. **Key pair:**
   - Create new key pair: `noesis-prod-key`
   - Type: RSA
   - Format: `.pem` (for OpenSSH)
   - **Download and save securely**

6. **Network settings:**
   - VPC: Default VPC
   - Subnet: Default (any AZ)
   - Auto-assign public IP: **Enable**

7. **Firewall (Security group):**
   - Create new security group: `noesis-sg`
   - **Inbound rules:**
     ```
     SSH       TCP  22    Your IP (e.g., 1.2.3.4/32)  # Restrict to your IP!
     HTTP      TCP  80    0.0.0.0/0                    # Let's Encrypt
     HTTPS     TCP  443   0.0.0.0/0                    # Public API
     ```
   - **Outbound rules:** Allow all (default)

8. **Configure storage:**
   - Size: **30 GiB**
   - Type: **gp3** (cheaper than gp2)
   - IOPS: 3000 (default)
   - Delete on termination: **No** (keep data if instance replaced)

9. **Advanced details:**
   - Enable **detailed monitoring**: No (costs $2.10/month extra)
   - Termination protection: **Enable** (prevents accidental deletion)

10. **Launch instance**

### Step 2: Allocate Elastic IP (Static IP)

**⚙️ Manual Action Required**

```bash
# In AWS Console:
# 1. EC2 → Elastic IPs → Allocate Elastic IP address
# 2. Allocate
# 3. Select the new IP → Actions → Associate Elastic IP address
# 4. Instance: noesis-production
# 5. Associate
```

**Why?** Prevents IP changes on instance restart. **Free** when associated with a running instance.

### Step 3: Connect to EC2

**⚙️ Manual Action Required**

```bash
# Set key permissions
chmod 400 ~/Downloads/noesis-prod-key.pem

# Connect via SSH
ssh -i ~/Downloads/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP
```

### Step 4: Initial Server Setup

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y \
    git \
    curl \
    vim \
    htop \
    ca-certificates \
    gnupg \
    lsb-release

# Install Docker (official method)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
rm get-docker.sh

# Install Docker Compose V2
sudo apt install -y docker-compose-plugin

# Enable Docker on startup
sudo systemctl enable docker
sudo systemctl start docker

# Install Nginx
sudo apt install -y nginx certbot python3-certbot-nginx

# Logout and login again for Docker group to take effect
exit
```

### Step 5: Enable Swap (Critical for 1GB RAM)

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Create 2GB swap file
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make swap permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Optimize swap usage (only use when necessary)
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Verify
free -h
```

### Step 6: Clone Repository & Configure

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Clone your repository
git clone https://github.com/yourusername/noesis.git
cd noesis

# Create production environment file
cp services/backend/.env.production.example services/backend/.env.production

# Edit with your credentials
nano services/backend/.env.production
```

**Fill in:**
- DB_PASSWORD (generate with `openssl rand -base64 32`)
- SUPABASE credentials
- OPENAI_API_KEY
- CORS_ORIGINS (your Vercel URL)

### Step 7: Initialize Database

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
cd ~/noesis/infra

# Create .env file for docker-compose
cat > .env << EOF
DB_USER=noesis_prod
DB_PASSWORD=YOUR_PASSWORD_FROM_STEP_6
EOF

# Start only database first
docker compose -f docker-compose.prod.yml up -d db

# Wait for DB to be ready (check logs)
docker compose -f docker-compose.prod.yml logs -f db
# Press Ctrl+C when you see "database system is ready to accept connections"

# Run migrations
docker compose -f docker-compose.prod.yml exec db psql -U noesis_prod -d noesis_prod -f /docker-entrypoint-initdb.d/01-init-pgvector.sql
# Repeat for other migration files...
```

### Step 8: Deploy All Services

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
cd ~/noesis/infra

# Build and start all services
docker compose -f docker-compose.prod.yml up -d --build

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f backend
```

### Step 9: Configure Nginx

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Create Nginx config
sudo nano /etc/nginx/sites-available/noesis
# Paste the configuration from Section 5

# Create symlink
sudo ln -s /etc/nginx/sites-available/noesis /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Start Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 7. Domain & SSL Setup

### DNS Configuration

**⚙️ Manual Action Required** (In your domain registrar)

1. **Go to your domain's DNS settings** (e.g., Namecheap, GoDaddy, Cloudflare)

2. **Add A record:**
   ```
   Type: A
   Host: api
   Value: YOUR_ELASTIC_IP
   TTL: 300 (or automatic)
   ```

3. **Wait for DNS propagation** (5-30 minutes)
   ```bash
   # Test from your local machine
   dig api.yourdomain.com
   # Should show your Elastic IP
   ```

### SSL Certificate (Let's Encrypt)

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Obtain certificate (Certbot will auto-configure Nginx)
sudo certbot --nginx -d api.yourdomain.com --non-interactive --agree-tos -m your@email.com

# Test renewal
sudo certbot renew --dry-run

# Auto-renewal is enabled by default via systemd timer
sudo systemctl status certbot.timer
```

**Certbot will:**
- ✅ Obtain SSL certificate
- ✅ Modify Nginx config to use SSL
- ✅ Set up auto-renewal (runs twice daily)

### Verify HTTPS

```bash
# Test from your local machine
curl https://api.yourdomain.com/health

# Should return: {"status": "healthy"}
```

---

## 8. Deployment Workflow

### Initial Deployment (Covered Above)

1. Launch EC2 instance
2. Install Docker + Nginx
3. Clone repository
4. Configure environment
5. Run `docker compose up`
6. Configure SSL

### Regular Updates (Code Changes)

**⚙️ Manual Action Required** (Run on EC2 instance)

```bash
# Connect to EC2
ssh -i ~/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP

# Navigate to project
cd ~/noesis

# Pull latest changes
git pull origin main

# Rebuild and restart services
cd infra
docker compose -f docker-compose.prod.yml up -d --build backend

# Check logs
docker compose -f docker-compose.prod.yml logs -f backend
```

**Zero-downtime deployment** (if needed):
```bash
# Build new image
docker compose -f docker-compose.prod.yml build backend

# Start new container alongside old
docker compose -f docker-compose.prod.yml up -d --no-deps --scale backend=2 backend

# Wait 10 seconds
sleep 10

# Scale back to 1 (removes old container)
docker compose -f docker-compose.prod.yml up -d --no-deps --scale backend=1 backend
```

### Optional: GitHub Actions CI/CD

**Note:** SSH-based deployment is simplest. GitHub Actions adds complexity but automates updates.

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Deploy to EC2
        env:
          SSH_PRIVATE_KEY: ${{ secrets.EC2_SSH_KEY }}
          HOST: ${{ secrets.EC2_HOST }}
        run: |
          echo "$SSH_PRIVATE_KEY" > key.pem
          chmod 600 key.pem
          ssh -o StrictHostKeyChecking=no -i key.pem ubuntu@$HOST << 'EOF'
            cd ~/noesis
            git pull origin main
            cd infra
            docker compose -f docker-compose.prod.yml up -d --build backend
          EOF
```

**Required GitHub Secrets:**
- `EC2_SSH_KEY`: Contents of `noesis-prod-key.pem`
- `EC2_HOST`: Your Elastic IP

**Cost:** $0 (GitHub Actions free tier: 2000 minutes/month)

---

## 9. Cost Breakdown & Safeguards

### Detailed Monthly Cost Estimate

| Service | Unit Cost | Usage | Monthly Cost |
|---------|-----------|-------|--------------|
| **EC2 t4g.micro** | $0.0042/hour | 730 hours | **$3.07** |
| **EBS gp3 30GB** | $0.08/GB-month | 30 GB | **$2.40** |
| **Elastic IP (attached)** | $0.005/hour | Associated | **$0.00** |
| **Elastic IP (unattached)** | $0.005/hour | If stopped | **$3.60** ⚠️ |
| **Data Transfer Out** | $0.09/GB | ~15 GB/month | **$1.35** |
| **Vercel Frontend** | Free | <100GB bandwidth | **$0.00** |
| **DNS (Route 53)** | Optional | If using AWS DNS | **$0.50** |
| **Subtotal** | | | **$7.42** |
| **Buffer (20%)** | | | **$1.48** |
| **Total Estimated** | | | **~$9-12/month** |

### 🚨 Cost Gotchas (Avoid These!)

| Gotcha | Monthly Cost | How to Avoid |
|--------|-------------|--------------|
| **NAT Gateway** | **$32+** | ❌ Don't create - not needed for single-instance |
| **Application Load Balancer** | **$16+** | ❌ Use Nginx instead |
| **RDS db.t3.micro** | **$15+** | ❌ Use containerized PostgreSQL |
| **ElastiCache** | **$13+** | ❌ Use containerized Redis |
| **Elastic IP (unattached)** | **$3.60** | ⚠️ Always associate with running instance |
| **CloudWatch detailed monitoring** | **$2.10** | ❌ Disable on EC2 instance |
| **Data transfer (>100GB)** | **$9/100GB** | ⚠️ Optimize responses, use compression |
| **Snapshots** | **$0.05/GB-month** | ⚠️ Only keep 2-3 recent backups |

### Cost Monitoring & Safeguards

**⚙️ Set Up AWS Budgets** (Manual - Do This First!)

1. **AWS Console** → Billing → Budgets → Create budget
2. **Budget type:** Cost budget
3. **Amount:** $15/month
4. **Alert threshold:** 80% ($12)
5. **Email:** Your email
6. **Create budget**

**⚙️ Enable Cost Alerts**

```bash
# AWS CLI (if installed)
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE
```

**⚙️ Monitor via EC2 Dashboard**

```bash
# On EC2 instance - monitor resource usage
htop                    # CPU/RAM usage
df -h                   # Disk usage
docker stats            # Container resource usage
sudo iftop              # Network bandwidth (install: sudo apt install iftop)
```

### Automatic Shutdown (Optional Cost Saver)

If not running 24/7, use AWS Instance Scheduler:

```bash
# Stop instance at 11 PM, start at 8 AM on weekdays
# Saves ~67% on compute costs
# Not recommended for production - only for dev/staging
```

---

## 10. Performance & Stability on Micro Instances

### Recommended Settings for t4g.micro (1GB RAM)

#### FastAPI / Uvicorn Configuration

**✅ Optimal Settings:**
```bash
# In Dockerfile.prod CMD
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \              # CRITICAL: Single worker for 1GB RAM
  --loop uvloop \            # Faster async event loop
  --log-level info \
  --proxy-headers \
  --forwarded-allow-ips "*" \
  --timeout-keep-alive 10 \  # Close idle connections
  --limit-concurrency 50     # Max concurrent requests
```

**Why single worker?**
- Each worker = ~200-300MB RAM
- 1GB total - 512MB (Postgres) - 128MB (Redis) - 400MB (OS) = **no room for multiple workers**
- Single worker with async I/O can handle 20-50 concurrent requests

#### PostgreSQL Tuning

**Already configured in docker-compose.prod.yml:**
```yaml
POSTGRES_SHARED_BUFFERS: 128MB      # 25% of allocated memory
POSTGRES_EFFECTIVE_CACHE_SIZE: 256MB # Expected OS + DB cache
POSTGRES_WORK_MEM: 4MB               # Per-operation memory
```

**Why these values?**
- Prevents PostgreSQL from consuming >512MB
- Optimized for small working sets
- Prioritizes stability over performance

#### Redis Configuration

```bash
# In docker-compose.prod.yml
--maxmemory 100mb              # Hard limit
--maxmemory-policy allkeys-lru # Evict least recently used
```

**Why 100MB?**
- Keeps Redis as a cache, not primary store
- Prevents memory exhaustion
- Automatically evicts old data

### Request Concurrency Limits

**Nginx Rate Limiting:**
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# Apply in location block
limit_req zone=api_limit burst=20 nodelay;
limit_conn conn_limit 10;
```

**Why rate limit?**
- Prevents abuse/DDoS
- Protects micro instance from overload
- Ensures fair resource allocation

### Performance Trade-offs

| Metric | Production (t4g.micro) | High-Performance Setup |
|--------|----------------------|----------------------|
| **Max concurrent users** | 10-20 | 100-500 |
| **Response time (simple)** | 50-200ms | 20-50ms |
| **Response time (AI)** | 2-10s | 1-5s |
| **PDF processing** | 5-30s | 2-10s |
| **Daily active users** | 50-200 | 1000+ |
| **Requests per minute** | 50-100 | 500-1000 |

### When Performance Degrades

**Symptoms:**
- Response time >5s for simple requests
- 502/503 errors from Nginx
- OOM (Out of Memory) kills
- Slow PDF processing

**Immediate fixes:**
1. **Restart services:**
   ```bash
   docker compose -f docker-compose.prod.yml restart backend
   ```

2. **Check memory:**
   ```bash
   free -h
   docker stats
   ```

3. **Clear Redis cache:**
   ```bash
   docker compose -f docker-compose.prod.yml exec redis redis-cli FLUSHALL
   ```

**Long-term fixes:**
- Upgrade to t4g.small (2GB RAM, $6/month)
- Move database to managed RDS
- Add caching layer (Cloudflare)

### Monitoring Commands

```bash
# Overall system health
htop

# Docker container stats (live)
docker stats

# Check disk space
df -h

# Check swap usage
free -h

# Backend logs
docker compose -f docker-compose.prod.yml logs -f backend

# Database performance
docker compose -f docker-compose.prod.yml exec db psql -U noesis_prod -d noesis_prod -c "SELECT * FROM pg_stat_activity;"
```

---

## 11. Future Scaling Path (Conceptual)

### When to Scale (Indicators)

**🚦 Green Light (Stay on Current Setup):**
- <50 daily active users
- <500 requests/day
- Stable response times (<2s avg)
- Memory usage <80%

**🟡 Yellow Light (Plan to Scale):**
- 50-200 daily active users
- 500-2000 requests/day
- Occasional slowdowns during peak
- Memory usage 80-95%

**🔴 Red Light (Scale Now):**
- >200 daily active users
- >2000 requests/day
- Frequent 502/503 errors
- Constant OOM kills
- Paying for OpenAI usage >$50/month

### Scaling Path 1: Vertical Scaling (Easiest)

**Step 1:** Upgrade EC2 instance
```
t4g.micro  → t4g.small  (+$3/month)  → 2GB RAM, 2 vCPUs
t4g.small  → t4g.medium (+$12/month) → 4GB RAM, 2 vCPUs
```

**Benefits:**
- ✅ Zero code changes
- ✅ Same architecture
- ✅ More workers possible

**Limitations:**
- ❌ Still single point of failure
- ❌ Limited to instance size

### Scaling Path 2: Managed Services (Moderate)

**When:** >100 DAU, want reliability

**Components to migrate:**

1. **PostgreSQL → RDS**
   - Cost: $15-30/month (db.t4g.micro)
   - Benefits: Automated backups, read replicas, high availability
   - Change: Update `DATABASE_URL` only

2. **Redis → ElastiCache**
   - Cost: $13/month (cache.t4g.micro)
   - Benefits: Managed maintenance, automatic failover
   - Change: Update `REDIS_URL` only

3. **Files → S3**
   - Cost: $1-5/month
   - Benefits: Unlimited storage, CDN integration
   - Change: Add S3 upload logic

**New Monthly Cost:** $35-50

### Scaling Path 3: ECS + Load Balancer (Advanced)

**When:** >500 DAU, need high availability

**Architecture:**
```
Users → ALB → ECS Service (2-4 tasks) → RDS + ElastiCache + S3
```

**Components:**
- ALB: $16/month
- ECS Fargate: $30-60/month (2-4 tasks)
- RDS: $30/month (larger instance)
- ElastiCache: $13-25/month
- S3: $5-10/month

**New Monthly Cost:** $95-150

**Benefits:**
- ✅ Auto-scaling
- ✅ Zero-downtime deployments
- ✅ High availability
- ✅ Load balancing

**Migration Steps (High-Level):**
1. Push Docker images to ECR
2. Create ECS task definition
3. Create ECS service with ALB
4. Migrate database to RDS
5. Update DNS to point to ALB
6. Decommission EC2 instance

### Scaling Path 4: Multi-Region (Enterprise)

**When:** >5000 DAU, global users

**Architecture:**
```
CloudFront → Multi-region ALB → ECS in multiple AZs → Aurora Global Database
```

**Cost:** $500-1000/month

**Not relevant for early-stage - mentioned for completeness only.**

---

## Quick Reference Commands

### 🚀 Deploy New Code
```bash
ssh -i ~/noesis-prod-key.pem ubuntu@YOUR_IP
cd ~/noesis && git pull
cd infra && docker compose -f docker-compose.prod.yml up -d --build backend
```

### 🔍 Check Status
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

### 💾 Backup Database
```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U noesis_prod noesis_prod > backup.sql
```

### 🔄 Restart Services
```bash
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml restart db
```

### 📊 Monitor Resources
```bash
htop                 # CPU/RAM
docker stats         # Container usage
df -h                # Disk space
```

---

## Security Checklist

- ✅ SSH key-only authentication (no password)
- ✅ Security group restricts SSH to your IP
- ✅ Non-root user in Docker containers
- ✅ SSL/TLS with Let's Encrypt
- ✅ Environment secrets not in git
- ✅ Database not exposed to public internet
- ✅ Rate limiting enabled
- ✅ Firewall (UFW) enabled:
  ```bash
  sudo ufw allow 22/tcp
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw enable
  ```

---

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker compose -f docker-compose.prod.yml logs backend

# Common issues:
# - Missing env vars → Check .env.production
# - Database not ready → Wait 30s after DB starts
# - Out of memory → Check `docker stats`, restart instance
```

### SSL certificate fails
```bash
# Check DNS
dig api.yourdomain.com

# Check Nginx
sudo nginx -t
sudo systemctl status nginx

# Re-run certbot
sudo certbot --nginx -d api.yourdomain.com
```

### Out of Memory
```bash
# Check swap
free -h

# Add more swap if needed
sudo fallocate -l 3G /swapfile2
sudo chmod 600 /swapfile2
sudo mkswap /swapfile2
sudo swapon /swapfile2

# Restart services
docker compose -f docker-compose.prod.yml restart
```

---

## Summary

✅ **Total Monthly Cost:** $9-12 (within budget)
✅ **Services:** All on one EC2 instance
✅ **SSL:** Free with Let's Encrypt
✅ **Deployment:** Simple `git pull && docker compose up`
✅ **Performance:** Suitable for 50-200 DAU
✅ **Scaling:** Clear path to ECS/RDS when needed

**You're ready to deploy!** Start with Step 1 of Section 6 and work through each manual step carefully.
