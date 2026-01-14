import logoImg from "../assets/logo.png";

export const Header = () => {
  return (
    <div className="container-header">
      <img
        className="logo-image"
        src={logoImg}
        alt="Logo de la pagina"
        height="60px"
      />
      <div className="container-navbar">
        <nav className="navbar-list">
          <a href="#">Inicio</a>
          <a href="#">Contacto</a>
          <a href="#">Conocenos</a>
        </nav>
      </div>
    </div>
  );
};
