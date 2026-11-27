# Mechanical Engineering Summer 2027 Job Board

Co-op and internship tracker for Summer 2027: Toronto, GTA and Hamilton, plus US roles.

**Live site:** turn on GitHub Pages (Settings → Pages → Deploy from branch → `main` / root). The site will be at https://evee2007.github.io/2027SummerMechJobBoard---Essam/.

## Features
- Tick jobs as you apply; ticks, notes and dates are saved in your browser.
- Filters: status, country, area, 4-month terms, hide US-citizen-only roles.
- **Tailor resume + letter** on every job: Essam's resume is built in (no phone/email in this repo), and each job instantly shows a reordered resume and a cover letter built only from real experience. Optional extras:
  - Add phone and email once under *Resume tailoring setup* (stored only in your browser, never committed to this repo).
  - *Copy prompt for Claude*: free, paste into claude.ai, then paste the reply back to save it.
  - *Generate here*: uses your own Anthropic API key (saved only in your browser).
  - *Save as PDF* prints the resume or letter; choose "Save as PDF" in the print window.

## Updating jobs
Job data is the `JOBS` array near the top of the `<script>` in `index.html`. Each job: company, role, loc, country (`Canada`/`USA`), terms (months), deadline (`YYYY-MM-DD`), posted, url, check, usp (US-citizen-only), cat, source, note.

## Privacy
Nothing personal is stored in this repo. Don't commit your resume or API key.

## Daily updates

A GitHub Action (`.github/workflows/daily-update.yml`) runs every morning. `scripts/update.py` pulls Summer 2027 listings from the coawp Canadian Engineering Internships list and SimplifyJobs, keeps mechanical roles in Ontario and the US, skips anything already on the board, and rebuilds `index.html`. New roles get a blue "new" chip for a week; tick "New this week" to see only those.

- `data/curated.json`: hand-picked roles (with notes, match ratings and year checks)
- `data/auto.json`: roles found automatically, rewritten each run (closed postings drop off)
- `data/seen.json`: the date each auto role first appeared

To run it by hand: Actions tab → Daily job update → Run workflow.
