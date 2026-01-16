import { Link } from "react-router-dom";
import { PATHS } from "../../routes/paths"; // Asegúrate que esta ruta sea correcta
import "./Register.css";

export const Register = () => {
  return (
    // 1. El Wrapper para centrar y permitir scroll
    <div className="register-wrapper">
      <div className="container-register">
        <h3>Regístrate</h3>

        <form action="">
          {/* 2. Fila para Nombre y Apellido juntos */}
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

          {/* 3. El Email (Ya está fuera del div anterior, corregido) */}
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

          {/* ... resto del formulario ... */}

          <div className="form-group">
            <label htmlFor="birthday">Fecha de nacimiento</label>
            <input
              type="date"
              id="birthday"
              name="birthday"
              max={new Date().toISOString().split("T")[0]}
            />
          </div>

          {/* NUEVO: Contraseñas en la misma fila para ahorrar espacio vertical */}
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="password-register">Contraseña</label>
              <input
                type="password"
                id="password-register"
                name="password"
                placeholder="Contraseña"
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

          {/* ... botón y link ... */}

          <div className="submit-register">
            <button type="submit" className="btn-register">
              Crear cuenta
            </button>
          </div>

          {/* 4. Enlace para volver al Login */}
          <div className="login-link">
            ¿Ya tienes cuenta? <Link to={PATHS.LOGIN}>Inicia sesión</Link>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Register; // Si lo exportas por defecto
