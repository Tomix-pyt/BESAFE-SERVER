# SentinelX — System Walkthrough

> **SentinelX** (formerly BeSafe) is a safety platform connecting vulnerable individuals to response agencies through a mobile app + agency dashboard, powered by AI-driven threat analysis.

---

## Architecture Overview

```
┌──────────────────────┐     HTTP / WebSocket      ┌──────────────────────┐
│                      │◄──────────────────────────►│                      │
│   Mobile App (User)  │                            │   Agency Dashboard   │
│   (React Native /    │                            │   (Web App / Flask)  │
│    Expo)             │                            │                      │
│                      │                            │                      │
│  - SOS / alerts      │                            │  - Real-time alerts  │
│  - Safe Chat reports │                            │  - Safe Chat reports │
│  - Safety check-ins  │                            │  - AI threat analyse │
│  - Live location     │                            │  - Map / tracking    │
│  - Emergency contacts│                            │  - Case management   │
└──────────────────────┘                            └──────────────────────┘
         │                                                     │
         │                    ┌──────────────────┐             │
         └────────────────────►                  ◄─────────────┘
                              │   Backend (Flask) │
                              │   - REST API      │
                              │   - Socket.IO     │
                              │   - JWT Auth      │
                              │   - MongoDB       │
                              │   - AI (FreeModel)│
                              │   - Twilio SMS    │
                              │   - Mailjet Email │
                              └──────────────────┘
```

**Live URLs:**
- Agency Dashboard: `https://besafe-server-production.up.railway.app`
- API Base URL: `https://besafe-server-production.up.railway.app`

---

## 1. Mobile App (User-Facing)

### Auth Flow

```
Welcome Screen
     │
     ▼
Enter Phone Number
     │
     ▼
OTP Verification (4-digit code)
     │
     ├── New User ──► Onboarding (name, email, emergency contacts)
     │
     └── Returning ──► Home Screen
```

**Key screens:**

| Screen | What it does |
|---|---|
| **Welcome** | Landing page with SentinelX branding and "Get Started" CTA |
| **Enter Phone** | Country code picker + phone input, sends OTP via backend |
| **Verify OTP** | 4-digit code entry with auto-verify, cooldown timer, resend |
| **Onboarding** | 2-step: personal details (name, email) → emergency contacts (up to 3) |
| **Home** | Main dashboard with mic listen, SOS button, safety check, emergency call |
| **Safe Chat** | Guided incident reporting with category selection, chat flow, evidence upload |
| **Settings** | Profile, location sharing toggle, notifications, contacts management |
| **Emergency Contacts** | List of saved contacts with call/delete, add contact modal |

### User Flows

#### A. SOS / Emergency Alert
```
1. User presses and holds SOS button on Home screen
2. POST /safety/sos → Backend sends SMS/email/push to emergency contacts
3. Backend creates an Alert in MongoDB → assigned to nearest agency
4. Socket.IO emits `new_alert` to the agency dashboard in real-time
5. Agency sees the alert appear on their dashboard with:
   - User name, phone, location (GPS coordinates)
   - Transcribed audio (if mic was recording)
   - Confidence score from NLP threat model
6. Agency can Acknowledge, Resolve, or Track the alert
```

#### B. Safe Chat (Guided Incident Reporting)
```
1. User opens Safe Chat tab (bottom navigation)
2. Selects incident category:
   - Feeling Unsafe / Abuse at Home / Harassment / Unsafe Ride / Threats / Other
3. Guided chat-style questions collect:
   - Description (free text or voice)
   - Timing (past 24h, past week, past month, ongoing)
   - Frequency (once, several times, daily, ongoing)
4. User can attach evidence: photos, audio recordings, documents (up to 10MB)
5. Optional: Submit for help → report is sent to nearest agency
6. POST /safechat/reports → report saved in MongoDB
7. If submitted for help → Socket.IO emits `new_report` to agency dashboard
8. Agency receives the report and can:
   - Review details and attachments
   - Run AI Threat Analysis
   - Change status: Pending → Reviewing → Resolved → Closed
```

#### C. Safety Check-In
```
1. User can start a periodic Safety Check from Home screen
2. Backend runs a cron job every 30s checking:
   - If user misses a check-in window → escalate to emergency contacts
3. User can extend, confirm, or cancel check-ins
4. Live location is shared during active check-in via WebSocket
```

#### D. AI Threat Detection (Listen Mode)
```
1. User taps "Listen" button on Home screen
2. Microphone captures audio → transcribed server-side
3. POST /safety/analyze → NLP model predicts threat probability
4. If threat confidence > threshold → suggests SOS trigger
5. User can cancel or confirm SOS escalation
```

---

## 2. Agency Dashboard (Web)

### Access

- **URL:** `https://besafe-server-production.up.railway.app`
- **Home page:** Marketing/landing page at `/`
- **Login:** Navigate to `/login` and sign in with agency credentials (email + password)

### Agency Registration (Sign-Up)

New agencies register at the `/login` page — toggle to the **Register** form:

```
1. Navigate to https://besafe-server-production.up.railway.app/login
2. Click "Register your agency" link below the Sign In button
3. Fill in the registration form (two-column layout):
   Left column:
     - Agency Name
     - Region / City
     - Official Phone Number
     - Email Address
     - Password + Confirm Password
   Right column:
     - Set agency location on the Mapbox map (search or click to place a pin)
4. Click "Register Agency"
5. POST /auth/register → saves agency to MongoDB with:
     name, phone_number, email, password (hashed), region, GPS location (lat/lng)
6. On success → auto-redirects to the dashboard
7. Future visits: Sign In with email + password → JWT token
```

**Registration requirements:**
- All fields required (name, phone, email, password, region, location pin)
- Email and phone must be unique (duplicates return 409)
- Location is set by clicking the map (used for nearest-agency routing when users submit SOS/reports)

### Dashboard Layout

```
┌──────────────────────────────────────────────────────────┐
│  HEADER: Logo  │  Search  │  Notifications  │  Profile  │
├─────────┬────────────────────────────────────────────────┤
│         │                                                │
│ SIDEBAR │             MAIN CONTENT AREA                  │
│         │                                                │
│ Overview│  ┌────────────────────────────────────────┐    │
│ Alerts  │  │  Stats Cards: Active / Total / Resolved │    │
│ Reports │  ├────────────────────────────────────────┤    │
│ Settings│  │  Alert List (table)                     │    │
│         │  │  - Priority badge                      │    │
│         │  │  - User name, phone, location          │    │
│         │  │  - Timestamp                           │    │
│         │  │  - Analyze button (AI)                 │    │
│         │  ├────────────────────────────────────────┤    │
│         │  │  Report List (table)                   │    │
│         │  │  - Category icon                       │    │
│         │  │  - Priority / Status tags              │    │
│         │  │  - Timing / Frequency                  │    │
│         │  │  - Analyze button (AI)                 │    │
│         │  └────────────────────────────────────────┘    │
│         │                                                │
└─────────┴────────────────────────────────────────────────┘
```

### Navigation

| Tab | Description |
|---|---|
| **Overview** | Dashboard home — stats cards, recent alerts, recent reports |
| **Alerts** | List of all SOS alerts. Filter by status (active, acknowledged, resolved), search by name/phone |
| **Reports** | List of Safe Chat reports submitted by users. Filter by status (pending_analysis, triaged, reviewing, resolved, closed) |
| **Settings** | Agency profile, update password, change location |

### Agency Flows

#### A. Receiving & Handling an Alert
```
1. Alert arrives in real-time via Socket.IO (no page refresh needed)
2. New alert card pops into the Alert list with:
   - Priority indicator (Critical / High / Medium / Low)
   - User name, phone number, GPS coordinates
   - Transcribed audio text
   - Confidence percentage
3. Agency clicks on the alert → Detail Panel slides open (right side)
4. Detail Panel shows:
   - User avatar, name, phone
   - Status badge, priority, confidence, timestamp
   - GPS location (with option to view on Mapbox map)
   - Transcribed audio text
   - AI Threat Analysis section (if analyzed)
   - Action buttons:
     - 🔍 Analyze with AI (if not yet analyzed)
     - 🗺 View on Map
     - ✓ Acknowledge
     - ✔ Resolve
     - 📍 Track Live (GPS tracking)
5. After analyzing → detail panel auto-opens with AI results
```

#### B. Receiving & Handling a Safe Chat Report
```
1. Report appears in Report list (real-time via Socket.IO if submitted for help)
2. Shows category icon, priority, status, timing/frequency
3. Click to open Detail Panel:
   - Category, status, priority
   - Timing, frequency, creation date
   - Location (if provided)
   - Description text
   - Attachments (photos, audio, documents) — clickable to view
   - AI Threat Analysis section (if analyzed)
   - Action buttons:
     - 🔍 Analyze with AI
     - 🔍 Review
     - ✔ Resolve
     - ✕ Close
```

#### C. AI Threat Analysis
```
1. Agency clicks "Analyze with AI" on any alert or report
2. POST /alerts/{id}/analyze or /agency/reports/{id}/analyze
3. Backend dispatches to FreeModel (gpt-4o-mini via OpenAI-compatible proxy)
4. AI returns structured analysis:
   - Severity Rating (0–100%)
   - Identified Pattern Type (e.g. "Digital Isolate & Command Pattern")
   - Escalation Risk (HIGH / MEDIUM / LOW)
   - Timeline Urgency (IMMEDIATE / DELAYED / ROUTINE)
   - Isolation Risk Detected (yes/no)
   - Investigation Priority (CRITICAL / HIGH / MEDIUM / LOW)
   - Pattern Tags (e.g. DIGITAL_EXPLOITATION, GROOMING)
   - Explainable AI Report (narrative summary)
5. Results display in the XAI panel within the detail panel
6. Detail panel auto-opens to show results with staggered animation
```

#### D. Map & GPS Tracking
```
1. Click "View on Map" to see the user's location on Mapbox
2. For alerts with active tracking:
   - Click "Track Live" to see user's GPS breadcrumb trail
   - Track points render as line + points on the map
   - Click "Stop Tracking" to end
```

---

## 3. System Integration Points

### How Mobile ↔ Dashboard Are Connected

| Event | Mobile App | Backend | Dashboard |
|---|---|---|---|
| **SOS Alert** | User holds SOS button | Creates alert, finds nearest agency by GPS | Alert appears in real-time list |
| **Safe Chat Report** | User submits report with/without help request | Saves report, if help-requested → notify nearest agency | Report appears in list + detail panel |
| **AI Analysis** | — | Agency clicks Analyze → calls FreeModel API | Analysis results in detail panel |
| **Live Tracking** | User shares GPS via WebSocket | Forwarded to dashboard via Socket.IO | Track points on Mapbox map |
| **Safety Check** | User starts/extends check-in | Cron job monitors check-ins | — |
| **Profile Update** | User edits profile/contacts | PATCH /user/me → updates MongoDB | Agency sees updated info on alerts/reports |

### Auth & Security

| Component | Method |
|---|---|
| **Mobile → Backend** | Phone OTP → JWT access + refresh tokens (stored in SecureStore) |
| **Dashboard → Backend** | Email/password → JWT (Flask-JWT-Extended) |
| **API Auth** | Bearer token in Authorization header |
| **Token Refresh** | Automatic via Axios interceptor (mobile) or redirect to login (dashboard) |

---

## 4. Tech Stack Summary

| Layer | Technology |
|---|---|
| **Mobile App** | React Native / Expo Router, TanStack Query, Zustand, Socket.IO Client |
| **Backend** | Python Flask, Gunicorn, Socket.IO, JWT (Flask-JWT-Extended) |
| **Database** | MongoDB Atlas |
| **AI Provider** | FreeModel (OpenAI-compatible, gpt-4o-mini) |
| **Maps** | Mapbox GL JS (dashboard), Mapbox SDK (mobile) |
| **Real-time** | Socket.IO (WebSocket) |
| **SMS** | Twilio |
| **Email** | Mailjet |
| **File Uploads** | Local filesystem (supports images, audio, documents up to 10MB) |
| **Hosting** | Railway (Flask backend) |
| **Mobile Distribution** | Expo Application Services (EAS) |

---

## 5. Key Environment Variables

| Variable | Purpose |
|---|---|
| `MONGO_URI` | MongoDB Atlas connection string |
| `AI_PROVIDER` | `freemodel` (primary), `gemini`, or `openai` |
| `FREEMODEL_API_KEY` | FreeModel API key for AI analysis |
| `MAPBOX_TOKEN` | Mapbox public token for dashboard maps |
| `TWILIO_*` | SMS for emergency alerts |
| `MAILJET_*` | Email notifications |
| `JWT_SECRET` / `JWT_ACCESS_SECRET` / `JWT_REFRESH_SECRET` | Token signing |
| `EXPO_PUBLIC_API_URL` | Mobile app's backend URL |
