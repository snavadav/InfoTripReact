import { Link } from "react-router-dom";
import { PATHS } from "../../routes/paths"; // Asegúrate de tener la ruta
import "./Recover.css";

export const Recover = () => {
  return (
    // Usamos un wrapper para centrarlo igual que el Login/Register
    <div className="recover-wrapper">
      <div className="container-recover">
        <h3>Recuperar contraseña</h3>
        <p className="recover-description">
          Ingresa tu correo y te enviaremos las instrucciones.
        </p>

        <form action="">
          <div className="form-group">
            {/* 1. Corregido: htmlFor coincide con id */}
            <label htmlFor="email">Correo electrónico</label>
            <input
              type="email"
              id="email" /* Coincide con el label */
              name="email"
              placeholder="ejemplo@correo.com"
              autoComplete="email"
            />
          </div>

          {/* 2. El botón ahora está FUERA del form-group para separarlo */}
          <button type="submit" className="btn-recover">
            Enviar instrucciones
          </button>

          {/* 3. Enlace para cancelar/volver */}
          <div className="back-link">
            <Link to={PATHS.LOGIN}>Volver al inicio de sesión</Link>
          </div>
        </form>
      </div>
    </div>
  );
};
