import { useEffect, useState } from "react";
import { Header, ROUTES, type Route } from "./components/Header";
import BenchPage from "./pages/BenchPage";
import HowPage from "./pages/HowPage";
import MissionPage from "./pages/MissionPage";
import ReportPage from "./pages/ReportPage";

function currentRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return (ROUTES.find((r) => r.id === hash)?.id ?? "mission") as Route;
}

export default function App() {
  const [route, setRoute] = useState<Route>(currentRoute);

  useEffect(() => {
    const onHash = () => {
      setRoute(currentRoute());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    const label = ROUTES.find((r) => r.id === route)?.label ?? "Mission";
    document.title = `Signal.eve — ${label}`;
  }, [route]);

  return (
    <>
      <div className="grain" aria-hidden="true" />
      <Header route={route} />
      <main className="app-main" key={route}>
        {route === "mission" && <MissionPage />}
        {route === "report" && <ReportPage />}
        {route === "bench" && <BenchPage />}
        {route === "how" && <HowPage />}
      </main>
    </>
  );
}
