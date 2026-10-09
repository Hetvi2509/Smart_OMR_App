# Deploying Smart OMR Evaluator

Two independent things get deployed: the **backend** (FastAPI + OMR engine,
to Render) and the **frontend** (the Expo app, shared via Expo Go or built as
a real app).

Your Neon database needs no changes -- it is already cloud-hosted and is used
as-is by the deployed backend.

---

## 1. Backend -> Render (free tier)

### What's already set up for this

- `Dockerfile` (repo root) -- builds the API with the OMR engine, no PaddleOCR.
- `render.yaml` (repo root) -- Render reads this automatically and sets the
  plan, health check and environment variables for you.
- `STORAGE_BACKEND=db` -- scanned sheets, overlays and PDF reports are stored
  as bytes in your Neon database instead of local disk, because Render's free
  tier has no persistent disk and would silently delete local files on every
  restart or redeploy.
- `ENABLE_OCR=0` -- PaddleOCR needs more RAM than the free tier's 512MB
  allows and would crash the service. Candidate details (roll no, name,
  class) are entered manually after each scan instead -- the app already
  supports this; nothing else changes.

### Steps

1. **Push this repo to GitHub** (Render deploys from a Git repo, not a local
   folder). If it isn't on GitHub yet:
   ```
   git init
   git add .
   git commit -m "Smart OMR Evaluator"
   git remote add origin <your-new-empty-GitHub-repo-url>
   git push -u origin main
   ```

2. **Create the service on Render**
   - Go to [dashboard.render.com](https://dashboard.render.com) -> New -> Blueprint
   - Connect your GitHub account and pick this repo
   - Render finds `render.yaml` automatically and shows the `smart-omr-api`
     service it's about to create

3. **Set the two secrets it asks for** (these are intentionally left out of
   `render.yaml` since that file is committed to the repo):
   - `DATABASE_URL` — your existing Neon connection string, exactly as it is
     in `api/.env` right now (the one starting `postgresql://neondb_owner:...`)
   - `JWT_SECRET` — a new random string (anything long and unguessable works;
     e.g. run `python -c "import secrets; print(secrets.token_hex(32))"`)

4. **Deploy.** Render builds the Docker image and starts it — first build
   takes a few minutes (installing opencv, reportlab, etc.). Render gives you
   a URL like `https://smart-omr-api.onrender.com`.

5. **Verify it's alive:**
   ```
   curl https://smart-omr-api-XXXX.onrender.com/health
   ```
   Should return `{"status":"ok","database":"connected","ocr_enabled":false,...}`.

### Free-tier behaviour to expect

- The service **spins down after 15 minutes idle** and takes 30-60s to wake
  up on the next request. The app's upload timeout (120s) already accounts
  for this, but the first request after idle will feel slow — this is Render
  free tier's own limitation, not something the app can fix.
- No OCR: roll number / name / class are typed in manually on the result
  screen after each scan, same screen that already supports it.

---

## 2. Frontend -> point it at the deployed backend

Once you have the Render URL, tell the app to use it instead of your LAN IP.

Edit `mobile/app.json`:
```json
"extra": {
  "apiUrl": "https://smart-omr-api-XXXX.onrender.com"
}
```
(Replace with your actual Render URL, no trailing slash.)

This only affects **production builds**. Local `npx expo start` dev sessions
still auto-detect your LAN IP as before, so local development is unaffected.

### 2a. Quick sharing via Expo Go (no app store, fastest)

```
cd mobile
npx eas update --branch production
```
(First run prompts you to `npx eas login` and `eas init` — follow the
prompts, it's free.) This publishes a JS bundle; whoever you share it with
opens it inside the Expo Go app via the link/QR code `eas update` prints.

### 2b. A real installable app (.apk for Android, no Play Store)

```
cd mobile
npx eas build --platform android --profile preview
```
This needs an `eas.json` build profile — if one doesn't exist yet, `eas
build:configure` creates it first. The build runs on Expo's servers (free
tier covers this) and gives you a downloadable `.apk` link when done; anyone
can install it directly on an Android phone (no Play Store review needed).

### 2c. Full app store release (Google Play / Apple App Store)

Needs developer accounts ($25 one-time for Play Store, $99/year for Apple),
store listing assets (screenshots, descriptions, privacy policy) and goes
through store review (hours to days). Ask when you're ready for this step —
it's a distinct, larger piece of work with its own checklist.

---

## Local development is unaffected

Nothing above changes how `npx expo start` + the local `api/run_server.bat`
work together on your own machine — `STORAGE_BACKEND` defaults to `disk` and
`extra.apiUrl` defaults to `null` (falls back to LAN auto-detect), so local
dev keeps working exactly as it does today.
