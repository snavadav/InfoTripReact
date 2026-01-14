import { Card } from "./Components/Card";
import { Header } from "./Components/Header";
import "./Components/Header.css";
import "./Components/Card.css";

export const InfoTrip = () => {
  return (
    <div>
      <Header />
      <Card>
        <h3>Inicio</h3>
        <p>Bienvenido</p>
      </Card>
    </div>
  );
};
