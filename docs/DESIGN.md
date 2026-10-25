# Design

One design system for the dashboard and the website. The tokens live in `design/tokens.css` and both apps import that file. If a screen needs something this document does not define, add it here first.

## Subject and job

OpenHAL is the layer between an AI agent and a bench full of real equipment. The people who use it own oscilloscopes, printers, Arduinos and power supplies. The dashboard's job is to show what every device is doing and stop anything unsafe in one click. The website's job is to show, within the first screen, that OpenHAL is real software that blocks an unsafe command, and to get a maker from install to a first read.

## References and what we take from each

| Reference | What we borrow |
|---|---|
| Bench power supply and oscilloscope front panels (Tektronix, Rigol, Siglent, Keysight) | Sections grouped behind a printed legend, like VERTICAL or OUTPUT. Tabular readouts with the unit set smaller beside the number. Status lamps next to the thing they describe |
| 3D printer control screens (Klipper Mainsail, Prusa) | Dense, calm lists of live values. Target and actual shown side by side |
| Datasheets | Parameter tables with Min, Typ, Max and Unit columns. Pinout and block diagrams with thin rules and small labels |
| Labeled toggle switches and panel silkscreen | Uppercase condensed legends with generous tracking, printed directly on the panel, never in a pill |
| ISO 7010 and ISO 3864 safety signage | Yellow and black hazard striping for the stopped state, red for prohibition, the triangle for warnings. Used only where it means what it means on a real sign |
| Component reels and part labels | Small label blocks with a part number, value and tolerance, used for device identity and verification badges |

## Color

Five core colors. Semantic colors are reused from them wherever the meaning matches.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--ink` | `#15181B` | `#E7E9E6` | Text, rules, knob black |
| `--panel` | `#E7E9E6` | `#1C2024` | Page background, the enamel of an instrument panel. A cool green-gray, not cream |
| `--bezel` | `#2B3035` | `#2B3035` | Header bar, the stop bar, dark legend plates |
| `--signal` | `#2D5B8C` | `#79A9DA` | Links, focus, interactive controls. Close to the blue of classic test gear |
| `--caution` | `#F2B705` | `#F2B705` | Limit line flags, hazard striping, warning fills. Never used for text on `--panel` |

Supporting neutrals are mixed from `--ink` and `--panel` only (`--ink-2` at 72 %, `--ink-3` at 52 %, `--rule` at 18 %).

Semantic states. Each state has a color, an icon or pattern, and a word, so color never carries meaning alone.

| State | Color | Shape | Word |
|---|---|---|---|
| ok | `#276B43` / dark `#5CB884` | filled circle lamp | OK |
| warning | `--caution` fill with `--ink` text | triangle | WARNING |
| blocked | `#B3261E` / dark `#EE6B62` | circle with bar | BLOCKED |
| stopped | `--caution` and `--ink` 45 degree stripes | striped band | STOPPED |
| unverified | `--ink-3` | dashed outline | UNVERIFIED |

Contrast. Body text is `--ink` on `--panel` (light 14.6 to 1, dark 13.4 to 1). `--signal` on `--panel` is 5.8 to 1 light and 6.6 to 1 dark. Blocked red is 5.4 to 1 and ok green 5.3 to 1 (light) and 6.8 to 1 (dark) on `--panel`. Ink on `--caution` is 9.8 to 1. All pairs are checked by the Playwright accessibility suite.

## Typography

| Role | Face | Why |
|---|---|---|
| Labels and display | Sofia Sans Condensed (OFL) | Panel silkscreen and DIN-style engineering lettering are condensed and upright. Used uppercase with +0.08em tracking for legends, mixed case for page titles |
| Text | Atkinson Hyperlegible Next (OFL) | Made by the Braille Institute for legibility. Distinguishes 0, O, 1, l and I, which matters on a page full of part numbers and units |
| Readouts and code | Martian Mono (OFL) | Wide, technical, tabular figures by default. Values read like an instrument display, not like a spreadsheet |

Inter and Inter-like system UI stacks are never used.

Fonts are self-hosted as WOFF2, subset to Latin plus the symbols the product uses (degree, micro, plus-minus, multiplication sign, arrows), with `font-display: swap` and size-adjusted fallbacks to avoid layout shift.

Scale, six steps (mobile / desktop).

| Step | Size | Line height | Use |
|---|---|---|---|
| `--t-0` | 12 / 12 | 16 | Legends, units, table headers |
| `--t-1` | 14 / 14 | 20 | Secondary text, captions |
| `--t-2` | 16 / 17 | 26 | Body |
| `--t-3` | 20 / 22 | 28 | Section titles |
| `--t-4` | 28 / 34 | 36 / 40 | Page titles |
| `--t-5` | 40 / 60 | 44 / 64 | Website hero headline only |

Readout numbers use Martian Mono at `--t-3` or larger, with the unit in Sofia Sans Condensed at `--t-0`, baseline aligned, as on a meter.

## Layout

- Base unit 4 px. Spacing scale 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Grid. 4 columns at 390, 8 at 768, 12 at 1024 and 1440. Gutters 16, 20, 24, 24. Max content width 1240.
- **Modules** are the main container. A module is a flat area with a 1 px `--rule` border, a 2 px radius at most, and its legend printed into the top border on the left, like a fieldset or a panel silkscreen. Modules group things that belong together on a real instrument (READ, WRITE, ACTIONS, LIMITS). There are no soft shadows and no floating cards.
- Tables follow datasheet layout, with Parameter, Min, Typ or Value, Max and Unit columns where they apply. Numbers are right-aligned in mono.
- Mobile is designed. On 390, module grids become one column, tables become label and value pairs, and the stop control stays fixed at the bottom of the screen within thumb reach.

## Signature element: the limit line

On real gauges, the red line marks where you must not go. In OpenHAL, every limit is drawn the same way, everywhere a limit exists.

- **Form.** A 2 px vertical (or horizontal) rule in the blocked red, with a small `--caution` flag at its end carrying the legend, for example `MAX 100 %`, in Sofia Sans Condensed uppercase at `--t-0` with `--ink` text.
- **Where it appears.** Slider tracks (the thumb physically stops at the line), sparklines (a dashed horizontal line at min and max), range bars in device tables, the playground on the website, and the hero.
- **On a block.** The attempted value is drawn as a hollow marker beyond the line for one second, the line pulses once, and the block reason appears directly under it, for example `Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.`
- **Rate limits** are drawn as a short diagonal bracket on the track showing how far the value may move right now.
- It is used for limits only. Never as decoration.

## Motion

Three patterns, nothing else.

1. **Readout update.** When a live value changes, the changed digits get a 150 ms background tint that fades out. The sparkline extends without easing.
2. **Block.** The attempted-value marker appears past the limit line, the line pulses once over 200 ms, and the reason slides down 8 px over 160 ms.
3. **State change.** Entering or leaving stopped, the hazard stripe band wipes across the stop bar in 240 ms. Device lamps cross-fade over 120 ms.

With `prefers-reduced-motion: reduce`, nothing moves. States change instantly and the block marker stays until dismissed.

## Components

- **Stop bar.** A full-width bar in `--bezel` with one large control labeled STOP ALL. When stopped, the bar becomes the hazard stripe band and the control becomes UNLOCK, which opens a deliberate confirmation (type `unlock`).
- **Lamp.** 10 px circle, color plus shape plus word per the state table.
- **Readout.** Mono value, condensed unit, optional target value in `--ink-2`, sparkline below.
- **Control.** Slider, stepper, toggle or select chosen from the channel type, always showing its limit line and current confirmation tier.
- **Part label.** Device identity block with model, manufacturer, driver, hazard class and verification status, styled like a reel label.
- **Data block.** Text that came from a device, manual or sketch is shown in a bordered block labeled `DEVICE DATA`, never styled like interface copy.

## Copy

- Precise, plain and a little dry, like good technical documentation.
- Name things by what people control. "Fan speed", "Stop all", "Approve", "Reject". A button keeps its name through the flow, so Approve produces "Approved".
- Errors say what happened, which rule, and what to do. "Blocked. heater.power needs fan.speed at 30 % or more. Fan is at 10 %."
- Sentence case everywhere except panel legends, which are uppercase.
- No em dashes, no en dashes, and no colons or semicolons in running prose. Use separate sentences.
- No exclamation marks.
- Banned words: unlock (except the literal control after a stop), seamless, supercharge, elevate, effortless, empower, revolutionary, "Welcome to".
- No fake stats, testimonials or logos. Demo data is always labeled as demo data.

## Banned

These rules apply to the website, the docs and the dashboard, and to every diagram and image in the repository. They come from the owner and override anything above that disagrees.

### Never, no exceptions

Honesty
- Fake stats, user counts, star counts, download numbers, "trusted by" logo strips, testimonials or quotes.
- Fake data presented as real. Screenshots come from the real product running on mocks, labeled as demo data where shown.
- Listing a device or driver as supported unless drivers/catalog.json has it with that status. Unverified things are labeled unverified.
- Lorem ipsum, "John Doe", placeholder avatars, stock photos of people.
- Pricing tables, "Book a demo", waitlist forms or "Enterprise" calls to action. There is nothing to sell.

Safety semantics
- Red used decoratively. Red means blocked, stopped or danger, and nothing else.
- Yellow and black hazard stripes or ISO 7010 symbols as decoration. They only appear next to real hazards.
- Status shown by color alone. Always pair it with an icon, a label or a shape.
- A stop control that is hidden, collapsed, small or styled like a normal button.
- Any UI where an agent action and a human confirmation look the same.

Accessibility
- Text contrast below WCAG AA, including gray on gray muted text and text over images or gradients.
- Body text under 16 px on the website or 14 px in the dashboard. Body weights under 400.
- Removing focus outlines without a visible replacement.
- Motion that ignores prefers-reduced-motion. Anything that flashes more than 3 times per second.
- Information only available on hover.

### Banned by default (only with a written justification in this file)

AI-slop visuals
- Purple, indigo, violet or blue-to-purple gradients. Aurora and mesh gradient backgrounds.
- Glassmorphism, frosted panels, backdrop blur as decoration.
- Neon glow, glowing orbs, light beams, spotlight effects that follow the cursor.
- 3D, clay or glossy rendered objects, isometric illustrations, floating decorative shapes.
- Grain or noise overlays, dot-grid or line-grid backgrounds used as filler.
- Animated gradient borders, shimmer effects, sparkle animations.
- The sparkles icon to mean AI.

Hardware and AI clichés
- Circuit-board trace patterns, glowing PCB backgrounds, chip icons as decoration.
- Robot mascots, robot hands, humanoid robots.
- Brains, neural network node diagrams, "digital DNA".
- Matrix code rain, cyberpunk neon, sci-fi HUD overlays.
- HAL 9000's red eye or 2001 references in the design. Jokes stay in copy, if anywhere.
- Terminal mockups with fake typing in the hero. Show real commands, static and copyable.

Layout templates
- Centered hero, one-line subhead, two pill buttons and a product card on the right.
- Three icon feature cards in a row.
- Bento grids.
- Zigzag sections alternating text and screenshot all the way down the page.
- A stats strip of big numbers.
- Logo marquees and auto-playing carousels.
- FAQ accordions used as filler.
- Footers with columns of placeholder links.
- Every container as a rounded card with a soft drop shadow. Hover-lift on everything.

Typography
- Inter, Geist, Poppins, Roboto, Montserrat or system-ui as the only typeface.
- A serif headline with one italic or gradient-colored accent word.
- Gradient-filled text.
- All caps for anything longer than a short label.
- More than 3 typefaces.

Components and icons
- Stock shadcn, MUI, Chakra or Tailwind UI appearance. Restyle everything to our tokens.
- Lucide or Heroicons used as-is everywhere as decoration. Icons only where they add meaning, drawn consistently.
- Emoji as icons or in headings.
- Toasts for things that need attention. Blocks and stops get persistent, visible states.
- Modals for anything except confirmations and destructive actions.

Dashboard
- Donut or pie charts for single values. Decorative gauges that can't be read precisely.
- Rainbow chart palettes. More than 5 series colors.
- Numbers without units. Values that jump or shift layout when they update.
- Spinners on content that is already loaded. Skeleton screens that don't match the real layout.
- Charts without axes or labeled scales.

Motion and interaction
- Scroll-jacking, parallax, scroll-triggered fade-in on every section.
- Typewriter text effects, counting-up numbers.
- Custom cursors, cursor trails, magnetic buttons.
- More than 3 motion patterns sitewide. Any animation that doesn't communicate a state change.

Copy
- Banned words: unlock (except the literal control after a stop), seamless, supercharge, elevate, effortless, empower, revolutionary, next-generation, cutting-edge, game-changer, magic, harness, unleash, journey, "Welcome to", "the future of".
- "X for Y" taglines ("Stripe for hardware"), "Say goodbye to...", "Meet X", rhetorical questions as headlines.
- "It's not X, it's Y" constructions.
- Exclamation marks.
- Em dashes.
- Vague claims without specifics ("works with everything", "blazing fast", "enterprise-grade").

## Generic-ness tests

Run these on every screen before calling it done.

1. **Swap.** Put another product's name on it. If it still fits, revise.
2. **Thumbnail.** Blur a screenshot to 200 px wide. It should still read as instruments and limits.
3. **Memory.** What does a visitor remember ten minutes later? It should be the limit line and the stop bar.
