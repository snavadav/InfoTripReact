// Simulamos que esto tarda un poco, como una base de datos real
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const AuthService = {
  // Función para Login (Simulada)
  login: async (email: string, password: string) => {
    console.log("Conectando con base de datos falsa...");
    await delay(1000); // Esperamos 1 segundo para dar realismo

    // Simulamos una validación
    if (email === "admin@infotrip.com" && password === "123456") {
      return {
        success: true,
        user: { name: "Sergio", email: email, token: "token-falso-123" },
      };
    } else {
      throw new Error("Credenciales incorrectas");
    }
  },

  // Función para Registro (Simulada)
  register: async (userData: any) => {
    console.log("Registrando usuario...", userData);
    await delay(1000);

    return { success: true, message: "Usuario creado con éxito" };
  },
};
