import { Card } from "./Components/Card/Card";
import "./Components/Header/Header.css";
import "./Components/Card/Card.css";
import { MainLayout } from "./Layouts/Main.layout";

export const InfoTrip = () => {
  return (
    <MainLayout>
      <Card>
        <h3>Inicio</h3>
        <p>Bienvenido</p>
      </Card>
    </MainLayout>
  );
};
