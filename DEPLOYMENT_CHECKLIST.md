# AWS Production Deployment Checklist

> **Total Time:** ~2-3 hours (first time)
> **Cost:** $9-12/month

---

## Pre-Deployment (Do Once)

### ✅ Local Preparation

- [ ] **Generate strong database password**
  ```bash
  openssl rand -base64 32
  # Save this securely!
  ```

- [ ] **Gather Supabase credentials**
  - [ ] Go to https://app.supabase.com
  - [ ] Open your project → Settings → API
  - [ ] Copy: Project URL
  - [ ] Copy: `anon` key (public)
  - [ ] Copy: `service_role` key (secret)

- [ ] **Get OpenAI API key**
  - [ ] Go to https://platform.openai.com/api-keys
  - [ ] Create new key → Copy and save

- [ ] **Choose your domain**
  - [ ] Decide on subdomain (e.g., `api.yourdomain.com`)
  - [ ] Have access to DNS settings

---

## AWS Setup (One-Time)

### ✅ Phase 1: Launch EC2 Instance (~10 minutes)

- [ ] **Open AWS Console** → EC2 → Launch Instance

- [ ] **Configure instance:**
  - [ ] Name: `noesis-production`
  - [ ] AMI: **Ubuntu 22.04 LTS (Arm)**
  - [ ] Instance type: **t4g.micro**
  - [ ] Key pair: Create new → `noesis-prod-key` → Download `.pem` file
  - [ ] Network: Default VPC, auto-assign public IP

- [ ] **Configure security group:**
  - [ ] Name: `noesis-sg`
  - [ ] Inbound rules:
    - [ ] SSH (22) → My IP
    - [ ] HTTP (80) → 0.0.0.0/0
    - [ ] HTTPS (443) → 0.0.0.0/0

- [ ] **Configure storage:**
  - [ ] 30 GB gp3 EBS
  - [ ] Delete on termination: **No**

- [ ] **Enable termination protection**

- [ ] **Launch instance**

### ✅ Phase 2: Allocate Elastic IP (~2 minutes)

- [ ] **EC2 → Elastic IPs → Allocate**

- [ ] **Associate with instance:**
  - [ ] Select IP → Actions → Associate
  - [ ] Instance: `noesis-production`
  - [ ] Associate

- [ ] **Copy Elastic IP address** (you'll need this!)

### ✅ Phase 3: Set Up AWS Budget Alert (~3 minutes)

- [ ] **AWS Console → Billing → Budgets**

- [ ] **Create budget:**
  - [ ] Type: Cost budget
  - [ ] Amount: $15/month
  - [ ] Alert at: 80% ($12)
  - [ ] Email: Your email
  - [ ] Create

---

## Server Configuration (~30 minutes)

### ✅ Phase 4: Connect to EC2

- [ ] **Set key permissions:**
  ```bash
  chmod 400 ~/Downloads/noesis-prod-key.pem
  ```

- [ ] **SSH into instance:**
  ```bash
  ssh -i ~/Downloads/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP
  ```

### ✅ Phase 5: Install Dependencies

Copy and paste these commands one by one:

- [ ] **Update system:**
  ```bash
  sudo apt update && sudo apt upgrade -y
  ```

- [ ] **Install essential packages:**
  ```bash
  sudo apt install -y git curl vim htop ca-certificates gnupg lsb-release
  ```

- [ ] **Install Docker:**
  ```bash
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  sudo usermod -aG docker ubuntu
  rm get-docker.sh
  ```

- [ ] **Install Docker Compose:**
  ```bash
  sudo apt install -y docker-compose-plugin
  ```

- [ ] **Install Nginx:**
  ```bash
  sudo apt install -y nginx certbot python3-certbot-nginx
  ```

- [ ] **Enable services:**
  ```bash
  sudo systemctl enable docker
  sudo systemctl enable nginx
  ```

- [ ] **Logout and login again:**
  ```bash
  exit
  # Then SSH back in
  ssh -i ~/Downloads/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP
  ```

### ✅ Phase 6: Configure Swap (Critical!)

- [ ] **Create 2GB swap:**
  ```bash
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  ```

- [ ] **Make permanent:**
  ```bash
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  sudo sysctl vm.swappiness=10
  echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
  ```

- [ ] **Verify:**
  ```bash
  free -h
  # Should show 2G swap
  ```

---

## Application Deployment (~30 minutes)

### ✅ Phase 7: Clone and Configure

- [ ] **Clone repository:**
  ```bash
  cd ~
  git clone https://github.com/yourusername/noesis.git
  cd noesis
  ```

- [ ] **Create backend .env.production:**
  ```bash
  cp services/backend/.env.production.example services/backend/.env.production
  nano services/backend/.env.production
  ```

- [ ] **Fill in these values:**
  - [ ] `DB_PASSWORD=` (your generated password)
  - [ ] `DATABASE_URL=` (update password in connection string)
  - [ ] `SUPABASE_URL=`
  - [ ] `SUPABASE_ANON_KEY=`
  - [ ] `SUPABASE_SERVICE_ROLE_KEY=`
  - [ ] `OPENAI_API_KEY=`
  - [ ] `CORS_ORIGINS=` (leave as example for now, update after Vercel deploy)

- [ ] **Save and exit** (Ctrl+X, Y, Enter)

- [ ] **Create Docker Compose .env:**
  ```bash
  cd ~/noesis/infra
  nano .env
  ```

- [ ] **Add these lines:**
  ```bash
  DB_USER=noesis_prod
  DB_PASSWORD=YOUR_PASSWORD_HERE
  ```

- [ ] **Save and exit**

### ✅ Phase 8: Deploy Database

- [ ] **Start database only:**
  ```bash
  cd ~/noesis/infra
  docker compose -f docker-compose.prod.yml up -d db
  ```

- [ ] **Wait for database (watch logs):**
  ```bash
  docker compose -f docker-compose.prod.yml logs -f db
  # Wait for "database system is ready to accept connections"
  # Press Ctrl+C to exit logs
  ```

- [ ] **Run migrations:**
  ```bash
  # List migration files
  ls db-init/

  # Run each migration in order
for file in db-init/*.sql; do docker compose -f docker-compose.prod.yml exec db psql -U noesis_prod -d noesis_prod -f /docker-entrypoint-initdb.d/$(basename $file); done
  ```

### ✅ Phase 9: Deploy All Services

- [ ] **Build and start all services:**
  ```bash
  docker compose -f docker-compose.prod.yml up -d --build
  ```

- [ ] **Check status:**
  ```bash
  docker compose -f docker-compose.prod.yml ps
  # All should show "running" and "healthy"
  ```

- [ ] **Check backend logs:**
  ```bash
  docker compose -f docker-compose.prod.yml logs -f backend
  # Should see "Uvicorn running on http://0.0.0.0:8000"
  ```

- [ ] **Test locally:**
  ```bash
  curl http://localhost:8000/health
  # Should return: {"status":"healthy"}
  ```

---

## Nginx & SSL (~20 minutes)

### ✅ Phase 10: Configure Nginx

- [ ] **Create Nginx config:**
  ```bash
  sudo nano /etc/nginx/sites-available/noesis
  ```

- [ ] **Copy template content:**
  - [ ] Open `infra/nginx.conf.template` on your local machine
  - [ ] Copy all content
  - [ ] Paste into nano
  - [ ] **Replace `api.yourdomain.com` with your actual domain** (2 places)
  - [ ] Save and exit

- [ ] **Enable site:**
  ```bash
  sudo ln -s /etc/nginx/sites-available/noesis /etc/nginx/sites-enabled/
  ```

- [ ] **Remove default site:**
  ```bash
  sudo rm /etc/nginx/sites-enabled/default
  ```

- [ ] **Test Nginx config:**
  ```bash
  sudo nginx -t
  # Should say "syntax is ok" and "test is successful"
  ```

- [ ] **Start Nginx:**
  ```bash
  sudo systemctl restart nginx
  ```

### ✅ Phase 11: Configure DNS

**⚠️ Do this in your domain registrar (Namecheap, GoDaddy, Cloudflare, etc.)**

- [ ] **Add A record:**
  - [ ] Type: `A`
  - [ ] Host: `api` (or your chosen subdomain)
  - [ ] Value: `YOUR_ELASTIC_IP`
  - [ ] TTL: `300` (or automatic)

- [ ] **Wait for DNS propagation** (5-30 minutes)

- [ ] **Test DNS:**
  ```bash
  # On your local machine
  dig api.yourdomain.com
  # Should show your Elastic IP
  ```

### ✅ Phase 12: Install SSL Certificate

**⚠️ Only run after DNS is working!**

- [ ] **Obtain certificate:**
  ```bash
  sudo certbot --nginx -d api.yourdomain.com --non-interactive --agree-tos -m your@email.com
  ```

- [ ] **Verify auto-renewal:**
  ```bash
  sudo certbot renew --dry-run
  ```

- [ ] **Check renewal timer:**
  ```bash
  sudo systemctl status certbot.timer
  # Should be "active"
  ```

### ✅ Phase 13: Test Production API

- [ ] **Test HTTPS:**
  ```bash
  # On your local machine
  curl https://api.yourdomain.com/health
  # Should return: {"status":"healthy"}
  ```

- [ ] **Test in browser:**
  - [ ] Open `https://api.yourdomain.com/health`
  - [ ] Should show JSON response
  - [ ] Check SSL certificate (should be valid)

---

## Frontend Deployment (Vercel)

### ✅ Phase 14: Deploy Frontend to Vercel

- [ ] **Install Vercel CLI** (on your local machine):
  ```bash
  npm install -g vercel
  ```

- [ ] **Navigate to frontend:**
  ```bash
  cd ~/path/to/noesis/services/frontend
  ```

- [ ] **Update .env:**
  ```bash
  nano .env
  ```

- [ ] **Set production API URL:**
  ```bash
  VITE_API_URL=https://api.yourdomain.com
  ```

- [ ] **Deploy to Vercel:**
  ```bash
  vercel
  # Follow prompts:
  # - Set up and deploy? Yes
  # - Which scope? Your account
  # - Link to existing project? No
  # - Project name? noesis
  # - Directory? ./
  # - Override settings? No
  ```

- [ ] **Note Vercel URL** (e.g., `https://noesis-abc123.vercel.app`)

- [ ] **Deploy to production:**
  ```bash
  vercel --prod
  ```

### ✅ Phase 15: Update CORS Settings

- [ ] **SSH back to EC2:**
  ```bash
  ssh -i ~/Downloads/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP
  ```

- [ ] **Update backend .env:**
  ```bash
  nano ~/noesis/services/backend/.env.production
  ```

- [ ] **Update CORS_ORIGINS:**
  ```bash
  CORS_ORIGINS=https://your-vercel-url.vercel.app,https://www.yourapp.com
  ```

- [ ] **Restart backend:**
  ```bash
  cd ~/noesis/infra
  docker compose -f docker-compose.prod.yml restart backend
  ```

### ✅ Phase 16: Final Testing

- [ ] **Test login flow:**
  - [ ] Open Vercel URL in browser
  - [ ] Try signing up
  - [ ] Try logging in
  - [ ] Create a project
  - [ ] Upload a PDF

- [ ] **Monitor logs:**
  ```bash
  # On EC2
  docker compose -f docker-compose.prod.yml logs -f
  ```

---

## Post-Deployment

### ✅ Phase 17: Security Hardening

- [ ] **Enable UFW firewall:**
  ```bash
  sudo ufw allow 22/tcp
  sudo ufw allow 80/tcp
  sudo ufw allow 443/tcp
  sudo ufw --force enable
  ```

- [ ] **Disable password auth (SSH key only):**
  ```bash
  sudo nano /etc/ssh/sshd_config
  # Set: PasswordAuthentication no
  sudo systemctl restart sshd
  ```

- [ ] **Update security group:**
  - [ ] AWS Console → EC2 → Security Groups
  - [ ] Find `noesis-sg`
  - [ ] Edit inbound SSH rule → Change `My IP` to your static IP only

### ✅ Phase 18: Monitoring Setup

- [ ] **Create monitoring script:**
  ```bash
  nano ~/monitor.sh
  ```

- [ ] **Add content:**
  ```bash
  #!/bin/bash
  echo "=== System Resources ==="
  free -h
  echo ""
  echo "=== Disk Usage ==="
  df -h
  echo ""
  echo "=== Docker Stats ==="
  docker stats --no-stream
  echo ""
  echo "=== Service Health ==="
  curl -s http://localhost:8000/health | jq .
  ```

- [ ] **Make executable:**
  ```bash
  chmod +x ~/monitor.sh
  ```

- [ ] **Run weekly:**
  ```bash
  ./monitor.sh
  ```

### ✅ Phase 19: Backup Setup

- [ ] **Create backup script:**
  ```bash
  nano ~/backup.sh
  ```

- [ ] **Add content:**
  ```bash
  #!/bin/bash
  BACKUP_DIR=~/backups
  DATE=$(date +%Y%m%d_%H%M%S)

  mkdir -p $BACKUP_DIR

  # Backup database
  cd ~/noesis/infra
  docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U noesis_prod noesis_prod > $BACKUP_DIR/db_$DATE.sql

  # Compress
  gzip $BACKUP_DIR/db_$DATE.sql

  # Keep only last 7 backups
  ls -t $BACKUP_DIR/db_*.sql.gz | tail -n +8 | xargs -r rm

  echo "Backup completed: $BACKUP_DIR/db_$DATE.sql.gz"
  ```

- [ ] **Make executable:**
  ```bash
  chmod +x ~/backup.sh
  ```

- [ ] **Schedule weekly backups:**
  ```bash
  crontab -e
  # Add this line:
  0 2 * * 0 /home/ubuntu/backup.sh
  ```

---

## Verification

### ✅ Final Checklist

- [ ] ✅ Frontend loads at Vercel URL
- [ ] ✅ Can sign up and log in
- [ ] ✅ Can create projects
- [ ] ✅ Can upload PDFs
- [ ] ✅ Can use AI chat
- [ ] ✅ SSL certificate is valid
- [ ] ✅ API responds at `https://api.yourdomain.com`
- [ ] ✅ All Docker containers are healthy
- [ ] ✅ AWS budget alert is configured
- [ ] ✅ Backups are scheduled
- [ ] ✅ Firewall is enabled
- [ ] ✅ Monitoring script works

---

## Cost Verification

- [ ] **Check AWS Billing:**
  - [ ] AWS Console → Billing Dashboard
  - [ ] Should show ~$0.30-0.50/day
  - [ ] Projected monthly: $9-12

- [ ] **Verify no unexpected charges:**
  - [ ] No NAT Gateway
  - [ ] No Load Balancer
  - [ ] No RDS
  - [ ] No ElastiCache
  - [ ] Elastic IP is associated

---

## 🎉 Deployment Complete!

**Your production infrastructure:**
- ✅ Backend API: `https://api.yourdomain.com`
- ✅ Frontend: Your Vercel URL
- ✅ Database: PostgreSQL + pgvector on EC2
- ✅ SSL: Let's Encrypt (auto-renewing)
- ✅ Cost: $9-12/month

**Next steps:**
1. Share with pilot users
2. Monitor performance
3. Collect feedback
4. Iterate!

---

## Quick Reference

**Deploy code updates:**
```bash
ssh -i ~/noesis-prod-key.pem ubuntu@YOUR_ELASTIC_IP
cd ~/noesis && git pull
cd infra && docker compose -f docker-compose.prod.yml up -d --build backend
```

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f
```

**Check status:**
```bash
docker compose -f docker-compose.prod.yml ps
./monitor.sh
```

**Backup now:**
```bash
./backup.sh
```
