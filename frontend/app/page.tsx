"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { tokenStore } from "@/lib/api";

/** Root: bounce to the dashboard if a token exists, else to login. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(tokenStore.access ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
