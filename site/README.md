# Misfire website

A self-contained static site (no build step, no dependencies):

- `index.html` — landing page
- `docs.html` — documentation (renders `../docs/GUIDE.md` in the browser with a
  generated sidebar, so the docs are single-sourced from the guide)
- `styles.css` — styling, built on the brand tokens
- `assets/` — brand assets used by the site (a curated subset of `docs/brand/`)
  plus `tokens.css` and the favicons

## Preview locally

The docs page fetches the guide over HTTP, so serve it rather than opening the
file directly:

```bash
# from the repo root
python3 -m http.server 8000
# then open http://localhost:8000/site/
```

The landing page (`index.html`) works on its own; the docs page needs the server
so it can load the guide.

## Deploy

The **Deploy site** GitHub Action (`.github/workflows/pages.yml`) publishes
`site/` to GitHub Pages. First enable Pages (Settings → Pages → Source:
"GitHub Actions"), then run the workflow manually. It copies `docs/GUIDE.md` to
`guide.md` next to `docs.html`, so the docs render with no cross-directory fetch.

## Design

A conventional landing structure (hero → worked example → feature grid →
how-it-works → footer) in Misfire's brand: cream ground, ink text, orange accent,
dark terminal panels. Brand source of truth: `docs/brand/`.
