"use client";
import React, { useEffect } from "react";
import { useState, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { LogoMark } from "../layout";
import { Field } from "../login/page";

export default function SignupPage() {
  const { user, loading, register } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await register(name, email, password);
      router.push("/login");
    } catch (err) {
      setError((err as Error).message || "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900/70 p-8">
      <div className="flex justify-center mb-4">
        <LogoMark className="h-10 w-10" />
      </div>
      <h1 className="text-2xl font-bold mb-1">Create your account</h1>
      <p className="text-sm text-slate-400 mb-6">Start turning recordings into intelligence.</p>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field label="Full name">
          <input
            className="w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 placeholder-slate-500"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jane Doe"
            required
          />
        </Field>
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
            placeholder="Minimum 8 characters"
            required
          />
        </Field>

        {error && <p className="text-sm text-rose-300">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {busy ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-sm text-slate-400">
        Already have an account?{" "}
        <Link className="text-indigo-400 hover:text-indigo-300" href="/login">
          Sign in
        </Link>
      </p>
    </div>
  );
}
