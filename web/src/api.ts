import type { Analysis, Health, Sample } from "./types";

async function failure(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return String(detail.message);
    return JSON.stringify(detail ?? body).slice(0, 240);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export async function health(): Promise<Health | null> {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) return null;
    return (await response.json()) as Health;
  } catch {
    return null;
  }
}

export async function samples(): Promise<Sample[]> {
  const response = await fetch("/api/samples");
  if (!response.ok) return [];
  const body = (await response.json()) as { items: Sample[] };
  return body.items;
}

export async function analyzeFile(file: File, endUser = "household"): Promise<Analysis> {
  const form = new FormData();
  form.append("file", file);
  form.append("end_user", endUser);
  const response = await fetch("/api/analyze", { method: "POST", body: form });
  if (!response.ok) throw new Error(await failure(response));
  return (await response.json()) as Analysis;
}

export async function analyzeSample(name: string, endUser = "household"): Promise<Analysis> {
  const image = await fetch(`/fixtures/${name}.png`);
  if (!image.ok) throw new Error("that sample could not be loaded");
  const blob = await image.blob();
  return analyzeFile(new File([blob], `${name}.png`, { type: "image/png" }), endUser);
}

export async function analyzeText(text: string, endUser = "household"): Promise<Analysis> {
  const form = new FormData();
  form.append("text", text);
  form.append("end_user", endUser);
  const response = await fetch("/api/analyze", { method: "POST", body: form });
  if (!response.ok) throw new Error(await failure(response));
  return (await response.json()) as Analysis;
}
