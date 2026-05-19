import { PropertyPickerPanel } from "../extraction/PropertyPickerPanel";

interface Props {
  onSaved: () => void;
}

export function PropertyTab({ onSaved }: Props) {
  return <PropertyPickerPanel onSaved={onSaved} />;
}
