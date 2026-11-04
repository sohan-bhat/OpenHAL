# Reference

The OpenHAL demo belongs to one series with the Oopsy, Taro and Wobbl videos. This file records what those three videos do, measured from the files and the YouTube player on 2026-11-03, so the OpenHAL video can match the series while using OpenHAL's own brand.

## How the videos were studied

| Video | Source | Frames | Sound |
|---|---|---|---|
| Oopsy, "Undo for rm -rf \| Oopsy" | `~/code/projects/oopsy/site/oopsy-demo.mp4`, 36.0 s, 1920 by 1080, 60 fps, H.264 with AAC at 48 kHz | ffmpeg, one frame a second, and ten a second around two cuts | ffmpeg `ebur128` and a spectrogram |
| Taro, "Meet Taro, an open source AI meeting assistant" | `~/code/projects/taro/apps/web/public/taro-demo.mp4`, 46.2 s, 1920 by 1080, 60 fps, H.264 with AAC at 48 kHz | the same | the same |
| Wobbl, "Simulate anything before you build it. \| Wobbl" | YouTube `RtCNKbhABqE`, 53.6 s | a headless Chromium seeking the player every 1.5 s, and every 0.3 to 0.4 s around three cuts | the player's audio captured in the same headless page, then `ebur128` and a spectrogram |

YouTube's own content loudness readout agrees with the measurements, at -14.2 dB for Wobbl, -27.4 dB for Taro and -14.3 dB for Oopsy against YouTube's -14 dB target.

## Timeline of each video

### Oopsy, 36 s

| Time | Scene |
|---|---|
| 0 to 3 s | A three line headline builds word by word on the dark background, then a short subline and the pencil |
| 4 to 13 s | A redrawn editor on a pink field, with a file tree on the left and a terminal on the right. The prompt types out, agent lines carry a small yellow `agent` badge, the file tree is scribbled out, then a huge "oops." drops in and the files come back |
| 12 to 13 s | One caption under the panel, "Like it never happened." |
| 14 to 15 s | "And everything else you wish you hadn't run." on a yellow field |
| 16 to 23 s | Four vignettes of 2 s each, a command on the left and a card on the right (a build folder, a code diff, a database table, a Kubernetes deployment), each crossed out by the pencil |
| 24 to 27 s | Two stat cards, "25 ms added before a command" and "0 bytes extra disk for a deleted file on APFS", the numbers counting up, with a source line in small type at the lower right |
| 28 to 31 s | "One line." over the install command tabs |
| 32 to 33 s | The closing line with a strike through one word |
| 34 to 36 s | The end card, the mark and the wordmark centered with the URL in mono under them |

### Taro, 46 s

| Time | Scene |
|---|---|
| 0 to 3 s | Three quoted lines type in, in an italic serif |
| 4 to 6 s | The headline, "Meeting follow-ups get lost. Taro does them before you hang up." |
| 7 to 11 s | A short crossfade to a redrawn Google Calendar, then a slow push in. The caption "Taro joins from your calendar." sits at the top left and the logo at the top right for the rest of the video |
| 12 to 20 s | A redrawn Meet call with live captions typing in, then a chat notification. Captions "Say "Hey Taro" and what you need." and "Updates land in the right channel." |
| 20 to 27 s | "It writes the ticket from the conversation." A redrawn Linear board and ticket, with a cursor |
| 27 to 37 s | "Ask for a few things at once." Two GitHub pull requests, one merged and one opened, with the cursor clicking tabs |
| 38 to 43 s | "Everything it did, in your dashboard." The product's own dashboard |
| 44 to 46 s | The end card on the brand purple, the mark and wordmark with the URL under them, then black |

### Wobbl, 54 s

| Time | Scene |
|---|---|
| 0 to 7 s | A redrawn Claude Code window, about 84 percent of the frame wide, centered, with macOS window buttons and the session title. The header shows the mascot, "Claude Code", the model and plan, and the folder. The prompt types out, and Claude's guess appears with a red underline on "should probably hold" |
| 7 to 12 s | `/exit`, then `npx wobbl setup` with its output in the same window |
| 13 to 19 s | Claude Code again. "I'll check it with Wobbl." then the MCP tool call box with a yellow outline and a yellow `WOBBL` badge at its top right, the result line under `⎿`, and a spinner line, "Simulating… (2m 36s · esc to interrupt)". The timer shows that time passed while the edit skips the wait |
| 19 to 23 s | The stressed bracket in 3D, the peak stress counting up beside a color scale, then a `MARGINAL` stamp |
| 24 to 29 s | Three panels in one layout. A left column holds the title, a mono subtitle, a small uppercase label, the big number with a smaller unit, a bar against the limit with a tick and its label, and the stamp. The 3D view fills the right two thirds. "Desktop robot arm" shows "SHOULDER TORQUE NEEDED 1.35 N m" against "1.07 available" and `FAILS` |
| 30 to 43 s | A montage of about 1.5 s per scene, each with a caption card at the lower left (a small label, a title, a number with its unit and a stamp) |
| 43 to 47 s | Every scene as a tile in one grid, tiles flying in, and "Parts. Circuits. Motors. Molecules. One command." building word by word |
| 48 to 54 s | The mark pops in, a full frame flash of the brand yellow with the logo, then the dark end card. Logo and wordmark, the tagline in mono, `$ npm i wobbl` with the `$` in yellow, and the URL in gray mono |

## What the series does

### Structure
- A cold open of 3 to 7 s that states the problem in the product's own UI or in a short headline, never a logo first.
- The product working in a redrawn UI for the longest stretch, 9 to 13 s.
- Proof in a short run of scenes of 1.5 to 4 s each, in one repeated layout.
- Measured numbers on stat cards, then the end card.
- Videos run 36 to 54 s. The end card holds for 2 to 6 s.

### Redrawn UI
- Every product UI is redrawn in code and set in the product's type, never screen recorded. Text is sharp at every size.
- Terminals and editors sit in a window with rounded corners and a soft shadow on the background, filling 84 to 90 percent of the frame width.
- Typing appears character by character with a block cursor. The prompt types at roughly 25 to 35 characters a second, and output lines appear whole.
- Wobbl's Claude Code window keeps the real layout. The submitted prompt sits on a gray band, assistant text starts with `●`, a tool call reads `server - tool (MCP)(args)` with the result under `⎿`, the spinner line is in Claude orange with a timer, and the input box sits between two rules with "? for shortcuts" under it.
- The product's tool call is the one place the product's color appears inside the terminal, as the outline of the call and a small badge with the product's name.
- Taro's cursor glides on an eased path and clicks with a small press.

### Panels and cards
- Wobbl's data panel is a left column on the dark background with no box around the text. The title is large and bold, the subtitle small mono, the label tiny uppercase mono with wide tracking, the number large mono with its unit about a third of its size, and the bar thin with a tick at the limit.
- The verdict appears after the number has counted up, about 0.5 s later.
- Oopsy's stat cards set the number huge and the unit much smaller on the same baseline, with a short plain label under each, and the measurement's source in small type at the lower right.
- Cards that stand for a real thing (a folder, a deployment, a table) are flat rectangles in the product's palette with a hard offset shadow, set in the UI's mono.

### Words
- Very few words. Oopsy and Wobbl have almost no captions. Taro has one short plain sentence per step at the top left, in the product's heading face, with the logo at the top right.
- Headlines build word by word, about 0.25 s per word.
- Every label stays on screen for at least 1.5 s.

### Motion and cuts
- Most cuts are hard cuts, and many change the background. Taro crossfades for about 0.3 s between the headline and the first UI.
- Inside a scene, things move on smooth ease out curves of 0.3 to 0.6 s, with a slow push in on UI that holds a while.
- Numbers count up over about 0.6 to 1 s.
- Nothing bounces, spins or glows.

### End card
- Dark background, everything centered. The wordmark is the largest thing, then the tagline, then the install command with the prompt sign in the accent color, then the URL in a quieter gray, in that order down the frame, each a little smaller.
- The lines appear one after another, about 0.3 s apart.

### Sound
| Video | Integrated | True peak | Loudness range | What plays |
|---|---|---|---|---|
| Oopsy | -14.3 LUFS | -1.9 dBFS | 3.7 LU | A beat driven music track throughout, with drops to near silence at two cuts (9.4 s and 14.7 s) |
| Wobbl | -14.2 LUFS | -1.7 dBFS | 4.2 LU | A beat driven track with a strong low end, changing section at the scene changes (14.3 s and 22.5 s) and dipping at single cuts |
| Taro | -27.4 LUFS | -10.1 dBFS | 4.2 LU | A soft low pad with typing ticks and soft whooshes on transitions |

Two of the three mix music to about -14 LUFS with peaks near -2 dBFS. The OpenHAL video follows those two, at -14 LUFS with a music bed, and adds the clicks, the servo and the tones the brief asks for.

## How the OpenHAL video adapts the series

| Series trait | In the OpenHAL video |
|---|---|
| The product's palette | OpenHAL's dark palette from `design/tokens.css`, `#111210` background, `#212220` surface, `#383a36` rules, `#eceeec` text, `#afb5ad` secondary text, with the pink `#ff8dcc` used rarely |
| A heavy display face and a mono | IBM Plex Sans at 700 for headings and the wordmark, IBM Plex Mono for UI, numbers, codes and labels, as `docs/DESIGN.md` sets |
| A logo on the end card | The wordmark "OpenHAL" alone, set as text in IBM Plex Sans 700 at -0.04 em tracking |
| The product's badge in the tool call | An `openhal` badge in the pink fill with dark text, and the pink outline on the call |
| Wobbl's boxed stamps, `FAILS` and `OK` | Plain words in the status colors, set in bold mono with no box, border, dot or icon, because `docs/DESIGN.md` never puts a status in a box. Red appears only for `LIMIT_EXCEEDED` and the stop |
| Status colors | The site's dulled tokens, green `#72b88e`, blue `#7db2f0` for pending, red `#d57a72` |
| 60 fps in Oopsy and Taro | 30 fps, as the brief sets, which halves the render load on this laptop |
