"use client";
import React, { useEffect } from "react";
import { useState, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LogoMark } from "../layout";

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.push("/dashboard");
    }
  }, [user, loading, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError((err as Error).message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/70 shadow-xl p-8">
      <div className="flex justify-center mb-4">
        <LogoMark className="h-10 w-10" />
      </div>
      <h1 className="text-2xl font-bold mb-1">Welcome back</h1>
      <p className="text-sm text-slate-400 mb-6">Sign in to your MeetingMind workspace.</p>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Email">
          <input
            className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 placeholder-slate-500"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
          />
        </Field>
        <Field label="Password">
          <input
            className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 placeholder-slate-500"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
        </Field>

        {error && <p className="text-sm text-rose-300">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-sm text-slate-400">
        New to MeetingMind?{" "}
        <Link className="text-indigo-400 hover:text-indigo-300" href="/signup">
          Create an account
        </Link>
      </p>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      {children}
    </label>
  );
}
