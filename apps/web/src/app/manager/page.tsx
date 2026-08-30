"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiRequest } from "@/lib/api";

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
};

export default function ManagerLoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");

  useEffect(() => {
    if (localStorage.getItem("bfa_manager_token")) {
      router.replace("/manager/dashboard");
    }
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const token = await apiRequest<TokenResponse>("/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      localStorage.setItem("bfa_manager_token", token.access_token);
      router.push("/manager/dashboard");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed");
    }
  }

  return (
    <section className="card">
      <h1>Manager sign in</h1>
      <p className="lede">
        Use the manager account created by the backend seed script.
      </p>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          minLength={8}
          required
        />
        <button>Sign in</button>
      </form>
      {error && <div className="notice error">{error}</div>}
    </section>
  );
}
