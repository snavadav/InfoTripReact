// Importar logo
import { useNavigate } from "react-router-dom";
import { PATHS } from "../../routes/paths";

export const Header = () => {
  const navigate = useNavigate();

  return (
    <div className="container-header">
      <h1>InfoTrip</h1>
      <div className="container-navbar">
        <nav className="navbar-list">
          <a href="/">Inicio</a>
          <a href="/">Conocenos</a>
          <a onClick={() => navigate(PATHS.LOGIN)} href="">
            Login
          </a>
        </nav>
      </div>
    </div>
  );
};
