import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { http } from "../api/client";
import { useAuthStore } from "../store/useAuthStore";

export default function Login() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const googleLogin = useAuthStore((s) => s.googleLogin);
  const googleButton = useRef(null);
  const [googleConfig, setGoogleConfig] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [pendingGoogleCredential, setPendingGoogleCredential] = useState("");
  const [pendingGoogleEmail, setPendingGoogleEmail] = useState("");
  const [professionalDetails, setProfessionalDetails] = useState({ full_name: "", organization: "", job_title: "", phone: "", access_reason: "" });

  useEffect(() => {
    let active = true;
    http.get("/auth/google/config").then(({ data }) => {
      if (active && data.client_id) setGoogleConfig(data);
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!googleConfig?.client_id || !googleButton.current) return undefined;
    let active = true;
    const renderButton = () => {
      if (!active || !window.google?.accounts?.id || !googleButton.current) return;
      window.google.accounts.id.initialize({
        client_id: googleConfig.client_id,
        callback: async ({ credential }) => {
          if (!credential) return;
          setError("");
          setSubmitting(true);
          try {
            const encodedPayload = credential.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
            const tokenPayload = JSON.parse(atob(encodedPayload.padEnd(Math.ceil(encodedPayload.length / 4) * 4, "=")));
            const email = String(tokenPayload.email || "").toLowerCase();
            if (email.split("@").pop() !== googleConfig.domain) {
              setPendingGoogleCredential(credential);
              setPendingGoogleEmail(email);
            } else {
              await googleLogin(credential);
              navigate("/", { replace: true });
            }
          } catch (err) {
            setError(err?.message || `Sign in with your ${googleConfig.domain} account failed.`);
          } finally {
            setSubmitting(false);
          }
        },
      });
      window.google.accounts.id.renderButton(googleButton.current, {
        type: "standard", theme: "outline", size: "large", text: "signin_with",
        shape: "rectangular", width: 360,
      });
    };
    if (window.google?.accounts?.id) renderButton();
    else {
      let script = document.querySelector('script[src="https://accounts.google.com/gsi/client"]');
      if (!script) {
        script = document.createElement("script");
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
      }
      script.addEventListener("load", renderButton, { once: true });
    }
    return () => { active = false; };
  }, [googleConfig, googleLogin, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err?.message || "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleProfessionalSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await googleLogin(pendingGoogleCredential, professionalDetails);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err?.message || "Google sign in failed. Please try again.");
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

        {googleConfig && <>
          <div className="space-y-2 text-center">
            <p className="text-xs text-text-muted">Sign in with Google. Non-company accounts must provide professional details.</p>
            <div className="flex justify-center min-h-10" ref={googleButton} />
          </div>
          <div className="flex items-center gap-3 text-[11px] text-text-muted"><span className="h-px flex-1 bg-border" /><span>OR USE YOUR APP ACCOUNT</span><span className="h-px flex-1 bg-border" /></div>
        </>}

        {pendingGoogleCredential && <form onSubmit={handleProfessionalSubmit} className="space-y-4 rounded-lg border border-border bg-base/40 p-4">
          <div><h2 className="text-sm font-semibold text-text-primary">Professional access details</h2><p className="mt-1 text-xs text-text-muted">Google account: {pendingGoogleEmail}</p></div>
          {[
            ["full_name", "Full name", "Your full name"],
            ["organization", "Company / organization", "Your organization"],
            ["job_title", "Job title", "Your role or designation"],
            ["phone", "Contact number", "Your phone number"],
          ].map(([key, label, placeholder]) => <div key={key} className="space-y-1.5">
            <label className="text-xs font-medium text-text-muted">{label}</label>
            <input required value={professionalDetails[key]} onChange={(e) => setProfessionalDetails((current) => ({ ...current, [key]: e.target.value }))} placeholder={placeholder} className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" />
          </div>)}
          <div className="space-y-1.5"><label className="text-xs font-medium text-text-muted">Reason for access</label><textarea required maxLength={500} value={professionalDetails.access_reason} onChange={(e) => setProfessionalDetails((current) => ({ ...current, access_reason: e.target.value }))} placeholder="Briefly describe why you need access" className="w-full min-h-20 bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" /></div>
          <button type="submit" disabled={submitting} className="w-full bg-accent hover:bg-accent-hover text-white py-3 px-4 rounded-lg font-semibold disabled:opacity-60">{submitting ? "Signing in..." : "Continue with Google"}</button>
        </form>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Username</label>
            <input type="text" required autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} placeholder="your username" className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Password</label>
            <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent" />
          </div>
          {error && <p className="text-xs text-negative">{error}</p>}
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-3 bg-accent hover:bg-accent-hover text-white py-3 px-4 rounded-lg font-semibold transition-colors shadow-sm disabled:opacity-60">
            <LogIn size={18} />{submitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
