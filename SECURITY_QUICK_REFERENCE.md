# Noesis Security - Quick Reference

**Use this for quick explanations to users, investors, or beta testers.**

---

## 30-Second Pitch

*"Noesis uses enterprise-grade security to protect your unpublished research. Your data is completely isolated from other users at the database level, all AI processing uses zero data retention (meaning OpenAI doesn't store your content), and everything is encrypted in transit and at rest. We don't share, sell, or use your research for AI training. You have complete control - export or delete your data anytime."*

---

## 3 Core Guarantees

### 🔒 **1. Your Data is Private**
- **Complete isolation:** Your research is mathematically separated from other users
- **No sharing:** We never share your drafts or documents with others
- **No training:** Your content is never used to train AI models

### 🛡️ **2. Your Data is Secure**
- **Enterprise encryption:** Same security as banks (AES-256, TLS 1.3)
- **Access control:** Only you can access your research
- **Time-limited links:** File URLs expire after 1 hour for extra protection

### 👤 **3. You're in Control**
- **Export anytime:** Download all your data (BibTeX, PDF, JSON)
- **Delete anytime:** Permanent removal within 30 days
- **Full transparency:** Clear privacy policy, no hidden data use

---

## Common User Questions

### Q: "Will my unpublished research leak to other users?"
**A:** No. Mathematically impossible. We use Row-Level Security (RLS) at the database level - every query is automatically filtered to your user ID only. Even if someone guesses your document ID, the database blocks access.

---

### Q: "Is my research used to train AI models?"
**A:** Absolutely not. We configure OpenAI API with **zero data retention** - your content is processed for analysis but never stored by OpenAI. It won't appear in responses to other users or be used for model training.

---

### Q: "What if Noesis gets hacked?"
**A:** Multiple layers of protection:
1. All data encrypted at rest (AES-256) - unreadable without encryption keys
2. Row-Level Security prevents cross-user data access
3. OpenAI doesn't store your data (zero retention)
4. File URLs expire after 1 hour
5. We monitor for suspicious activity 24/7

---

### Q: "Can Noesis employees read my drafts?"
**A:** Technically yes (for support), but:
1. All admin access is logged (audit trail)
2. Only authorized support staff with legitimate need
3. We follow principle of least privilege (minimal access)
4. No casual browsing allowed

For extra privacy, we can offer admin-restricted accounts for sensitive research.

---

### Q: "How is this different from ChatGPT/Claude?"
**A:** Critical differences:
| Feature | ChatGPT/Claude | Noesis |
|---------|---------------|--------|
| Data retention | 30 days default | Zero (not stored) |
| Model training | May use for training | Never used for training |
| User isolation | None (general use) | Complete (RLS database) |
| Research focus | General purpose | Academic research only |
| Export formats | Copy/paste | BibTeX, PDF, structured |
| Compliance | Consumer-focused | GDPR/CCPA compliant |

---

### Q: "What happens if I delete my account?"
**A:** Complete permanent removal:
1. All data deleted immediately from active database
2. Removed from all backups within 30 days
3. File storage wiped
4. No recovery possible after deletion
5. Confirmation required (to prevent accidents)

---

### Q: "Where is my data stored?"
**A:**
- **Database:** Supabase (US-based, SOC 2 certified)
- **Files:** Supabase Storage (encrypted)
- **AI Processing:** OpenAI API (zero retention)
- **Frontend:** Vercel edge network (no data access)

All providers are GDPR/CCPA compliant with enterprise SLAs.

---

### Q: "Is Noesis GDPR/CCPA compliant?"
**A:** Yes:
- ✅ Right to access (export your data)
- ✅ Right to deletion (permanent removal)
- ✅ Right to portability (BibTeX, PDF, JSON)
- ✅ Right to opt-out (analytics, emails)
- ✅ Data minimization (only essential data)
- ✅ Breach notification (72 hours)

---

## Technical Details (for technical users)

### Database Security
```
- PostgreSQL with Row-Level Security (RLS)
- 100% user data table coverage (24+ policies)
- Parameterized queries (SQL injection prevention)
- AES-256 encryption at rest
```

### Application Security
```
- JWT authentication (Supabase Auth)
- bcrypt password hashing
- Rate limiting (10/min documents, 5/min drafts)
- Security headers (CSP, HSTS, X-Frame-Options)
- Input validation (XSS prevention)
```

### AI Processing
```
- OpenAI API with zero data retention
- Organization-specific configuration
- No model training on user data
- PII scrubbing in error tracking (Sentry)
```

### File Storage
```
- Signed URLs (1-hour expiration)
- User-specific folder paths
- Storage policies enforce access control
- TLS 1.3 for all transfers
```

---

## Quick Comparisons

### Noesis vs. Research Management Tools

| Feature | Noesis | Zotero | Mendeley | EndNote |
|---------|--------|--------|----------|---------|
| AI draft analysis | ✅ | ❌ | ❌ | ❌ |
| Zero AI retention | ✅ | N/A | N/A | N/A |
| Cloud sync | ✅ | Optional | ✅ | ✅ |
| Database RLS | ✅ | N/A | ❌ | ❌ |
| GDPR compliance | ✅ | ✅ | ⚠️ (Elsevier) | ⚠️ (Clarivate) |

### Noesis vs. AI Writing Tools

| Feature | Noesis | Grammarly | Turnitin | Writefull |
|---------|--------|-----------|----------|-----------|
| Research-specific | ✅ | ❌ | ✅ | ✅ |
| Zero data retention | ✅ | ❌ | ❌ | ⚠️ |
| Citation management | ✅ | ❌ | ❌ | ❌ |
| Database isolation | ✅ | ❌ | ⚠️ | ❌ |
| No model training | ✅ | ❌ | ❌ | ⚠️ |

---

## Email Template for Beta Testers

**Subject:** Your Research is Secure on Noesis

Hi [Name],

Thank you for your privacy concerns about Noesis - you were absolutely right to ask.

Here's how we protect your unpublished research:

**1. Complete Data Isolation**
Your drafts are mathematically isolated from other users. We use Row-Level Security at the database level - other users cannot access your data even if they know internal IDs.

**2. Zero AI Training**
OpenAI processes your content but doesn't store it (zero data retention enabled). Your research won't appear in responses to other users or be used for model training.

**3. Encrypted & Secure**
All data encrypted at rest (AES-256) and in transit (TLS 1.3). File URLs expire after 1 hour. No temporary files stored on disk.

**4. You're in Control**
Export your data anytime (BibTeX, PDF, JSON). Delete your account for permanent removal within 30 days.

**Full details:** See SECURITY.md in our repository or visit https://noesis.app/security

Questions? Email me directly or reach out to privacy@noesis.app (48-hour response time).

Best regards,
[Your Name]

---

## Investor/Partnership Pitch

**Security Highlights:**
- ✅ **Enterprise-grade isolation:** Row-Level Security on all user tables
- ✅ **Zero data retention:** OpenAI API configured for privacy compliance
- ✅ **GDPR/CCPA ready:** Full compliance with international privacy laws
- ✅ **SOC 2 roadmap:** Infrastructure providers already certified, pursuing our own Q3 2026
- ✅ **Audit trail:** All administrative access logged for compliance
- ✅ **Scalable security:** Same model works for 10 or 10,000 users

**Risk mitigation:**
- No data monetization (no selling to third parties)
- No AI training on user content (contractual + technical)
- Encryption everywhere (at rest, in transit, in processing)
- Regular security audits planned (quarterly internal, annual external)

**Competitive advantage:**
- Academic researchers trust us with unpublished work
- Institutional customers can verify security independently
- GDPR compliance enables EU expansion
- Can pursue health research (HIPAA-ready architecture)

---

## One-Page Handout (Plain English)

**Noesis Security Promise**

*Your unpublished research deserves the highest level of protection.*

**We guarantee:**
- 🔒 **Private:** Your data is isolated from other users (mathematically impossible to access)
- 🚫 **Not for training:** We never use your research to train AI models
- 🔐 **Encrypted:** Bank-level encryption protects your data at rest and in transit
- 👤 **Your control:** Export or delete your data anytime, no questions asked

**How we do it:**
- Database security: Row-Level Security filters every query to your user ID
- AI security: Zero data retention (OpenAI doesn't store your content)
- File security: Time-limited URLs that expire after 1 hour
- Monitoring: 24/7 security monitoring with PII scrubbing

**Your rights:**
- ✅ Export data (BibTeX, PDF, JSON)
- ✅ Delete data (permanent within 30 days)
- ✅ Opt-out of analytics
- ✅ Request privacy report

**Questions?**
- Email: privacy@noesis.app
- Response time: 48 hours
- Full details: https://noesis.app/security

---

**Last Updated:** February 14, 2026
