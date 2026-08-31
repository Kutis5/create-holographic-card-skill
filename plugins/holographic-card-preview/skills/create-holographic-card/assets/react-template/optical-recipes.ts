import type { CardPresentation, EffectTarget, MaterialFamily } from "./presentation";
import { MATERIAL_PROFILES } from "./holo-engine.js";

export interface OpticalRecipe {
  family: MaterialFamily;
  rimFactor: number;
  backgroundGlareFactor: number;
  surfaceGlareFactor: number;
}

export const OPTICAL_RECIPES: Readonly<Record<MaterialFamily, OpticalRecipe>> = MATERIAL_PROFILES;

const PATTERNED_MATERIALS = new Set<MaterialFamily>(["pearl", "brushed-metal", "spectral-lines", "etched-holo", "cosmic-flake", "star-holo"]);

export interface ResolvedTargets {
  foil: EffectTarget;
  texture: EffectTarget;
  sparkle: EffectTarget;
  glare: EffectTarget;
}

export function resolveEffectTargets(presentation: CardPresentation): ResolvedTargets {
  const foil = presentation.foil.target === "surface" && PATTERNED_MATERIALS.has(presentation.surface.material)
    ? "background" : presentation.foil.target;
  return {
    foil,
    texture: presentation.texture.target === "surface" ? "background" : presentation.texture.target,
    sparkle: presentation.sparkle.target === "surface" ? "background" : presentation.sparkle.target,
    glare: presentation.glare.target,
  };
}

export function opticalRecipe(family: MaterialFamily): OpticalRecipe {
  return OPTICAL_RECIPES[family];
}
