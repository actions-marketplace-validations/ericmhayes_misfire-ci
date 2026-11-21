# Misfire: logo kit

The mascot is a worried V-engine in sticker style. It has angled cylinder banks with orange caps, an intake on top and a finned sump.
Its two pulleys are the eyes, linked by the timing belt. The right-hand cylinder has misfired: a spark jumps off its cap,
it puffs smoke, and the engine sweats while it works out why.

## Files
- `svg/`: source vectors, text converted to outlines.
  - `mascot`: full illustration with the puff and the sweat drop.
  - `mark`: the same engine without the puff and sweat.
  - `avatar`: full-bleed square (GitHub org avatar).
  - `icon`: rounded app tile.
  - `-small-`: chunkier cut for 24–47 px.
  - `pixel16`: hand-fitted 16 px.
- `png/`: 512/256/128/64/32/16 px for mascot, mark, avatar and icon (the 32 and 16 px files already use the small and pixel cuts). Lockups come at @1x/@2x/@4x, plus the 1200×630 OG card.
- `favicon.svg`, `favicon.ico`, `misfire-tokens.json`, `misfire-tokens.css`.

## Themes
- `light`: cream ground, dark outline. This is the primary look.
- `dark`: ink ground, with a paper sticker halo around the mascot so the outline still reads.
- `mono-black` / `mono-white`: one ink, for stamps and single-color print.

## Rules
- Keep the eyes worried. Misfire is concerned, never angry or panicked.
- The spark belongs to the right-hand cylinder cap. Don't add flames.
- Use `#B54509` for orange text on cream; `#FF7A1A` is for shapes only.

## Animated (`animated/`)
The animation is a 4-second loop: one blink at 1.6 s, then a double blink at 3.2 s. The lids close from the top and bottom and meet in the middle.
- `*-animated-*.svg`: SMIL animation with no scripts. It works in `<img>`, in GitHub READMEs and in all modern browsers. Use it for READMEs and docs headers.
- `*.gif`: fallback for places that strip SVG, like Slack, some markdown renderers and email.
- `*.mp4`: 12-second clip (3 loops), H.264, for decks and social posts.
