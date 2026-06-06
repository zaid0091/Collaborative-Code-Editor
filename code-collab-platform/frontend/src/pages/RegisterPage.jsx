import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth.js";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register, login, isLoading, error, clearError } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event) => {
    event.preventDefault();
    clearError();
    try {
      await register({ email, display_name: displayName, password });
      await login(email, password);
      navigate("/dashboard");
    } catch {
      // Error stored in auth store.
    }
  };

  return (
    <main className="auth-page">
      <h1>Create account</h1>
      <form onSubmit={handleSubmit}>
        <label htmlFor="display_name">Display name</label>
        <input
          id="display_name"
          type="text"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          required
        />

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={8}
        />

        {error ? <p className="auth-error">{String(error)}</p> : null}

        <button type="submit" disabled={isLoading}>
          {isLoading ? "Creating account..." : "Register"}
        </button>
      </form>

      <p>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </main>
  );
}
