"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function GroupChatsRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace("/dashboard/connectors"); }, [router]);
  return null;
}
