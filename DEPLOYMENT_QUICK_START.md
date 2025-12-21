# Deployment Quick Start

> **Get Noesis running in production for $10-20/month in ~2 hours**

---

## Prerequisites

- [ ] AWS Account
- [ ] Domain name (with DNS access)
- [ ] Supabase account (free tier)
- [ ] OpenAI API key

---

## Three-Step Deployment

### 1️⃣ AWS Setup (30 minutes)

**Launch EC2 instance:**
- Type: t4g.micro (ARM)
- OS: Ubuntu 22.04 LTS
- Storage: 30GB gp3
- Security: SSH (your IP), HTTP (all), HTTPS (all)
- Download: SSH key (.pem file)

**Get Elastic IP:**
- Allocate → Associate with instance
- Note the IP address

**SSH into instance:**
```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

**Run auto-setup:**
```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/noesis/main/scripts/ec2-setup.sh | bash
```

**Logout and login again:**
```bash
exit
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
```

---

### 2️⃣ Deploy Application (45 minutes)

**Clone repository:**
```bash
git clone https://github.com/yourusername/noesis.git
cd noesis
```

**Configure environment:**
```bash
# Backend
cp services/backend/.env.production.example services/backend/.env.production
nano services/backend/.env.production
# Fill in: DB_PASSWORD, SUPABASE_*, OPENAI_API_KEY

# Docker Compose
cd infra
nano .env
# Add: DB_USER=noesis_prod, DB_PASSWORD=YOUR_PASSWORD
```

**Deploy:**
```bash
# Start database
docker compose -f docker-compose.prod.yml up -d db

# Wait 30 seconds, then run migrations
for file in db-init/*.sql; do
  docker compose -f docker-compose.prod.yml exec db \
    psql -U noesis_prod -d noesis_prod -f /docker-entrypoint-initdb.d/$(basename $file)
done

# Start all services
docker compose -f docker-compose.prod.yml up -d --build

# Verify
docker compose -f docker-compose.prod.yml ps
```

**Configure Nginx:**
```bash
# Copy template
sudo nano /etc/nginx/sites-available/noesis
# Paste content from infra/nginx.conf.template
# Replace api.yourdomain.com with your domain

# Enable
sudo ln -s /etc/nginx/sites-available/noesis /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

### 3️⃣ DNS & SSL (30 minutes)

**Configure DNS:**
- Go to your domain registrar
- Add A record: `api` → `YOUR_ELASTIC_IP`
- Wait 5-30 minutes for propagation

**Install SSL certificate:**
```bash
sudo certbot --nginx -d api.yourdomain.com --non-interactive --agree-tos -m your@email.com
```

**Test:**
```bash
curl https://api.yourdomain.com/health
# Should return: {"status":"healthy"}
```

---

## Deploy Frontend (15 minutes)

**Local machine:**
```bash
cd ~/noesis/services/frontend

# Update .env
nano .env
# Set: VITE_API_URL=https://api.yourdomain.com

# Deploy to Vercel
npm install -g vercel
vercel
vercel --prod
```

**Update backend CORS:**
```bash
# SSH to EC2
nano ~/noesis/services/backend/.env.production
# Update: CORS_ORIGINS=https://your-vercel-url.vercel.app

# Restart backend
cd ~/noesis/infra
docker compose -f docker-compose.prod.yml restart backend
```

---

## Test Everything

- [ ] Open Vercel URL in browser
- [ ] Sign up with email
- [ ] Create a project
- [ ] Upload a PDF
- [ ] Try AI chat
- [ ] Check `https://api.yourdomain.com/health`

---

## Daily Operations

### Deploy Updates
```bash
ssh -i your-key.pem ubuntu@YOUR_ELASTIC_IP
cd ~/noesis && git pull
cd infra && docker compose -f docker-compose.prod.yml up -d --build backend
```

### Monitor
```bash
~/monitor.sh           # System resources
docker compose -f docker-compose.prod.yml logs -f  # Live logs
```

### Backup
```bash
~/backup.sh            # Manual backup
crontab -e             # Schedule: 0 2 * * 0 /home/ubuntu/backup.sh
```

---

## Cost Breakdown

| Item | Monthly Cost |
|------|-------------|
| EC2 t4g.micro | $3.07 |
| 30GB EBS gp3 | $2.40 |
| Data transfer (~15GB) | $1.35 |
| Vercel (frontend) | $0.00 |
| **Total** | **~$7-9** |

**Plus buffer:** ~$9-12/month total

---

## Troubleshooting

### Backend won't start
```bash
docker compose -f docker-compose.prod.yml logs backend
# Check .env.production has all required values
```

### Out of memory
```bash
free -h                # Check swap is active
docker stats           # Check container memory usage
docker compose -f docker-compose.prod.yml restart
```

### SSL fails
```bash
dig api.yourdomain.com  # Verify DNS
sudo nginx -t           # Test Nginx config
sudo certbot --nginx -d api.yourdomain.com  # Re-run
```

---

## Documentation

- **Full Guide:** [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)
- **Detailed Checklist:** [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- **Environment Setup:** [ENV_SETUP.md](ENV_SETUP.md)

---

## Support

**Common issues:**
1. DNS not propagating → Wait longer (up to 48h max, usually 30min)
2. Docker out of memory → Check swap is enabled (`free -h`)
3. Backend crashes → Check logs, verify .env.production
4. SSL redirect loop → Check CORS_ORIGINS matches Vercel URL

**Need help?** Open an issue on GitHub.

---

## Security Checklist

- [ ] ✅ UFW firewall enabled
- [ ] ✅ SSH restricted to your IP
- [ ] ✅ SSL certificate installed
- [ ] ✅ .env.production not in git
- [ ] ✅ Strong database password set
- [ ] ✅ AWS budget alert configured ($15/month)
- [ ] ✅ Backups scheduled

---

## 🎉 You're Live!

**Your infrastructure:**
- Frontend: Vercel (free, global CDN)
- Backend: AWS EC2 (ARM, $3/month)
- Database: PostgreSQL + pgvector
- SSL: Let's Encrypt (auto-renewing)
- Total: $9-12/month

**Ready for:**
- 50-200 daily active users
- 500-2000 requests/day
- Early pilots and testing
- I2P programs

**Next steps:**
1. Share with users
2. Collect feedback
3. Monitor performance
4. Scale when needed (see AWS_DEPLOYMENT_GUIDE.md section 11)
