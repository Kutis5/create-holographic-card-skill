# Full-bleed card face

Accept one 5:7 raster image as the complete visual face. It must fill the card inside the frame; do not reserve header, footer, caption, tag, serial, or logo regions. Do not bake card borders, UI, watermarks, typography, foil, sparkle, or glare into the source image.

Keep the intended subject readable at card size. For source-free generation, keep the complete intended subject inside the canvas. For a reference edit, preserve the source's existing field of view and cutoff boundaries exactly: a person or object already cropped by the source is not incomplete content and must never be extended. Material and depth layers must never conceal identity, product labels, faces, hands, or defining detail that is visible in the accepted art.

Before any image generation, run `python scripts/inspect_card_face.py --art <input>`. Deterministic acceptance requires a readable, fully opaque raster, a 5:7 ratio within the existing tolerance, and at least 840x1176 pixels. Then inspect every `visualChecksRequired` item: the subject is fully inside the canvas and readable at card size, the bottom has safe breathing room, and no raster text, UI, card chrome, border, watermark, foil, sparkle, glare, or rainbow effect is baked in.

If all checks pass, reuse the art without regenerating it. If the only deterministic failure is ratio, compile a ratio-only EDIT: output an opaque `1060 x 1484` 5:7 image, preserve identity, camera distance, pose, clothing, lighting, scene elements, visible subject extent, and every existing crop boundary, and change only the spatial distribution required by the new canvas. Explicitly forbid zooming out, outpainting, completing the body, revealing unseen background, adding objects, beautifying, or restaging.

Use this binding language in the compiled prompt:

```text
EDIT — Change only the canvas proportion to a full-bleed vertical 5:7 image at 1060 x 1484. Treat the reference's visible field of view and every existing crop boundary as authoritative.
CONSTRAINTS — PRESERVE: identity, face, pose, clothing, camera distance, lighting, visible subject extent, and all existing scene content; CHANGE: only the minimum spatial distribution needed for the 5:7 canvas; AVOID: zooming out, outpainting, completing cropped anatomy, revealing unseen background, adding objects, beautifying, restaging, text, borders, and optical effects.
```

Generate the card face once. A source-free prompt still requires the complete intended subject, safe bottom margin, and no text, UI, frame, or optical effects. Rerun deterministic and visual checks after the single result. If identity, geometry, visible extent, or any hard field fails, stop and report it; never generate a second card face. This keeps the complete successful workflow at no more than three image generations.
