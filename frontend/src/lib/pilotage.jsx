import { createContext, useContext } from "react";

// Point de jonction entre un moteur externe (démonstration Polaris) et les vrais
// composants de l'application. Hors démonstration : null — comportement inchangé.
const PilotageCtx = createContext(null);

export function PilotageProvider({ value, children }) {
  return <PilotageCtx.Provider value={value}>{children}</PilotageCtx.Provider>;
}

export const usePilotage = () => useContext(PilotageCtx);
