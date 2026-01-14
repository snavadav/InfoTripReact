import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { InfoTrip } from "./InfoTrip.tsx";
import "./InfoTrip.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InfoTrip />
  </StrictMode>
);
