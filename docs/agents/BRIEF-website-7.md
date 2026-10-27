# Brief: make the website faster on phones and desktops

Read docs/agents/COMMON.md first, then docs/DESIGN.md and website/ with its tests and docs/verification/ui.md.

## What the owner said

"Optimize the website for mobile and desktop in terms of speed."

## Where it stands

Measured on the live site (https://sohan-bhat.github.io/OpenHAL/) on 2026-10-26, before the print babysitter rounds merged, with Lighthouse 13.5.0 through website/scripts/lighthouse.mjs. Re-measure first, because the landing story, page transitions and smooth scrolling changed since.

- Scores are 98 to 100, with no layout shift anywhere. Pages weigh 65 to 75 KB, and the two fonts are 51 KB of that.
- The home page on mobile has first paint at 1.13 s and largest paint at 1.45 s, but a Speed Index of 3.70 s and 59 ms of blocking time. Something keeps painting for seconds after the first frame.
- docs/architecture is 312 KB of HTML (67 KB over the wire). Its 17 inline SVGs carry 122 KB of base64 fonts that D2 embeds, two per diagram, and every diagram ships twice, once per theme.
- The Inspector page downloads 210 KB of full-size WebP captures on a phone and crops them with CSS.
- The Python reference has 88 ms of blocking time on mobile, the most of any page, with 1,912 elements in its DOM. The Playground and every other page score 100 on mobile and desktop.
- Both fonts are preloaded on every page. One playwright-cli run logged that a preloaded font was not used within a few seconds.
- No link prefetching, so every click waits for a full page fetch.
- GitHub Pages sends `cache-control: max-age=600` for everything, hashed assets included, and its headers can't be changed.

## Goal

1. **Instant navigation.** Prerender or prefetch nav and in-page links on hover and pointer down. Use Speculation Rules where the browser supports them, with Astro's prefetch as the fallback. Make sure the view transitions from the landing round still play with prerendered pages. Don't prefetch the Playground's or the search's heavy files until they're needed.
2. **The home page paints once.** Find what drives the home page's Speed Index past the first paint on mobile and fix it, so the first screen is complete at first paint. Target a Speed Index under 1.5 s and blocking time under 50 ms on Lighthouse mobile.
   Bring the Python reference's blocking time under 50 ms too.
3. **Fonts.** Subset both faces to the glyphs the site uses. Narrow the weight axis to the weights in use, or ship static instances if they come out smaller. Preload only the face and weight the first screen needs. Keep the fallback metrics, so the swap doesn't move anything. Put the before and after sizes in your report.
4. **Diagrams on the page.** When the site inlines a diagram, strip D2's embedded font data, since the page already has the fonts, and ship one SVG that follows the theme through CSS custom properties instead of a light copy and a dark copy. The files in docs/diagrams stay self-contained for the README. Target docs/architecture under 100 KB of HTML.
5. **Images.** Serve the Inspector captures as cropped, responsive images (srcset at the sizes the page shows, AVIF with WebP fallback, width and height set, lazy below the fold), and the full image only behind "Open the whole screen". website/src/data/inspector-captures.json gives each shot's file, caption, alt text and a crop the capture script measured from the page, so build the crops from it at build time.
6. **JavaScript and CSS.** Every page loads only what it uses. The Playground's kernel loads only on the Playground page, search loads only when opened, and the story and smooth scrolling load only on home. Look for dead CSS and duplicate bundles.
7. **Budgets that stay.** Add a test that builds the site and fails when a page passes its budget: HTML, CSS, JS and fonts, gzipped, per template. Set each budget from your final numbers with a little headroom. Record the budgets and how to run the check in docs/verification/ui.md.
8. **Repeat visits.** Pages can't set cache headers. Propose, but don't add, a small service worker that keeps hashed `/_astro/` files for repeat visits, with how it would handle updates and the /OpenHAL/ base. The owner decides.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, `uv run pytest tests/docs tests/website tests/demo` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`), and the build under /OpenHAL/ checked the way the Pages workflow builds it. Lighthouse mobile and desktop, three runs each with the median reported, on home, docs, a spec page, drivers, the Playground, the Python reference, docs/architecture and the Inspector page: 100 on desktop everywhere, 98 or more on mobile, no layout shift. Put a before and after table in docs/verification/ui.md. Nothing may look different except where this brief says so. Screenshot home, docs/architecture and the Inspector page at 1440 and 390 before and after, and compare them.

## Files you own

website/ (including how the site inlines diagrams and how the Inspector page shows the captures, but not the capture images themselves) and docs/verification/ui.md.

## Not yours

docs/diagrams/ and scripts/diagrams.py (the README needs the SVGs self-contained), dashboard/, openhal/, the capture script and images, and every safety rule.
