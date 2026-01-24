import { Card } from "./Components/Card/Card";
import "./Components/Header/Header.css";
import "./Components/Card/Card.css";
import { MainLayout } from "./Layouts/Main.layout";
import { SearchBar } from "./Components/SearchBar/SearchBar";
export const InfoTrip = () => {
  return (
    <MainLayout>
      <div className="superior-row">
        <Card>
          <h3>Inicio</h3>
          <p>Bienvenido</p>
        </Card>
        <SearchBar />
      </div>
    </MainLayout>
  );
};
