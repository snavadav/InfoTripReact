import React from "react";
import { Header } from "../Components/Header/Header";
// Importar footer

// Interface de las props
interface MainLayoutProps {
  children: React.ReactNode;
}

// 2. Aplicamos la interfaz al componente
export const MainLayout = ({ children }: MainLayoutProps) => {
  return (
    <div className="layout-wrapper">
      {/* El Header es una pieza fija */}
      <Header />

      {/* Aquí se inyectan tus páginas (Login, Home, etc.) */}
      <main style={{ minHeight: "80vh", padding: "20px" }}>{children}</main>

      {/* <Footer /> */}
    </div>
  );
};
