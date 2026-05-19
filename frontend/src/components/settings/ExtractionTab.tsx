// Phase B: filled in after Phase A onboarding ships.
// Real implementation appears below — this comment will be replaced.
import { ObjectToggleGrid } from "../extraction/ObjectToggleGrid";

interface Props {
  onSaved: () => void;
}

export function ExtractionTab({ onSaved }: Props) {
  return <ObjectToggleGrid onSaved={onSaved} />;
}
