import { createBrowserRouter } from "react-router-dom";
import { InfoTrip } from "./InfoTrip";
import { Login } from "./pages/Login/Login";
import { PATHS } from "./routes/paths";
import { MainLayout } from "./Layouts/Main.layout";
import { Register } from "./pages/Register/Register";
import { Recover } from "./pages/Recover/Recover";

export const router = createBrowserRouter([
  {
    path: PATHS.INFOTRIP,
    element: <InfoTrip />,
  },
  {
    path: PATHS.LOGIN,
    element: (
      <MainLayout>
        <Login />,
      </MainLayout>
    ),
  },
  {
    path: PATHS.REGISTER,
    element: <Register />,
  },
  {
    path: PATHS.RECOVER,
    element: <Recover />,
  },
]);
