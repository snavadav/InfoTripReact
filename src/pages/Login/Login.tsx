import { useState } from "react";
import { Link, useNavigate } from "react-router-dom"; // 1. Importamos useNavigate
import { PATHS } from "../../routes/paths";
import { AuthService } from "../../services/auth.services"; // 2. Importamos tu servicio
import "./Login.css";

interface Credentials {
  usuario: string;
  password: string;
}

export const Login = () => {
  const [credentials, setCredentials] = useState<Credentials>({
    usuario: "",
    password: "",
  });

  // --- NUEVOS ESTADOS ---
  const [error, setError] = useState<string | null>(null); // Para guardar el mensaje de error
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate(); // El hook para movernos de página
  // ----------------------

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCredentials({
      ...credentials,
      [name]: value,
    });
    // Si el usuario escribe algo nuevo, borramos el error viejo para que se vea limpio
    if (error) setError(null);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    // Validamos que no estén vacíos antes de enviar
    if (!credentials.usuario || !credentials.password) {
      setError("Por favor completa todos los campos");
      return;
    }

    console.log("Intentando iniciar sesión...");
    setIsLoading(true); // Bloqueamos el botón
    setError(null); // Limpiamos errores previos

    try {
      // AQUÍ LLAMAMOS EL SERVICIO FALSO
      const response = await AuthService.login(
        credentials.usuario,
        credentials.password,
      );

      if (response.success) {
        console.log("¡Login exitoso!", response.user);

        localStorage.setItem("userToken", "123456");

        navigate(PATHS.INFOTRIP);
      }
    } catch (err: any) {
      console.error(err.message);
      setError("Usuario o contraseña incorrectos");
    } finally {
      // Pase lo que pase, quitamos el loading
      setIsLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="container-login">
        <h3 className="login-title">Inicia Sesión</h3>
        <p className="login-description">Bienvenido de nuevo a InfoTrip</p>

        {error && <div className="error-message">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="usuario">Usuario</label>
            <input
              type="text"
              id="usuario"
              name="usuario"
              placeholder="admin@infotrip.com" // Puse este placeholder para que recuerdes el user válido
              autoComplete="username"
              value={credentials.usuario}
              onChange={handleChange}
              disabled={isLoading}
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
              disabled={isLoading}
            />

            <div className="forgot-container">
              <Link to={PATHS.RECOVER} className="forgot-password">
                ¿Olvidaste tu contraseña?
              </Link>
            </div>
          </div>

          <button
            type="submit"
            className="btn-login"
            disabled={isLoading} // Bloquear botón para evitar doble clic
            style={{ opacity: isLoading ? 0.7 : 1 }} // Efecto visual simple
          >
            {isLoading ? "Cargando..." : "Ingresar"}
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
