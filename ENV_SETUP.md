# Environment Setup Guide

## Quick Start (Development)

Your environment variables are already configured in:
- **Backend**: `services/backend/.env`
- **Frontend**: `services/frontend/.env`

Just run `docker compose up` from the `infra/` directory and you're good to go!

```bash
cd infra/
docker compose up -d
```

## Environment Files

### Current Setup
```
noesis/
├── .env.template           # Template for production deployment
├── services/
│   ├── backend/.env       # Backend configuration (active)
│   └── frontend/.env      # Frontend configuration (active)
```

### Backend (.env)
Located at: `services/backend/.env`

**Contains:**
- Supabase credentials (authentication)
- OpenAI API key
- Database URL (PostgreSQL + pgvector)
- Redis URL
- GROBID URL
- CORS settings
- Application configuration

### Frontend (.env)
Located at: `services/frontend/.env`

**Contains:**
- Backend API URL
- Supabase credentials (public keys only)
- Optional analytics configuration

## Architecture Notes

### What's Stored Where

**Supabase** (Cloud):
- ✅ User authentication (sign up, login, JWT tokens)
- ❌ NOT used for application data storage

**Local PostgreSQL** (Docker):
- ✅ All application data (projects, documents, research papers)
- ✅ Vector embeddings for RAG/semantic search
- ✅ Chat history, insights, recommendations
- ⚠️ Requires pgvector extension

**Local Redis** (Docker):
- ✅ Caching layer
- ✅ Session storage
- ✅ Background job queues

**GROBID** (Docker):
- ✅ PDF text extraction
- ✅ Citation parsing
- ✅ Metadata extraction

## Production Deployment

When deploying to production:

1. **Copy `.env.template`** and fill in production values
2. **Replace Docker service URLs** with hosted services:
   - `db:5432` → Your PostgreSQL host (Render, Supabase, AWS RDS)
   - `redis:6379` → Your Redis host (Upstash, Redis Cloud)
   - `http://grobid:8070` → Your GROBID deployment
3. **Update CORS_ORIGINS** with your production frontend URL
4. **Set ENVIRONMENT=production**
5. **Use secret management** (never commit .env files!)

### Required Production Services

1. **PostgreSQL with pgvector**
   - Providers: Supabase, Render, AWS RDS, DigitalOcean
   - Must support pgvector extension

2. **Redis**
   - Providers: Upstash (free tier), Redis Cloud, AWS ElastiCache

3. **GROBID** (PDF Processing)
   - Self-host as Docker container
   - Needs ~2-4GB RAM minimum

## Security Checklist

- ✅ `.env` files are in `.gitignore`
- ✅ Never commit API keys or secrets
- ✅ Use different credentials for dev/staging/prod
- ✅ Frontend uses public Supabase keys only
- ✅ Backend uses service role keys (never exposed to client)
- ⚠️ Rotate OpenAI API key regularly
- ⚠️ Monitor Supabase usage and set rate limits

## Troubleshooting

### Backend can't connect to database
- Check `DATABASE_URL` in `services/backend/.env`1
- In Docker: Use hostname `db` (not `localhost`)
- In production: Use your hosted PostgreSQL URL

### Frontend can't reach backend
- Check `VITE_API_URL` in `services/frontend/.env`
- In Docker: Use `http://localhost:8000`
- In production: Use your deployed backend URL (e.g., `https://api.yourapp.com`)

### CORS errors
- Add your frontend URL to `CORS_ORIGINS` in backend .env
- Format: `http://localhost:5173,https://yourapp.com` (comma-separated)

### Authentication not working
- Verify Supabase credentials match in both frontend and backend
- Check that anon key is correct in frontend
- Check that service role key is correct in backend
