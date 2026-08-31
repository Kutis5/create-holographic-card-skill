# Image Prompt IR v1

Use this internal Markdown IR for card-art generation and reference-image editing. Do not require users to write it and do not return it unless asked. Compile only instructions that can affect pixels.

## Core fields

Write present fields once, in this order, as `FIELD — value`:

```text
MODE — GENERATE | EDIT
INTENT — one-sentence visual outcome
CANVAS — aspect ratio, orientation, output surface
SUBJECT — count, identity, defining attributes, action
SCENE — setting, time, weather, spatial relation
COMPOSITION — framing, viewpoint, placement, negative space
VISUAL — medium, style evidence, lighting, palette, texture
CONSTRAINTS — PRESERVE: ...; CHANGE: ...; AVOID: ...
```

Add these fields only when needed, at their fixed insertion point: `REFERENCE` after `MODE`, `EDIT` after `REFERENCE`, `CAMERA` after `COMPOSITION`, `TYPE` after `VISUAL`, and `VARIATION` before `CONSTRAINTS`. Omit empty fields; do not repeat a field or use vague placeholders such as “etc.” or “as appropriate.”

`REFERENCE` assigns each image a role: identity, product fidelity, composition, or style. `EDIT` names the target region and boundary. `TYPE` quotes exact in-image wording and states placement; keep text short. `VARIATION` is allowed only when the user asks for alternatives.

## Resolve and compile

Apply this precedence: explicit user request > observable reference fact > selected profile default > conservative default. A profile fills only missing detail and never changes identity, exact text, or requested constraints. Select one primary profile; add one auxiliary profile only when it contributes a necessary, non-conflicting field.

Compile in this order, omitting empty sections: task and canvas; subject; scene and composition; visual system and camera; exact text; reference/edit preserve-change boundary; relevant avoids. Use English for visual instructions. Preserve user-supplied in-image text, names, and proper nouns verbatim in quotation marks. Keep ordinary prompts to 120–220 English words and complex edits to 300 words or fewer.

For `EDIT`, preserve all unlisted regions and identity features by default. A ratio-only edit changes the canvas geometry, not the depicted event: bind the original field of view, camera distance, visible subject extent, and existing crop boundaries. Never infer that an already cropped person or object should be completed. Ask only when a reference is required but absent, the target cannot be located, or preserve/change instructions directly conflict.

## Quality gate

Before generation, confirm every abstract request has visible evidence; canvas and composition are explicit; the prompt contains no conflicting preserve/change rules; and avoids are specific to the task rather than a generic blacklist. After the single card-face generation, check the requested identity, full-bleed 5:7 composition, preserved source cutoff, and absence of raster text/UI/card chrome. If one hard requirement fails, stop and report the field; do not regenerate the card face.

Return the accepted image followed by the final prompt used. Do not expose source paths, internal analysis, or the IR by default.
