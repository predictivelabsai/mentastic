# Changelog v2 — Landing Page Restructure

**Date:** 2026-04-13
**Based on:** Review feedback from Ain Aaviksoo — spec compliance audit

## Summary

Major restructure of the landing page to follow the spec's user journey: **value before commitment**. The previous build followed a generic SaaS landing page pattern. This iteration implements the specific flow: hero tension → Patrick chat → personalised reflection → account creation.

## Changes

### 1. Hero Message — Individual Tension (Priority: Critical)

**Before:** "Build power people. Build power teams." — generic B2B jõuretoorika.
**After:** "Is how you feel aligned with how you actually perform?" — speaks to the individual user's core tension: the gap between perceived state and actual performance.

- Supporting line addresses fatigue, stress, and recovery eroding focus/judgement
- Primary CTA: "Talk to Patrick" (scrolls to chat section)
- Secondary CTA: "Learn more" (scrolls to journey steps)
- **Removed** "Get Started Free" from hero — registration comes after value

### 2. Post-Chat Reflection Card (Priority: Critical — was missing entirely)

**Before:** After 5 messages, Patrick pushed a generic "sign up to continue" message.
**After:** After 3 exchanges, Patrick generates a **personalised reflection card**:

- Uses the actual conversation content to generate a specific reflection
- Format: "Based on your answers, [specific pattern identified]. Mentastic can help you [specific value]."
- Example: "Based on your answers, sleep deprivation may be significantly affecting your focus and recovery capacity."
- Two CTAs: "Create account for full assessment" (primary) + "Learn how it works" (secondary)
- Styled as a distinct card with green gradient border — visually different from chat messages
- After reflection + 2 more messages, gently closes with account creation suggestion

This was the **core missing UX principle** from the spec: deliver value before asking for commitment.

### 3. Page Flow Restructured

**Before:** Hero → Chat (small widget) → How It Works → **Patrick's Toolkit** → Integrations → Sectors → CTA
**After:** Hero → **Chat (prominent full-width section)** → How It Works → Sectors → Integrations → Footer CTA

Key changes:
- **Patrick's Toolkit section removed** from landing page (moved to post-login experience). Showing 6 tools upfront overwhelmed first-time visitors.
- **Chat section is now prominent** — full-width dark section with large heading "Talk to Patrick", not a small widget inside the hero.
- **"How It Works" reframed** from feature list to user journey: "Talk to Patrick → Get your first insight → Connect your data → Stay in sync"
- **Sectors expanded** with more context per environment and italic supporting lines
- Registration CTA **only appears at page bottom** after user has seen value

### 4. Navigation Simplified

**Before:** "About | Integrations | Sign In | **Get Started**" — registration prominent in nav.
**After:** "About | Integrations | Sign In" — only returning user login visible.

- Removed "Get Started" green CTA button from nav
- Registration appears contextually: after reflection card and at page bottom
- Goal: user encounters Patrick before they encounter a registration form

## Spec Compliance After Changes

| Spec Requirement | Before | After |
|---|---|---|
| Hero: individual tension, not B2B | ❌ Generic B2B | ✅ "Feel vs perform" |
| Anonymous mini-chat | ✅ Working | ✅ Prominent section |
| Quick reflection/summary card | ❌ Missing | ✅ Personalised after 3 msgs |
| Account creation after value | ❌ Nav prominent | ✅ Only after reflection + footer |
| Toolkit not shown upfront | ❌ 6 cards on landing | ✅ Removed from landing |
| Journey as user story | ❌ Feature list | ✅ "Talk → Insight → Connect → Sustain" |
| Sectors with context | ⚠️ Basic | ✅ Expanded with descriptions |

## Files Changed

- `app.py` — Landing page route, CSS (chat-section, reflection-card), anonymous WS handler, nav structure
