// Importar logo
import { useNavigate } from "react-router-dom";
import { PATHS } from "../../routes/paths";

export const Header = () => {
  const navigate = useNavigate();

  const isLogged = localStorage.getItem("userToken");

  const handleLogout = () => {
    localStorage.removeItem("userToken");

    window.location.reload();
  };

  return (
    <div className="container-header">
      <h1>InfoTrip</h1>
      <div className="container-navbar">
        <nav className="navbar-list">
          <a href="/">Inicio</a>
          <a href="/">Conocenos</a>
          {isLogged ? (
            <a href="" onClick={handleLogout} className="btn-logout">
              Cerrar Sesion
            </a>
          ) : (
            <a href="" onClick={() => navigate(PATHS.LOGIN)}>Iniciar Sesion</a>
          )}
        </nav>
      </div>
    </div>
  );
};
