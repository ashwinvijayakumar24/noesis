# Email Onboarding Sequence Setup Guide

**Purpose:** Automated email sequence to convert demo viewers and new signups into activated users

**Tools:** Mailchimp (free tier) or Loops.so (free tier)

**Owner:** Praneel

---

## Email Sequence Overview

### Trigger: User views demo OR signs up

**Sequence:**
- **Day 0:** Welcome + Quick Start Guide (sent immediately)
- **Day 3:** Tips for Better Draft Analysis (sent 3 days after signup)
- **Day 7:** Invite to Feedback Call (sent 7 days after signup)

---

## Email 1: Welcome + Quick Start Guide (Day 0)

**Trigger:** User signs up or submits email in demo

**Send:** Immediately after signup

**Subject:** Welcome to Noesis - Your AI Research Assistant

**From:** Praneel <praneel@noesis.is> or team@noesis.is

**Content:**

```
Hi [Name],

Welcome to Noesis! 👋

Thanks for signing up. We're excited to help you strengthen your research drafts before peer review.

Here's how to get started in 5 minutes:

1. **Upload a paper** to your literature base
   → Click "Projects" → "New Project" → "Upload Documents"
   → We'll analyze it and extract key insights

2. **Upload your draft** (PDF, DOCX, or TXT)
   → Click "Upload Draft" in your project
   → We'll extract claims, check citations, and generate feedback

3. **Review the analysis**
   → Unsupported claims (red flags)
   → Reviewer feedback (like a peer reviewer)
   → Coverage gaps (missing literature)

4. **Export your report** (PDF, JSON, or BibTeX)
   → Click "Export" to save your analysis

🎥 **Watch the 5-minute tutorial:** [Link to video]

Need help? Just reply to this email. We're here for you.

Best,
Praneel
Co-founder, Noesis

P.S. Built by GT students for serious researchers. No fluff, just helpful feedback.

---

Noesis - AI Research Assistant
https://noesis.is
```

---

## Email 2: Tips for Better Draft Analysis (Day 3)

**Trigger:** 3 days after signup

**Condition:** Only send if user has NOT analyzed a draft yet

**Subject:** 3 Tips to Get Better Feedback from Noesis

**Content:**

```
Hi [Name],

It's Praneel from Noesis. I noticed you signed up 3 days ago - awesome!

Here are 3 tips to get the most valuable feedback from Noesis:

**1. Upload your literature FIRST** 📚
   Before analyzing your draft, upload 5-10 papers from your literature review.
   Why? Noesis will map your draft claims to YOUR literature, not just generic sources.

**2. Use structured drafts** 📝
   PDFs work best if they have clear sections (Introduction, Methods, Results, etc.).
   DOCX and TXT also work great.

**3. Focus on unsupported claims** 🚩
   The red flags are what matter most. These are claims that:
   - Need citations (but don't have them)
   - Have weak evidence (only 1 citation for important claims)
   - Contradict your own literature

**Real Example:**
PhD student Sarah uploaded her dissertation chapter with 8 papers.
Noesis found 5 unsupported claims she hadn't noticed.
She fixed them before her advisor review. ✅

**Ready to try?**
[Upload Your First Draft]

Questions? Just reply to this email.

Best,
Praneel

P.S. If you've already analyzed a draft, ignore this! How did it go?

---

Noesis - AI Research Assistant
https://noesis.is
```

---

## Email 3: Invite to Feedback Call (Day 7)

**Trigger:** 7 days after signup

**Condition:** Only send if user has analyzed ≥1 draft

**Subject:** 15-minute chat? I'd love your feedback on Noesis

**Content:**

```
Hi [Name],

Praneel here from Noesis. You've been using Noesis for a week now - thank you!

I'm reaching out because I'd love to hear your thoughts:
- What's working well?
- What's frustrating?
- What would make this a must-have tool for you?

Would you be open to a quick 15-minute call this week?

**Pick a time:** [Calendly link]

Why I'm asking:
We're a small team (2 GT students) building this for serious researchers.
Your feedback directly shapes what we build next.

**As a thank you:**
- Early access to new features
- Free Pro account when we launch pricing (worth $12/mo)
- Direct line to the founders (reply to this email anytime)

No pressure if you're busy - but if you have 15 minutes, I'd be grateful.

Best,
Praneel
Co-founder, Noesis

P.S. Not ready for a call? That's okay! Just reply with your biggest pain point
and I'll see what we can do.

---

Noesis - AI Research Assistant
https://noesis.is
```

---

## Alternative Email 3: For Users Who HAVEN'T Analyzed a Draft (Day 7)

**Trigger:** 7 days after signup

**Condition:** User has NOT analyzed a draft yet

**Subject:** Still exploring Noesis? Let me help

**Content:**

```
Hi [Name],

Praneel from Noesis here. You signed up a week ago, but I noticed you
haven't uploaded a draft yet.

No worries! But I wanted to check in:
- **Confused about how it works?** I can walk you through it (5 mins).
- **Not the right tool?** I'd love to know what you were looking for.
- **Just busy?** Totally get it. This email is your reminder :)

**Here's the fastest way to try it:**
1. Click here: [Direct link to demo]
2. See a sample analysis (no login required)
3. Then try it with your own draft

Or just reply and tell me what's blocking you. I'll help.

Best,
Praneel

P.S. If Noesis isn't a fit, no hard feelings. But if there's something we can
do to make it work for you, I want to know.

---

Noesis - AI Research Assistant
https://noesis.is
```

---

## Implementation Steps

### Option 1: Mailchimp (Recommended for Now)

**1. Create Mailchimp Account**
- Sign up at mailchimp.com
- Free tier: Up to 500 contacts, 1,000 emails/month

**2. Create Audience**
- Name: "Noesis Users"
- Tags: "demo_viewer", "signed_up", "analyzed_draft", "power_user"

**3. Create Automation**
- **Automation 1:** Welcome Sequence
  - Trigger: User added to audience (tag: signed_up)
  - Email 1: Welcome (immediate)
  - Email 2: Tips (delay 3 days, condition: NOT tagged "analyzed_draft")
  - Email 3: Feedback Call (delay 7 days, condition: tagged "analyzed_draft")

**4. Create Alternative Email 3**
- **Automation 2:** Re-engagement
  - Trigger: 7 days after signup
  - Condition: NOT tagged "analyzed_draft"
  - Send: Alternative Email 3

**5. Add Users to Mailchimp**
- Method 1: Manual CSV upload (for now)
- Method 2: API integration (future - automate from backend)

**6. Set Up Tags**
- Add tag "signed_up" when user creates account
- Add tag "analyzed_draft" when user completes first analysis
- Add tag "power_user" when user analyzes 3+ drafts

---

### Option 2: Loops.so (Alternative)

**1. Create Loops.so Account**
- Sign up at loops.so
- Free tier: Up to 2,000 contacts

**2. Create Email Templates**
- Template 1: Welcome
- Template 2: Tips
- Template 3: Feedback Call
- Template 4: Re-engagement

**3. Create Loops**
- Loop 1: Onboarding Sequence
  - Trigger: Contact created
  - Step 1: Send Welcome (immediate)
  - Step 2: Wait 3 days
  - Step 3: Send Tips (if NOT analyzed_draft)
  - Step 4: Wait 4 days
  - Step 5: Send Feedback Call (if analyzed_draft) OR Re-engagement (if NOT analyzed_draft)

**4. API Integration**
```javascript
// Add user to Loops via API
fetch('https://app.loops.so/api/v1/contacts/create', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${LOOPS_API_KEY}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    email: 'user@example.com',
    firstName: 'John',
    source: 'demo' // or 'signup'
  })
})
```

---

## Tracking & Metrics

### Key Metrics to Track

**Email Performance:**
- Open rate (target: >30%)
- Click-through rate (target: >5%)
- Reply rate (target: >2%)

**User Behavior:**
- % who activate after Email 1 (target: 20%)
- % who activate after Email 2 (target: 10%)
- % who schedule calls from Email 3 (target: 5%)

**Conversion Funnel:**
```
100 signups
→ 40 open Email 1 (40% open rate)
→ 8 upload first draft (20% activation)
→ 20 open Email 2 (50% open rate, sent to 40 who haven't activated)
→ 4 activate after Email 2 (10% activation)
→ 12 total activated (12% total activation rate)
```

---

## Email Copy Best Practices

**1. Keep it short**
- 150-200 words max
- Use bullet points
- Break up paragraphs (2-3 sentences max)

**2. One clear CTA**
- Don't ask for multiple actions
- Make the button/link obvious
- Use action verbs ("Upload Draft", not "Click Here")

**3. Personal tone**
- Write from Praneel (co-founder), not "The Noesis Team"
- Use "I" and "we", not "the platform"
- Reply-friendly (encourage responses)

**4. Provide value**
- Email 1: Quick start (immediate value)
- Email 2: Tips (actionable advice)
- Email 3: Personal connection (build relationship)

---

## Future Enhancements (Post-Week 1)

**Behavioral Triggers:**
- User uploads 5+ papers → Send "Great! Now analyze your draft"
- User analyzes 1st draft → Send "How did it go? Here's how to improve"
- User analyzes 3+ drafts → Send "You're a power user! Join beta advisor program"

**Segmentation:**
- PhD students vs Faculty (different messaging)
- By research area (CS, Biology, etc.)
- By university (GT students get different emails)

**A/B Testing:**
- Test subject lines (emoji vs no emoji)
- Test CTA placement (top vs bottom)
- Test timing (Day 3 vs Day 5)

---

## Setup Timeline

**Day 1 (2 hours):**
- Create Mailchimp account
- Set up audience and tags
- Create email templates (copy/paste from this doc)

**Day 2 (1 hour):**
- Set up automation workflow
- Test emails (send to yourself)
- Adjust timing/conditions

**Day 3 (ongoing):**
- Manually add users as they sign up (export from Supabase)
- Monitor open rates and replies
- Adjust copy based on feedback

**Week 2+ (future):**
- Integrate backend API with Mailchimp
- Automate tagging based on user behavior
- A/B test email variations

---

## Questions / Support

**Need help with setup?**
- Mailchimp docs: https://mailchimp.com/help/
- Loops.so docs: https://loops.so/docs

**Technical integration:**
- See backend file: `services/backend/app/services/email_service.py` (to be created)
- Mailchimp API: https://mailchimp.com/developer/
- Loops.so API: https://loops.so/docs/api-reference

---

**Status:** ✅ Ready to implement
**Owner:** Praneel
**Estimated Time:** 3 hours (setup + testing)
**Next Steps:**
1. Choose platform (Mailchimp or Loops.so)
2. Create account and set up templates
3. Configure automation workflow
4. Test with personal email
5. Add first batch of users
