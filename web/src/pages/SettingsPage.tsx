import { signOut } from "firebase/auth";
import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNote, Loading, Stepper, messageOf } from "../components/ui";
import { auth } from "../firebase";
import { DAYS, MEALS } from "../lib/weeks";
import { enablePush, pushState, type PushState } from "../push";
import { useMe } from "../session";
import { PROTEINS, type Rule, type Settings } from "../types";

export function SettingsPage() {
  const me = useMe();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newRule, setNewRule] = useState<Rule>({ kind: "min", count: 2, tag: "chicken" });
  const [staple, setStaple] = useState("");
  const [push, setPush] = useState<PushState | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((e) => setError(messageOf(e)));
    void pushState().then(setPush);
  }, []);

  if (!settings) return <div className="page"><h1>Settings</h1><ErrorNote message={error} /><Loading /></div>;

  const slots = settings.slots ?? {};
  const rules = settings.rules ?? [];
  const staples = settings.staples ?? [];
  const cooked = Object.values(slots).filter((slot) => slot.cook).length;

  function change(changes: Partial<Settings>) {
    setSettings({ ...settings!, ...changes });
    setDirty(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      setSettings(await api.saveSettings(settings!));
      setDirty(false);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setSaving(false);
    }
  }

  async function copy(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  const apiBase = `${window.location.origin}/api/shortcuts`;

  return (
    <div className="page">
      <header className="page-head">
        <h1>Settings</h1>
        {dirty && (
          <button className="primary small" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        )}
      </header>
      <ErrorNote message={error} />

      <section className="panel">
        <h2>Meals you cook</h2>
        <p className="muted">
          Switch on the meals you cook and set how many portions to make. A dinner that also covers tomorrow's lunch is
          one cooked meal with more portions; leave that lunch switched off. {cooked} meals a week.
        </p>
        <div className="slots">
          {DAYS.map((day) => (
            <div className="slot-day" key={day.key}>
              <h3>{day.name}</h3>
              {MEALS.map((meal) => {
                const key = `${day.key}_${meal.key}`;
                const slot = slots[key] ?? { cook: false, portions: 2 };
                const set = (changes: Partial<typeof slot>) => change({ slots: { ...slots, [key]: { ...slot, ...changes } } });
                return (
                  <div className="slot-row" key={key}>
                    <label>
                      <input type="checkbox" id={`slot-${key}`} checked={!!slot.cook} onChange={(e) => set({ cook: e.target.checked })} />
                      {meal.name}
                    </label>
                    {slot.cook ? (
                      <Stepper label={`${day.name} ${meal.name} portions`} value={slot.portions ?? 2} onChange={(portions) => set({ portions })} />
                    ) : (
                      <span className="muted">not cooked</span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Rules for the weekly plan</h2>
        <p className="muted">Every generated plan follows these. Swaps that would break one are marked.</p>
        {rules.length === 0 && <p className="muted">No rules yet.</p>}
        <ul className="plain">
          {rules.map((rule, index) => (
            <li key={index} className="row between">
              <span>
                {rule.kind === "max" ? "At most" : "At least"} {rule.count} {rule.tag} meals a week
              </span>
              <button className="icon-button" aria-label="Remove rule" onClick={() => change({ rules: rules.filter((_, i) => i !== index) })}>
                ✕
              </button>
            </li>
          ))}
        </ul>
        <div className="rule-form">
          <select id="rule-kind" aria-label="At least or at most" value={newRule.kind ?? "min"} onChange={(e) => setNewRule({ ...newRule, kind: e.target.value as Rule["kind"] })}>
            <option value="min">At least</option>
            <option value="max">At most</option>
          </select>
          <Stepper label="How many" min={0} max={14} value={newRule.count} onChange={(count) => setNewRule({ ...newRule, count })} />
          <input id="rule-tag" list="rule-tags" aria-label="Protein or tag" value={newRule.tag} onChange={(e) => setNewRule({ ...newRule, tag: e.target.value })} />
          <datalist id="rule-tags">
            {[...PROTEINS.filter((p) => p !== "other"), "quick", "pasta", "soup"].map((tag) => <option key={tag} value={tag} />)}
          </datalist>
          <button className="secondary small" disabled={!newRule.tag.trim()} onClick={() => { const tag = newRule.tag.trim().toLowerCase(); change({ rules: [...rules.filter((r) => !(r.kind === newRule.kind && r.tag === tag)), { ...newRule, tag }] }); }}>
            Add rule
          </button>
        </div>
        <div className="grid-2">
          <div>
            <label htmlFor="repeat-weeks">Avoid repeats from the last</label>
            <select id="repeat-weeks" value={settings.repeat_window_weeks ?? 2} onChange={(e) => change({ repeat_window_weeks: Number(e.target.value) })}>
              {[0, 1, 2, 3, 4].map((weeks) => <option key={weeks} value={weeks}>{weeks === 0 ? "no weeks (repeats allowed)" : `${weeks} week${weeks > 1 ? "s" : ""}`}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="repeat-ratio">Repeats allowed</label>
            <select id="repeat-ratio" value={settings.max_repeat_ratio ?? 0.2} onChange={(e) => change({ max_repeat_ratio: Number(e.target.value) })}>
              {[0, 0.1, 0.2, 0.3, 0.5].map((ratio) => <option key={ratio} value={ratio}>{ratio * 100}% of meals</option>)}
            </select>
          </div>
        </div>
      </section>

      <section className="panel">
        <h2>Always in the house</h2>
        <p className="muted">Ingredients you never need on the generated list, such as salt or olive oil.</p>
        <div className="chips">
          {staples.map((name) => (
            <button key={name} className="chip active" onClick={() => change({ staples: staples.filter((s) => s !== name) })} aria-label={`Remove ${name}`}>
              {name} ✕
            </button>
          ))}
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (staple.trim()) { change({ staples: [...staples, staple.trim().toLowerCase()] }); setStaple(""); } }}>
          <input id="staple-add" value={staple} onChange={(e) => setStaple(e.target.value)} placeholder="olive oil" aria-label="Add a staple" />
          <button className="secondary small" disabled={!staple.trim()}>Add</button>
        </form>
      </section>

      <section className="panel">
        <h2>Friday notification</h2>
        <p className="muted">Get “Your meal plan for next week is ready” on this phone every Friday.</p>
        {push === "on" && <p className="note note-ok">Notifications are on for this phone.</p>}
        {push === "off" && (
          <button className="secondary" onClick={() => enablePush().then(setPush).catch((e) => setError(messageOf(e)))}>
            Turn on notifications
          </button>
        )}
        {push === "needs-install" && <p className="note">On iPhone, first add this app to your home screen (Share, then Add to Home Screen) and open it from there.</p>}
        {push === "denied" && <p className="note note-warn">Notifications are blocked for this app in your phone's settings.</p>}
        {push === "unavailable" && <p className="note">Notifications are not set up on this device.</p>}
      </section>

      <section className="panel">
        <h2>Siri and the share sheet</h2>
        <p className="muted">
          Create two Apple Shortcuts that send to the addresses below, using your key. Step-by-step instructions are in
          docs/shortcuts.md in the project.
        </p>
        <dl className="keys">
          <dt>Add to groceries</dt>
          <dd><code>{apiBase}/grocery</code> <button className="link" onClick={() => copy("grocery", `${apiBase}/grocery`)}>{copied === "grocery" ? "Copied" : "Copy"}</button></dd>
          <dt>Save a recipe screenshot</dt>
          <dd><code>{apiBase}/recipe-image</code> <button className="link" onClick={() => copy("image", `${apiBase}/recipe-image`)}>{copied === "image" ? "Copied" : "Copy"}</button></dd>
          <dt>Your key (keep it private)</dt>
          <dd><code>{me.shortcut_token}</code> <button className="link" onClick={() => copy("key", me.shortcut_token)}>{copied === "key" ? "Copied" : "Copy"}</button></dd>
        </dl>
      </section>

      <section className="panel">
        <h2>Account</h2>
        <p className="muted">Signed in as {auth.currentUser?.email}</p>
        <button className="secondary" onClick={() => signOut(auth)}>Sign out</button>
      </section>
    </div>
  );
}
