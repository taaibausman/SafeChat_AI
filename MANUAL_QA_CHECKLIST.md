# SafeChat AI Manual QA Checklist

Use this before screenshots, demo recording, and final submission.

## Browsers

- Chrome latest
- Microsoft Edge latest
- Firefox latest

Optional if available:

- Safari latest

## Environment Setup

- Backend starts successfully
- Frontend dev server starts successfully
- WhatsApp bridge starts if live-monitor checks are required
- `python backend\scripts\migrate.py` completes successfully
- `frontend\npm.cmd run build` completes successfully

## Core Navigation

- Landing page loads without layout breakage
- Sidebar navigation works on desktop
- Mobile menu opens and closes cleanly
- Top bar stays usable while scrolling
- No overlapping content at common widths: `375px`, `768px`, `1024px`, `1440px`

## Dashboard

- Dashboard loads without API errors
- Refresh button updates timestamp
- Recent analyses list renders correctly
- Health summary cards render correctly
- No clipped text or broken wrapping in cards

## Export Analysis

- `.txt` upload accepts a valid WhatsApp export
- Invalid file type shows a clear error
- Successful analysis opens a report
- Long-running upload still shows a visible loading state

## Image Analyzer

- Image upload accepts PNG/JPG/WEBP
- Invalid file type shows a clear error
- Preview renders at mobile and desktop widths
- OCR analysis navigates to a report page

## Results / Report

- Report page loads successfully
- Pie chart renders correctly
- Flagged message list renders correctly
- Message table scrolls horizontally on small screens
- Download safety report button downloads a `.txt` file

## Live Monitor

- Page loads without crashing when bridge is unavailable
- Filters update data correctly
- Empty states are readable
- Refresh button works
- Last updated label changes after refresh
- Mobile layout remains usable

## Admin Ops

- Page loads successfully
- Refresh button works
- Loading, error, and empty states remain readable
- Cards do not overflow on narrow screens

## Settings / Admin User Management

- Register flow works
- Login flow works
- Logout returns user to settings flow
- Non-admin session does not expose admin actions
- Admin session can load users
- Admin session can search users
- Admin session can promote/demote users
- Admin session can activate/deactivate users
- Admin cannot deactivate their own account

## Visual / UX Checks

- No obvious mojibake text such as `â€¢`, `Â·`, or `â€”`
- Buttons have visible hover/focus states
- Reduced-motion preference does not break layout
- Backdrop blur fallback still keeps panels readable
- No unreadable color contrast in primary screens

## Final Signoff

- Capture screenshots only after all items above pass
- Record demo video only after all blocking UI/API issues are closed
- Note any browser-specific deviations in the final report
