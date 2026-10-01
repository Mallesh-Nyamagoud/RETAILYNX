import { LogIn } from "lucide-react";

export default function Login() {
  const handleGoogleLogin = () => {
    window.location.href = "/api/auth/login";
  };

  return (
    <div className="min-h-screen bg-base flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-lg p-8 text-center space-y-8">
        <div className="space-y-3">
          <div className="w-20 h-20 mx-auto flex items-center justify-center">
            <img
              src="/logo.png"
              alt="RETAILYNX"
              className="max-w-full max-h-full object-contain drop-shadow-md"
              onError={(e) => (e.currentTarget.style.display = 'none')}
            />
          </div>
          <h1 className="text-3xl font-display font-bold text-text-primary tracking-wide">
            RETAILYNX
          </h1>
          <p className="text-text-secondary font-medium">
            Retail Intelligence & Analysis Platform
          </p>
        </div>

        <div className="pt-4">
          <button
            onClick={handleGoogleLogin}
            className="w-full flex items-center justify-center gap-3 bg-accent hover:bg-accent-hover text-white py-3 px-4 rounded-lg font-semibold transition-colors shadow-sm"
          >
            <LogIn size={18} />
            Sign in with Google
          </button>
        </div>
      </div>
    </div>
  );
}
