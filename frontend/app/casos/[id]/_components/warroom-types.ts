// Sala de estrategia (nombre interno: warroom) — tipos del contrato de diseño
// congelado (ver scratchpad/warroom-contrato.md). §G: estos tipos son internos,
// nunca se muestra "panel"/"stance"/"warroom" al abogado — solo "counsel" y
// "posturas" en el copy visible.

export type Panelist = {
  persona_id: string | null; // null = panelista sintético de código
  stance: string;
  name: string;
  stance_label: string;
  focus: string;
};

export type AvailablePersona = {
  persona_id: string;
  name: string;
  title: string;
  focus_areas: string[];
};

export type PanelProposal = {
  proposed: Panelist[];
  available: AvailablePersona[];
};

export type TesisViable = "Sí" | "Con reservas" | "Riesgosa";

export type Conclusions = {
  tesis_viable: TesisViable;
  fortalezas: string[];
  riesgos: string[];
  puntos_ciegos: string[];
  estrategia: string;
  proximo_paso: string;
};

export type DebateTurn = {
  round: number;
  persona_id: string | null;
  name: string;
  stance_label: string;
  text: string;
};

export type WarRoomVerification = {
  marcadas: number;
  respaldadas: number;
  anotadas: number;
  docs_fantasma: number;
};

export type WarRoomResult = {
  conclusions: Conclusions;
  debate: DebateTurn[];
  panel: Panelist[];
  verification: WarRoomVerification;
  generated_at: string;
};
