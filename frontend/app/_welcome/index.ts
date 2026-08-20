// Infraestructura visual compartida de la bienvenida cinematográfica de MIA (F3).
// Punto único de importación para las pantallas de la Oleada 2.
export { default as BrandMark } from "./BrandMark";
export type { BrandMarkProps } from "./BrandMark";
export { default as WelcomeShell } from "./WelcomeShell";
export type { WelcomeShellProps } from "./WelcomeShell";
export { default as ThemeChoice } from "./ThemeChoice";
export type { ThemeChoiceProps } from "./ThemeChoice";
export { default as WelcomeProgress, JOURNEY_STEPS } from "./WelcomeProgress";
export type { WelcomeProgressProps } from "./WelcomeProgress";
export { default as Celebration } from "./Celebration";
export type { CelebrationProps } from "./Celebration";
export { default as WelcomeField } from "./WelcomeField";
export type { WelcomeFieldProps } from "./WelcomeField";
export { default as MiaLine } from "./MiaLine";
export type { MiaLineProps } from "./MiaLine";
export { StepTransition, Stagger, StaggerItem } from "./MotionField";
export type { StepTransitionProps, StaggerProps } from "./MotionField";
export {
  MIA_EASE,
  STEP_DURATION,
  POP_SPRING,
  stepVariants,
  stepVariantsReduced,
  staggerContainer,
  staggerItem,
  staggerItemReduced,
  useReducedMotion,
} from "./motion";
