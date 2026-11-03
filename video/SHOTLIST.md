# Shot list

The launch film runs 46.23 seconds, 1387 frames at 30 frames a second. Twelve shots come from Blender, then a black hold after STOP and the end card from Remotion. The plan behind every row is `scenes/film.json`, and `scenes/convert_recording.py` writes the shot files from that plan and the hub recording in `data/`.

Film frames count from 1. Recording times are seconds on the recording's clock, and rows are the 120 Hz rows of each beat file, counted from 0. Every lens is a full-frame lens on a 36 mm wide sensor, so the vertical cut keeps the landscape cut's horizontal field of view at the same focal length.

## Shots

| Shot | Beat | Film frames | Film time | Recording | Speed | Rows used |
|---|---|---|---|---|---|---|
| `s1-reveal` | Cold open | 1 to 90 | 0.00 to 3.00 s | 1.02 to 3.99 s | 1.0x | `beat-1-devices.json` 1 to 357 |
| `s1-servo` | Cold open | 91 to 129 | 3.00 to 4.30 s | 4.02 to 5.29 s | 1.0x | `beat-1-devices.json` 361 to 513 |
| `s1-cable` | Cold open | 130 to 168 | 4.30 to 5.60 s | 5.32 to 6.59 s | 1.0x | `beat-1-devices.json` 517 to 669 |
| `s1-gripper` | Cold open | 169 to 216 | 5.60 to 7.20 s | 6.62 to 8.19 s | 1.0x | `beat-1-devices.json` 673 to 861 |
| `s2-sides` | The two sides | 217 to 396 | 7.20 to 13.20 s | 8.20 to 10.94 s | 0.46x | `beat-1-devices.json` 863 to 1180, `beat-2-pick-and-place.json` 0 to 10 |
| `s3-request` | Agent to arm | 397 to 444 | 13.20 to 14.80 s | 10.95 to 12.52 s | 1.0x | `beat-2-pick-and-place.json` 12 to 199 |
| `s3-pick` | Agent to arm | 445 to 600 | 14.80 to 20.00 s | 12.55 to 17.72 s | 1.0x | `beat-2-pick-and-place.json` 204 to 823 |
| `s4-limit` | The limit | 601 to 706 | 20.00 to 23.53 s | 17.90 to 21.40 s | 1.0x | `beat-2-pick-and-place.json` 846 to 910, `beat-3-limit.json` 0 to 354 |
| `s5-hold` | Held for a person | 707 to 802 | 23.53 to 26.73 s | 23.15 to 26.32 s | 1.0x | `beat-4-approval.json` 196 to 575 |
| `s5-drop` | Held for a person | 803 to 892 | 26.73 to 29.73 s | 26.35 to 29.32 s | 1.0x | `beat-4-approval.json` 580 to 935 |
| `s6-stop` | One STOP | 893 to 982 | 29.73 to 32.73 s | 31.00 to 33.97 s | 1.0x | `beat-4-approval.json` 1138 to 1171, `beat-5-stop.json` 0 to 321 |
| black | One STOP | 983 to 1000 | 32.73 to 33.33 s | none | | |
| `s7-devices` | Any hardware | 1001 to 1192 | 33.33 to 39.73 s | 1.02 to 8.98 s | 1.25x | `beat-1-devices.json` 1 to 956 |
| `s8-end` | End card | 1193 to 1387 | 39.73 to 46.23 s | none | | |

## Cameras

Each camera move is a straight line between its keys. The STOP shot's camera stays still from the frame of the STOP press.

| Shot | Landscape camera | Vertical camera |
|---|---|---|
| `s1-reveal` | 55 mm f/3.2, low from the front right, slow push in as the lights come up | 60.8 mm f/3.2, the same push in |
| `s1-servo` | 70 mm f/8, close on the shoulder servo, small arc | 50 mm f/8, the same arc |
| `s1-cable` | 70 mm f/8, close on a servo cable from the back right, small arc | 50 mm f/8, the same arc |
| `s1-gripper` | 60 mm f/8, close on the gripper, slow push in | 45 mm f/8, the same push in |
| `s2-sides` | 60 mm on the gripper, then a pull back to 36 mm f/5.6 over both sides of the layer | 45 mm on the gripper, then a pull back to 53 to 54 mm f/5.6, high from the front right |
| `s3-request` | 38 mm f/5.6, wide from the front right, slow push in | 62.7 mm f/6.2, high from the front, slow push in |
| `s3-pick` | 45 mm f/4.5 on the arm, slow arc | 66.5 mm f/5.9, the same arc |
| `s4-limit` | 32 mm f/6.3, wide and high from the front right, slow push in | 49.3 mm f/9.6, the same push in |
| `s5-hold` | 36 mm f/5.6, wide and high over the display, the phone and the arm, slow push in | 69.7 mm f/7.2, high from the front, slow push in |
| `s5-drop` | 45 mm f/4 on the bin, slow arc | 87 mm f/16, the same arc |
| `s6-stop` | 40 mm f/5 on the arm, push in to a still frame at the STOP press | 63.6 mm f/16, the same push in and still frame |
| black | none | none |
| `s7-devices` | 45 mm f/4 on the printer, then a pull back and up to 30 mm f/8 over the whole set | 34 mm f/4 on the printer, then a rise to 45.7 mm and 61.7 mm f/11.4 high over the whole set |
| `s8-end` | Remotion end card | Remotion end card |

## Labels

| Label | Shot | Color | Trigger |
|---|---|---|---|
| `hal/action move_to` | `s3-request` | light gray | the agent's action request |
| `LIMIT_EXCEEDED` | `s4-limit` | red | the hub's LIMIT_EXCEEDED response |
| `pending` | `s5-hold` | blue | the hub's pending response, until the approval |
| `approved` | `s5-hold` | green | the person's approval |
| `STOP` | `s6-stop` | red | the person's STOP press |

In the landscape cut the labels sit at the lower left, with STOP to the right of the arm. In the vertical cut every label sits at the top center. The wordmark in the two sides shot takes the label's place in each cut.
