# Layered card assets

Load this only after final 5:7 art is accepted.

## Produce

Create one background edit and one keyed mask source from the accepted art. Launch these two independent edits in parallel, give them distinct output paths, and wait for both to succeed before subject preparation:

- **Background plate:** remove only the principal foreground subject and reconstruct the occluded scene. Preserve every pixel outside the removal boundary as closely as possible. Do not introduce text, props, color shifts, lighting changes, borders, or effects.
- **Keyed mask source:** edit only the non-subject pixels. Keep the principal subject's identity, silhouette, pose, scale, coordinates, and existing crop boundaries fixed. Choose saturated green or magenta according to which family is farther from the subject edge palette. Request one flat, high-chroma background reaching all four corners, with low texture and no cast shadow. Do not require diffusion output to equal an exact RGB triplet. Forbid checkerboards, transparency-preview squares, strong gradients, texture, floor planes, reflections, outlines, halos, text, and added padding.

For the keyed edit, bind alignment more strongly than color numerics: “Keep every foreground pixel at the same canvas coordinate and scale; replace only non-subject pixels with one flat saturated green or magenta field reaching all four corners.” The result is valid when the background is perceptually separable and the subject is registered, not when its pixels equal a requested hex code.

Generate the keyed source once. Never request direct transparent output and never regenerate a rejected keyed source. Build the subject layer with:

```text
python scripts/prepare_subject_layer.py --art <accepted-art> --keyed <keyed-edit> --key-color auto --subject-kind <human|generic> --out <subject.png>
```

The script rejects mismatched canvases, estimates the actual green or magenta cluster from the outer 2% and four corners in Lab space, and accepts ordinary diffusion brightness variation. It removes only pixels belonging to a chroma region connected to the canvas edge, creates a soft matte for mixed edge pixels, and checks foreground edge alignment against the accepted art. A shifted, scaled, or restaged keyed subject is a hard failure.

The keyed image supplies Alpha evidence only; every visible RGB pixel comes from the accepted art, so no green or magenta despill color can enter the subject layer. When the key cluster is usable but the matte is uncertain, `u2net_human_seg` or `u2netp` may guide only the uncertain edge band. A complete local fallback is allowed only when no stable chroma cluster exists. Do not download a model, make another image request, or switch to an API transparency model. The JSON report uses `adaptive-chroma`, `chroma-guided-local`, or `local-fallback`, includes the estimated key, cluster spread, border coverage, alignment result, ordered `attempts`, and validation; it never includes timing or image data.

## Validate

Both assets must have identical pixel dimensions and a 5:7 ratio. The subject must have meaningful transparent and opaque pixels, 1%–94% Alpha coverage, and a non-full-canvas Alpha bounding box. Read the script's JSON result and report `method`, `attempts`, `validation`, and any `fallbackReason`.

Recompose the layers at zero offset and compare against the accepted art: subject location, silhouette, identity, scale, and boundary color must match. Inspect at full resolution for holes, jaggedness, matte, color fringe, background fragments, and inpainting spill. Opaque subject RGB must equal the accepted art. Do not repair by regenerating either layer. If inspection still fails, stop and report the failed field; do not emit a flat-card fallback or exceed the three-generation budget.
