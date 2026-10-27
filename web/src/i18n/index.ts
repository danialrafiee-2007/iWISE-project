import { useSyncExternalStore } from "react";
import { ar } from "./ar";
import { en } from "./en";
import { es } from "./es";
import { fa } from "./fa";
import { fr } from "./fr";
import { ru } from "./ru";
import { zh } from "./zh";

// The interface language. English is the source: every other language must define every key (TypeScript checks it),
// so nothing is left untranslated by accident. The language is chosen by ?lang=, then the last choice on this
// browser, then the browser's own language, then English. Persian and Arabic turn the page right-to-left. The menu
// names Arabic and Persian in English, so the whole list reads left to right.

export type Plural = Partial<Record<Intl.LDMLPluralRule, string>> & { other: string };
type Source = typeof en;
export type Messages = { [K in keyof Source]: Source[K] extends string ? string : Plural };
export type MessageKey = keyof Source;
type Vars = Record<string, string | number>;

export const LANGUAGES = [
  { code: "en", name: "English", locale: "en", dir: "ltr", messages: en },
  { code: "ar", name: "Arabic", locale: "ar-u-nu-latn", dir: "rtl", messages: ar },
  { code: "zh", name: "中文", locale: "zh-CN", dir: "ltr", messages: zh },
  { code: "fr", name: "Français", locale: "fr-FR", dir: "ltr", messages: fr },
  { code: "ru", name: "Русский", locale: "ru-RU", dir: "ltr", messages: ru },
  { code: "es", name: "Español", locale: "es-ES", dir: "ltr", messages: es },
  { code: "fa", name: "Persian", locale: "fa-IR", dir: "rtl", messages: fa },
] as const satisfies readonly { code: string; name: string; locale: string; dir: "ltr" | "rtl"; messages: Messages }[];

export type Lang = (typeof LANGUAGES)[number]["code"];
const STORAGE = "tg-lang";

const find = (code: string | null | undefined) => LANGUAGES.find((l) => l.code === code?.toLowerCase().split("-")[0]);

function detect(): Lang {
  try {
    const fromUrl = find(new URLSearchParams(window.location.search).get("lang"));
    if (fromUrl) return fromUrl.code;
  } catch {
    /* no window */
  }
  try {
    const saved = find(localStorage.getItem(STORAGE));
    if (saved) return saved.code;
  } catch {
    /* storage unavailable */
  }
  for (const code of typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language]) {
    const match = find(code);
    if (match) return match.code;
  }
  return "en";
}

let current: Lang = detect();
const listeners = new Set<() => void>();

const info = (lang: Lang = current) => LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0];

function apply() {
  if (typeof document === "undefined") return;
  document.documentElement.lang = current;
  document.documentElement.dir = info().dir;
}
apply();

export function setLang(lang: Lang) {
  if (lang === current) return;
  current = lang;
  try {
    localStorage.setItem(STORAGE, lang);
  } catch {
    /* storage unavailable */
  }
  apply();
  listeners.forEach((listener) => listener());
}

export const getLang = () => current;
export const isRtl = () => info().dir === "rtl";

// In a right-to-left sentence each filled-in value is a Unicode isolate (FSI … PDI), so a Latin name such as
// "20261022-082833-ensemble" keeps its own order instead of being reordered by the Persian text around it.
const isolate = (value: string) => (isRtl() ? `⁨${value}⁩` : value);
const fill = (text: string, vars?: Vars) => (vars ? text.replace(/\{(\w+)\}/g, (all, name: string) => (name in vars ? isolate(String(vars[name])) : all)) : text);

function message(key: MessageKey): string | Plural {
  return (info().messages as Messages)[key] ?? (en as Messages)[key];
}

/** The message for `key` in the current language, with {name} placeholders filled from `vars`. */
export function t(key: MessageKey, vars?: Vars): string {
  const value = message(key);
  return fill(typeof value === "string" ? value : value.other, vars);
}

/** A message with plural forms, chosen for `n` by the language's own plural rules; {n} is the formatted number. */
export function tp(key: MessageKey, n: number, vars?: Vars): string {
  const value = message(key);
  const text = typeof value === "string" ? value : (value[new Intl.PluralRules(info().locale).select(n)] ?? value.other);
  return fill(text, { n: formatNumber(n, 0), ...vars });
}

/** A number in the current language's digits (Persian digits in Persian). */
export function formatNumber(x: number, digits = 0, minDigits = 1): string {
  return new Intl.NumberFormat(info().locale, { minimumFractionDigits: digits, maximumFractionDigits: digits, minimumIntegerDigits: minDigits, useGrouping: Math.abs(x) >= 10000 }).format(x);
}

export function formatPercent(x: number, digits = 0): string {
  return new Intl.NumberFormat(info().locale, { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(x);
}

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** Re-renders the component when the language changes. */
export function useI18n() {
  const lang = useSyncExternalStore(subscribe, getLang, getLang);
  return { lang, dir: info(lang).dir, t, tp };
}
