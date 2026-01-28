# Noesis Production Security Checklist

### 4. Configure Environment Variables in Deployment Platform

**For AWS EC2 (Backend):**
```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Create secure .env file
sudo nano /opt/noesis/backend/.env

# Add environment variables (use new regenerated keys):
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-NEW-service-role-key
OPENAI_API_KEY=your-NEW-openai-key
GROBID_URL=http://grobid:8070
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
ENVIRONMENT=production
CORS_ORIGINS=https://your-frontend-domain.vercel.app
LOG_LEVEL=INFO

# Secure the file
sudo chmod 600 /opt/noesis/backend/.env
sudo chown root:root /opt/noesis/backend/.env

# Verify permissions
ls -la /opt/noesis/backend/.env
# Should show: -rw------- (only root can read/write)
```

## 🟡 MEDIUM PRIORITY - Fix Within 1 Week of Launch

### 11. Configure Production CORS
- [ ] Update `.env.production`:
```bash
# CRITICAL: Replace with your actual production domain
CORS_ORIGINS=https://noesis.vercel.app

# NO wildcards, NO localhost in production!
```

### 12. Enable HTTPS Only
- [ ] Verify SSL/TLS certificates:
  - Vercel: Automatic HTTPS (nothing to do)
  - AWS EC2: Set up Let's Encrypt or AWS Certificate Manager

- [ ] Configure HSTS (Strict-Transport-Security):
  - Already handled by SecurityHeadersMiddleware
  - Verify header is present in production

### 13. Set Up Error Tracking
- [ ] Configure Sentry for production:
```python
# In main.py, verify Sentry is configured
sentry_sdk.init(
    dsn=settings.SENTRY_DSN,  # Store in environment variable
    environment=settings.ENVIRONMENT,
    traces_sample_rate=0.1,  # 10% of requests
    profiles_sample_rate=0.1,
)
```

- [ ] Test error reporting:
  - Trigger a test error
  - Verify it appears in Sentry dashboard

### 14. Implement Request Logging
- [ ] Add secure logging middleware:

```python
from app.core.security_middleware import LogSanitizer

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"from {request.client.host}"
    )

    # Log headers (sanitized)
    headers = dict(request.headers)
    if "authorization" in headers:
        headers["authorization"] = "Bearer [REDACTED]"

    response = await call_next(request)

    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"status={response.status_code}"
    )

    return response
```

### 15. Configure Database Backups
- [ ] Enable automated backups in Supabase:
  - Dashboard → Database → Backups
  - Enable daily backups
  - Set retention to 30 days

- [ ] Test backup restoration:
  - Create test project
  - Trigger manual backup
  - Restore and verify

### 16. Set Up Monitoring & Alerts
- [ ] Configure Supabase monitoring:
  - Dashboard → Reports
  - Set up email alerts for:
    - High API usage (>80% quota)
    - Storage usage (>80% quota)
    - Error rate spikes

- [ ] Configure backend monitoring:
  - Set up CloudWatch (AWS) or equivalent
  - Alert on:
    - High CPU usage (>80%)
    - High memory usage (>80%)
    - Error rate >1%
    - Response time >2s


