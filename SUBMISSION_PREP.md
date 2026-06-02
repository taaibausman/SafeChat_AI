# SafeChat AI Submission Prep

Use this as the final handoff checklist for report/demo packaging.

## 1. Verify Code State

- Confirm backend tests pass:
  `.\.venv\Scripts\python.exe -m pytest backend\tests -q`
- Confirm frontend build passes:
  `cd frontend`
  `npm.cmd run build`
- Confirm repo state is clean enough for submission
- Decide whether untracked files such as `backend/.dockerignore` should be included

## 2. Manual QA

- Run the checks in [MANUAL_QA_CHECKLIST.md](./MANUAL_QA_CHECKLIST.md)
- Log any remaining browser-specific issues
- Resolve blocking issues before recording demo assets

## 3. Capture Screenshots

Recommended screens:

- Landing page
- Dashboard
- Analyze Chat upload screen
- Results report page
- Live Monitor
- Admin Ops
- Settings / admin user management

Guidance:

- Use consistent browser zoom and window size
- Prefer clean sample data without broken states unless showing error handling intentionally
- Keep one mobile-width screenshot and the rest desktop unless the submission requires more

## 4. Record Demo Video

Suggested flow:

1. Open landing page
2. Show dashboard
3. Upload a WhatsApp export and open the generated report
4. Show downloadable safety report
5. Show image OCR analysis flow
6. Show live monitor and admin ops pages
7. Show settings page with admin user management

Recommended notes:

- Mention that backend tests pass cleanly
- Mention that frontend production build passes
- Mention that SQLite is for prototype/demo use

## 5. Prepare Presentation Slides

Suggested slide order:

1. Project title and team
2. Problem statement
3. System architecture
4. Key features
5. Backend/API summary
6. Frontend/UI summary
7. Live monitoring workflow
8. Demo screenshots
9. Testing and verification
10. Limitations and future work

## 6. Final Deliverables

- Source code
- Project report
- Presentation slides
- Demo video
- Screenshot set
- Setup/run instructions

## 7. Final Notes to Mention

- Backend tests currently pass:
  `27 passed`
- Frontend production build passes
- Admin user management and downloadable report are now implemented
- Cross-browser code polish is done, but manual browser QA should still be documented explicitly
