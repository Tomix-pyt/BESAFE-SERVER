# BeSafe App — Complete Feature Inventory, User Journey & Testing Plan

---

## Table of Contents

1. [Complete Feature Inventory](#1-complete-feature-inventory)
   - [Mobile App (User-Facing)](#mobile-app-user-facing)
   - [Backend (Flask + MongoDB)](#backend-flask--mongodb)
   - [Agency Dashboard (Web)](#agency-dashboard-web)
2. [User Journey (End-to-End)](#2-user-journey-end-to-end)
3. [Interactive Element Reference](#3-interactive-element-reference)
4. [Testing Plan](#4-testing-plan)
5. [Key Files Reference](#5-key-files-reference)

---

## 1. Complete Feature Inventory

### Mobile App (User-Facing)

| Feature | Description |
|---|---|
| **Phone Auth (OTP)** | Enter phone → receive OTP (`2026` hardcoded) → verify → JWT access (15m) + refresh (7d) tokens. Rate-limited (3/hr, progressive cooldown, 8min expiry, 5 attempts → 1h block) |
| **Onboarding** | Step 1: Name + email. Step 2: Up to 3 emergency contacts (name, phone, relationship). Can skip entirely. |
| **Home Screen** | Time-based greeting ("Good morning/afternoon/evening"), 5 scenario chips, listen button, hold-to-SOS, safety check trigger, drawer access |
| **Safety Scenarios** | "Walking alone?" → green/walk. "In a ride?" → blue/car. "Going home?" → amber/home. "On a date?" → pink/heart (enables discreet mode). "Feeling unsafe?" → red/alert (activates urgent mode) |
| **Urgent Mode** | Red full-screen UI, auto-starts mic listening, SOS pulses faster (1.06x, 800ms), call-contact card (tap dials first, long-press opens picker), cancel button exits |
| **Discreet Mode** | "On a date?" activates it — no overt safety text visible, green "● Private" dot in top bar replaces avatar, ScenarioContextCard returns null |
| **Speech Listening + Threat Detection** | Tap Listen → mic active → buffers audio → 1.5s of silence → sends to NLP API → if threat detected (`shouldTriggerSOS === true`): red "Threat Detected" state → 3s countdown → auto-SOS or tap Cancel |
| **Hold-to-SOS** | 3s press-and-hold → haptic ramp-up (light → medium → heavy) → SVG circular progress ring fills → on release: SOS fires with GPS to nearest 3 agencies + notifies emergency contacts via email (Mailjet) + SMS (Twilio) + push (Expo). Short tap opens SOSInfoModal. |
| **SOS Active State** | Full-screen red card: "SOS Activated" + "Your location has been shared with nearby response agencies." + "Add emergency contacts" nudge (if 0 contacts) + "View on Map" → Location tab + "I'm Safe" → resolves all alerts via API |
| **Safety Check-In** | Start from scenario tap or SafetyCheckTrigger card → pick activity (6 options) + interval (15m/30m/1h/2h) + select contacts → periodic background notifications → due countdown → 2m grace → overdue escalation (SOS to contacts + agency alert) |
| **Active Safety Check Screen** | Timer countdown with progress bar (yellow→red when urgent), "I'm Safe" confirm button, Add Time modal (15m/30m/1h), contact toggles with call buttons, Stop button with confirmation |
| **Location Tab (Mapbox)** | Mapbox map with standard style, user location dot, Watcher markers (pulsing ring), Agency markers (SVG teardrop pin #353FAB), gorhom BottomSheet (25%/50%/85%), Watchers/Agencies tabs, Directions API route line (purple), Navigate opens Apple/Google Maps, Fit All button |
| **Safe Chat (Anonymous Reporting)** | 6 categories: "I feel unsafe now" → EmergencyEscalation. "Abuse at home" (shield/dark red), "Harassment/stalking" (eye-off/amber), "Unsafe ride/date" (car/purple), "Threats" (alert-circle/dark red), "Other" (ellipsis/gray) → GuidedChatView |
| **Guided Chat View** | 4-step sequential flow: Description (min 3 chars) → Timing (just now/today/this-week/longer-ago, auto-advances) → Frequency (first/few/many, auto-advances) → Outcome: "Keep Private" (AsyncStorage), "Submit for Help" (consent modal → nearest agency), "Send SOS Now" (→ EmergencyEscalation). BackHandler intercept (Android), back chevron on later steps, X on first step. |
| **Evidence Log** | List of locally saved private reports, expandable cards with category icon + date + description + timing + frequency, delete with confirmation, empty state |
| **Emergency Escalation** | "Send SOS" (red card, confirmation then SOS), "Call a Contact" (opens dialer alert), "Share My Location" (expo-location getCurrentPositionAsync + native Share.share with Apple/Google Maps URL), "Quick Exit" → back to category selection |
| **Emergency Contacts** | List all contacts, add up to 5 (name, phone, email, relationship), call button opens dialer, delete with confirmation. Accessed via Home Drawer or `/contact` route |
| **Settings** | Live Location Sharing toggle (optimistic update, revert on error), Push Notifications toggle (permission request, denied → alert with Open Settings), Manage Contacts, Change Phone (confirm → EnterPhone), Privacy/Terms/Help links |
| **Edit Profile** | Change avatar (photo picker, camera overlay), edit full name + email, Save button (disabled when no changes) |
| **Home Drawer** | 3 sections: **Safety** (Safety Check, My Location → Location tab, Emergency Contacts → `/contact`), **Support** (Safe Chat → Safe Chat tab, Saved Reports → Safechat with `?evidence=1`), **App** (Settings → `/settings`, Log Out with confirmation) |
| **Push Notifications** | 9 types: SAFETY_CHECK_STARTED/TICK/DUE/DUE_TICK/OVERDUE/ENDED, SOS_ALERT, SOS_RESOLVED, CONTACT_ADDED. Foreground sticky notifications with countdown, background action buttons (I'm Safe, Stop). Silent for tick/started/ended, banner+sound for due/overdue. |

### Backend (Flask + MongoDB)

| Feature | Description |
|---|---|
| **Phone OTP Auth** | 7 endpoints: send-otp (rate-limited 3/hr, progressive cooldown 30s×count, cap 120s), verify-otp (8min expiry, 5 attempts → 1h block, SHA-256 hashed), resend-otp, otp-cooldown, refresh (access+refresh tokens), logout. Hardcoded OTP `"2026"`. |
| **NLP Threat Detection** | `safety/routes.py` → `POST /v1/safety/analyze` → calls `https://besafev1.onrender.com/predict` → returns prediction + confidence + shouldTriggerSOS (true when prediction="Threat" && confidence >= 0.75) |
| **Alert Pipeline** | `POST /alert` (no auth) → receives transcribed text + GPS → calls NLP API → creates Alert document → routes to nearest 3 agencies via Haversine distance → emits `new_alert` via WebSocket to agency rooms. Supports `sos_contacts` for multi-channel notifications. |
| **SOS Dispatch** | `services/sos_service.py` → `send_sos()`: iterates emergency contacts → sends email via Mailjet (HTML template) + SMS via Twilio (if configured, else logs `[SMS]` to terminal) + push via Expo → then `_route_to_agency()`: creates alerts for nearest 3 agencies (or all if no pins), emits `new_alert` per agency room |
| **I'm Safe** | `POST /safety/im-safe` + `POST /v1/safety/im-safe` → marks all active user alerts as `resolved` → notifies agencies via WebSocket `alert_status_update` with `im_safe: true` |
| **Safety Check Service** | Full lifecycle: start (cancels existing, creates new, push notification), extend (adds minutes), update_location (broadcasts to contacts via WebSocket `safety:contact_location`), stop (cancels), confirm (if was triggered, sends "resolved" to contacts), cancel (all active), get_active. |
| **Safety Check Background Job** | APScheduler: `_tick_30_seconds()` (due countdown notifications), `_tick_minute()` (tick notifications, overdue detection → 2m grace → marks `triggered` → sends SOS_ALERT to contacts → calls `send_sos()`) |
| **Safe Chat Reports** | `POST /v1/safechat/reports` → creates report → if `submittedToAgency: true`: routes to nearest agency via Haversine → emits `new_report` to `agency_{id}` room. `GET /reports` (user's own), `GET /reports/<id>` (ownership check). Priority auto-calculated from category + frequency. |
| **User Management** | Full CRUD: `POST /v1/user/me/onboard` (name, email, emergency contacts), `GET /me`, `PATCH /me` (with multipart Cloudinary upload), `PATCH /me/settings` (liveLocationSharing). Emergency contact invites via email/SMS. |
| **Watchers** | `GET /v1/user/me/watchers` → finds users who have this user's phone in their emergency contacts → returns live location + safety check status + name + phone |
| **Push Notifications** | `services/notification_service.py` → `send_to_user()`, `send_to_users()`, `send_to_emergency_contacts()`. Token management via `PATCH /v1/notifications/token` and `DELETE /v1/notifications/token`. |
| **Live Location Tracking** | `POST /location/update` (no auth) → saves to Locations collection → forwards via WebSocket `location_update` to agency dashboard for live tracking trail |
| **Socket.IO Events** | Emitted: `new_alert`, `location_update`, `alert_status_update`, `new_report`, `report_status_update`, `safety:contact_location`. Listened: `join` (agency_{id} room), `safety:auth` (mobile JWT auth + user_{id} room), `safety:location` (live location during safety check). Transport fallback: polling → websocket. |

### Agency Dashboard (Web)

| Feature | Description |
|---|---|
| **Auth** | Flask-JWT-Extended (24h expiry), `/auth/register` (name, phone, email, password, region, optional HQ map pin), `/auth/login` (email + password), token in localStorage as `besafe_token` |
| **Alerts Panel** | Real-time alert list sorted by dynamic priority (confidence + time decay + unacknowledged status, recalculated every 60s). Status filter tabs: Active / Acked / Resolved / All. Each card: user name, priority tag (CRITICAL/HIGH/MEDIUM/LOW), status badge, time ago, text snippet, confidence bar. |
| **Alert Map** | Leaflet/OpenStreetMap centered on Sudan. Pulsing colored markers per alert (color = priority). Popup on click: name, confidence, time. Click marker or card opens detail panel. |
| **Alert Detail Panel** | Slides in. Victim avatar (photo or initial), name, phone. Status, priority score, timestamp, GPS coordinates. Threat confidence meter. Full transcribed text. Action buttons: Acknowledge / Resolve. Live Tracking button: toggles real-time location trail (dashed polyline + blue marker on map). |
| **Reports Panel** | Safe Chat reports assigned to agency. Status filter tabs: New / Reviewing / Resolved / Closed / All. Cards with category icon (color-coded), category label, description snippet, status badge, priority tag, time. Detail panel: status, priority, category, timing, frequency, full description. Action buttons: Review / Resolve / Close. |
| **Navbar Stats** | Alert counts (active/acked/resolved/total) and Report counts (new/reviewing/resolved/closed/total), refreshed every 30s. |
| **Settings Panel** | Edit agency identity (name, region, phone, email). Change password (current + new + confirm). Headquarters Location: interactive Leaflet map to pin HQ coordinates (saves lat/lng for proximity-based alert routing). |
| **WebSocket Realtime** | `new_alert` (toast + alarm sound + card appears), `location_update` (marker moves on map), `alert_status_update` (card/chip updates), `new_report` (toast + sound + card appears), `report_status_update` (card/chip updates). Auto-reconnect on disconnect. |
| **Live Tracking** | Toggle per alert → real-time dashed polyline trail updates as locations stream in. Blue moving marker on map. |

---

## 2. User Journey (End-to-End)

### First Launch Path

```
Splash Screen (minimum 2.5s) + Location Initialization
  → Auth Welcome Screen ("Get Started" / "Sign In")
  → Enter Phone Number (international phone input with country picker, validation)
  → Verify OTP (4+ digit numpad input, Auto-submit on fill, resend with cooldown timer)
    → FAIL: Wrong Code alert, attempts remaining, clear boxes
    → FAIL: Too many attempts → 1h block → Request New Code
    → FAIL: Session expired → back to EnterPhone
  → Onboarding Step 1: Personal Details (First Name, Last Name, Email optional)
  → Onboarding Step 2: Emergency Contacts (up to 3 or Skip)
  → Home Screen (tabs layout: Home | Location | Safe Chat)
```

### Daily Use — Home Screen

```
[HOME TAB]
  ├── Time-based greeting + Protected subtitle (top bar)
  ├── Hamburger menu → Drawer (3 sections: Safety / Support / App)
  ├── Avatar (top right) → Edit Profile
  ├── [0 contacts] → "Secure Your Profile" prompt card → /contact
  ├── Scenario Chips (5):
  │   ├── "Walking alone?" → SafetyCheckSheet
  │   ├── "In a ride?" → SafetyCheckSheet
  │   ├── "Going home?" → SafetyCheckSheet
  │   ├── "On a date?" → SafetyCheckSheet + Discreet Mode
  │   └── "Feeling unsafe?" → URGENT MODE
  ├── ScenarioContextCard: animated contextual message per selection (hidden in discreet)
  ├── Listen Button:
  │   ├── Tap → Mic active (green, pulse)
  │   ├── Speak → Buffer 1.5s → NLP API
  │   │   ├── [No threat] → Continue listening
  │   │   └── [Threat detected] → Red "Threat Detected" + 3s countdown
  │   │       ├── Cancel → Back to listening
  │   │       └── Timeout → Auto-SOS
  │   └── Tap again → Stop listening
  ├── SOS Button:
  │   ├── Tap → SOSInfoModal (explains hold gesture)
  │   ├── Hold 3s → Haptic ramp-up → Progress ring → Release → SOS SENT
  │   │   └── [SOS Active screen]:
  │   │       ├── "SOS Activated" + body text
  │   │       ├── [0 contacts] → "Add emergency contacts" link
  │   │       ├── "View on Map" → Location tab
  │   │       └── "I'm Safe" → API resolve → back to idle
  │   └── Release early → Cancel
  └── SafetyCheck Trigger:
      ├── [Inactive] → Tap → SafetyCheckSheet
      └── [Active] → Tap → /safety-check-active modal
```

### Urgent Mode Path

```
[HOME] → Tap "Feeling unsafe?" chip
  → UI collapses (no scenarios, no context card)
  → Mic starts listening automatically
  → SOS button pulses faster (1.06x, 800ms cycle)
  → "Feeling unsafe?" title (red)
  → Call Contact card:
      ├── [Has contacts] → Tap → dials first contact immediately
      │                    → Long-press → ContactPickerSheet → pick → dial
      └── [No contacts] → "Add emergency contacts" card → /contact
  → SOS Button (pulsing wrapper) → Hold 3s → SOS (same as above)
  → "Cancel" button → exits urgent mode, stops mic, clears state
```

### Safety Check-In Path

```
[HOME] → Tap scenario (or SafetyCheckTrigger) → SafetyCheckSheet opens
  → Step 1: Pick Activity (6 options) + Interval (15m/30m/1h/2h)
  → Step 2: Select Emergency Contacts (checkbox list)
  → "Start" → GPS location → API call → Sheet dismisses
  → Background monitoring begins:
      ├── Push: SAFETY_CHECK_STARTED (silent sticky)
      ├── Regular ticks → SAFETY_CHECK_TICK (silent sticky with countdown)
      ├── Due soon → SAFETY_CHECK_DUE (urgent, banner + sound, "Are you safe?")
      ├── Missed → 2-minute grace period
      ├── Overdue → SAFETY_CHECK_OVERDUE → marks triggered → SOS to emergency contacts
      └── Notification tap → opens /safety-check-active modal

[SAFETY CHECK ACTIVE MODAL]
  ├── Activity badge + timer countdown + progress bar
  ├── "I'm Safe" button → confirm → timer resets → "Confirmed!" banner (3s)
  │     States: Normal → Urgent (<60s, orange) → Overdue (red, contacts being notified MM:SS)
  ├── "Add Time" → bottom sheet: 15m / 30m / 1h
  ├── Contact list with checkboxes + call buttons
  └── "Stop" button → confirm → final location → API stop → back to Home
```

### Location & Map Path

```
[LOCATION TAB]
  → Mapbox map loads (standard style, default [8.6753, 9.082] zoom 5)
  → On load + own location: fly to user location zoom 14
  → User dot visible
  → Watcher markers (pulsing ring, active/inactive states)
  → Agency markers (teardrop pins, #353FAB)

  → BottomSheet (gorhom, snap: 25% / 50% / 85%):
      ├── [Watchers tab] (default):
      │   ├── List of watcher cards (name, status, activity, last seen)
      │   ├── Cards: tap selects → fly to pin; "Directions" → route line on map
      │   ├── Empty state: floating animation illustration
      │   └── FitAllButton (floating, >1 marker, sheet not max snap)
      └── [Agencies tab]:
          ├── Fetches nearby agencies (sorted by distance)
          ├── Cards: name, phone, distance, "Directions" button
          └── Empty state: "No agencies nearby"

  → Route Overlay (when directions active):
      ├── "Route to {name}" title
      ├── Loading spinner (fetching Mapbox Directions API)
      ├── "Navigate" → opens Apple Maps (iOS) / Google Maps (Android)
      └── "Clear" → removes route line
```

### Safe Chat Path

```
[SAFE CHAT TAB]
  ├── Header: "Safe Chat" + "Your space. Your story. Your control."
  ├── "Saved reports (N)" link (top right) → EvidenceLog
  ├── 6 Category Cards:
  │   ├── "I feel unsafe now" (red, warning icon) → EmergencyEscalation
  │   ├── "Abuse at home" (dark red, shield icon) → GuidedChatView
  │   ├── "Harassment/stalking" (amber, eye-off icon) → GuidedChatView
  │   ├── "Unsafe ride/date" (purple, car icon) → GuidedChatView
  │   ├── "Threats" (dark red, alert-circle icon) → GuidedChatView
  │   └── "Other" (gray, ellipsis-horizontal icon) → GuidedChatView
  └── Footer: "Everything you share here is private unless you choose to submit it for help."

[GUIDED CHAT VIEW] (categories 2-6)
  Step 1 — Description:
    ├── Text area (min 3 characters)
    ├── "Next" button (disabled until valid)
    └── "X" (first step) or "←" (later steps)
  Step 2 — Timing:
    ├── Just now / Today / This week / Longer ago
    └── Tap → auto-advances to Step 3
  Step 3 — Frequency:
    ├── First time / A few times / Many times
    └── Tap → auto-advances to Step 4
  Step 4 — Outcome:
    ├── "Keep Private" → saves to AsyncStorage → completion screen → Done
    ├── "Submit for Help" → Consent Modal:
    │   ├── "This will send your report and location to a response agency so they can review it."
    │   ├── Confirm → API call → routes to nearest agency → completion screen → Done
    │   └── Cancel → back to outcome
    └── "Send SOS Now" → EmergencyEscalation
  → Hardware back (Android): previous step, exits only from step 1
  → Step dots in header (3 dots: description, timing, frequency)

[EMERGENCY ESCALATION]
  ├── "Send SOS" → confirmation → fires SOS (same as hold-to-SOS)
  ├── "Call a Contact" → dialer alert with contact list
  ├── "Share My Location" → location permission → GPS → native share sheet with maps URL
  └── "Quick Exit" → back to category selection

[EVIDENCE LOG]
  ├── Header: "Saved Reports (N)" + close button
  ├── [Empty] → "No saved reports" with icon
  └── [Has reports] → FlatList of report cards:
      ├── Category icon + label + date
      ├── Tap → expand: description, timing, frequency
      └── Trash button → confirmation → delete
```

### Settings Path

```
[SETTINGS] (standalone route, back chevron in header)
  ├── Profile Card: avatar/initials, name, phone
  ├── Safety Section:
  │   └── Live Location Sharing toggle (optimistic update, revert on error)
  ├── Emergency Contacts:
  │   └── "Manage Contacts" → /contact (shows count or "No contacts added yet")
  ├── Notifications:
  │   └── Push Notifications toggle (permission request, denied → alert with "Open Settings")
  └── Account:
      ├── Change Phone Number → confirm → EnterPhone
      ├── Privacy Policy → opens URL
      ├── Terms of Service → opens URL
      └── Help & Support → opens mailto
```

---

## 3. Interactive Element Reference

| Screen | Element | Tap | Long Press / Hold |
|---|---|---|---|
| **Auth Welcome** | AuthCTA | → EnterPhone | — |
| **EnterPhone** | Phone input | Type digits | — |
| | Send Code button | Submit → VerifyOTP | — |
| **VerifyOTP** | OTP boxes | Auto-submit on fill | — |
| | Resend code | Request new OTP | — |
| **Home** | Menu icon | Open drawer | — |
| | Avatar (right) | → Edit Profile | — |
| | Scenario chip (5) | Select/deselect | — |
| | Listen button | Toggle listening | — |
| | SOS button | → SOSInfoModal | Hold 3s → SOS |
| | Threat Cancel | Cancel auto-SOS | — |
| | Safety Check card | Open sheet / go to active | — |
| | "I'm Safe" (SOS) | End SOS | — |
| | "View on Map" (SOS) | → Location tab | — |
| | Urgent Call contact | Call first contact | → ContactPickerSheet |
| | Urgent Cancel | Exit urgent mode | — |
| **Drawer** | Each item | → respective screen | — |
| **Location** | Watcher card | Select → fly | — |
| | Agency card | Show details | — |
| | Directions button | Draw route | — |
| | Navigate | Open maps app | — |
| | Clear route | Remove route | — |
| | Fit All button | Fit markers to map | — |
| | Map marker | Fly to pin | — |
| **Safe Chat** | Category card | → Guided/Escalation | — |
| | Saved reports link | → EvidenceLog | — |
| | Guided: Next | Advance step | — |
| | Guided: Back | Previous step | — |
| | Timing/Frequency | Tap → auto-advance | — |
| | Keep Private | Save locally | — |
| | Submit for Help | Consent → send | — |
| | Send SOS Now | → Escalation | — |
| **Evidence** | Report card | Expand/collapse | — |
| | Delete | Confirm → delete | — |
| **Escalation** | Each button | Respective action | — |
| **Settings** | Toggles | Toggle (with flow) | — |
| | Manage Contacts | → /contact | — |
| | Change Phone | Confirm → EnterPhone | — |
| **Contacts** | Add (+) | → AddContactModal | — |
| | Call button | Open dialer | — |
| | Delete | Confirm → remove | — |
| **Safety Check Active** | I'm Safe | Confirm check-in | — |
| | Add Time | → AddTimeModal | — |
| | Contact checkbox | Toggle included | — |
| | Contact call icon | Open dialer | — |
| | Stop | Confirm → stop | — |
| **Edit Profile** | Avatar | Pick photo | — |
| | Name/Email inputs | Edit fields | — |
| | Save | Submit changes | — |

---

## 4. Testing Plan

### Phase A: Authentication & Onboarding

| # | Test | Steps | Expected Result |
|---|---|---|---|
| A1 | **OTP send** | Enter valid phone → tap Send Code | "Sending..." → success → navigates to VerifyOTP |
| A2 | **OTP verify (correct)** | Enter `2026` | Auto-submits → JWT issued → navigates to onboarding |
| A3 | **OTP verify (wrong)** | Enter wrong 4 digits | Alert "Wrong Code" with attempts remaining, boxes clear |
| A4 | **OTP too many attempts** | Fail verify 5 times | Alert "Account Temporarily Blocked" (1h), option to Request New Code |
| A5 | **OTP expired** | Wait 8+ min, enter `2026` | Alert "Code Expired" → back to EnterPhone |
| A6 | **OTP resend** | Tap "Resend code" | New OTP sent, cooldown timer starts |
| A7 | **Onboarding step 1** | Enter First + Last name + email → Next | Validates, moves to step 2 |
| A8 | **Onboarding step 2** | Add 3 contacts (name + phone) → Finish | Contacts saved, `isOnboarded=true`, navigates to Home |
| A9 | **Onboarding skip** | Tap "Skip" on step 2 | Completes with 0 contacts, goes to Home |
| A10 | **Token refresh** | Wait 15+ min, use app | Auto-refresh via axios interceptor, no forced logout |

### Phase B: Home Screen & Navigation

| # | Test | Steps | Expected Result |
|---|---|---|---|
| B1 | **Tab navigation** | Tap Home / Location / Safe Chat | Each tab renders, tab icon changes (outline → filled) |
| B2 | **Home Drawer** | Tap hamburger menu | Drawer slides in (82% width, spring animation), 3 sections visible |
| B3 | **Drawer items** | Tap each item | Navigates to correct screen (Safety Check, My Location, Contacts, Safe Chat, Saved Reports, Settings, Log Out) |
| B4 | **Logout** | Tap Log Out → confirm | Auth store cleared, returns to Auth Welcome |
| B5 | **Avatar tap** | Tap avatar in top bar | Navigates to Edit Profile modal |
| B6 | **No contacts prompt** | 0 emergency contacts | "Secure Your Profile" card shows above scenarios |
| B7 | **Scenario chips** | Tap each of 5 chips | Chip highlights, others deselect, ContextCard shows matching message |
| B8 | **Discreet mode** | Tap "On a date?" | Green dot replaces avatar, ContextCard hidden, no safety wording |

### Phase C: Safety Check-In

| # | Test | Steps | Expected Result |
|---|---|---|---|
| C1 | **Start check-in** | Tap scenario → SafetyCheckSheet | Activity picker (6 options) + Interval picker (4 options) shown |
| C2 | **Select contacts** | Next → toggle contacts → Start | Check-in starts, push notification: SAFETY_CHECK_STARTED |
| C3 | **Confirm check-in** | Tap "I'm Safe" | Timer resets, "Confirmed! Timer reset." banner (3s auto-dismiss) |
| C4 | **Extend check-in** | Tap "Add Time" → 30m | Timer extends by 30 minutes |
| C5 | **Stop check-in** | Tap "Stop" → confirm | API stops check, returns to Home |
| C6 | **Check-in due** | Wait until timer <60s | Orange UI, countdown pulses, "Check in soon" label |
| C7 | **Check-in overdue** | Wait past interval + 2m grace | SAFETY_CHECK_OVERDUE push, SOS to emergency contacts, agency alert created |
| C8 | **Replace check-in** | Start 2nd check-in while 1st active | Old check-in cancelled, new one starts |

### Phase D: Speech & Threat Detection

| # | Test | Steps | Expected Result |
|---|---|---|---|
| D1 | **Start listening** | Tap Listen button | Green background, mic icon, subtle pulse animation |
| D2 | **Stop listening** | Tap Listen again | Gray idle state, mic-off icon |
| D3 | **Speech buffering** | Speak, pause 1.5s | Single NLP API call with full utterance (check server logs) |
| D4 | **No threat** | Speak neutral phrase | Returns to listening, no state change |
| D5 | **Threat detected** | Speak threatening phrase | Red "Threat Detected" state, 3s countdown appears |
| D6 | **Cancel threat** | Tap "Cancel" during countdown | Countdown stops, medium haptic, returns to listening |
| D7 | **Auto-SOS from threat** | Let countdown reach 0 | SOS fires (same as hold-to-SOS path) |

### Phase E: SOS

| # | Test | Steps | Expected Result |
|---|---|---|---|
| E1 | **Hold-to-SOS** | Press & hold SOS 3s | Haptic light→medium→heavy, progress ring fills → SOS fires |
| E2 | **Release early** | Press, hold <3s, release | Cancels, returns to idle state |
| E3 | **Short tap** | Single tap (no hold) | SOSInfoModal slides up explaining hold gesture |
| E4 | **SOS sent** | Complete 3s hold | "SOS Activated" screen, check server: Alert created in DB, agency notified via WS |
| E5 | **SOS with 0 contacts** | Trigger SOS with no emergency contacts | Still works, routes to agencies only, "Add emergency contacts" nudge shown |
| E6 | **View on Map** | Tap "View on Map" | Navigates to Location tab, agencies visible in BottomSheet |
| E7 | **I'm Safe** | Tap "I'm Safe" | API resolves alerts, returns to Home idle state |
| E8 | **Debounce** | Rapidly tap SOS | Taps under 300ms apart ignored |

### Phase F: Location & Map

| # | Test | Steps | Expected Result |
|---|---|---|---|
| F1 | **Map loads** | Navigate to Location tab | Mapbox map renders, user location dot visible |
| F2 | **BottomSheet snap** | Swipe up/down | Snaps to 25% / 50% / 85% smoothly |
| F3 | **Watchers tab** | View watchers | Lists users who have you in contacts (or empty state) |
| F4 | **Agencies tab** | Tap Agencies tab | Fetches nearby agencies, sorted by distance, cards show distance |
| F5 | **Directions on card** | Tap "Directions" | Purple route line drawn on map from user to destination |
| F6 | **Navigate** | Tap "Navigate" in overlay | Opens Apple Maps (iOS) or Google Maps (Android) with destination |
| F7 | **Clear route** | Tap "Clear" | Route line removed from map |
| F8 | **Fit All** | Multiple watchers | Floating button appears, tap fits all markers to bounds |

### Phase G: Safe Chat

| # | Test | Steps | Expected Result |
|---|---|---|---|
| G1 | **Category selection** | Tap categories 2-6 | GuidedChatView opens at description step |
| G2 | **Emergency category** | Tap "I feel unsafe now" | EmergencyEscalation view opens |
| G3 | **Description step** | Type <3 chars → Next disabled. Type ≥3 chars → Next enabled | |
| G4 | **Timing step** | Tap timing option | Auto-advances to frequency step |
| G5 | **Frequency step** | Tap frequency option | Auto-advances to outcome step |
| G6 | **Back navigation** | Tap ← in header | Goes to previous step. X on first step closes |
| G7 | **Hardware back (Android)** | Press back button | Previous step, X on step 1 exits |
| G8 | **Keep Private** | Tap "Keep Private" | Saves to AsyncStorage, completion screen with checkmark |
| G9 | **Saved reports counter** | Return to safechat home | Counter shows "Saved reports (N)" reflecting the save |
| G10 | **Submit for Help** | Tap "Submit for Help" | Consent modal: "This will send your report and location to a response agency." |
| G11 | **Consent accept** | Tap confirm | Report sent to backend, routes to nearest agency, completion screen |
| G12 | **Consent cancel** | Tap cancel | Returns to outcome step |
| G13 | **Evidence Log** | Tap "Saved reports (N)" | List of private reports, expandable cards |
| G14 | **Evidence Log detail** | Tap a report card | Expands to show description, timing, frequency |
| G15 | **Delete report** | Tap trash → confirm | Report removed from list, counter decrements |

### Phase H: Emergency Escalation

| # | Test | Steps | Expected Result |
|---|---|---|---|
| H1 | **Send SOS** | Tap "Send SOS" → confirm | SOS fires, same as hold-to-SOS |
| H2 | **Call Contact** | Tap "Call a Contact" | Contact list shown, tap → opens dialer |
| H3 | **Share Location** | Tap "Share My Location" | Location permission request → GPS → native share sheet with maps URL |
| H4 | **Quick Exit** | Tap "Quick Exit" | Returns to Safe Chat category selection |

### Phase I: Settings & Contacts

| # | Test | Steps | Expected Result |
|---|---|---|---|
| I1 | **Toggle Live Location** | Toggle ON | API call updates setting, optimistic UI, green toggle |
| I2 | **Toggle Push ON (granted)** | Toggle ON | Permission request → granted → toggle green |
| I3 | **Toggle Push ON (denied)** | Toggle ON | Permission request → denied → alert "Notifications disabled" with Open Settings |
| I4 | **Toggle Push OFF** | Toggle OFF | Alert "To disable notifications, go to phone Settings" |
| I5 | **Manage Contacts** | Tap "Manage Contacts" | Navigates to `/contact` |
| I6 | **Add contact** | Tap + → fill form → save | Contact appears in list, count updates |
| I7 | **Call contact** | Tap phone icon | Opens dialer with contact's number |
| I8 | **Delete contact** | Tap trash → confirm | Contact removed from list |
| I9 | **Max contacts** | Add 5 contacts | + button disappears (max limit) |
| I10 | **Change Phone** | Tap → confirm | Navigates to EnterPhone flow |

### Phase J: Agency Dashboard (Web)

| # | Test | Steps | Expected Result |
|---|---|---|---|
| J1 | **Agency login** | Visit `/login`, enter email + password | Token stored, redirects to `/dashboard` |
| J2 | **Agency register** | Visit `/login`, use register form, pin HQ on map | Agency created in DB, redirected to dashboard |
| J3 | **Alerts view (default)** | Dashboard loads | Alert cards sorted by priority (CRITICAL first), color-coded tags |
| J4 | **Alert filter** | Tap Active / Acked / Resolved / All | List filters correctly |
| J5 | **Alert detail** | Click alert card | Detail panel slides in from right |
| J6 | **Acknowledge alert** | Tap "Acknowledge" in detail | Status → `acknowledged`, socket event emitted |
| J7 | **Resolve alert** | Tap "Resolve" in detail | Status → `resolved`, socket event emitted |
| J8 | **Live tracking** | Tap "Live Tracking" | Dashed polyline trail on map, real-time updates |
| J9 | **Reports view** | Tap "Reports" in view switcher | Report list with category icons, status badges |
| J10 | **Report filter** | Tap New / Reviewing / Resolved / Closed | List filters |
| J11 | **Review report** | Tap "Review" | Status → `reviewing`, socket `report_status_update` emitted |
| J12 | **Resolve/Close report** | Tap respective button | Status changes, socket event |
| J13 | **New alert notification** | Trigger SOS while dashboard open | Toast + audio alarm, card appears in real-time without refresh |
| J14 | **New report notification** | Submit report from mobile while dashboard open | Toast + audio, card appears in real-time |
| J15 | **Settings: edit profile** | Edit name/region/phone/email | Updates saved |
| J16 | **Settings: change password** | Enter current + new + confirm | Password updated |
| J17 | **Settings: pin HQ** | Click map, place marker | Coordinates saved, appears on next load |
| J18 | **Logout** | Click logout | Token cleared, redirects to login |
| J19 | **Auto-redirect** | Visit dashboard with valid token | Redirects past login, straight to dashboard |
| J20 | **Stats refresh** | Wait 30s | Navbar stat pills update (active/acked/resolved/total) |

### Phase K: Cross-Cutting & Edge Cases

| # | Test | Steps | Expected Result |
|---|---|---|---|
| K1 | **Offline mode** | Turn off WiFi | OfflineBanner shows, existing screens still navigable |
| K2 | **Online recovery** | Turn on WiFi | Auto-reconnects, Socket re-establishes, data syncs |
| K3 | **Notification tap (safety check)** | Receive SAFETY_CHECK_DUE → tap | Opens safety-check-active modal |
| K4 | **Notification tap (SOS)** | Receive SOS alert → tap | Opens app to relevant screen |
| K5 | **Background location** | Minimize app, move 100m | Location sent to server (`/location/update`), check server logs |
| K6 | **Rapid tab switching** | Rapidly switch Home→Location→Safe Chat | No crashes, smooth transitions |
| K7 | **Token expiry + refresh** | Wait 15min, make API call | Axios interceptor auto-refreshes, retries original request, seamless |
| K8 | **Concurrent SOS** | Trigger SOS twice quickly | Second is idempotent or blocked, no duplicate alerts |
| K9 | **No agencies in DB** | Trigger SOS with 0 agencies | Alert still created, logged to dashboard console |
| K10 | **No contacts flows** | SOS / submit-for-help / check-in with 0 contacts | Each feature degrades gracefully, routes to agencies, shows nudge |
| K11 | **Empty state screens** | Navigate each screen with no data | All show appropriate empty states (illustration + message) |
| K12 | **Socket reconnection** | Kill server, restart | Client auto-reconnects, re-authenticates via `safety:auth` |
| K13 | **Multiple agency dashboards** | Open 2+ agency dashboards simultaneously | Each receives only its own alerts/reports |

---

## 5. Key Files Reference

### Mobile App Key Files

| Path | Purpose |
|---|---|
| `app/_layout.tsx` | Root navigation, providers (query, safe area, bottom sheet), auth guards |
| `app/(tabs)/_layout.tsx` | Tab navigation (Home, Location, Safe Chat) |
| `app/(tabs)/index.tsx` | Home screen: scenarios, listen, SOS, urgent mode, discreet mode, safety check |
| `app/(tabs)/safechat.tsx` | Safe Chat: category selection, saved reports link, evidence param |
| `app/(tabs)/location.tsx` | Location: Mapbox map, BottomSheet (watchers/agencies), Directions |
| `app/contact.tsx` | Emergency contacts list, add, call, delete |
| `app/settings.tsx` | Settings toggles, manage contacts, account actions |
| `app/(auth)/index.tsx` | Auth welcome screen |
| `app/(auth)/EnterPhone.tsx` | Phone input with country picker |
| `app/(auth)/VerifyOTP.tsx` | OTP input with numpad, resend timer |
| `app/(onboarding)/` | 2-step onboarding (personal details + emergency contacts) |
| `app/(modals)/safety-check-active.tsx` | Active safety check timer, confirm, extend, stop |
| `app/(modals)/edit-profile.tsx` | Edit avatar, name, email |
| `components/home/SOSButton.tsx` | Hold-to-SOS with svg progress ring, haptic ramp-up |
| `components/home/ListenButton.tsx` | Mic toggle button, visual states |
| `components/home/HomeTopBar.tsx` | Time-based greeting, discreet mode dot |
| `components/home/HomeDrawer.tsx` | 3-section navigation drawer |
| `components/home/SafetyScenarioSelector.tsx` | 5 scenario chips, urgent mode trigger |
| `components/home/ScenarioContextCard.tsx` | Animated contextual message per scenario |
| `components/home/SOSInfoModal.tsx` | "Press & Hold" instructions (always shows on tap) |
| `components/safechat/GuidedChatView.tsx` | 4-step guided report builder |
| `components/safechat/EmergencyEscalation.tsx` | SOS/Call/Share/Exit |
| `components/safechat/EvidenceLog.tsx` | Private report list, expand/delete |
| `components/safety/SafetyCheckSheet.tsx` | Start safety check bottom sheet |
| `components/safety/ContactPickerSheet.tsx` | Contact list for urgent call picker |
| `components/location/WatcherMarker.tsx` | Pulsing ring marker |
| `components/location/WatcherCard.tsx` | Watcher info card with directions |
| `components/location/AgencyMarker.tsx` | Teardrop SVG pin |
| `components/location/AgencyCard.tsx` | Agency card with distance, directions |
| `components/location/FitAllButton.tsx` | Fit-all-markers floating button |
| `components/location/EmptyState.tsx` | Empty watchers illustration |
| `hooks/useReportStorage.ts` | AsyncStorage CRUD for private reports |
| `hooks/useNotification.ts` | Push token registration, notification handlers |
| `hooks/useSafetyCheck.ts` | Safety check lifecycle hook |
| `stores/auth.store.ts` | Zustand auth state (persisted) |
| `lib/axios.ts` | Axios client with token refresh interceptor |
| `lib/socket.ts` | Socket.IO client (single instance, polling fallback) |
| `lib/mapbox.ts` | Mapbox token initialization |

### Backend Key Files

| Path | Purpose |
|---|---|
| `besafe_app.py` | Main app, root routes (auth, alerts, agencies), Flask-JWT, blueprints |
| `auth/routes.py` | OTP send/verify/resend/cooldown, token refresh/logout |
| `auth/helpers.py` | JWT signing/verification, OTP hashing, hardcoded `"2026"` |
| `auth/middleware.py` | `require_auth`, `require_onboarded`, `require_role` decorators |
| `user/routes.py` | User profile CRUD, onboarding, watchers, settings |
| `safety/routes.py` | SOS trigger, I'm Safe, analyze text, safety check CRUD |
| `safechat/routes.py` | Safe chat report submit/list/get |
| `services/sos_service.py` | SOS dispatch engine: multi-channel contact notification + agency routing |
| `services/safety_check_service.py` | Safety check lifecycle management |
| `services/safety_service.py` | NLP API client |
| `services/notification_service.py` | Expo push notification dispatcher |
| `services/email_service.py` | Mailjet email sender |
| `services/sms_service.py` | Twilio SMS (logs to terminal if unpaid) |
| `models/agency.py` | Agency model, Haversine geo-routing functions |
| `models/alert.py` | Alert + Location models |
| `models/user.py` | User model (phone, contacts, settings, push tokens) |
| `models/safe_chat_report.py` | Report model with priority calculator |
| `models/safety_check.py` | Safety check model |
| `models/otp.py` | OTP session with rate limiting fields |
| `jobs/safety_check_job.py` | APScheduler: 30s/60s ticks, overdue escalation |
| `config/socket.py` | Socket.IO server setup, event handlers |
| `templates/dashboard.html` | Agency command dashboard UI |
| `templates/login.html` | Agency login + register with map pin |
| `static/dashboard.js` | Dashboard client logic: alerts, reports, map, socket, live tracking |
| `static/main.css` | Dashboard styles: report cards, tags, panels, animations |
