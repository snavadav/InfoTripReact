import { Link } from "react-router-dom";
import { PATHS } from "../../routes/paths";
import "./Login.css";

export const Login = () => {
  return (
    <div className="login-wrapper">
      <div className="container-login">
        <h3 className="login-title">Inicia Sesión</h3>
        <p className="login-description">Bienvenido de nuevo a InfoTrip</p>

        <form action="">
          <div className="form-group">
            <label htmlFor="usuario">Usuario</label>
            <input
              type="text"
              id="usuario"
              name="usuario"
              placeholder="Ingresa tu usuario"
              autoComplete="username"
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Contraseña</label>
            <input
              type="password"
              id="password"
              name="password"
              placeholder="••••••••"
              autoComplete="current-password"
            />

            {/* Link corregido para React Router */}
            <div className="forgot-container">
              <Link to={PATHS.RECOVER} className="forgot-password">
                ¿Olvidaste tu contraseña?
              </Link>
            </div>
          </div>

          <button type="submit" className="btn-login">
            Ingresar
          </button>

          <div className="register-link">
            <p>
              ¿No tienes cuenta?{" "}
              <Link to={PATHS.REGISTER}>Regístrate aquí</Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;
