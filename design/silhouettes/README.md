# Animal silhouettes

Stand-ins for an animal with no photograph, shared by the web app and the
mobile app. They are the supplied cattle artwork, traced as it is by
`scripts/trace_silhouettes.py` (potrace; the only changes are a cleaned,
smoothed outline, the grass cropped from one grazing cow, and stray specks
dropped). Re-run the script to regenerate this folder and
`upande_livestock/public/images/silhouettes/`, which the web app inlines.

Every file is one `currentColor` path with a tight viewBox (the shapes differ:
a cow side on is wide, a calf facing us is tall, so fit each inside a box). In
React Native, render them with `react-native-svg` and pass `color`.

| File                    | Source                         | Used for          |
|-------------------------|--------------------------------|-------------------|
| `cow.svg`               | `illustration 5.png`           | cow (standing)    |
| `cow-udder.svg`         | `illuistraton 2.png`, row 1, 3 | cow               |
| `cow-grazing.svg`       | `illuistraton 2.png`, row 3, 1 | cow, heifer       |
| `cow-grazing-2.svg`     | `illustration 6.png`, grass cropped | cow          |
| `cow-grazing-grass.svg` | `illustration 6.png`, with its grass | not picked (for print / splash use) |
| `heifer.svg`            | `illuistraton 2.png`, row 2, 2 | heifer            |
| `bull.svg`              | `illuistraton 2.png`, row 1, 1 | bull              |
| `steer.svg`             | `illuistraton 2.png`, row 2, 1 | steer             |
| `steer-turned.svg`      | `illuistraton 2.png`, row 3, 3 | steer             |
| `steer-grazing.svg`     | `illuistraton 2.png`, row 2, 3 | steer             |
| `calf.svg`              | `illuistraton 2.png`, row 1, 2 | calf (and sheep, goat) |
| `calf-grazing.svg`      | `illuistraton 2.png`, row 3, 2 | calf (and sheep, goat) |

`illustration .png` is the same grazing cow as `illustration 6.png` at another
crop, so it is not traced twice. There is no sheep or goat artwork: sheep and
goats wear the calf's two pictures until drawings of their own are supplied.

## Which one an animal gets

The web app's rule is `frontend/src/lib/silhouettes.ts` (with tests); the
phone should do the same so an animal wears the same picture on both:

1. **Class**, first match wins:
   - species Sheep → `sheep`; Goat → `goat`;
   - stage `calf`, or younger than 210 days → `calf`;
   - male → `bull` if his stage is `bull` (breeding bull), else `steer`;
   - sex not recorded → `steer`;
   - female → `heifer` if her stage is `heifer`; `cow` if fresh, served or in
     calf; otherwise (open, or not known) `heifer` under 730 days old, else `cow`.
2. **Pose**: FNV-1a 32-bit hash of the animal's number (trimmed, upper-cased),
   modulo the number of poses of the class, indexing its list in order:
   cow `cow, cow-udder, cow-grazing-2, cow-grazing`; heifer `heifer,
   cow-grazing`; bull `bull`; steer `steer, steer-turned, steer-grazing`; calf,
   sheep and goat `calf, calf-grazing`.

The web app shows them on a soft card tinted with the stage colour
(`color-mix(tone 15%, bg-soft)`) with the drawing in a deeper shade
(`color-mix(tone 58%, ink)`), like a picture in a frame.
