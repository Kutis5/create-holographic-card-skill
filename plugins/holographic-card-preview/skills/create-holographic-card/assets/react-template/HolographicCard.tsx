"use client";

import { type CSSProperties, type KeyboardEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import type { CardRecord } from "./card-registry";
import { extractFramePalette, paletteFromColor } from "./frame-palette.js";
import type { FramePalette } from "./frame-palette.js";
import { createHolographicRenderer } from "./holo-engine.js";
import type { HolographicRenderer } from "./holo-engine.js";
import { computeOpticalState, expandFoilColors } from "./optical-state.js";
import { opticalRecipe } from "./optical-recipes";
import styles from "./HolographicCard.module.css";

export interface HolographicCardProps {
  card: CardRecord;
  interactive?: boolean;
  className?: string;
}

type Vars = CSSProperties & Record<`--${string}`, string | number>;
type PaletteState = { key: string; palette: FramePalette };
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const pct = (value: number) => `${value}%`;
const paletteVars = (palette: FramePalette): Vars => ({
  "--frame-color": palette.base,
  "--frame-highlight": palette.highlight,
  "--frame-shadow": palette.shadow,
});

export function HolographicCard({ card, interactive = true, className }: HolographicCardProps) {
  const cardRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const backgroundRef = useRef<HTMLImageElement>(null);
  const backRef = useRef<HTMLImageElement>(null);
  const rendererRef = useRef<HolographicRenderer | null>(null);
  const point = useRef({ x: 50, y: 50 });
  const [backgroundLoaded, setBackgroundLoaded] = useState(false);
  const [backLoaded, setBackLoaded] = useState(false);
  const [rendererReady, setRendererReady] = useState(false);
  const [renderError, setRenderError] = useState("");
  const [flipped, setFlipped] = useState(false);
  const { backgroundSrc, subjectSrc, artAlt, presentation, backSrc, backAlt } = card;
  const colorMode = presentation.frame.colorMode ?? "fixed";
  const fixedPalette = useMemo(() => paletteFromColor(presentation.frame.color), [presentation.frame.color]);
  const frontPaletteKey = `${backgroundSrc}|${presentation.frame.color}|${colorMode}`;
  const backPaletteKey = `${backSrc ?? ""}|${presentation.frame.color}|${colorMode}`;
  const [frontPaletteState, setFrontPaletteState] = useState<PaletteState>(() => ({ key: frontPaletteKey, palette: fixedPalette }));
  const [backPaletteState, setBackPaletteState] = useState<PaletteState>(() => ({ key: backPaletteKey, palette: fixedPalette }));
  const rendererFamilyRef = useRef(presentation.surface.material);
  const hasBack = Boolean(backSrc);
  const recipe = opticalRecipe(presentation.surface.material);

  const write = (x: number, y: number, driveRenderer = true) => {
    const element = cardRef.current;
    if (!element) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const nx = reduced ? 0.48 : (x - 50) / 50;
    const ny = reduced ? -0.36 : (y - 50) / 50;
    const state = computeOpticalState(presentation, nx, ny, recipe);
    const distance = Math.min(1, Math.hypot(nx, ny));
    element.style.setProperty("--rotate-x", reduced ? "0deg" : `${state.rotateX}deg`);
    element.style.setProperty("--rotate-y", reduced ? "0deg" : `${state.rotateY}deg`);
    element.style.setProperty("--card-scale", reduced ? "1" : String(state.scale));
    element.style.setProperty("--subject-x", pct(nx * presentation.depth.parallaxX));
    element.style.setProperty("--subject-y", pct(ny * presentation.depth.parallaxY));
    element.style.setProperty("--subject-z", `${reduced ? 0 : distance * presentation.depth.lift}px`);
    if (driveRenderer) {
      element.style.setProperty("--tilt-duration", `${Math.round(presentation.motion.smoothing * 1000)}ms`);
      element.style.setProperty("--tilt-ease", "cubic-bezier(.2,.75,.22,1)");
      rendererRef.current?.setPointer(nx, ny, true);
    }
  };

  useEffect(() => {
    setBackgroundLoaded(false);
    setRendererReady(false);
    setRenderError("");
  }, [backgroundSrc]);

  useEffect(() => { setBackLoaded(false); }, [backSrc]);

  useEffect(() => {
    let cancelled = false;
    if (colorMode === "fixed" || !backgroundLoaded || !backgroundRef.current) return;
    Promise.resolve().then(() => {
      const palette = extractFramePalette(backgroundRef.current!, presentation.frame.color);
      if (!cancelled) setFrontPaletteState({ key: frontPaletteKey, palette });
    });
    return () => { cancelled = true; };
  }, [backgroundLoaded, colorMode, frontPaletteKey, presentation.frame.color]);

  useEffect(() => {
    let cancelled = false;
    if (colorMode === "fixed" || !backSrc || !backLoaded || !backRef.current) return;
    Promise.resolve().then(() => {
      const palette = extractFramePalette(backRef.current!, presentation.frame.color);
      if (!cancelled) setBackPaletteState({ key: backPaletteKey, palette });
    });
    return () => { cancelled = true; };
  }, [backLoaded, backPaletteKey, backSrc, colorMode, presentation.frame.color]);

  useEffect(() => {
    if (!backgroundLoaded || !canvasRef.current || !backgroundRef.current) return;
    setRenderError("");
    setRendererReady(false);
    let cancelled = false;
    let renderer: HolographicRenderer;
    try {
      renderer = createHolographicRenderer({
        canvas: canvasRef.current,
        image: backgroundRef.current,
        presentation,
        onError: error => { if (!cancelled) setRenderError(error.message); },
      });
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : String(error));
      return;
    }
    rendererRef.current = renderer;
    rendererFamilyRef.current = presentation.surface.material;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reduce = () => {
      renderer.setReducedMotion(media.matches);
      if (media.matches) write(74, 32, false);
      else write(point.current.x, point.current.y, false);
    };
    reduce();
    media.addEventListener("change", reduce);
    const observer = new ResizeObserver(() => renderer.resize());
    observer.observe(canvasRef.current);
    const visibility = () => renderer.setPaused(document.hidden);
    document.addEventListener("visibilitychange", visibility);
    visibility();
    renderer.ready().then(() => {
      if (!cancelled) setRendererReady(true);
    }).catch(error => {
      if (!cancelled) setRenderError(error instanceof Error ? error.message : String(error));
    });
    return () => {
      cancelled = true;
      observer.disconnect();
      document.removeEventListener("visibilitychange", visibility);
      media.removeEventListener("change", reduce);
      renderer.dispose();
      if (rendererRef.current === renderer) rendererRef.current = null;
    };
  }, [backgroundLoaded, backgroundSrc]);

  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    let cancelled = false;
    try {
      const familyChanged = rendererFamilyRef.current !== presentation.surface.material;
      if (familyChanged) setRendererReady(false);
      renderer.setPresentation(presentation);
      rendererFamilyRef.current = presentation.surface.material;
      if (familyChanged) {
        renderer.ready().then(() => { if (!cancelled) setRendererReady(true); }).catch(error => {
          if (!cancelled) setRenderError(error instanceof Error ? error.message : String(error));
        });
      }
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : String(error));
    }
    return () => { cancelled = true; };
  }, [presentation]);

  const reset = () => {
    point.current = { x: 50, y: 50 };
    cardRef.current?.style.setProperty("--tilt-duration", "1200ms");
    cardRef.current?.style.setProperty("--tilt-ease", "cubic-bezier(.18,1.38,.32,1)");
    write(50, 50, false);
    rendererRef.current?.releasePointer();
  };
  const move = (event: PointerEvent<HTMLElement>) => {
    if (!interactive) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    point.current = {
      x: clamp((event.clientX - bounds.left) / bounds.width * 100, 0, 100),
      y: clamp((event.clientY - bounds.top) / bounds.height * 100, 0, 100),
    };
    write(point.current.x, point.current.y);
  };
  const key = (event: KeyboardEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget) return;
    if ((event.key === "Enter" || event.key === " ") && hasBack) { event.preventDefault(); setFlipped(value => !value); return; }
    if (!interactive) return;
    if (event.key === "Home") { event.preventDefault(); reset(); return; }
    const delta = { x: 0, y: 0 };
    if (event.key === "ArrowLeft") delta.x = -8; else if (event.key === "ArrowRight") delta.x = 8;
    else if (event.key === "ArrowUp") delta.y = -8; else if (event.key === "ArrowDown") delta.y = 8; else return;
    event.preventDefault();
    point.current = { x: clamp(point.current.x + delta.x, 0, 100), y: clamp(point.current.y + delta.y, 0, 100) };
    write(point.current.x, point.current.y);
  };

  const p = presentation;
  const frontPalette = colorMode === "fixed" || frontPaletteState.key !== frontPaletteKey ? fixedPalette : frontPaletteState.palette;
  const backPalette = colorMode === "fixed" || backPaletteState.key !== backPaletteKey ? fixedPalette : backPaletteState.palette;
  const foilColors = expandFoilColors(p.foil.colors, p.surface.accent);
  const vars = useMemo<Vars>(() => ({
    "--outer-radius": pct(p.radius.outer), "--inner-radius": pct(p.radius.inner), "--frame-width": pct(p.frame.width),
    "--surface": p.surface.color, "--accent": p.surface.accent,
    "--foil-a": foilColors[0], "--foil-b": foilColors[1], "--foil-c": foilColors[2],
    "--foil-d": foilColors[3], "--foil-e": foilColors[4], "--foil-f": foilColors[5],
    "--shadow-opacity": p.depth.shadowOpacity, "--shadow-blur": `${p.depth.shadowBlur}px`,
    "--tilt-duration": `${Math.round(p.motion.smoothing * 1000)}ms`, "--flip-y": flipped ? "180deg" : "0deg",
  }), [flipped, foilColors.join("|"), p, recipe]);

  if (renderError) return <div className={styles.renderError} role="alert">Holographic preview unavailable: {renderError}</div>;

  return <article ref={cardRef} className={[styles.card, !rendererReady ? styles.pending : "", styles[`frame-${p.frame.style}`], interactive ? styles.interactive : "", className].filter(Boolean).join(" ")} style={vars} onPointerMove={move} onPointerLeave={reset} onPointerCancel={reset} onBlur={reset} onFocus={reset} onKeyDown={key} tabIndex={0} aria-label={artAlt} aria-busy={!rendererReady} data-card-id={card.id} data-recipe={recipe.family}>
    <div className={styles.rotator}>
      <div className={styles.front} style={paletteVars(frontPalette)} aria-hidden={flipped}>
        <canvas ref={canvasRef} className={styles.materialCanvas} aria-hidden="true" />
        <img ref={backgroundRef} className={styles.background} src={backgroundSrc} alt={artAlt} onLoad={() => setBackgroundLoaded(true)} onError={() => setRenderError("The background image could not be loaded.")} />
        <img className={styles.subjectShadow} src={subjectSrc} alt="" aria-hidden="true" />
        <img className={styles.subject} src={subjectSrc} alt="" aria-hidden="true" />
      </div>
      {hasBack && <div className={styles.back} style={paletteVars(backPalette)} aria-hidden={!flipped}><div className={styles.surface}><img ref={backRef} className={styles.background} src={backSrc} alt={backAlt ?? ""} onLoad={() => setBackLoaded(true)} /></div></div>}
    </div>
  </article>;
}
