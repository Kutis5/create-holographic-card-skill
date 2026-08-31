---
name: create-holographic-card
description: Create an original full-bleed layered holographic card from uploaded or generated art, preview it, and optionally register it as an isolated CardRecord in a Vite React or Next.js TypeScript project. Use for 3D tilt, foil, glare, collectible cards, or turning an uploaded person, pet, product, or artwork into a polished interactive 5:7 card.
---

# Create Holographic Card

Create one full-bleed 5:7 image card with a clean frame, clear 3D depth, and a flagship multi-layer holographic response. Do not copy branded card systems, source code, or third-party assets.

## Route

1. Classify the input as accepted 5:7 art, ratio-only source art, ordinary source art, or a reference-image edit. Before any image generation, run `python scripts/inspect_card_face.py --art <input>` when a local raster exists, then inspect the listed visual checks with `view_image`. Reuse art only when deterministic and visual checks pass. When the only failure is ratio, use the ratio-only reference-edit route: preserve the source field of view and every existing subject cutoff, and never treat an already cropped body as missing content to complete.
2. For generation/editing, read [image-prompt-ir.md](references/image-prompt-ir.md), [card-face-spec.md](references/card-face-spec.md), and one relevant `profile-*.md`. Generate the card face exactly once. For ratio-only edits, require an opaque `1060 x 1484` result and permit only the minimum spatial redistribution needed for 5:7; forbid zooming out, outpainting, revealing or inventing body parts or background, changing the camera, beautifying, or restaging. For source-free generation, require the complete intended subject and a safe bottom margin. Every route forbids text, UI, card frame, and baked optical effects. If the single card-face result fails, stop instead of spending a fourth generation or silently accepting a reconstruction.
3. Treat every intermediate image as path-only. Consume the built-in image tool's `output_hint`, copy the file to a unique workspace path, and never call `generatedImage` for an intermediate or serialize, quote, decode, or forward its `image_url`. If no usable saved path is returned, stop; do not guess the newest generated file. Use `view_image` only for required visual checks. The final answer returns file links, the actual prompt, and the validation summary, never image binary data.
4. Read [layered-card-assets.md](references/layered-card-assets.md). After card-face acceptance, launch exactly one background plate edit and exactly one flat chroma-key edit in parallel from the same accepted art, with separate output paths. The ordinary successful path is therefore `1 card face + 1 background + 1 keyed source`, with a hard maximum of three image generations. Join both successful results before running `scripts/prepare_subject_layer.py --key-color auto`. Never retry either edit. The script estimates the real green or magenta cluster, extracts only border-connected chroma, checks subject alignment, and uses a cached local model only when no stable chroma cluster exists or to guide an uncertain matte. Inspect and validate both layers, then stop on any remaining failure.
5. Read [material-api.md](references/material-api.md). Choose one material family, one compatible microtexture, targets, a one-to-six-color palette, and either a fixed or image-derived frame color; never generate internal optical-layer parameters. First classify the accepted art: light, low-saturation, pastel, or product-photography compositions use the restrained silver mode with an explicit six-stop low-saturation palette and foil `0.28`, texture `0.32`, glare `0.36`; vivid, iridescent, fantasy, or explicitly rainbow art uses the flagship rainbow mode with foil `0.78`, texture `0.48`, glare `0.62`. In silver mode, the foil must preserve the subject's inherent color and hierarchy at idle, without broad white clipping or visible pink, green, or blue bands. The shared optical stack remains below the transparent subject. The subject is a separate physical layer: it may parallax and cast only an achromatic natural shadow, and never receives foil, texture, sparkle, glare, colored shaping, or rim light. Use `frame.colorMode: "image"` only when the border should adapt to the outer 20% of each face, keeping `frame.color` as the deterministic fallback. Call `preview_holographic_card` once with its unchanged v5 arguments. Open `previewUrl` with one minimal Browser navigation, inspect the actual production-renderer error state and warnings, and leave that right-side tab as the deliverable; never create a separate acceptance page, Widget, or replacement preview.
6. When the user explicitly asks to import the completed card into Cardex, run `python scripts/export_hcard.py --card-dir <output-dir> --id <stable-id> --title <title> --output <file.hcard>` after all layer validation. This creates the versioned Cardex exchange package from the accepted background, alpha subject and Presentation IR; it never regenerates art or alters render parameters.
7. Return one Workflow Summary v1 matching [workflow-summary.schema.json](references/workflow-summary.schema.json). Include generation counts, segmentation method, fallback reason, output paths, four validation results, and preview warnings. Do not include timing fields, image bytes, data URLs, or internal image-result fields.

## Project integration

Only when the user explicitly requests React project integration:

```text
python scripts/install_component.py --project <project-path>
python scripts/register_card.py --project <project-path> --slug <short-name> --background <path> --subject <path> --art-alt <text> --presentation <json-file>
```

Without an explicit project, stop after the image layers, Presentation IR, and preview; do not create a Vite project or modify source code. Install the component once, then register every card through `register_card.py`. It assigns `slug-01`, `slug-02`, and so on, copies each layer into its own `cards/<cardId>/` directory, and updates the catalog and registry without overwriting existing cards. Use `--out` only for an existing convention and `--force` only with approval. Render with `<HolographicCard card={cardRegistry[cardId]} />`; the old direct image/presentation props are removed. Run lint, type check, production build, registration tests, and installer tests. Do not run Playwright or visual browser automation.

## Resources

- [card-face-spec.md](references/card-face-spec.md): full-bleed card acceptance rules.
- [layered-card-assets.md](references/layered-card-assets.md): keyed-mask prompt, local fallback, and layer validation.
- [material-api.md](references/material-api.md): Presentation IR v2 and rendering guardrails.
- `assets/react-template/holo-textures/manifest.json`: GPU Optical Recipe Registry v2 的原创 RGBA 通道资产包清单。
- [workflow-summary.schema.json](references/workflow-summary.schema.json): strict binary-free final workflow summary.
- [image-prompt-ir.md](references/image-prompt-ir.md) and `profile-*.md`: optional generation compiler.
- `scripts/inspect_card_face.py`: deterministic ratio, resolution, and opacity preflight before generation.
- `scripts/prepare_subject_layer.py`: adaptive Lab/chroma preparation with border connectivity, alignment validation, original-RGB recomposition, and one cached local fallback.
- `scripts/export_hcard.py`: deterministic Cardex `.hcard` exporter for accepted layered cards.
- `assets/react-template/`, `scripts/install_component.py`, and `scripts/register_card.py`: integration and multi-card registration resources.
