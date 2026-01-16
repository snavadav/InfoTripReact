import "./Login.css";

export const Login = () => {
  return (
    <div className="container-login">
      <h3 className="login-title">Inicia Sesión</h3>

      <form action="">
        <div className="form-group">
          <label htmlFor="usuario">Usuario</label>
          <input
            type="text"
            id="usuario"
            name="usuario"
            placeholder="Ingresa tu usuario"
          />
        </div>

        <div className="form-group">
          <label htmlFor="password">Contraseña</label>
          <input
            type="password"
            id="password"
            name="password"
            placeholder="Ingresa tu contraseña"
          />

          <a href="/recover" className="forgot-password">
            ¿Olvidaste tu contraseña?
          </a>
        </div>

        <button type="submit" className="btn-login">
          Ingresar
        </button>

        <div className="register-link">
          <p>
            ¿No tienes cuenta? <a href="/register">Regístrate aquí</a>
          </p>
        </div>
      </form>
    </div>
  );
};

export default Login;
