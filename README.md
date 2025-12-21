# Noesis - AI-Powered Research Assistant

> Transform how you analyze academic literature with intelligent automation

Noesis is an AI-powered research management platform that helps researchers analyze papers, generate insights, and accelerate literature reviews using advanced AI.

---

## 🎯 Key Features

- **🤖 AI-Powered Chat**: Ask questions about your research papers with RAG (Retrieval-Augmented Generation)
- **💡 Automated Insights**: Generate comprehensive insights and identify research gaps automatically
- **📚 Literature Review Generation**: Create structured reviews in multiple formats
- **🕸️ Citation Network Analysis**: Visualize and explore relationships between papers
- **❓ Research Questions**: Auto-generate relevant questions from your collection
- **🔬 Methodology Recommendations**: Get AI-suggested research methodologies
- **📄 Intelligent PDF Processing**: Extract metadata and citations using GROBID
- **🎯 Paper Recommendations**: Discover related papers based on your research


## 📖 How to Use

### 1️⃣ Create an Account
Sign up using Supabase authentication

### 2️⃣ Create a Project
Organize papers by research topic or area

### 3️⃣ Upload Research Papers
Drag and drop PDF files - automatic processing includes:
- Text extraction via GROBID
- Citation parsing
- Semantic embedding generation
- AI-powered analysis

### 4️⃣ Explore Features

**💬 Chat with Your Papers**
```
"What are the main findings?"
"What methodologies were used?"
"What are the research gaps?"
```

**🔍 Generate Insights**
- Key themes and patterns
- Research gaps
- Common methodologies
- Citation analysis

**📊 Visualize Citation Network**
- Interactive D3.js visualization
- Filter by year, citations, authors
- Identify influential papers

**📝 Create Literature Reviews**
- Auto-generate structured reviews
- Multiple format options
- Export as Markdown

## 🏗️ Technology Stack

### Frontend
- React 18 + TypeScript + Vite
- TailwindCSS
- Zustand (state management)
- D3.js (visualizations)

### Backend
- Python 3.11 + FastAPI
- PostgreSQL + pgvector
- Redis (caching)
- OpenAI GPT-4o

### Services
- **Supabase**: Authentication only (user signup/login)
- **PostgreSQL + pgvector**: Local database for all application data
- **GROBID**: PDF processing
- **Docker**: Containerization

## 📚 Documentation

### 🚀 Production Deployment
- [⚡ Quick Start Guide](DEPLOYMENT_QUICK_START.md) - Get running in 2 hours
- [📘 Complete AWS Guide](AWS_DEPLOYMENT_GUIDE.md) - Comprehensive step-by-step
- [✅ Deployment Checklist](DEPLOYMENT_CHECKLIST.md) - Track your progress

### 🛠️ Configuration & Setup
- [🔧 Environment Setup](ENV_SETUP.md) - Understanding .env files
- [📝 Environment Template](.env.template) - Production variables reference

## 🚢 Deployment

### Budget-Friendly Production ($10-20/month)

**Recommended for early-stage & pilot programs:**

```
Frontend: Vercel (Free)
Backend: AWS EC2 t4g.micro ($3/month)
Database: PostgreSQL + pgvector (on EC2)
SSL: Let's Encrypt (Free)
Total: $9-12/month
```

**Supports:** 50-200 daily active users, perfect for I2P programs

👉 **Start here:** [DEPLOYMENT_QUICK_START.md](DEPLOYMENT_QUICK_START.md)

### Alternative Platforms
- **Render.com** - Easy Docker deployment (~$25/month)
- **Railway.app** - Simple container hosting (~$20/month)
- **DigitalOcean** - App Platform (~$30/month)

### Environment Configuration

Production environment files:
- `services/backend/.env.production` - Backend config
- `services/frontend/.env` - Frontend config

⚠️ **Never commit `.env` files to version control**
📖 **See:** [ENV_SETUP.md](ENV_SETUP.md) for complete guide

## 🔒 Security

- ✅ Supabase authentication
- ✅ Environment variable secrets
- ✅ CORS configuration
- ✅ Input validation
- ✅ SQL injection prevention (ORMs)

## 💡 Use Cases

### 👨‍🎓 Graduate Students
- Organize dissertation literature
- Prepare for comprehensive exams
- Write literature review chapters

### 👩‍🔬 Academic Researchers
- Manage research paper collections
- Identify research gaps quickly
- Generate comprehensive reviews

### 👥 Research Teams
- Collaborate on literature
- Share insights across team
- Track citation networks

## 🗺️ Roadmap

- [ ] Team collaboration features
- [ ] Zotero/Mendeley integration
- [ ] Mobile app
- [ ] Advanced citation analysis
- [ ] LaTeX export
- [ ] Multi-language support

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

