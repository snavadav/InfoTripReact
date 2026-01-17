import { Link } from "react-router-dom";
import { PATHS } from "../../routes/paths";
import "./Register.css";

export const Register = () => {
  return (
    // 1. WRAPPER PREMIUM (Fondo degradado)
    <div className="register-wrapper">
      <div className="container-register">
        <h3 className="register-title">Crea tu cuenta</h3>
        <p className="register-description">Únete a InfoTrip hoy mismo</p>

        <form action="">
          {/* FILA 1: Nombre y Apellido */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="name">Nombre</label>
              <input
                type="text"
                id="name"
                name="name"
                placeholder="Nombre"
                autoComplete="given-name"
              />
            </div>

            <div className="form-group">
              <label htmlFor="last-name">Apellido</label>
              <input
                type="text"
                id="last-name"
                name="last-name"
                placeholder="Apellido"
                autoComplete="family-name"
              />
            </div>
          </div>

          {/* Email */}
          <div className="form-group">
            <label htmlFor="email">Correo Electrónico</label>
            <input
              type="email"
              id="email"
              name="email"
              placeholder="ejemplo@correo.com"
              autoComplete="email"
            />
          </div>

          {/* Fecha */}
          <div className="form-group">
            <label htmlFor="birthday">Fecha de nacimiento</label>
            <input
              type="date"
              id="birthday"
              name="birthday"
              max={new Date().toISOString().split("T")[0]}
            />
          </div>

          {/* FILA 2: Contraseñas */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="password-register">Contraseña</label>
              <input
                type="password"
                id="password-register"
                name="password"
                placeholder="Crear"
                autoComplete="new-password"
              />
            </div>

            <div className="form-group">
              <label htmlFor="confirm-password">Confirmar</label>
              <input
                type="password"
                id="confirm-password"
                name="confirm-password"
                placeholder="Repetir"
                autoComplete="new-password"
              />
            </div>
          </div>

          <div className="submit-register">
            <button type="submit" className="btn-register">
              Crear cuenta
            </button>
          </div>

          <div className="login-link">
            ¿Ya tienes cuenta? <Link to={PATHS.LOGIN}>Inicia sesión</Link>
          </div>
        </form>
      </div>
    </div>
  );
};
