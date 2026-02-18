# Noesis Security & Privacy

**Your research is private, secure, and under your control.**

This document explains how Noesis protects your unpublished research, academic drafts, and literature collections using enterprise-grade security measures.

---

## 🔒 Core Security Principles

### 1. **Complete Data Isolation**
Your data is **mathematically isolated** from other users at the database level.

**How it works:**
- Every database table uses **Row-Level Security (RLS)** with user-specific access policies
- User A **cannot** access User B's data, even if they know the internal IDs
- Database enforces isolation automatically on every query
- **100% coverage** across all user data tables (projects, documents, drafts, analysis results)

**Why it matters:**
- Even if someone guesses your document ID, the database blocks unauthorized access
- Protects against application bugs, SQL injection, and insider threats
- Same security model used by banks and healthcare systems

---

### 2. **Zero AI Training Data**
Your research is **never used to train AI models**.

**How it works:**
- OpenAI API configured with **zero data retention** mode
- Your drafts and documents are processed but **never stored** by OpenAI
- No data reuse across users or for model improvement
- Organization-specific configuration ensures compliance

**Why it matters:**
- Your unpublished research won't appear in AI-generated responses to other users
- Prevents accidental leakage of novel ideas or findings
- OpenAI's API Enterprise agreement prohibits training on your data

**Technical details:**
- Configuration: `OPENAI_ZERO_DATA_RETENTION=true`
- Organization headers sent with every API request
- Verified in 24+ backend service files

---

### 3. **Encrypted Data Storage**
All data is encrypted at rest and in transit.

**How it works:**
- **At rest:** AES-256 encryption for all database records and file storage
- **In transit:** TLS 1.3 for all API communications
- Files stored in private Supabase Storage buckets with user-specific paths

**Why it matters:**
- Even if someone physically accessed our servers, data is unreadable
- Man-in-the-middle attacks cannot intercept your research
- Industry-standard encryption used by Fortune 500 companies

---

### 4. **Time-Limited File Access**
Draft files use **signed URLs** that expire after 1 hour.

**How it works:**
- Draft file URLs are generated on-demand with cryptographic signatures
- URLs automatically expire after 3600 seconds (1 hour)
- No predictable URL patterns that could be guessed
- Storage policies enforce user-specific folder access

**Why it matters:**
- Even if someone intercepts a URL, it expires quickly
- Prevents URL sharing or leakage from being a long-term security risk
- Defense-in-depth security (multiple layers of protection)

---

### 5. **Private Data Processing**
No sensitive content leaves secure infrastructure.

**How it works:**
- **No temporary files:** All analysis happens in-memory
- **PII scrubbing:** Error tracking automatically redacts research content
- **No server logs:** Draft text and claims never logged to disk
- **Minimal data collection:** Only essential metadata tracked

**Why it matters:**
- Your drafts can't leak via server logs or backups
- Error reports don't contain your research text
- Reduces attack surface and data retention

**Technical details:**
- Sentry error tracking: PII scrubbing enabled
- Redacts: `claim_text`, `draft_text`, `content`, `analysis`, `feedback_text`
- Truncates long messages to 200 characters

---

## 🛡️ Technical Security Measures

### Authentication & Access Control
- **JWT-based authentication** with Supabase Auth
- **Secure password hashing** using bcrypt algorithm
- **Session management** with automatic token expiration
- **Rate limiting:** 10 document uploads/min, 5 draft uploads/min

### Application Security
- **Security headers:** CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- **Input validation:** SQL injection and XSS prevention
- **CORS policies:** Restricted to approved origins only
- **API authentication:** All endpoints require valid JWT token

### Database Security
- **Row-Level Security (RLS):** User isolation on all tables
- **Parameterized queries:** Prevents SQL injection
- **Connection pooling:** Secure connection management
- **Automated backups:** Daily encrypted backups (deleted after account removal)

### Infrastructure Security
- **Containerized deployment:** Docker isolation between services
- **Network segmentation:** Database not exposed to public internet
- **Secrets management:** Environment variables, never in code
- **Dependency scanning:** Regular vulnerability checks (Dependabot)

---

## 🔐 Third-Party Services & Data Handling

We use trusted, enterprise-grade services. Here's exactly what data they access:

### OpenAI (AI Analysis)
**What they process:**
- Your draft text and research documents (for analysis only)
- Document titles and metadata

**Privacy guarantees:**
- ✅ **Zero data retention** enabled (not stored after processing)
- ✅ **No model training** on your data (API Enterprise agreement)
- ✅ **No cross-user contamination** (isolated per request)
- ✅ **GDPR compliant** with EU data residency options

**Privacy policy:** https://openai.com/policies/privacy-policy

---

### Supabase (Database, Auth, Storage)
**What they store:**
- Your account information (email, name)
- Research content (projects, documents, drafts, analysis)
- Authentication tokens and session data

**Privacy guarantees:**
- ✅ **Encrypted at rest** (AES-256) and in transit (TLS 1.3)
- ✅ **Private database** (not shared with other customers)
- ✅ **Row-Level Security** enforced at database level
- ✅ **SOC 2 Type II certified** infrastructure

**Privacy policy:** https://supabase.com/privacy

---

### Vercel (Frontend Hosting)
**What they process:**
- Static frontend assets (HTML, CSS, JavaScript)
- User IP addresses and browser metadata (standard web logs)

**Privacy guarantees:**
- ✅ **No access to research content** (backend handles all data)
- ✅ **Edge network CDN** for fast, secure delivery
- ✅ **DDoS protection** included
- ✅ **GDPR compliant**

**Privacy policy:** https://vercel.com/legal/privacy-policy

---

### Sentry (Error Tracking)
**What they receive:**
- Error messages and stack traces
- Browser/OS information
- User IDs (anonymized)

**Privacy guarantees:**
- ✅ **PII scrubbing enabled** (research content automatically redacted)
- ✅ **No research text** in error logs
- ✅ **Limited data retention** (30 days)
- ✅ **GDPR compliant**

**Privacy policy:** https://sentry.io/privacy/

---

## 👤 Your Rights & Control

You have complete control over your data:

### Right to Access
- **Export all data:** Download projects, documents, drafts in JSON, BibTeX, or PDF format
- **View activity:** See all analysis results and chat history
- **Audit logs:** Track your own account activity (available in settings)

### Right to Deletion
- **Delete individual items:** Remove documents, drafts, or projects anytime
- **Delete account:** Permanent removal of all data within 30 days
- **Cascade deletion:** Deleting a project removes all associated data
- **Backup removal:** Data removed from backups after 30 days

### Right to Portability
- **BibTeX export:** Compatible with Zotero, Mendeley, LaTeX
- **PDF export:** Draft analysis reports with citations and feedback
- **JSON export:** Machine-readable format for custom processing
- **Markdown export:** Human-readable analysis summaries

### Right to Opt-Out
- **Analytics:** Disable usage tracking (keeps platform functional)
- **Email notifications:** Control what emails you receive
- **Feature updates:** Opt out of non-critical communications

---

## 📊 What We DO NOT Do

We are committed to responsible data handling:

### ❌ We DO NOT:
- Share your research with other users
- Sell your data to third parties
- Use your content for AI model training
- Cross-reference your work across projects
- Send marketing emails without consent
- Share data with advertisers
- Use your research for our own publications
- Allow employee access without audit trail

### ✅ We DO:
- Isolate your data at the database level
- Encrypt all data at rest and in transit
- Use zero data retention with AI services
- Delete data permanently when you request it
- Respond to privacy inquiries within 48 hours
- Comply with GDPR and CCPA regulations
- Maintain transparent privacy policies

---

## 🌍 Compliance & Standards

### GDPR (EU General Data Protection Regulation)
- ✅ **Lawful basis:** Processing based on consent and legitimate interest
- ✅ **Data minimization:** Only collect essential information
- ✅ **Right to erasure:** Complete data deletion on request
- ✅ **Data portability:** Export in machine-readable formats
- ✅ **Breach notification:** 72-hour notification requirement

### CCPA (California Consumer Privacy Act)
- ✅ **Right to know:** What data we collect and why
- ✅ **Right to delete:** Permanent data removal on request
- ✅ **Right to opt-out:** Disable data selling (we don't sell data)
- ✅ **Non-discrimination:** Same service quality regardless of privacy choices

### SOC 2 Type II (Infrastructure)
- ✅ **Supabase infrastructure** is SOC 2 Type II certified
- ✅ **Annual audits** of security controls
- ✅ **Industry-standard practices** for data protection

---

## 🔍 Security Audits & Monitoring

### Continuous Monitoring
- **Automated vulnerability scanning:** Weekly dependency checks
- **Security headers testing:** Automated verification
- **RLS policy validation:** Daily database security checks
- **Error tracking:** Real-time monitoring with PII scrubbing

### Regular Reviews
- **Quarterly security audits:** Internal review of access logs
- **Dependency updates:** Monthly security patches
- **Policy reviews:** Annual privacy policy updates
- **Penetration testing:** Planned for 2026 Q2 (if seeking enterprise customers)

### Incident Response
- **Response time:** Security issues addressed within 24 hours
- **Notification:** Affected users notified within 72 hours (GDPR requirement)
- **Transparency:** Public disclosure of resolved security issues
- **Contact:** security@noesis.app for vulnerability reports

---

## 📞 Security Questions?

We're committed to transparency about our security practices.

### Contact Us
- **General questions:** privacy@noesis.app
- **Security vulnerabilities:** security@noesis.app
- **GDPR/CCPA requests:** privacy@noesis.app
- **Response time:** Within 48 hours for privacy concerns

### Request Data
- **Data export:** Available in dashboard → Settings → Export Data
- **Account deletion:** Dashboard → Settings → Delete Account
- **Privacy settings:** Dashboard → Settings → Privacy Preferences

---

## 🎯 Summary: Why Noesis is Secure

### **5-Layer Security Model:**

1. **Database Layer:** Row-Level Security isolates user data
2. **Application Layer:** Authentication, rate limiting, input validation
3. **Storage Layer:** Encrypted files with signed URL access
4. **AI Layer:** Zero data retention, no model training
5. **Monitoring Layer:** PII scrubbing, audit logs, incident response

### **Real-World Protection:**

**Scenario:** Malicious user tries to access your draft
- ❌ **Database:** RLS blocks query (different user_id)
- ❌ **Storage:** Signed URLs expire + user-specific folders
- ❌ **Application:** JWT validation fails for other user's resources

**Scenario:** Data breach at third-party service
- ✅ **OpenAI:** No data stored (zero retention)
- ✅ **Database:** Encrypted at rest (unreadable without keys)
- ✅ **Backups:** Encrypted and access-controlled

**Scenario:** Noesis employee wants to view your research
- ✅ **Audit trail:** All admin access logged
- ✅ **Principle of least privilege:** Minimal employee access
- ✅ **No casual browsing:** Database policies prevent unauthorized queries

---

## 📈 Continuous Improvement

Security is an ongoing commitment. We regularly:

- **Update dependencies** to patch vulnerabilities
- **Review access logs** for suspicious activity
- **Test security controls** with automated tools
- **Respond to security research** from the community
- **Improve transparency** with detailed documentation

**Last Updated:** February 14, 2026

**Last Security Audit:** February 14, 2026 (internal)

**Next Planned Audit:** May 2026 (external, if pursuing enterprise)

---

## 🏆 Security Certifications (Planned)

As Noesis grows, we plan to pursue:

- **SOC 2 Type II:** Q3 2026 (for enterprise customers)
- **ISO 27001:** Q4 2026 (for international customers)
- **HIPAA Compliance:** On request for health research customers
- **FedRAMP:** If pursuing US government contracts

---

**Your research deserves the highest level of protection. We take that responsibility seriously.**

For the latest security updates, visit https://noesis.app/security or contact privacy@noesis.app.
