import { useState, type ChangeEvent, type FormEvent } from "react";

interface LoginData {
  username: string;
  password: string;
}

export const Login = () => {
  const [datos, setDatos] = useState<LoginData>({
    username: "",
    password: "",
  });

  // Funcion para cada vez que escribes
  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setDatos({
      ...datos,
      [name]: value,
    });
  };

  //Funcion para enviar los datos
  const enviarDatos = (e: FormEvent) => {
    e.preventDefault();
    console.log("Enviando Datos", datos);
  };

  return (
    <div className="container-Login">
      <h3 className="title-login">Inicia Sesion</h3>
      <form onSubmit={enviarDatos}>
        <div className="form-group">
          <label htmlFor="username">Usuario</label>
          <input
            type="text"
            id="username"
            name="username"
            placeholder="Nombre de usuario"
            value={datos.username}
            onChange={handleInputChange}
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Contraseña</label>
          <input
            type="password"
            id="password"
            name="password"
            placeholder="Contraseña"
            value={datos.password}
            onChange={handleInputChange}
          />
        </div>
        <button type="submit" className="button-send">
          Enviar
        </button>
      </form>
    </div>
  );
};
