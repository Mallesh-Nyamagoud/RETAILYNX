import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { useAuthStore } from "../store/useAuthStore";

export default function Login() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err?.message || "Username or password is incorrect.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-lg p-8 space-y-7">
        <div className="space-y-3 text-center">
          <div className="w-20 h-20 mx-auto flex items-center justify-center">
            <img src="/logo.png" alt="RETAILYNX" className="max-w-full max-h-full object-contain drop-shadow-md" onError={(e) => (e.currentTarget.style.display = "none")} />
          </div>
          <h1 className="text-3xl font-display font-bold text-text-primary tracking-wide">RETAILYNX</h1>
          <p className="text-text-secondary font-medium">Retail Intelligence &amp; Analysis Platform</p>
        </div>
        {error && <p role="alert" className="text-center text-xs text-negative">{error}</p>}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="username" className="text-xs font-medium text-text-muted">Username</label>
            <input id="username" type="text" required autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your username" className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-xs font-medium text-text-muted">Password</label>
            <input id="password" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Your password" className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" />
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-3 bg-accent hover:bg-accent-hover text-white py-3 px-4 rounded-lg font-semibold transition-colors shadow-sm disabled:opacity-60">
            <LogIn size={18} />{submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
