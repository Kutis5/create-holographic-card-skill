import type { CardPresentation } from "./presentation";

export interface CardRecord {
  id: string;
  backgroundSrc: string;
  subjectSrc: string;
  artAlt: string;
  presentation: CardPresentation;
  backSrc?: string;
  backAlt?: string;
}

export type CardRegistry = Record<string, CardRecord>;

export function getCard(registry: CardRegistry, cardId: string): CardRecord {
  const card = registry[cardId];
  if (!card) throw new Error(`Unknown holographic card: ${cardId}`);
  return card;
}
