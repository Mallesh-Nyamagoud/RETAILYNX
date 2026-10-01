import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";

export default function AppShell() {
  return (
    <div className="flex min-h-screen bg-base overflow-hidden">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-[1600px] w-full mx-auto space-y-6">
            <Header />
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
