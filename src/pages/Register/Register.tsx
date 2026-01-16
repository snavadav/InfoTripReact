import "./Register.css";

export const Register = () => {
  return (
    <div className="container-register">
      <h3>Registrate</h3>
      <form action="">
        <div className="form-group">
          <label htmlFor="name">Nombre</label>
          <input type="text" id="name" name="name" placeholder="Nombre" />
        </div>
        <div className="form-group">
          <label htmlFor="last-name">Apellido</label>
          <input
            type="text"
            id="last-name"
            name="last-name"
            placeholder="Apellido"
          />
        </div>
        <div className="form-group">
          <label htmlFor="email">Correo Electronico</label>
          <input
            type="email"
            id="email"
            name="email"
            placeholder="Correo"
            autoComplete="email"
          />
        </div>
        <div className="form-group">
          <label htmlFor="name">Fecha de nacimiento</label>
          <input
            type="date"
            id="birthday"
            name="birthday"
            placeholder="Fecha de nacimiento"
            max={new Date().toISOString().split("T")[0]} //Evita fechas futuras
          />
        </div>

        <div className="submit-register">
          <button type="submit" className="btn-register"></button>
        </div>
      </form>
    </div>
  );
};
