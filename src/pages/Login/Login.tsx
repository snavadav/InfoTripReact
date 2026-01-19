import { Link } from "react-router-dom";
import { PATHS } from "../../routes/paths";
import "./Login.css";
import { useState, type ChangeEvent, type FormEvent } from "react";

export const Login = () => {
  //Login

  const [credentials, setCredentials] = useState({
    usuario: "",
    password: "",
  });

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCredentials({
      ...credentials,
      [name]: value,
    });
  };

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    console.log("Enviando", credentials);
  };

  return (
    <div className="login-wrapper">
      <div className="container-login">
        <h3 className="login-title">Inicia Sesión</h3>
        <p className="login-description">Bienvenido de nuevo a InfoTrip</p>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="usuario">Usuario</label>
            <input
              type="text"
              id="usuario"
              name="usuario"
              placeholder="Ingresa tu usuario"
              autoComplete="username"
              value={credentials.usuario}
              onChange={handleChange}
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
              value={credentials.password}
              onChange={handleChange}
            />

            {/* React Router */}
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
